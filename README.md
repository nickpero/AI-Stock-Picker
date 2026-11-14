# AI Stock Picker

Independent research and decision-support engine for short-term equity setups (2–15 trading sessions).

## Principles
- Recommendation-only: no automatic order execution.
- A setup score is a ranking aid, not a probability of profit.
- No predictive edge is claimed before point-in-time backtesting and paper-trading validation.

## Current MVP
- Configurable starter watchlist for US and European equities (`config/universe.json`).
- Yahoo Finance historical OHLCV adapter (`yfinance`).
- Transparent technical ranking using 5/20-session momentum, moving-average trend, relative volume, and ATR-based volatility penalty.
- Illustrative ATR-based stop/targets and share sizing, capped by account-risk and concentration limits.
- Portfolio-level cash simulation with next-session open entries, ATR stops/targets, transaction costs and integer-share sizing.
- Aggregate open stop-risk cap (default 2% of marked equity) alongside per-trade risk limits.
- Four comparable signal modes, including an experimental regime-adaptive filter that trades established long-term uptrends and avoids unusually high volatility.
- Equal-weight benchmark calculated on the same available symbols and dates.
- JSON scan output with UTC generation time and latest data date.
- Unit tests and GitHub Actions workflow (push, pull request, and manual trigger).

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
PYTHONPATH=src python -m stock_picker.scanner --top 10 --capital 1000 --risk-fraction 0.01
PYTHONPATH=src python -m stock_picker.backtest AAPL --period 5y --holding 5 --cost-bps 20
pytest -q
```

## Run a GitHub portfolio simulation

1. Open the repository's **Actions** tab.
2. Select **Portfolio Simulation** and choose **Run workflow**.
3. Select one currency (EUR, USD or CHF), strategy (momentum, breakout or pullback_reclaim), historical period, starting capital, holding period, maximum open positions and estimated transaction costs.
4. When the workflow finishes, download the `portfolio-simulation-...` artifact. It contains the JSON report, including the equity curve and trade-by-trade details.

Run one currency at a time. Results from separate currencies must not be added together until FX conversion is implemented. The workflow downloads historical data from Yahoo Finance at run time; missing symbols and download errors are listed in the report.

## Current limitations
- The universe is a small starter watchlist, not a complete US/EU market scan.
- Yahoo Finance coverage, timestamps, corporate actions, and symbol mapping can be incomplete or delayed.
- The scoring weights are heuristic and have not been optimized or validated for predictive performance.
- Execution follows market phases: prior-close signal, next-open fill, opening-gap exits, then intraday stop/target checks; daily OHLC still cannot reconstruct intraday sequencing, so stop is assumed first if both levels trade.
- The benchmark is frictionless and equal-weight daily rebalanced; it is a reference, not an executable portfolio.
- FX conversion, taxes, borrow, delisted securities, market impact and point-in-time constituents are not modeled.
- News catalysts, primary-source verification, Telegram delivery, and a proper walk-forward evaluation are not implemented yet.
- Trade plans are illustrative calculations based on the latest historical close, not live executable orders.

## Next milestones
1. Validate data quality and broaden a liquid, survivorship-aware US/EU universe.
2. Add news/catalyst ingestion with timestamped primary sources.
3. Run all four signal modes on identical periods and compare them with the equal-weight benchmark.
4. Add walk-forward and out-of-sample evaluation before any paper-trading use.
5. Add catalyst-aware ranking and calibrated probability estimates only if supported by validation.
6. Add Telegram reporting after the signal and risk layers pass paper-trading checks.
