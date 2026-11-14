"""Command-line market scanner. Data is indicative and may be delayed."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

from stock_picker.risk import build_trade_plan
from stock_picker.scoring import score_history


ROOT = Path(__file__).resolve().parents[2]


def load_universe(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    symbols = data.get("symbols", [])
    if not isinstance(symbols, list) or not all(isinstance(s, str) for s in symbols):
        raise ValueError("Universe must contain a list of ticker strings")
    return symbols


def scan(
    symbols: list[str],
    period: str = "6mo",
    capital: float = 1000.0,
    risk_fraction: float = 0.01,
) -> list[dict]:
    results = []
    for symbol in symbols:
        try:
            history = yf.Ticker(symbol).history(period=period, auto_adjust=True)
            metrics = score_history(history)
            as_of = str(history.index[-1].date())
            item = {
                "symbol": symbol,
                **metrics,
                "data_as_of": as_of,
                "status": "OK",
            }
            if metrics["signal"] == "WATCH":
                item["illustrative_trade_plan"] = build_trade_plan(
                    entry=metrics["price"],
                    atr=metrics["atr_14"],
                    capital=capital,
                    risk_fraction=risk_fraction,
                )
                item["plan_note"] = "Reference uses latest completed close; not a live quote or guaranteed fill."
            results.append(item)
        except Exception as exc:
            results.append({"symbol": symbol, "status": "ERROR", "error": str(exc)[:180]})
    return sorted(results, key=lambda item: item.get("score", -1), reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank a configured stock watchlist")
    parser.add_argument("--universe", type=Path, default=ROOT / "config/universe.json")
    parser.add_argument("--period", default="6mo")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--capital", type=float, default=1000.0)
    parser.add_argument("--risk-fraction", type=float, default=0.01)
    parser.add_argument("--output", type=Path, help="Optional path for a JSON report")
    args = parser.parse_args()
    if args.capital <= 0:
        parser.error("--capital must be positive")
    if not 0 < args.risk_fraction <= 0.05:
        parser.error("--risk-fraction must be between 0 and 0.05")

    ranked = scan(load_universe(args.universe), args.period, args.capital, args.risk_fraction)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_provider": "Yahoo Finance via yfinance",
        "disclaimer": "Indicative research output; quotes may be delayed or incomplete. Verify all data before acting.",
        "results": ranked[: max(1, args.top)],
    }
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
