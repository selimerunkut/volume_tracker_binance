# Feather Data Operational Report

Date: 2026-07-27 UTC
Audience: the agent responsible for Freqtrade Feather-data maintenance

## Objective

Keep the two source artifacts readable by `CEX_volume_tracker_B` on bagent. The regime labeler reads them through a read-only path; this repository never writes the Feather files.

Configured bagent paths:

- OKX: `/opt/cex_trader/user_data/profiles/okx-spot/data/okx/BTC_USDC-1h.feather`
- Kraken: `/opt/cex_trader/user_data/data/kraken/BTC_USDC-1h.feather`

The service reads these paths from `REGIME_SOURCE_FEATHER_OKX` and `REGIME_SOURCE_FEATHER_KRAKEN`.

## Observed state on bagent

At the last inspection:

| Venue | Rows | First timestamp | Last timestamp | Problem |
|---|---:|---|---|---|
| OKX | 4,341 | 2026-01-21 00:00 UTC | 2026-07-20 20:00 UTC | Last UTC day is partial; the latest completed day is older than the current freshness window. |
| Kraken | 5,202 | 2025-10-01 00:00 UTC | 2026-07-06 21:00 UTC | Incomplete 2025-11-01; one candle on 2026-04-02; no daily rows from 2026-04-03 through the first post-gap data; final 2026-07-06 day is partial. |

The Kraken `kraken-pre-full-sync-20260719` artifact also exists, but it is an older snapshot and is not silently substituted for the configured source.

## Required weekly update contract

Run the update after the Freqtrade data downloader has completed, then verify the artifact before the labeler runs.

For each venue, the updater must:

1. Update or replace the Feather artifact atomically on the same filesystem.
2. Preserve the exact columns: `date`, `open`, `high`, `low`, `close`, `volume`.
3. Store UTC-aware timestamps, sorted and unique.
4. Include all 24 hourly rows for every completed UTC day that it claims to provide.
5. It may leave the current UTC day partial. The labeler discards that day.
6. Record row count, first/last timestamp, SHA-256, and incomplete/missing-day diagnostics in its job log.
7. Not mutate the file while the labeler is reading it.
8. Keep the source at least within the accepted freshness window: one week old is acceptable; older artifacts fail closed.

The labeler does **not** need to wait for today's final hourly candle. It uses the latest completed UTC day. A weekly update is therefore compatible with the causal algorithm, provided the source is no more than seven days behind and the displayed label includes its `date`/as-of timestamp.

## Kraken temporary exception

The currently missing interval beginning **2026-04-03** is intentionally excluded for now. No candles are imputed and no label is generated for the excluded interval. The regime state resets when complete post-gap data resumes.

The deployed temporary exclusion covers the observed boundary interval `2026-04-02` through `2026-07-05`, because 2026-04-02 has only one row and 2026-07-06 is currently partial. This prevents a one-row boundary artifact from being treated as a valid day.

This is temporary. When the Q2 2026 Kraken history file is available:

- merge/replace the source through the missing interval;
- rerun row-count and continuity checks;
- remove the temporary exclusion from `src/services/regime_service.py`;
- rerun the Kraken oracle/parity tests;
- verify that pre-gap labels remain unchanged and post-gap labels begin only after a complete day.

Do not fill the gap with interpolation or exchange data from another venue.

## Current upstream blocker

The bagent OKX history refresh currently fails before download because the cex-trader service cannot create its UV cache in its read-only service environment. Its rendered Freqtrade configuration also reports a Telegram `enabled` schema error. The data-maintenance agent should fix those upstream issues rather than weakening this labeler's validation.

## Acceptance evidence to return each week

Return one report containing:

- update timestamp and source path;
- SHA-256 before/after;
- row count;
- first timestamp and last timestamp;
- latest completed UTC day;
- partial final-day row count, if any;
- duplicate and out-of-order counts;
- missing/incomplete UTC dates;
- whether the seven-day freshness contract passes;
- whether the update used an atomic replacement;
- any Kraken temporary-gap status.

The CEX labeler should then produce either:

- a per-venue label with an explicit `date`/as-of timestamp; or
- `unknown/stale` with the validation reason.

Never hide stale, changing, or incomplete source data behind a successful-looking regime label.
