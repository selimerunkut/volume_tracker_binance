# Signal-Bot BTC Market Labeling Plan

Created: 2026-07-29 UTC
Owner: `/Users/semacair/dev/CEX_volume_tracker_B`

## Scope correction

This repository is the signal bot. It consumes exchange data and attaches deterministic BTC market labels to signal analysis.

Feather downloading, merging, repairing, and retention belong to the `cex_trader` application. The signal bot must not repair or rewrite those files.

`memory-bank/feather-data-repair-todos.md` is an external handoff/reference for the `cex_trader` owner. It is not a CEX_volume_tracker_B implementation plan.

## Objective

For every configured venue, independently calculate the frozen causal BTC structural label from that venue's own BTC 1h source:

- `structural_bull`
- `structural_bear`
- `range_or_transition`
- volatility: `high` or `normal_or_low`
- volume: `expanded` or `normal_or_low`

A venue's missing, stale, or invalid source must not block labels from another venue.

Labels are diagnostic evidence only. They do not gate or change the deterministic trading action.

## Current venue policy

### OKX — required and currently working

- Source: configured OKX BTC/USDC 1h Feather file.
- Keep the existing contract and golden-fixture parity.
- Current live label path is working when source freshness passes.

### Kraken — optional and non-blocking

- Keep Kraken as a separate BTC/USDC 1h instance when valid data exists.
- Do not repair Kraken data in this repository.
- Do not make Kraken's missing candles or stale source block OKX, Hyperliquid, or the strategy analysis.
- Skip unavailable daily intervals without imputing candles or splicing another venue.
- Preserve valid labels before a gap.
- After a gap, reset the direction state and resume labels only from valid post-gap data.
- If there is not enough valid history or the source is too stale, display `unknown/stale` with the source date/age.
- A few missing days are a data-quality warning, not a global labeler failure.

The unresolved Q2 Kraken gap remains excluded as a source-data exception until `cex_trader` supplies the history. The signal bot should consume the valid pre-gap and post-gap sections independently.

### Hyperliquid — desired future venue

- Add Hyperliquid as a third independent BTC label instance if a validated 1h BTC source is available.
- Do not assume the pair name or quote asset. Confirm the canonical Hyperliquid symbol, timestamp convention, and source path from `cex_trader` before implementation.
- Give Hyperliquid its own contract ID, source environment variable, validation result, and provenance.
- Never merge Hyperliquid candles with OKX or Kraken candles.
- Hyperliquid availability must also be non-blocking: absent or stale Hyperliquid data produces `unknown/stale` only for Hyperliquid.

## Data-gap policy

The current labeler fails closed on unadjudicated missing days. That is too strict for optional venue feeds.

Change the signal-bot policy as follows:

1. Validate each venue independently.
2. Treat a missing daily interval as a boundary in that venue's label series, not as a failure for all venues.
3. Emit no label for missing days.
4. Reset the direction persistence state at the gap.
5. Resume only when complete daily candles return.
6. Never interpolate, forward-fill, or use another exchange's candle.
7. Keep a bounded/adjudicated gap policy so a truncated source cannot silently look valid. A source with too little total history still returns `unknown/stale`.
8. Store the gap reason and source provenance in the venue result/log.

Implementation decision: tolerate a maximum gap of seven UTC calendar days only when the complete gap is outside the protected recent window. The protected window is the current UTC day and the preceding seven UTC days. Any missing or incomplete interval in that window fails closed, even when it is listed as an explicit historical exception. Longer historical gaps require explicit configuration, such as the current Kraken Q2 interval.

## Freshness and visibility

- A partial current UTC day is discarded.
- A completed source up to seven days old is usable for a live label.
- A source older than seven days may still produce historical labels, but its live result is `unknown/stale`.
- Every displayed venue line must show the calculation-data date and age, for example:

```text
OKX: range_or_transition · vol normal_or_low · volume expanded · as of 2026-08-05 · calculation data through 2026-08-05 (2 days behind today)
Kraken: unknown/stale · calculation data through 2026-07-29 (9 days behind today)
```

