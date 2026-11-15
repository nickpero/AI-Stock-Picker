# Investment discipline policy

## Purpose and scope

This policy translates the principles in the Moneysurfers booklet *I 7 errori - Stock Mastery* into controls for AI Stock Picker.

The current engine is a short-term, long-only research and decision-support system for setups held approximately 2–15 trading sessions. It is not a long-term fundamental stock portfolio manager. The booklet's five-year investment horizon and 20–30-company portfolio guidance must therefore not be applied mechanically to short-term trades.

No rule in this document authorizes automatic order execution. Signals remain research candidates and must be validated by backtests and paper trading.

## Eight principles translated into system rules

### 1. Look beyond today's price

**Book principle:** ask whether the business is likely to earn more in five years and why; a low share price alone does not mean value.

**System treatment:**
- Do not treat nominal share price, recent price weakness, or a low valuation multiple by itself as a buy signal.
- Add a separate fundamental-quality layer only when timestamped, comparable financial data is available.
- Keep fundamental quality separate from the 2–15-session technical entry score. Do not fabricate missing financial metrics or silently substitute estimates.
- Classify companies, where data supports it, as Growth, Value, or Dividend and assess them with the corresponding metrics described in the source.

### 2. Match the horizon to the capital

**Book principle:** do not put into equities money needed in the next five years; give each investment an appropriate horizon.

**System treatment:**
- Preserve the project's explicit short-term trading horizon (2–15 sessions).
- Label every candidate as a tactical trade, not a five-year investment recommendation.
- Require the operator to confirm that the capital allocated to this high-volatility strategy is risk capital and is not needed for near-term obligations.
- Never imply that a short-term setup is suitable for a long-term holding merely because its price has fallen.

### 3. Diversify deliberately

**Book principle:** the source suggests 20–30 companies for a long-term equity portfolio, with no single holding above 10%, and diversification across sectors, countries, and styles.

**System treatment:**
- Do not import the 20–30 holding target into this short-term strategy: the project has a maximum of three concurrent positions.
- Retain the project's stricter tactical exposure controls: maximum 25% of account equity per position, maximum 1% initial account risk per trade, mandatory stop, and no more than three concurrent positions.
- Before adding a position, check sector and country concentration and obvious overlap/correlation with existing holdings. Flag concentration; do not claim true diversification from ticker count alone.
- Keep portfolio-level open stop-risk capped at 2% of marked equity unless a separately tested policy explicitly changes it.

### 4. Do not try to predict the perfect entry

**Book principle:** decide the entry method in advance; avoid decisions driven by daily news or fear of a correction.

**System treatment:**
- Keep entries rule-based and reproducible: signal at a completed session close, execution no earlier than the next session open in backtests.
- Compare one-shot entry and staged entry only as separate, explicitly defined experiments; do not assume staged entry always improves returns.
- Include realistic transaction costs and opening gaps in simulations.
- Do not change a strategy's entry rules in response to a single recent market move.

### 5. Do not fall in love with a story

**Book principle:** a compelling narrative is a reason to investigate, not sufficient grounds to buy. The source highlights revenue, operating margin, operating cash flow, debt, and management changes as checks.

**System treatment:**
- News, themes, analyst narratives, and social attention must never independently create a buy signal.
- When reliable financial statements are available, review at least three years of revenue, operating margin, and operating cash flow, alongside debt/liquidity and material management or accounting warnings.
- Missing or stale fundamental data must be shown as unknown, not treated as a pass.
- Catalyst/news verification must use timestamped sources; distinguish the publication time from the time the system detected it.

### 6. Define the exit before entry

**Book principle:** write down why the investment is being made and the conditions that would invalidate the thesis; do not hold solely to recover the purchase price.

**System treatment:**
- Every trade plan must have an entry, mandatory stop, target(s), maximum holding period, and a concise invalidation condition before entry.
- Keep ATR-based stops and targets explicit. The current baseline uses a 1.5 ATR stop and predefined reward targets; any change must be evaluated in backtests.
- Keep time-based exits and gap handling explicit in simulations.
- A losing trade must not be held merely to return to breakeven. A stop is a risk control, not a guarantee against gaps or slippage.

### 7. Account for taxes and costs

**Book principle:** understand which gains can offset losses, the expiry of tax losses, and the tax treatment of the instruments used.

**System treatment:**
- Continue to include transaction costs in backtests and report them separately from gross performance.
- Do not hard-code tax assumptions from the booklet into performance results. Its tax discussion is simplified and stated as of September 2026; Italian tax rules and individual circumstances require current verification with an authorized professional.
- Taxes, tax-loss carryforwards, dividends, and cross-border tax treatment remain explicitly out of scope until implemented and independently checked.
- Never describe ETF gains, share gains, dividends, and other instruments as tax-interchangeable.

### 8. Use a method, not improvisation

**Book principle:** the source's eighth chapter identifies lack of method as the common root of the seven errors and distinguishes Growth, Value, and Dividend companies.

**System treatment:**
- Keep signal definitions, risk limits, data dates, costs, and execution assumptions visible in every research report.
- Preserve separate technical setup scores and fundamental-quality assessments; a score is not a probability of profit.
- Record why a candidate qualified, what would invalidate it, and which required fields are unavailable.
- Promote a strategy only after comparable out-of-sample and walk-forward tests, followed by paper trading.

## Pre-trade review checklist

A candidate should be marked **REVIEW REQUIRED** until the operator can confirm:

1. The setup matches the configured 2–15-session trading horizon.
2. The signal is based on completed data and its latest data date is visible.
3. The entry rule and next-session execution assumption are explicit.
4. The mandatory stop, target(s), time exit, and invalidation condition are defined.
5. Position size respects the 1% per-trade risk budget and 25% position-value cap.
6. The addition respects the three-position limit and 2% aggregate open stop-risk cap.
7. Sector/country overlap with existing positions has been checked or is clearly marked unknown.
8. No decision is based solely on a narrative, headline, low share price, or recent price move.
9. Transaction costs are included; taxes and any unmodeled costs are disclosed.
10. Missing data is reported as unknown and does not silently pass the review.

This checklist is a research and operational control, not an automatic investment recommendation. A candidate can be technically ranked highly and still remain unsuitable for entry.

## Implementation order

1. Preserve the current technical strategies and existing risk engine as the baseline.
2. Add visible portfolio concentration and overlap diagnostics without changing signal weights.
3. Add a timestamp-aware fundamental data layer only after selecting and testing a reliable data source.
4. Add the Growth/Value/Dividend assessment as a separate, explainable report section.
5. Add the pre-trade checklist and invalidation rationale to scan and simulation reports.
6. Compare the original baseline against each new filter on identical historical windows; use out-of-sample/walk-forward tests and paper trading before considering any strategy change.

## Source note

This policy is based on *I 7 errori - Stock Mastery*, especially chapters 1–8 and the one-page summary and checklist (printed pages 8–26). The source itself says its data and Italian tax discussion are updated to September 2026 and are educational, not personalized investment advice. The operational adaptations above are project-specific design decisions, not claims made by the source.
