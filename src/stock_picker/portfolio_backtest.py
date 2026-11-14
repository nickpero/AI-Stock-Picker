"""Portfolio-aware long-only daily-bar backtest.

Signals are formed at a completed close and can enter no earlier than the
following session's open. When stop and target are both touched in one daily
bar, the stop is assumed first (conservative). All symbols must be quoted in
the same account currency; FX conversion is intentionally not guessed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from dataclasses import dataclass
from math import floor
from typing import Mapping

import yfinance as yf

import numpy as np
import pandas as pd


@dataclass
class Position:
    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: int
    stop: float
    target: float
    risk_per_share: float
    sessions_held: int = 0


def _benchmark_result(frames: Mapping[str, pd.DataFrame], calendar: list[pd.Timestamp], initial_capital: float) -> dict:
    """Equal-weight daily-rebalanced price benchmark using the same available symbols/dates.

    Prices are adjusted by yfinance in the CLI download path. The benchmark is
    frictionless and is intended as a reference, not an executable portfolio.
    """
    dates = pd.DatetimeIndex(calendar)
    returns = []
    for frame in frames.values():
        close = frame["Close"].reindex(dates).ffill()
        returns.append(close.pct_change(fill_method=None).fillna(0.0).rename("return"))
    daily = pd.concat(returns, axis=1).mean(axis=1).fillna(0.0)
    equity = initial_capital * (1.0 + daily).cumprod()
    if len(equity) == 0:
        return {"method": "equal-weight daily-rebalanced, frictionless", "final_equity": round(initial_capital, 2)}
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1 / 365.25)
    total_return = float(equity.iloc[-1] / initial_capital - 1.0)
    cagr = (float(equity.iloc[-1]) / initial_capital) ** (1.0 / years) - 1.0 if equity.iloc[-1] > 0 else -1.0
    daily_returns = equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    volatility = float(daily_returns.std(ddof=1) * np.sqrt(252)) if len(daily_returns) > 1 else 0.0
    sharpe = float(daily_returns.mean() / daily_returns.std(ddof=1) * np.sqrt(252)) if len(daily_returns) > 1 and daily_returns.std(ddof=1) > 0 else None
    max_drawdown = float((equity / equity.cummax() - 1.0).min())
    return {
        "method": "equal-weight daily-rebalanced, frictionless; same available symbols and dates",
        "final_equity": round(float(equity.iloc[-1]), 2),
        "total_return_pct": round(total_return * 100, 3),
        "cagr_pct": round(cagr * 100, 3),
        "max_drawdown_pct": round(max_drawdown * 100, 3),
        "annualized_volatility_pct": round(volatility * 100, 3),
        "sharpe_ratio": round(sharpe, 3) if sharpe is not None else None,
    }


def _prepare_history(history: pd.DataFrame, symbol: str = "UNKNOWN", strategy: str = "momentum") -> pd.DataFrame:
    required = {"Open", "High", "Low", "Close"}
    if history is None or not required.issubset(history.columns):
        raise ValueError(f"{symbol}: history must contain {sorted(required)}")
    frame = history[list(required)].copy().sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    if (frame[["Open", "High", "Low", "Close"]] <= 0).any().any():
        raise ValueError(f"{symbol}: OHLC prices must be positive")

    # Exclude malformed vendor bars rather than silently changing their prices.
    scale = frame[["Open", "High", "Low", "Close"]].abs().max(axis=1).clip(lower=1.0)
    tolerance = scale * 1e-5
    bad_high = frame["High"] + tolerance < frame[["Open", "Close", "Low"]].max(axis=1)
    bad_low = frame["Low"] - tolerance > frame[["Open", "Close", "High"]].min(axis=1)
    bad = bad_high | bad_low
    dropped = int(bad.sum())
    frame = frame.loc[~bad].copy()
    if len(frame) < 25:
        raise ValueError(
            f"{symbol}: fewer than 25 coherent daily bars after excluding {dropped} malformed OHLC rows"
        )
    frame.attrs["dropped_ohlc_rows"] = dropped

    previous_close = frame["Close"].shift(1)
    true_range = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - previous_close).abs(),
            (frame["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["atr14"] = true_range.rolling(14, min_periods=14).mean()
    frame["sma20"] = frame["Close"].rolling(20, min_periods=20).mean()
    frame["momentum20"] = frame["Close"].pct_change(20)
    frame["sma50"] = frame["Close"].rolling(50, min_periods=50).mean()
    prior_high20 = frame["High"].rolling(20, min_periods=20).max().shift(1)
    if strategy == "momentum":
        frame["signal"] = (frame["Close"] > frame["sma20"]) & (frame["momentum20"] > 0)
        frame["signal_score"] = frame["momentum20"]
    elif strategy == "breakout":
        frame["signal"] = (frame["Close"] > prior_high20) & (frame["Close"] > frame["sma20"])
        frame["signal_score"] = frame["Close"] / prior_high20 - 1.0
    elif strategy == "pullback_reclaim":
        crossed_above_sma20 = (frame["Close"].shift(1) <= frame["sma20"].shift(1)) & (frame["Close"] > frame["sma20"])
        frame["signal"] = crossed_above_sma20 & (frame["Close"] > frame["sma50"])
        frame["signal_score"] = frame["momentum20"]
    else:
        raise ValueError("strategy must be momentum, breakout or pullback_reclaim")
    return frame


def portfolio_backtest(
    histories: Mapping[str, pd.DataFrame],
    initial_capital: float = 1000.0,
    holding_sessions: int = 5,
    max_positions: int = 4,
    risk_fraction: float = 0.01,
    max_position_fraction: float = 0.25,
    max_portfolio_risk_fraction: float = 0.02,
    strategy: str = "momentum",
    stop_atr: float = 1.5,
    target_r: float = 2.0,
    round_trip_cost_bps: float = 20.0,
) -> dict:
    """Simulate cash, concurrent positions, integer shares, costs and daily exits.

    Each side incurs half of round-trip costs. No leverage, shorting, taxes,
    dividends, FX conversion or portfolio rebalancing are simulated.
    """
    if not histories:
        raise ValueError("At least one symbol history is required")
    if strategy not in {"momentum", "breakout", "pullback_reclaim"}:
        raise ValueError("strategy must be momentum, breakout or pullback_reclaim")
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if not 1 <= holding_sessions <= 15 or max_positions < 1:
        raise ValueError("holding_sessions must be 1..15 and max_positions >= 1")
    if not 0 < risk_fraction <= 0.05:
        raise ValueError("risk_fraction must be in (0, 5%]")
    if not 0 < max_position_fraction <= 1:
        raise ValueError("max_position_fraction must be in (0, 1]")
    if not 0 < max_portfolio_risk_fraction <= 0.10:
        raise ValueError("max_portfolio_risk_fraction must be in (0, 10%]")
    if stop_atr <= 0 or target_r <= 0 or not 0 <= round_trip_cost_bps <= 1000:
        raise ValueError("Invalid stop, target or transaction cost")

    frames = {str(s): _prepare_history(h, str(s), strategy) for s, h in histories.items()}
    data_quality = {s: {"bars_used": len(f), "malformed_ohlc_rows_excluded": int(f.attrs.get("dropped_ohlc_rows", 0))} for s, f in frames.items()}
    # Daily bars from different exchanges need not share every holiday.
    calendar = sorted(set().union(*(set(f.index) for f in frames.values())))
    half_cost = round_trip_cost_bps / 20000.0
    cash = float(initial_capital)
    positions: dict[str, Position] = {}
    trades: list[dict] = []
    equity_rows: list[dict] = []
    last_prices: dict[str, float] = {}

    def record_exit(symbol, pos, day, price, reason):
        nonlocal cash
        proceeds = pos.shares * price
        exit_fee = proceeds * half_cost
        entry_cost = pos.shares * pos.entry_price
        entry_fee = entry_cost * half_cost
        cash += proceeds - exit_fee
        pnl = proceeds - exit_fee - entry_cost - entry_fee
        trades.append({
            "symbol": symbol, "entry_date": pos.entry_date.date().isoformat(),
            "exit_date": pd.Timestamp(day).date().isoformat(),
            "entry_price": round(pos.entry_price, 6), "exit_price": round(price, 6),
            "shares": pos.shares, "pnl": round(pnl, 4),
            "return_pct": round(pnl / (entry_cost + entry_fee) * 100, 4),
            "exit_reason": reason, "sessions_held": pos.sessions_held,
        })

    for day in calendar:
        # Opening phase: only opening prices and prior completed closes are known.
        todays = {s: f.loc[day] for s, f in frames.items() if day in f.index}
        exited_today = set()
        for symbol, pos in list(positions.items()):
            if symbol not in todays:
                continue
            op = float(todays[symbol]["Open"])
            if op <= pos.stop:
                record_exit(symbol, pos, day, op, "stop_gap")
                del positions[symbol]
                exited_today.add(symbol)
            elif op >= pos.target:
                record_exit(symbol, pos, day, op, "target_gap")
                del positions[symbol]
                exited_today.add(symbol)

        candidates = []
        for symbol, frame in frames.items():
            if symbol in positions or symbol in exited_today or symbol not in todays:
                continue
            loc = frame.index.get_loc(day)
            if not isinstance(loc, (int, np.integer)) or loc == 0:
                continue
            sig = frame.iloc[loc - 1]
            if bool(sig["signal"]) and pd.notna(sig["atr14"]):
                score = float(sig["signal_score"])
                if np.isfinite(score):
                    candidates.append((score, symbol, todays[symbol], float(sig["atr14"])))
        candidates.sort(key=lambda x: (-x[0], x[1]))

        def open_mark(s):
            return float(todays[s]["Open"]) if s in todays else last_prices.get(s, 0.0)

        # Fill at today's open; intraday OHLC cannot free capacity before these fills.
        for _, symbol, bar, atr in candidates:
            if len(positions) >= max_positions:
                break
            entry = float(bar["Open"])
            stop = entry - stop_atr * atr
            if entry <= 0 or stop <= 0:
                continue
            rps = entry - stop
            mv = sum(p.shares * open_mark(s) for s, p in positions.items())
            eq_open = cash + mv
            risk_open = sum(p.shares * p.risk_per_share for p in positions.values())
            risk_capacity = max(0.0, eq_open * max_portfolio_risk_fraction - risk_open)
            budget = min(eq_open * risk_fraction, risk_capacity)
            shares = min(floor(budget / rps), floor(eq_open * max_position_fraction / entry),
                         floor(cash / (entry * (1 + half_cost))))
            if shares < 1:
                continue
            cost = shares * entry
            cash -= cost + cost * half_cost
            positions[symbol] = Position(
                symbol=symbol, entry_date=pd.Timestamp(day), entry_price=entry,
                shares=shares, stop=stop, target=entry + target_r * rps,
                risk_per_share=rps, sessions_held=1,
            )

        # Intraday phase: process all stops/targets only after opening orders.
        for symbol, pos in list(positions.items()):
            if symbol not in todays:
                continue
            bar = todays[symbol]
            hi, lo, cl = (float(bar[k]) for k in ("High", "Low", "Close"))
            if pos.entry_date != pd.Timestamp(day):
                pos.sessions_held += 1
            price = reason = None
            if lo <= pos.stop and hi >= pos.target:
                price, reason = pos.stop, "stop_and_target_same_bar_stop_first"
            elif lo <= pos.stop:
                price, reason = pos.stop, "stop"
            elif hi >= pos.target:
                price, reason = pos.target, "target"
            elif pos.sessions_held >= holding_sessions:
                price, reason = cl, "time_exit"
            if price is not None:
                record_exit(symbol, pos, day, price, reason)
                del positions[symbol]
                exited_today.add(symbol)

        # Only now do today's closing prices become available as portfolio marks.
        for symbol, bar in todays.items():
            last_prices[symbol] = float(bar["Close"])
        mv = sum(p.shares * last_prices[s] for s, p in positions.items() if s in last_prices)
        marked_equity = cash + mv
        open_risk = sum(p.shares * p.risk_per_share for p in positions.values())
        equity_rows.append({
            "date": pd.Timestamp(day), "equity": marked_equity, "cash": cash,
            "open_positions": len(positions),
            "open_stop_risk_pct": open_risk / marked_equity * 100 if marked_equity > 0 else 0.0,
        })

    # Liquidate remaining positions at their last available close, with costs.
    for symbol, pos in list(positions.items()):
        frame = frames[symbol]
        last_day = frame.index[-1]
        exit_price = float(frame.iloc[-1]["Close"])
        proceeds = pos.shares * exit_price
        exit_fee = proceeds * half_cost
        cash += proceeds - exit_fee
        entry_cost = pos.shares * pos.entry_price
        pnl = proceeds - exit_fee - entry_cost - entry_cost * half_cost
        trades.append({
            "symbol": symbol,
            "entry_date": pos.entry_date.date().isoformat(),
            "exit_date": pd.Timestamp(last_day).date().isoformat(),
            "entry_price": round(pos.entry_price, 6),
            "exit_price": round(exit_price, 6),
            "shares": pos.shares,
            "pnl": round(pnl, 4),
            "return_pct": round(pnl / (entry_cost * (1 + half_cost)) * 100, 4),
            "exit_reason": "end_of_data",
            "sessions_held": pos.sessions_held,
        })
        del positions[symbol]

    curve = pd.DataFrame(equity_rows).drop_duplicates("date").set_index("date")["equity"]
    if len(curve):
        final_equity = cash
        # Include end-of-data liquidation costs before calculating drawdown/returns.
        curve.iloc[-1] = final_equity
        total_return = final_equity / initial_capital - 1
        daily_returns = curve.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        running_max = curve.cummax()
        drawdown = curve / running_max - 1
        years = max((curve.index[-1] - curve.index[0]).days / 365.25, 1 / 365.25)
        cagr = (final_equity / initial_capital) ** (1 / years) - 1 if final_equity > 0 else -1.0
        volatility = float(daily_returns.std(ddof=1) * np.sqrt(252)) if len(daily_returns) > 1 else 0.0
        sharpe = float(daily_returns.mean() / daily_returns.std(ddof=1) * np.sqrt(252)) if len(daily_returns) > 1 and daily_returns.std(ddof=1) > 0 else None
        max_dd = float(drawdown.min())
    else:
        final_equity, total_return, cagr, volatility, sharpe, max_dd = initial_capital, 0.0, 0.0, 0.0, None, 0.0

    trade_frame = pd.DataFrame(trades)
    wins = trade_frame[trade_frame["pnl"] > 0]["pnl"] if trades else pd.Series(dtype=float)
    losses = trade_frame[trade_frame["pnl"] <= 0]["pnl"] if trades else pd.Series(dtype=float)
    result = {
        "strategy": strategy,
        "execution_model": "prior_close_signal_next_open_fill; gap_exits_before_open_entries; intraday_exits_after_entries; stop_first_same_bar",
        "initial_capital": round(initial_capital, 2),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return * 100, 3),
        "cagr_pct": round(cagr * 100, 3),
        "max_drawdown_pct": round(max_dd * 100, 3),
        "annualized_volatility_pct": round(volatility * 100, 3),
        "sharpe_ratio": round(sharpe, 3) if sharpe is not None else None,
        "trades": len(trades),
        "win_rate_pct": round(float((trade_frame["pnl"] > 0).mean() * 100), 2) if trades else 0.0,
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 3) if len(losses) and abs(losses.sum()) > 0 else None,
        "average_trade_pnl": round(float(trade_frame["pnl"].mean()), 4) if trades else 0.0,
        "max_positions": max((int(x) for x in pd.DataFrame(equity_rows)["open_positions"]), default=0) if equity_rows else 0,
        "round_trip_cost_bps": round_trip_cost_bps,
        "per_trade_risk_fraction_pct": round(risk_fraction * 100, 3),
        "max_portfolio_open_risk_fraction_pct": round(max_portfolio_risk_fraction * 100, 3),
        "max_observed_open_stop_risk_pct": round(float(pd.DataFrame(equity_rows)["open_stop_risk_pct"].max()), 3) if equity_rows else 0.0,
        "benchmark_equal_weight": _benchmark_result(frames, calendar, initial_capital),
        "data_quality_by_symbol": data_quality,
        "trades_detail": trades,
        "equity_curve": [
            {"date": pd.Timestamp(d).date().isoformat(), "equity": round(float(v), 4)}
            for d, v in curve.items()
        ],
        "limitations": [
            "All symbols must be expressed in the same account currency; FX conversion is not included.",
            "Daily OHLC bars cannot reconstruct intraday order; if stop and target both trade, stop is assumed first.",
            "No dividends, taxes, borrow costs, delisted securities, point-in-time constituents or market impact.",
            "The strategy is a transparent baseline, not a validated predictive edge.",
        ],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a cash- and risk-constrained portfolio simulation")
    parser.add_argument("--universe", type=Path, default=Path("config/universe.json"))
    parser.add_argument("--period", default="5y")
    parser.add_argument("--currency", choices=["EUR", "USD", "CHF"], required=True,
                        help="Run one currency at a time; FX conversion is not yet implemented")
    parser.add_argument("--capital", type=float, default=1000.0)
    parser.add_argument("--holding", type=int, default=5)
    parser.add_argument("--max-positions", type=int, default=4)
    parser.add_argument("--risk-fraction", type=float, default=0.01)
    parser.add_argument("--max-portfolio-risk-fraction", type=float, default=0.02)
    parser.add_argument("--strategy", choices=["momentum", "breakout", "pullback_reclaim"], default="momentum")
    parser.add_argument("--max-position-fraction", type=float, default=0.25)
    parser.add_argument("--cost-bps", type=float, default=20.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    universe = json.loads(args.universe.read_text(encoding="utf-8"))
    symbols = universe.get("symbols", [])
    currencies = universe.get("currencies", {})
    if not symbols or not all(isinstance(s, str) for s in symbols):
        parser.error("Universe file must contain a non-empty symbols list")
    untagged = [s for s in symbols if s not in currencies]
    if untagged:
        parser.error(f"Missing currency tags for: {', '.join(untagged)}")
    requested_symbols = [s for s in symbols if currencies[s] == args.currency]
    if not requested_symbols:
        parser.error(f"No symbols configured in {args.currency}")

    histories = {}
    errors = {}
    for symbol in requested_symbols:
        try:
            history = yf.Ticker(symbol).history(period=args.period, auto_adjust=True)
            if not history.empty:
                histories[symbol] = history
            else:
                errors[symbol] = "No historical data returned"
        except Exception as exc:
            errors[symbol] = str(exc)[:180]

    if not histories:
        parser.error("No usable histories were downloaded")

    result = portfolio_backtest(
        histories,
        initial_capital=args.capital,
        holding_sessions=args.holding,
        max_positions=args.max_positions,
        risk_fraction=args.risk_fraction,
        max_portfolio_risk_fraction=args.max_portfolio_risk_fraction,
        strategy=args.strategy,
        max_position_fraction=args.max_position_fraction,
        round_trip_cost_bps=args.cost_bps,
    )
    report = {
        "strategy": args.strategy,
        "signal_definition": {
            "momentum": "Close above SMA20 and positive 20-session momentum",
            "breakout": "Close above prior 20-session high and above SMA20",
            "pullback_reclaim": "Close crosses back above SMA20 while above SMA50",
        }[args.strategy],
        "data_provider": "Yahoo Finance via yfinance",
        "period_requested": args.period,
        "account_currency": args.currency,
        "symbols_requested": len(requested_symbols),
        "symbols_downloaded": len(histories),
        "download_errors": errors,
        "result": result,
        "warning": "Indicative historical simulation, not a forecast or investment recommendation.",
    }
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
