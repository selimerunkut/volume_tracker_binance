# Signal validation iteration plan

Date: 2026-09-20

## Current evidence

- The server contains historical deterministic analyses, but database rows are not proof of the exact Telegram text delivered.
- The observed cohort has about 99.7% WAIT and only 13 directional signals. This is too selective for threshold tuning or a directional edge claim.
- WAIT outcomes are an avoidance metric, not trading profit.
- Existing historical rows can lack candle coverage and raw 24-hour returns.

## Telegram history

The Telegram Bot API does not provide a normal history endpoint for messages sent by the bot. Use the server database for structured historical analysis. Obtain a user-account Telegram export only if exact wording or delivery history is needed. Keep message rendering tests and prospective message/context snapshots for new observations.

## Iteration 1: measurement quality (before strategy changes)

1. Keep LONG/SHORT thresholds and deterministic scoring unchanged.
2. Validate the evaluator's timestamp contract against exchange candle-open timestamps, including off-hour suggestions, incomplete candles, missing intervals, early TP/SL exits, and both-level touches.
3. Store raw 24-hour return and candle/path coverage separately from WIN/LOSS/WAIT utility.
4. Produce matched-cohort comparisons: current policy, always cash, and always buy must use the same eligible rows. Report WAIT utility separately from investable return.
5. Record a frozen evidence snapshot: database identity, code SHA, date range, source/exchange, action counts, and exclusion reasons.

## Iteration 2: live context quality

1. Fetch BTC context independently from Hyperliquid 1h candles; do not depend on the separate Freqtrade data process.
2. Enforce freshness, positive finite prices, hourly cadence, and exclusion of unfinished candles.
3. Keep the context informational. It must not change deterministic scoring.
4. Show a concise explanation with source, candle age, 6h/24h return, EMA relationship, volatility, and volume comparison.

## Iteration 3: prospective shadow experiment

After measurement is reliable, collect a held-out prospective cohort. Compare the unchanged policy with cash and buy baselines. Only then test normalized indicator-strength scoring. Do not loosen thresholds, tune TP/SL, or treat confidence as calibrated probability based on the current sample.

## Oracle recommendation

The next best step is measurement and context validation, not more signals: validate endpoint alignment and coverage, enforce BTC freshness/cadence, use matched cohorts, and collect prospective shadow evidence before any policy change.
