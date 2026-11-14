# Out-of-sample validation — short holding (1–5 sessions)

**Run date:** 2026-11-14  
**GitHub Actions run:** [Portfolio Simulation #9](https://github.com/nickpero/AI-Stock-Picker/actions/runs/43643627594)  
**Tests:** [Tests run](https://github.com/nickpero/AI-Stock-Picker/actions/runs/43643627671) — passed  
**Status:** 16/16 simulations passed; 16 JSON artifacts uploaded.

## Method

- Historical data: Yahoo Finance via yfinance, adjusted OHLC, requested 5-year history.
- Evaluation window: from **2024-11-14**; earlier history is retained only to warm up indicators.
- Currency/universe: EUR, 11 configured symbols with available data.
- Starting capital: €1,000; maximum 4 concurrent positions.
- Holding limits: 1, 2, 3 or 5 trading sessions.
- Round-trip transaction cost: 20 bps.
- Entry: signal from previous completed close, fill at next session open.
- Stops/targets: daily OHLC simulation, conservative stop-first assumption if both levels trade.
- Regime Adaptive ATR percentile threshold now uses only prior bars (rolling quantile shifted by one session).

## Results

| Strategy | Max hold | Final equity | Return | Max drawdown | Sharpe | Trades | Win rate | Profit factor |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Momentum | 1 | €650.06 | -34.99% | -38.95% | -2.56 | 1,187 | 46.3% | 0.71 |
| Momentum | 2 | €880.95 | -11.90% | -24.41% | -0.68 | 712 | 48.2% | 0.89 |
| Momentum | 3 | €1,018.07 | +1.81% | -14.85% | 0.12 | 512 | 50.0% | 1.02 |
| Momentum | 5 | €939.07 | -6.09% | -18.08% | -0.32 | 346 | 48.8% | 0.93 |
| Breakout | 1 | €866.23 | -13.38% | -14.93% | -1.84 | 289 | 43.6% | 0.63 |
| Breakout | 2 | €911.07 | -8.89% | -12.47% | -0.92 | 208 | 46.1% | 0.77 |
| Breakout | 3 | €909.20 | -9.08% | -13.79% | -0.83 | 174 | 44.2% | 0.76 |
| Breakout | 5 | €925.52 | -7.45% | -15.10% | -0.58 | 145 | 43.5% | 0.81 |
| Pullback Reclaim | 1 | €893.73 | -10.63% | -11.18% | -2.12 | 142 | 38.0% | 0.48 |
| Pullback Reclaim | 2 | €960.64 | -3.94% | -5.95% | -0.51 | 142 | 45.8% | 0.85 |
| Pullback Reclaim | 3 | €1,002.54 | +0.25% | -4.86% | 0.05 | 131 | 52.7% | 1.01 |
| Pullback Reclaim | 5 | €978.52 | -2.15% | -6.40% | -0.17 | 115 | 45.2% | 0.93 |
| Regime Adaptive | 1 | €725.58 | -27.44% | -29.83% | -2.26 | 881 | 45.0% | 0.71 |
| Regime Adaptive | 2 | €881.21 | -11.88% | -20.32% | -0.81 | 517 | 46.2% | 0.86 |
| Regime Adaptive | 3 | €984.77 | -1.52% | -13.93% | -0.08 | 375 | 48.5% | 0.98 |
| Regime Adaptive | 5 | €1,012.40 | +1.24% | -9.66% | 0.09 | 253 | 48.2% | 1.02 |

## Benchmark and decision

The frictionless equal-weight daily-rebalanced reference on the same available symbols/dates returned **+26.25%** (from €1,000 to €1,262.50). It is not a directly executable benchmark and does not include transaction costs.

**No strategy passes the current deployment bar.** Best strategy-duration result in this evaluation window was Momentum 3 sessions (+1.81%), but its Sharpe (0.12), profit factor (1.02), and drawdown (-14.85%) do not establish a robust edge. The previously strongest full-period result, Pullback Reclaim 3 sessions (+16.30% over the full 5-year sample), fell to +0.25% in this later window.

## Important limitations

This is a useful temporal robustness check, not a fully pristine independent test: the full 5-year results had already been inspected before this run. The rules were not tuned on this evaluation window, but selection bias cannot be ruled out. The universe is a small current watchlist, not point-in-time constituents; delisted securities, dividends, taxes, FX, market impact and realistic spread/slippage by symbol are not fully modeled. Daily OHLC cannot reconstruct intraday order sequencing. The benchmark is frictionless.

**Operational decision:** do not deploy real capital from these signals yet. Next milestone is a frozen-rule paper-trading forward test with timestamped signals and realistic spread/slippage, plus a broader survivorship-aware universe.
