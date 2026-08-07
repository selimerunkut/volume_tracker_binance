# Live Regime Data TODOs

Owner: `CEX_volume_tracker_B`

## Incident

On 2026-08-07, Telegram showed only OKX and Kraken. Hyperliquid was absent because the signal bot still had a two-venue allow-list. Kraken showed `unknown/stale` because the deployed bot was using an old code/database state and the configured canonical Kraken artifact ended at `2026-07-30 14:00 UTC` (last complete day: `2026-07-29`), not because Telegram was hiding a fresh label.

The current Hyperliquid artifact exists at:

```text
/opt/cex_trader/user_data/research/hyperliquid-spot/BTC_USDC-1h.feather
```

The current canonical Kraken artifact remains owned and updated by `cex_trader`:

```text
/opt/cex_trader/user_data/data/kraken/BTC_USDC-1h.feather
```

This bot must consume those files only. It must not repair them.

## Completed in this change

- [x] Add Hyperliquid to the independent regime venue registry.
- [x] Add the Hyperliquid source environment variable and systemd path.
- [x] Render OKX, Hyperliquid, and Kraken dynamically in Telegram.
- [x] Make strategy fallback entries dynamic for all configured venues.
- [x] Refresh regime labels every 15 minutes instead of once per day.
- [x] Add tests for Hyperliquid configuration and Telegram output.

## Remaining operational TODOs

- [x] Deploy the exact signal-bot commit to bagent.
- [x] Confirm the running systemd unit has all three `REGIME_SOURCE_FEATHER_*` variables.
- [x] Confirm the first refresh logs successful Hyperliquid calculation through `2026-08-06`.
- [ ] Confirm Kraken becomes `ok` automatically after `cex_trader` updates the canonical Kraken file through a complete recent day.
- [ ] If Kraken remains stale, report the exact validation error and source completion date; do not substitute a staging or repaired file from this repository.
- [ ] Keep a live-data monitoring check for source age and protected-window gaps.
- [ ] Add a deployment smoke test that checks every configured venue is either `ok` or explicitly `unknown/stale` with a reason.
- [ ] Recheck Telegram output after one 15-minute refresh interval.
