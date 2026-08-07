# Feather Data Repair TODOs

> **External handoff only.** This work belongs to the `cex_trader` application, not this signal-bot repository. `CEX_volume_tracker_B` must not repair, rewrite, or merge Feather files. See `memory-bank/regime-market-labeling-plan.md` for the signal-bot plan.

Created: 2026-07-29 UTC

## Current facts

### Bagent

- OKX currently has 4,535 rows, from `2026-01-21 00:00 UTC` through `2026-07-28 22:00 UTC`.
- OKX latest complete day is `2026-07-27`; the current day has 23 candles.
- Kraken currently has only 839 rows, from `2026-04-01 00:00 UTC` through `2026-07-06 21:00 UTC`.
- Kraken currently has only 35 completed daily candles, so the regime labeler fails its 120-day minimum.
- Kraken incomplete days are `2026-04-02=1` and `2026-07-06=22`.
- Both services are active.

### Local recovery candidates

- Full local snapshot:
  `/Users/semacair/dev/cex_trader/user_data/data/kraken/BTC_USDC-1h.feather`
  - 5,202 rows
  - `2025-10-01` through `2026-07-06 21:00 UTC`
- Equivalent worktree copy:
  `/Users/semacair/dev/.worktrees/cex_trader/plan-tournament-strategy-import/user_data/data/kraken/BTC_USDC-1h.feather`
- Pre-gap historical artifact:
  `/Users/semacair/dev/.external/freqtrade-stuff-evaluation/f6c38def0b2fe01d8d42e47740cdeab53511527b/x7-kraken-history/data/kraken/BTC_USDC-1h.feather`
  - 19,680 rows
  - `2024-01-01` through `2026-03-31 23:00 UTC`

Do not overwrite the current bagent artifact until the current file is backed up and hashes/metadata are recorded.

## Priority TODOs

### 1. Find how Kraken history disappeared

- [ ] Record bagent Kraken file path, size, mtime, SHA-256, row count, first/last timestamps, and daily coverage before repair.
- [ ] Inspect the Freqtrade updater command, systemd units/timers, cron jobs, and recent updater logs.
- [ ] Search for code that writes `BTC_USDC-1h.feather` with a short/incremental dataframe instead of merging with existing history.
- [ ] Compare the old 5,202-row artifact hash with the current 839-row artifact hash, if the old hash is available in logs or backups.
- [ ] Check whether an updater used a temporary file/rename that replaced the full history with a partial download.
- [ ] Preserve the forensic result in this file before changing the updater.

### 2. Back up and restore Kraken history safely

- [ ] Back up the current 839-row bagent file with timestamp and SHA-256. Do not delete it.
- [ ] Verify the local 5,202-row recovery candidate and calculate its SHA-256.
- [ ] If the local candidate is trusted, package it as a compressed archive with a checksum and transfer it to bagent.
- [ ] Unpack it into a staging path on bagent, never directly over the production file.
- [ ] Validate the staged file before installation.
- [ ] Atomically replace the production file only after validation passes.
- [ ] Recheck the installed file hash and metadata.
- [ ] Keep the original 839-row file as a forensic backup.

The Q2 gap is not to be filled by interpolation or cross-venue data. The restored file may still have the intended missing interval; the temporary regime exclusion remains until the Q2 history file arrives.

### 3. Repair the missing Kraken candles on 2026-07-06

- [ ] Identify exactly which two hourly timestamps are missing from `2026-07-06`.
- [ ] Prefer downloading those candles from the configured Kraken source/API through the normal Freqtrade mechanism.
- [ ] If necessary, fetch only the missing hours from the authoritative Kraken endpoint and record the request/source.
- [ ] Merge the two candles into the restored dataframe with deduplication, UTC normalization, sorting, and invariant checks.
- [ ] Confirm `2026-07-06` has exactly 24 rows.
- [ ] Keep the current UTC day partial if it is still in progress; do not fabricate candles.
- [ ] Record before/after hashes and the source of the repaired candles.

### 4. Validate both venue artifacts

- [ ] Required columns are exactly `date`, `open`, `high`, `low`, `close`, `volume`.
- [ ] Dates are timezone-aware UTC, sorted, and unique.
- [ ] OHLCV values are finite and non-negative where required.
- [ ] Every completed UTC day has exactly 24 hourly rows.
- [ ] The final partial UTC day is reported but not labeled.
- [ ] Missing intervals are listed explicitly.
- [ ] The Q2 Kraken gap is still explicitly identified and not silently hidden.
- [ ] The source file does not regress in first timestamp, row count, or completed-through date during future updates.

### 5. Prevent another history loss

- [ ] Change the updater so a short/incremental download is merged with the existing history rather than replacing it.
- [ ] Use a staging file and same-filesystem atomic rename.
- [ ] Add a lock so the labeler cannot read during replacement.
- [ ] Add a pre-replacement guard: reject any candidate that loses historical coverage or drops below the expected minimum history.
- [ ] Keep a timestamped previous artifact or backup before replacement.
- [ ] Emit a manifest/log with row count, first/last timestamps, complete-through date, missing days, and SHA-256.
- [ ] Make the weekly update job fail loudly when validation fails.
- [ ] Add monitoring/alerting for row-count regression, coverage regression, or an unexpectedly short artifact.

### 6. Re-run regime verification after repair

- [ ] Run the labeler for OKX and Kraken with freshness checks enabled.
- [ ] Confirm both venues produce current labels when source age is within seven days.
- [ ] Confirm Kraken labels before the Q2 gap remain stable.
- [ ] Confirm post-gap labels use valid data after the excluded interval.
- [ ] Re-run the historical replay tests for `2026-03-30`, `2026-05-15`, and `2026-07-01`.
- [ ] Verify the live `/a` message shows each venue's calculation-through date and age.
- [ ] Confirm comparison messages still do not contain duplicate macro sections.
- [ ] Run the full non-e2e test suite.
- [ ] Record final hashes and service/log status.

## Completion criteria

This repair is complete only when:

1. Kraken has its intended historical coverage restored.
2. The two missing `2026-07-06` candles are either restored and verified or documented as unavailable.
3. No updater can replace a full history with a shorter artifact without failing validation.
4. Both Feather files pass structural validation.
5. The regime labeler and historical replay tests pass.
6. Bagent services are active and recent logs contain no data-repair errors.
7. The unresolved Q2 gap remains explicit and is not imputed.
