"""Portfolio-aware long-only daily-bar backtest.

Signals are formed at a completed close and can enter no earlier than the
following session's open. When stop and target are both touched in one daily
bar, the stop is assumed first (conservative). All symbols must be quoted in
the same account currency; FX conversion is intentionally not guessed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor
from typing import Mapping

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


def _prepare_history(history: pd.DataFrame) -> pd.DataFrame:
    required = {"Open", "High", "Low", "Close"}
    if history is None or not required.issubset(history.columns):
        raise ValueError(f"Each history must contain {sorted(required)}")
    frame = history[list(required)].copy().sort_index()
    frame = frame[~frame.index.duplicated(keep="last")].dropna()
    if len(frame) < 25:
        raise ValueError("Each symbol needs at least 25 complete daily bars")
    if (frame[["Open", "High", "Low", "Close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    if (frame["High"] < frame[["Open", "Close", "Low"]].max(axis=1)).any():
        raise ValueError("High price is inconsistent with OHLC values")
    if (frame["Low"] > frame[["Open", "Close", "High"]].min(axis=1)).any():
        raise ValueError("Low price is inconsistent with OHLC values")

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
    frame["signal"] = (frame["Close"] > frame["sma20"]) & (frame["momentum20"] > 0)
    return frame


def portfolio_backtest(
    histories: Mapping[str, pd.DataFrame],
    initial_capital: float = 1000.0,
    holding_sessions: int = 5,
    max_positions: int = 4,
    risk_fraction: float = 0.01,
    max_position_fraction: float = 0.25,
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
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if not 1 <= holding_sessions <= 15 or max_positions < 1:
        raise ValueError("holding_sessions must be 1..15 and max_positions >= 1")
    if not 0 < risk_fraction <= 0.05:
        raise ValueError("risk_fraction must be in (0, 5%]")
    if not 0 < max_position_fraction <= 1:
        raise ValueError("max_position_fraction must be in (0, 1]")
    if stop_atr <= 0 or target_r <= 0 or not 0 <= round_trip_cost_bps <= 1000:
        raise ValueError("Invalid stop, target or transaction cost")

    frames = {str(s): _prepare_history(h) for s, h in histories.items()}
    # Daily bars from different exchanges need not share every holiday.
    calendar = sorted(set().union(*(set(f.index) for f in frames.values())))
    half_cost = round_trip_cost_bps / 20000.0
    cash = float(initial_capital)
    positions: dict[str, Position] = {}
    trades: list[dict] = []
    equity_rows: list[dict] = []
    last_prices: dict[str, float] = {}

    for day in calendar:
        # Carry forward the last close for markets that are shut on this date.
        for symbol, frame in frames.items():
            if day in frame.index:
                last_prices[symbol] = float(frame.loc[day, "Close"])

        # Manage existing positions first; no same-day re-entry after an exit.
        exited_today: set[str] = set()
        for symbol, pos in list(positions.items()):
            frame = frames[symbol]
            if day not in frame.index:
                continue
            bar = frame.loc[day]
            pos.sessions_held += 1
            o, h, l, c = (float(bar[k]) for k in ("Open", "High", "Low", "Close"))
            exit_price = None
            reason = None
            if o <= pos.stop:
                exit_price, reason = o, "stop_gap"
            elif o >= pos.target:
                exit_price, reason = o, "target_gap"
            elif l <= pos.stop and h >= pos.target:
                exit_price, reason = pos.stop, "stop_and_target_same_bar_stop_first"
            elif l <= pos.stop:
                exit_price, reason = pos.stop, "stop"
            elif h >= pos.target:
                exit_price, reason = pos.target, "target"
            elif pos.sessions_held >= holding_sessions:
                exit_price, reason = c, "time_exit"

            if exit_price is not None:
                gross_proceeds = pos.shares * exit_price
                exit_fee = gross_proceeds * half_cost
                cash += gross_proceeds - exit_fee
                entry_cost = pos.shares * pos.entry_price
                entry_fee = entry_cost * half_cost
                pnl = gross_proceeds - exit_fee - entry_cost - entry_fee
                trades.append({
                    "symbol": symbol,
                    "entry_date": pos.entry_date.date().isoformat(),
                    "exit_date": pd.Timestamp(day).date().isoformat(),
                    "entry_price": round(pos.entry_price, 6),
                    "exit_price": round(exit_price, 6),
                    "shares": pos.shares,
                    "pnl": round(pnl, 4),
                    "return_pct": round(pnl / (entry_cost + entry_fee) * 100, 4),
                    "exit_reason": reason,
                    "sessions_held": pos.sessions_held,
                })
                del positions[symbol]
                exited_today.add(symbol)

        # Signals use the previous completed bar only; entry is today's open.
        candidates = []
        for symbol, frame in frames.items():
            if symbol in positions or symbol in exited_today or day not in frame.index:
                continue
            loc = frame.index.get_loc(day)
            if not isinstance(loc, (int, np.integer)) or loc == 0:
                continue
            signal_bar = frame.iloc[loc - 1]
            today = frame.iloc[loc]
            if bool(signal_bar["signal"]) and pd.notna(signal_bar["atr14"]):
                score = float(signal_bar["momentum20"])
                candidates.append((score, symbol, today, float(signal_bar["atr14"])))
        candidates.sort(key=lambda x: (-x[0], x[1]))

        # Mark current portfolio at today's close before sizing new entries.
        market_value = sum(p.shares * last_prices[s] for s, p in positions.items() if s in last_prices)
        equity_before_entries = cash + market_value

        for _, symbol, bar, atr in candidates:
            if len(positions) >= max_positions:
                break
            entry = float(bar["Open"])
            stop = entry - stop_atr * atr
            if entry <= 0 or stop <= 0:
                continue
            risk_per_share = entry - stop
            risk_budget = equity_before_entries * risk_fraction
            by_risk = floor(risk_budget / risk_per_share)
            by_concentration = floor(equity_before_entries * max_position_fraction / entry)
            by_cash = floor(cash / (entry * (1 + half_cost)))
            shares = min(by_risk, by_concentration, by_cash)
            if shares < 1:
                continue
            cost = shares * entry
            fee = cost * half_cost
            cash -= cost + fee
            pos = Position(
                symbol=symbol,
                entry_date=pd.Timestamp(day),
                entry_price=entry,
                shares=shares,
                stop=stop,
                target=entry + target_r * risk_per_share,
                risk_per_share=risk_per_share,
                sessions_held=1,
            )
            # Entry-day OHLC is checked after the opening fill. If both levels
            # are touched, assume stop first because daily bars lack sequencing.
            high, low = float(bar["High"]), float(bar["Low"])
            entry_exit = None
            entry_reason = None
            if low <= pos.stop and high >= pos.target:
                entry_exit, entry_reason = pos.stop, "stop_and_target_same_bar_stop_first"
            elif low <= pos.stop:
                entry_exit, entry_reason = pos.stop, "stop_entry_day"
            elif high >= pos.target:
                entry_exit, entry_reason = pos.target, "target_entry_day"
            if entry_exit is not None:
                proceeds = shares * entry_exit
                exit_fee = proceeds * half_cost
                cash += proceeds - exit_fee
                entry_cost = shares * entry
                entry_fee = entry_cost * half_cost
                pnl = proceeds - exit_fee - entry_cost - entry_fee
                trades.append({
                    "symbol": symbol,
                    "entry_date": pd.Timestamp(day).date().isoformat(),
                    "exit_date": pd.Timestamp(day).date().isoformat(),
                    "entry_price": round(entry, 6),
                    "exit_price": round(entry_exit, 6),
                    "shares": shares,
                    "pnl": round(pnl, 4),
                    "return_pct": round(pnl / (entry_cost + entry_fee) * 100, 4),
                    "exit_reason": entry_reason,
                    "sessions_held": 1,
                })
            else:
                positions[symbol] = pos

        market_value = sum(
            p.shares * float(frames[s].loc[day, "Close"])
            for s, p in positions.items() if day in frames[s].index
        )
        equity_rows.append({"date": pd.Timestamp(day), "equity": cash + market_value, "cash": cash, "open_positions": len(positions)})

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

    if len(curve):
        # The last observation is net of the costs incurred by end-of-data liquidation.
        curve.iloc[-1] = final_equity

    trade_frame = pd.DataFrame(trades)
    wins = trade_frame[trade_frame["pnl"] > 0]["pnl"] if trades else pd.Series(dtype=float)
    losses = trade_frame[trade_frame["pnl"] <= 0]["pnl"] if trades else pd.Series(dtype=float)
    result = {
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
