# Regime Historical Replay Test Plan

Date: 2026-07-28 UTC

## Objective

Verify that the regime labeler can calculate and retrieve historical labels from the current bagent Feather files, even when the files are old relative to today.

This is a historical replay test. It is separate from today's live `/a` freshness check.

## Important distinction

- Today's `/a` lookup applies the source freshness rule.
- A lookup for a historical event must use only labels strictly before that event.
- Historical testing must not be blocked merely because the Feather file is old today.

## Test dates

### 1. 2026-03-30

Expected:

- OKX returns a valid regime result.
- Kraken returns a valid regime result.
- Both returned label dates are strictly before `2026-03-30`.
- The later Kraken gap does not affect this historical result.

### 2. 2026-05-15

This date is inside the temporary Kraken gap.

Expected:

- Kraken does not use future June data.
- Kraken returns the last valid pre-gap label, dated before the event, or an explicit unknown/stale result if the lookup contract requires no carry-forward across the gap.
- No label from the missing interval is created.

### 3. 2026-07-01

The current Kraken source has complete data from `2026-06-03` through `2026-07-05`.

Expected:

- Kraken uses the complete post-gap data beginning `2026-06-03`.
- The latest usable Kraken label is `2026-06-30` or earlier.
- Kraken does not use the `2026-07-01` candle/day itself.
- OKX also returns its latest label strictly before the event.
- The gap filter does not accidentally exclude valid post-gap data.

The post-gap Kraken period has enough observations for 7-, 14-, and 28-day calculations. Longer warm-up-dependent fields, particularly the 75th-percentile volatility baseline, may still be unavailable or conservative. This is acceptable if the result remains deterministic and explicitly represented.

## Execution boundary

This is an agent-run verification. The user must not manually issue Telegram commands to test it.

The normal live `/a` path uses the current timestamp, so it cannot by itself replay `2026-03-30` or `2026-07-01`. The test must intercept the data boundary before Telegram formatting:

- call the labeler and `get_regimes_at(event_ts)` directly for each historical event;
- pass those results into the same strategy-message formatter used by `/a`;
- inspect the rendered message and assert the expected data dates/statuses;
- separately verify that the current live lookup remains `unknown/stale` while the source is older than seven days.

No real Telegram message should be sent. This is a local/server-side automated simulation.

## Procedure

1. Read the current bagent Feather files:
   - OKX: `/opt/cex_trader/user_data/profiles/okx-spot/data/okx/BTC_USDC-1h.feather`
   - Kraken: `/opt/cex_trader/user_data/data/kraken/BTC_USDC-1h.feather`
2. Record row counts, first/last timestamps, complete daily ranges, and missing days.
3. Generate labels with live freshness enforcement disabled.
4. Apply the temporary Kraken exclusion only for the missing interval:
   - `2026-04-02` through `2026-06-02`
   - the already-adjudicated one-day gap `2025-11-01`
5. Verify that complete Kraken data from `2026-06-03` onward remains included.
6. Query each test event through `get_regimes_at(event_ts)`.
7. Verify strict-before-event behavior.
8. Verify that gap data and future data cannot contaminate a result.
9. Intercept the same analysis-message formatting path used by `/a` and render messages with the historical regime results.
10. Assert the rendered messages contain the expected `as of`/calculation-data dates and do not contain future or gap labels.
11. Assert the current live lookup and current-style message remain `unknown/stale` when the source is older than seven days.
12. Do not send Telegram messages and do not require any manual user action.
13. If a test fails, fix the smallest relevant code path and rerun the tests.
14. Run the full non-e2e test suite.
15. Deploy only if code changes are required.
16. Record exact labels, label dates, statuses, source age, rendered-message assertions, and remaining limitations.

## Success criteria

- Historical events before the gap return valid pre-gap labels.
- Events inside the gap never use later post-gap data.
- Events after the gap can use valid data beginning `2026-06-03`.
- Every returned label is strictly before its event timestamp.
- Current live lookups still correctly enforce the seven-day freshness rule.
- Telegram output identifies the calculation-data date and age when regime context is present.