- Do not hide stale or missing sources behind a generic successful-looking label.

## Telegram output policy

- The deterministic strategy message displays one independent line per configured venue.
- A stale/unknown venue line remains visible with its source date/age.
- Legacy and DeepSeek comparison messages do not display duplicate regime or altseason sections unless they carry grounded context themselves.
- No Telegram message is sent by the background labeler job.

## TODOs

### Phase 1 — make venue failures non-blocking

- [x] Add per-venue result handling so one failed/stale source does not cause `run_all()` to fail the other venues.
- [x] Change gap validation from global fail-closed to venue-local gap boundaries with reset semantics.
- [x] Preserve strict validation for malformed rows, duplicate timestamps, wrong timezone, and insufficient total history.
- [x] Add tests for historical short gaps, current-window gaps, long gaps, and failed persisted venue state.
- [x] Keep the current Kraken Q2 exclusion explicit and provenance-tagged.

### Phase 2 — verify current OKX/Kraken behavior

- [ ] Run the labeler against the current bagent source paths without modifying those files.
- [ ] Verify OKX labels from its own BTC source and confirm bull/bear/range transitions against the frozen fixture and historical replay dates.
- [ ] Verify Kraken pre-gap and post-gap labels when source data is available.
- [ ] Verify Kraken missing/stale data yields only Kraken `unknown/stale`.
- [ ] Verify OKX remains usable when Kraken fails.
- [ ] Verify the Telegram line uses the correct venue-specific source age.

### Phase 3 — add Hyperliquid as an optional third venue

- [x] Inspect `cex_trader`: the canonical spot pair is `BTC/USDC`, and its history service targets `/opt/cex_trader/user_data/research/hyperliquid-spot`.
- [x] Confirm a sufficiently long validated Hyperliquid BTC/USDC 1h artifact exists at the `cex_trader` research output path.
- [x] Add Hyperliquid to the venue contract registry and independent source configuration.
- [x] Add Hyperliquid persistence, gap handling, freshness, and message output.
- [ ] Create an independent Hyperliquid parity/reference fixture or explicitly document why the frozen algorithm is sufficient.
- [x] Add tests proving venue configuration and non-blocking output behavior.

Operational deployment and first-refresh verification are tracked in `memory-bank/regime-live-data-todos.md`.

### Phase 4 — live verification

- [ ] Run a no-send simulation using current bagent data for each venue.
- [ ] Test historical events before, inside, and after the Kraken gap.
- [ ] Test current live output with fresh OKX and stale/missing Kraken.
- [ ] Verify `/a` includes the correct venue lines and calculation-data ages.
- [ ] Run the complete non-e2e test suite.
- [ ] Deploy only signal-bot code changes.
- [ ] Verify service status and logs on bagent.

## Decisions needed before implementation

1. **Resolved:** the optional short-gap bound is seven UTC days, excluding the protected current/recent window.
2. **Resolved:** an event inside a gap must return `unknown/stale`, not the last pre-gap label.
3. What exact Hyperliquid BTC pair and source artifact does `cex_trader` provide?
4. Should Hyperliquid appear before or after Kraken in Telegram output?

## Implementation status

Implemented in the signal bot:

- Historical gaps up to seven UTC days are tolerated.
- The current UTC day and preceding seven UTC days are protected; missing or incomplete data there fails closed.
- Failed venue validation is persisted separately, so old labels cannot appear as live `ok`.
- Historical labels remain queryable by explicit event timestamp.
- No source Feather file is modified.

## Completion criteria

- OKX labels are independently calculated and remain usable when optional venues fail.
- Kraken gaps/staleness do not block OKX or the strategy signal.
- Hyperliquid is either integrated with a verified source or explicitly deferred with a documented blocker.
- No venue data is repaired, rewritten, interpolated, or mixed by this repository.
- Telegram output clearly identifies each venue, label as-of date, source date, and age.
- Tests prove causal ordering, gap reset behavior, and non-blocking venue failures.
