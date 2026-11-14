# AI Stock Picker

Independent research and decision-support engine for short-term equity setups (2–15 trading sessions).

## Principles
- Recommendation-only: no automatic order execution.
- Independent from Pharma Radar and PSIG; those repositories and workflows are not modified.
- A setup score is a ranking aid, not a probability of profit.
- No predictive edge is claimed before point-in-time backtesting and paper-trading validation.

## Current MVP
- Configurable starter watchlist for US and European equities (`config/universe.json`).
- Yahoo Finance historical OHLCV adapter (`yfinance`).
- Transparent technical ranking using 5/20-session momentum, moving-average trend, relative volume, and ATR-based volatility penalty.
- JSON output from the command line.
- Unit tests and GitHub Actions test workflow.

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
PYTHONPATH=src python -m stock_picker.scanner --top 10
pytest -q
```

## Known limitations
- The current universe is a small starter watchlist, not a complete US/EU market scan.
- Yahoo Finance data availability, timing, corporate-action handling, and symbol coverage are not guaranteed; verify data before acting.
- News catalysts, entry/stop/target construction, portfolio sizing, backtesting, and Telegram delivery are not implemented yet.
- The scanner is research software, not investment advice or an execution system.

## Next milestones
1. Validate data quality and add a broader liquid universe.
2. Add news/catalyst ingestion with timestamped primary sources.
3. Build risk-aware trade plans (entry, invalidation, targets, sizing).
4. Backtest with realistic spreads, slippage, fees, FX, and point-in-time universes.
5. Paper trade before any live-use recommendations.
