"""Simple next-session-entry momentum baseline for research, not production validation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yfinance as yf


def backtest_history(
    history: pd.DataFrame,
    holding_sessions: int = 5,
    cost_bps: float = 20.0,
) -> dict:
    """Test a basic trend/momentum rule with next-open entries and fixed holding time.

    Signal is computed using information available at close t. Entry is next open;
    exit is close after the selected number of sessions. Overlapping trades are
    treated as independent observations, so this is not a portfolio simulation.
    """
    if holding_sessions < 1 or holding_sessions > 15:
        raise ValueError("holding_sessions must be between 1 and 15")
    if cost_bps < 0 or cost_bps > 500:
        raise ValueError("cost_bps must be between 0 and 500")
    required = {"Open", "Close"}
    if history is None or len(history) < 60 or not required.issubset(history.columns):
        raise ValueError("At least 60 rows with Open and Close are required")

    data = history[["Open", "Close"]].dropna().copy()
    close = data["Close"]
    sma20 = close.rolling(20).mean()
    momentum20 = close.pct_change(20)
    signal = (close > sma20) & (momentum20 > 0)
    entry = data["Open"].shift(-1)
    exit_price = data["Close"].shift(-(holding_sessions + 1))
    gross = exit_price / entry - 1.0
    valid = signal & entry.notna() & exit_price.notna() & (entry > 0)
    trades = gross[valid] - (cost_bps / 10_000.0)

    if trades.empty:
        return {"trades": 0, "message": "No valid trades in selected history"}

    wins = trades[trades > 0]
    losses = trades[trades <= 0]
    return {
        "trades": int(len(trades)),
        "holding_sessions": holding_sessions,
        "round_trip_cost_bps": cost_bps,
        "win_rate_pct": round(float((trades > 0).mean() * 100), 2),
        "mean_return_pct": round(float(trades.mean() * 100), 3),
        "median_return_pct": round(float(trades.median() * 100), 3),
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 3) if len(losses) and abs(losses.sum()) > 0 else None,
        "max_trade_return_pct": round(float(trades.max() * 100), 3),
        "min_trade_return_pct": round(float(trades.min() * 100), 3),
        "warning": "Overlapping trades; no portfolio constraints, point-in-time universe, FX, borrow, or intraday stop/target simulation. Not evidence of a tradable edge.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a simple historical baseline backtest")
    parser.add_argument("symbol")
    parser.add_argument("--period", default="5y")
    parser.add_argument("--holding", type=int, default=5)
    parser.add_argument("--cost-bps", type=float, default=20.0)
    args = parser.parse_args()
    history = yf.Ticker(args.symbol).history(period=args.period, auto_adjust=True)
    print(json.dumps(backtest_history(history, args.holding, args.cost_bps), indent=2))


if __name__ == "__main__":
    main()
