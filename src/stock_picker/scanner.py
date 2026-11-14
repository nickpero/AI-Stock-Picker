"""Command-line market scanner. Data is indicative and may be delayed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yfinance as yf

from stock_picker.scoring import score_history


ROOT = Path(__file__).resolve().parents[2]


def load_universe(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["symbols"]


def scan(symbols: list[str], period: str = "6mo") -> list[dict]:
    results = []
    for symbol in symbols:
        try:
            history = yf.Ticker(symbol).history(period=period, auto_adjust=True)
            metrics = score_history(history)
            results.append({"symbol": symbol, **metrics, "status": "OK"})
        except Exception as exc:
            results.append({"symbol": symbol, "status": "ERROR", "error": str(exc)[:180]})
    return sorted(
        results,
        key=lambda item: item.get("score", -1),
        reverse=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank a configured stock watchlist")
    parser.add_argument("--universe", type=Path, default=ROOT / "config/universe.json")
    parser.add_argument("--period", default="6mo")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    ranked = scan(load_universe(args.universe), args.period)
    print(json.dumps(ranked[: max(1, args.top)], indent=2))


if __name__ == "__main__":
    main()
