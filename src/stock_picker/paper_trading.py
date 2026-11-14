"""Daily forward paper-trading ledger for short-hold candidate strategies.

Signals are recorded after a completed daily close and filled at the next
available session open. This is a research simulation, not order execution.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from stock_picker.portfolio_backtest import _prepare_history

STRATEGIES = {"momentum": 3, "pullback_reclaim": 3, "regime_adaptive": 5}
STARTING_CAPITAL = 1000.0
RISK_FRACTION = 0.01
MAX_PORTFOLIO_RISK = 0.02
MAX_POSITION_FRACTION = 0.25
MAX_POSITIONS = 4
STOP_ATR = 1.5
TARGET_R = 2.0
ROUND_TRIP_COST_BPS = 20.0


def load_symbols(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    currencies = data.get("currencies", {})
    return [
        symbol for symbol in data.get("symbols", [])
        if currencies.get(symbol) == "EUR"
    ]


def empty_state() -> dict:
    return {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "strategies": {
            name: {
                "holding_sessions": holding,
                "cash": STARTING_CAPITAL,
                "positions": {},
                "pending": [],
                "trades": [],
                "last_processed_date": None,
                "sessions_elapsed": 0,
                "equity": STARTING_CAPITAL,
                "last_prices": {},
            }
            for name, holding in STRATEGIES.items()
        },
    }


def _bar(frame: pd.DataFrame, day: pd.Timestamp) -> dict | None:
    if day not in frame.index:
        return None
    row = frame.loc[day]
    return {key: float(row[key]) for key in ("Open", "High", "Low", "Close")}


def _exit(portfolio: dict, symbol: str, day: pd.Timestamp, price: float, reason: str) -> None:
    pos = portfolio["positions"].pop(symbol)
    half_cost = ROUND_TRIP_COST_BPS / 20000.0
    gross_entry = pos["shares"] * pos["entry_price"]
    gross_exit = pos["shares"] * price
    fees = (gross_entry + gross_exit) * half_cost
    pnl = gross_exit - gross_entry - fees
    portfolio["cash"] += gross_exit * (1.0 - half_cost)
    portfolio["trades"].append({
        "symbol": symbol,
        "entry_date": pos["entry_date"],
        "exit_date": day.date().isoformat(),
        "entry_price": round(pos["entry_price"], 6),
        "exit_price": round(price, 6),
        "shares": pos["shares"],
        "pnl_eur": round(pnl, 4),
        "return_pct": round(pnl / (gross_entry * (1.0 + half_cost)) * 100.0, 4),
        "exit_reason": reason,
        "sessions_held": pos["sessions_held"],
    })


def _mark_equity(portfolio: dict, bars: dict[str, dict]) -> float:
    for symbol, values in bars.items():
        portfolio["last_prices"][symbol] = values["Close"]
    market_value = sum(
        pos["shares"] * portfolio["last_prices"].get(symbol, pos["entry_price"])
        for symbol, pos in portfolio["positions"].items()
    )
    portfolio["equity"] = round(portfolio["cash"] + market_value, 2)
    return portfolio["equity"]


def _process_day(portfolio: dict, strategy: str, holding: int,
                 day: pd.Timestamp, bars: dict[str, dict],
                 signal_rows: dict[str, pd.Series]) -> list[dict]:
    events = []
    # 1) Exit positions at the open if the market gaps through a stop/target.
    for symbol, pos in list(portfolio["positions"].items()):
        if symbol not in bars:
            continue
        op = bars[symbol]["Open"]
        if op <= pos["stop"]:
            _exit(portfolio, symbol, day, op, "stop_gap")
            events.append({"type": "EXIT", "symbol": symbol, "reason": "stop_gap", "price": op})
        elif op >= pos["target"]:
            _exit(portfolio, symbol, day, op, "target_gap")
            events.append({"type": "EXIT", "symbol": symbol, "reason": "target_gap", "price": op})

    # 2) Execute signals generated at the previous completed close.
    pending = portfolio["pending"]
    portfolio["pending"] = []
    for order in pending:
        symbol = order["symbol"]
        if symbol not in bars:
            portfolio["pending"].append(order)
            continue
        if symbol in portfolio["positions"] or len(portfolio["positions"]) >= MAX_POSITIONS:
            continue
        entry = bars[symbol]["Open"]
        stop = entry - STOP_ATR * order["atr"]
        if entry <= 0 or stop <= 0:
            continue
        risk_per_share = entry - stop
        marked = sum(
            p["shares"] * portfolio["last_prices"].get(s, p["entry_price"])
            for s, p in portfolio["positions"].items()
        )
        equity_open = portfolio["cash"] + marked
        risk_open = sum(p["shares"] * p["risk_per_share"] for p in portfolio["positions"].values())
        risk_budget = min(equity_open * RISK_FRACTION,
                          max(0.0, equity_open * MAX_PORTFOLIO_RISK - risk_open))
        shares = min(
            int(risk_budget // risk_per_share),
            int(equity_open * MAX_POSITION_FRACTION // entry),
            int(portfolio["cash"] // (entry * (1.0 + ROUND_TRIP_COST_BPS / 20000.0))),
        )
        if shares < 1:
            continue
        fee = shares * entry * ROUND_TRIP_COST_BPS / 20000.0
        portfolio["cash"] -= shares * entry + fee
        portfolio["positions"][symbol] = {
            "entry_date": day.date().isoformat(),
            "entry_price": entry,
            "shares": shares,
            "stop": stop,
            "target": entry + TARGET_R * risk_per_share,
            "risk_per_share": risk_per_share,
            "sessions_held": 1,
            "strategy": strategy,
            "signal_date": order["signal_date"],
        }
        events.append({"type": "ENTRY", "symbol": symbol, "price": entry, "shares": shares,
                       "signal_date": order["signal_date"]})

    # 3) Intraday exits are evaluated after open fills; stop wins ambiguous bars.
    for symbol, pos in list(portfolio["positions"].items()):
        if symbol not in bars:
            continue
        bar = bars[symbol]
        if pos["entry_date"] != day.date().isoformat():
            pos["sessions_held"] += 1
        price = reason = None
        if bar["Low"] <= pos["stop"] and bar["High"] >= pos["target"]:
            price, reason = pos["stop"], "stop_and_target_same_bar_stop_first"
        elif bar["Low"] <= pos["stop"]:
            price, reason = pos["stop"], "stop"
        elif bar["High"] >= pos["target"]:
            price, reason = pos["target"], "target"
        elif pos["sessions_held"] >= holding:
            price, reason = bar["Close"], "time_exit"
        if price is not None:
            _exit(portfolio, symbol, day, price, reason)
            events.append({"type": "EXIT", "symbol": symbol, "reason": reason, "price": price})

    # 4) Close marks and generate next-session orders from today's completed bar.
    _mark_equity(portfolio, bars)
    portfolio["sessions_elapsed"] = int(portfolio.get("sessions_elapsed", 0)) + 1
    if portfolio["sessions_elapsed"] >= 30:
        for symbol, pos in list(portfolio["positions"].items()):
            close_price = bars.get(symbol, {}).get("Close", portfolio["last_prices"].get(symbol, pos["entry_price"]))
            _exit(portfolio, symbol, day, close_price, "30_session_test_end")
            events.append({"type": "EXIT", "symbol": symbol, "reason": "30_session_test_end", "price": close_price})
        portfolio["pending"] = []
    existing = set(portfolio["positions"]) | {o["symbol"] for o in portfolio["pending"]}
    candidates = []
    for symbol, row in signal_rows.items():
        if symbol in existing or symbol not in bars:
            continue
        if bool(row.get("signal", False)) and pd.notna(row.get("atr14")):
            score = float(row.get("signal_score", 0.0))
            atr = float(row["atr14"])
            if pd.notna(score) and score == score and atr > 0:
                candidates.append((score, symbol, atr))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    for score, symbol, atr in candidates[:MAX_POSITIONS] if portfolio["sessions_elapsed"] < 30 else []:
        portfolio["pending"].append({
            "symbol": symbol, "atr": atr, "score": score,
            "signal_date": day.date().isoformat(),
        })
        events.append({"type": "SIGNAL_NEXT_OPEN", "symbol": symbol, "score": round(score, 6)})
    portfolio["last_processed_date"] = day.date().isoformat()
    return events


def run(state_path: Path, universe_path: Path, output_path: Path) -> dict:
    symbols = load_symbols(universe_path)
    if not symbols:
        raise ValueError("No EUR-denominated symbols found in configured universe")
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state = empty_state()

    histories = {}
    errors = {}
    for symbol in symbols:
        try:
            raw = yf.Ticker(symbol).history(period="1y", auto_adjust=True)
            if raw is None or raw.empty:
                errors[symbol] = "no data"
                continue
            histories[symbol] = raw
        except Exception as exc:
            errors[symbol] = str(exc)[:180]

    frames = {}
    for symbol, history in histories.items():
        for strategy in STRATEGIES:
            try:
                frames.setdefault(strategy, {})[symbol] = _prepare_history(history, symbol, strategy)
            except Exception as exc:
                errors[symbol] = str(exc)[:180]

    all_days = sorted(set().union(*(set(f.index) for group in frames.values() for f in group.values()))) if frames else []
    if not all_days:
        raise RuntimeError("No valid EUR daily price history downloaded")

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_provider": "Yahoo Finance via yfinance; auto-adjusted daily OHLC",
        "market_currency": "EUR only; USD and CHF symbols excluded to avoid FX assumptions",
        "starting_capital_per_strategy_eur": STARTING_CAPITAL,
        "round_trip_cost_bps": ROUND_TRIP_COST_BPS,
        "risk_per_trade_pct": RISK_FRACTION * 100,
        "max_open_portfolio_risk_pct": MAX_PORTFOLIO_RISK * 100,
        "holding_sessions": STRATEGIES,
        "data_errors": errors,
        "strategies": {},
        "events": {},
        "disclaimer": "Paper trading only. Signals after close, simulated fills at next available open. Not investment advice or live execution.",
    }

    for strategy, holding in STRATEGIES.items():
        portfolio = state["strategies"].setdefault(strategy, empty_state()["strategies"][strategy])
        group = frames.get(strategy, {})
        if not group:
            summary["strategies"][strategy] = {"status": "NO_DATA"}
            continue
        last_date = portfolio.get("last_processed_date")
        if "sessions_elapsed" not in portfolio:
            portfolio["sessions_elapsed"] = 1 if last_date else 0
        if int(portfolio.get("sessions_elapsed", 0)) >= 30:
            days = []
        elif last_date:
            days = [d for d in all_days if d.date().isoformat() > last_date]
        else:
            # First activation: start from the latest completed session only.
            days = [all_days[-1]]
        day_events = []
        for day in days:
            bars = {s: b for s, f in group.items() if (b := _bar(f, day)) is not None}
            rows = {s: f.loc[day] for s, f in group.items() if day in f.index}
            day_events.extend({"date": day.date().isoformat(), **event}
                              for event in _process_day(portfolio, strategy, holding, day, bars, rows))
        summary["events"][strategy] = day_events
        open_positions = []
        for symbol, pos in portfolio["positions"].items():
            open_positions.append({"symbol": symbol, **pos})
        summary["strategies"][strategy] = {
            "status": "COMPLETED" if int(portfolio.get("sessions_elapsed", 0)) >= 30 else "ACTIVE",
            "sessions_elapsed": int(portfolio.get("sessions_elapsed", 0)),
            "target_sessions": 30,
            "last_processed_date": portfolio["last_processed_date"],
            "equity_eur": round(portfolio["equity"], 2),
            "cash_eur": round(portfolio["cash"], 2),
            "return_pct": round((portfolio["equity"] / STARTING_CAPITAL - 1) * 100, 3),
            "open_positions": open_positions,
            "pending_next_open": portfolio["pending"],
            "closed_trades": len(portfolio["trades"]),
            "wins": sum(1 for t in portfolio["trades"] if t["pnl_eur"] > 0),
            "realized_pnl_eur": round(sum(t["pnl_eur"] for t in portfolio["trades"]), 2),
            "recent_trades": portfolio["trades"][-20:],
        }

    state["updated_at_utc"] = summary["generated_at_utc"]
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Advance the short-hold paper-trading ledger")
    parser.add_argument("--state", type=Path, default=Path("state/paper-trading.json"))
    parser.add_argument("--universe", type=Path, default=Path("config/universe.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/paper-trading-latest.json"))
    args = parser.parse_args()
    report = run(args.state, args.universe, args.output)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
