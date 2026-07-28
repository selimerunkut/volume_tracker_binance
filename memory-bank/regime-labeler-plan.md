# Implementation Plan: Structural BTC Regime Labeler (+ CMC Altcoin Season Index)

Source contract: `cex_trader/tournament-intake/docs/agent-prompts/regime-labeler-integration-instructions.md`
Reference implementation (verified, zero deviations from spec):
`/Users/semacair/dev/.external/freqtrade-stuff-evaluation/f6c38def0b2fe01d8d42e47740cdeab53511527b/fixed-stake-spot-reality-check/structural-regime-analysis.py`

## 1. Declared contracts (decision: two separate instances, both displayed)

Two independent label series, one per venue. Never merged, never spliced. Both Freqtrade paper-trading profiles (OKX + Kraken) already maintain the source feeds.

**Instance A (build first): OKX**
- venue: `okx`, instrument: `BTC/USDC`, timeframe: `1h`, candles UTC.
- Contract ID: `fixed-stake-structural-regime-contract-v1-okx`.
- The reference golden fixture transfers directly (2026-07-19: direction `range_or_transition`, raw `structural_bull`, volatility `normal_or_low`, volume `expanded`) — full parity testing from day 1.
- The three historical exclusions (2024-06-25, 2025-08-20/21) exist **only inside the parity test fixture** to reproduce the reference run. The production service never skips dates: a live gap fails closed -> `unknown/stale` + state reset.

**Instance B (second): Kraken**
- venue: `kraken`, instrument: `BTC/USDC`, same rules.
- Contract ID: `fixed-stake-structural-regime-contract-v1-kraken`.
- Oracle procedure (avoid circular testing): the untouched reference is OKX-path-specific and cannot directly process Kraken gaps. Create a minimally patched, hash-pinned reference harness whose only changes are: Kraken input path, the separately adjudicated Kraken gap set (`2024-01-08`, `2024-01-20`, `2024-04-14`, `2024-07-03`, `2025-01-25`, `2025-08-28`, `2025-11-01`), and explicit selection of `date/open/high/low/close/volume` columns. Preserve the algorithm unchanged. Record the patch diff, patched-harness sha256, input sha256, and output fixture hash; freeze the expected output. Never regenerate expectations with the port under test. Kraken production runs fail closed on gaps. Temporary bagent exception: exclude the observed boundary interval `2026-04-02` through `2026-07-05` and the already-adjudicated one-day gap `2025-11-01` without imputation until the Q2 2026 history file is installed; reset state when complete post-gap data resumes, record `complete_with_temporary_gap_exclusion`, then remove the exception and rerun the Kraken oracle/parity checks. Details: `memory-bank/feather-data-operational-report.md`.

**Cross-venue observability**: log daily agreement between the two series (expect ~95%+). Persistent divergence = venue event or data problem; investigate, don't average.

## 2. Data flow

```
Freqtrade shared volumes (OKX + Kraken BTC_USDC-1h.feather)
  -> labeler reads the source files directly through a read-only mount
  -> regime_labeler.py runs per venue (pure pandas; validates freshness, fails closed)
     freshness: artifact must complete through the previous UTC day; older/changing -> unknown/stale
  -> SQLite regime_labels table (single source of truth; append-only except logged data repairs)
  -> strategy_advisor attaches per-venue btc_market_regime (reads latest rows from SQLite)
```

- Source paths via env vars `REGIME_SOURCE_FEATHER_OKX` / `REGIME_SOURCE_FEATHER_KRAKEN`, pointing to the shared Freqtrade volume. CEX_volume_tracker_B never writes these files.
- The labeler runs only after the Freqtrade downloader has completed. Before and after reading, verify file metadata/hash is stable; reject a file that changes during processing. For live use, the source may be up to seven days behind the current UTC date; the latest completed day is the explicit as-of date shown to users, and a partial current day is discarded. If older, calculate and persist valid historical labels anyway, but return `unknown/stale` for the live snapshot and current `/a` lookup.
- If direct reads are unsafe because Freqtrade writes in place or container permissions prevent a read-only mount, use a temporary-file copy followed by same-filesystem atomic rename. This is a fallback, not the default.
- Provenance lives as columns in `regime_labels` + timestamped logs. No manifest.json, no current_state.json cache (DRY: one source of truth). Approved deviation from the contract doc: no run_id/run table — labels are deterministic in (source_sha256, contract_sha256), so recomputation with identical inputs yields identical rows; overwrite happens only on data repair, where the new label is desired. Log every overwrite. Before production, record this no-manifest/no-run-table/repair-upsert deviation, approver, and date in `memory-bank/`.
- Venue/instrument enforcement comes from the pinned per-venue configuration and source path (`OKX`/`Kraken`, `BTC/USDC`, `1h`, UTC), not from OHLCV bytes, which contain no venue metadata. A wrong venue or instrument configuration is rejected before labeling; test 7 covers that configuration/path mismatch.

## 3. Files

| File | Change |
|---|---|
| `src/services/regime_labeler.py` | NEW. Verbatim port of the frozen algorithm (~150 lines, pure pandas), venue-parametrized. Functions: `load_validated_1h()`, `build_daily()`, `compute_labels()` (direction features, OLS slope/t-stat, 3-obs persistence state machine, rv28/rv75, volume ratio90), `current_snapshot()`. |
| `src/services/regime_service.py` | NEW. Orchestration per venue: run labeler on the feather, persist, expose canonical **`get_regimes_at(event_ts)`** (latest label per venue strictly before ts — used by live attach AND backfill); `get_current_regimes()` is a thin wrapper. Returns `{okx: {...}, kraken: {...}}`, each label or `unknown/stale`. Logs cross-venue agreement. |
| `src/services/db_service.py` | ADD table `regime_labels(venue TEXT, instrument TEXT, timeframe TEXT, date TEXT, direction, raw_direction, volatility, volume_tag, computed_at, contract_sha256, validation_result, source_rows, source_first_ts, source_last_ts, source_completed_through, source_sha256, PRIMARY KEY(venue, instrument, timeframe, date))`; add `PRAGMA busy_timeout=5000` for multi-process SQLite access. |
| `src/services/strategy_advisor.py` | In `analyze_and_suggest()`: attach `analysis_data["btc_market_regime"]` inside an **isolated try/except** — the function's broad `except` (line 77) must never let a regime/altseason failure abort analysis; on failure attach `unknown/stale`. Never block or change the action based on it (v1). |
| `telegram_bot_handler.py` | Two lines in analysis output, e.g. `BTC regime OKX: structural_bull · vol high · volume expanded` / `BTC regime Kraken: ...` (+`stale` marker if stale). |
| `telegram_bot_handler.py` `main()` | Register the regime job with the existing `application.job_queue.run_daily(...)` next to the current `run_repeating` jobs; run after the Freqtrade data-update job and no earlier than 00:05 UTC. |
| `pyproject.toml` | Add `pyarrow` for Feather reads and fixtures. |
| `tests/test_regime_labeler.py` | NEW. Acceptance tests below. |

## 4. Algorithm invariants (must not change)

- Discard current partial UTC day; labels only for completed days; event lookup uses label strictly before event time.
- Direction: 7/14/28d returns, SMA28, OLS on log(close) 28d with t-stat; bull/bear require ALL conditions; 3 consecutive raw observations to enter state, immediate exit; gap resets state.
- Volatility: rv28 = std of daily log returns (28d); rv75 = trailing 365d 75th percentile **of rv28 values**, `shift(1)`, `min_periods=60`; `high` iff rv28 >= rv75.
- Volume: `volume[t-1] / median(volume[t-90:t-1]) >= 1.5`; frozen warm-up `rolling(90, min_periods=30)` (reference line 82 — easy to miss, changes early labels).
- Validation: tz-aware UTC, sorted, unique, non-negative/finite, exactly 24 rows per completed day, no imputation. Any violation -> fail closed.
- Gap semantics: pre-gap rows stay immutable; emit **no** labels for gap days or any day after until complete days resume; current snapshot -> `unknown/stale`; direction state restarts at `range_or_transition` after a gap — never carried across a missing date.

## 5. Acceptance tests (from the contract doc)

1. OKX: exact parity vs the reference golden fixture. Kraken: parity vs the frozen oracle fixture produced once by the minimally patched, hash-pinned reference harness (see §1).
2. No lookahead: mutating a future candle cannot change an earlier label.
3. Strict-before-event lookup, incl. events inside an unfinished UTC day.
4. 3-day bull and 3-day bear persistence.
5. Immediate reset after a missing day.
6. Reject duplicate / unordered / tz-naive / incomplete input.
7. Reject a wrong venue/instrument/timeframe configuration before labeling; test source-path/contract mismatch. Feather content alone cannot prove venue because it has no venue metadata.
8. `>=`/`<=` boundary behavior (volatility, volume, t-stat) + volume warm-up rows (min_periods=30).
9. Final partial UTC day is not labeled.
10. Deterministic output + matching source/contract hashes.

## 6. Bootstrap & rollout

1. **OKX first**: one-time backfill from local `x7-okx-history/data/okx/BTC_USDC-1h.feather` (dev) / freqtrade OKX volume (server). Run parity tests against the reference golden fixture — must match exactly.
2. **Kraken second**: backfill from `x7-kraken-history/data/kraken/BTC_USDC-1h.feather`; generate and freeze the oracle with the minimally patched reference harness; eyeball last 30 daily labels vs the OKX series (expect high agreement, not equality).
3. Deploy: mount both Freqtrade data directories read-only into CEX_volume_tracker_B; schedule the labeler after the Freqtrade data-update job; verify via Telegram `/a BTC` showing both regime lines. Keep atomic copy as the documented fallback if direct reads prove unsafe.
4. Later (optional): regime cohorts in performance_tracker win-rate stats (Phase 5).

## 7. Add-on: CMC Altcoin Season Index (separate, orthogonal indicator)

- **Facts**: index = % of top-100 coins (ex-stablecoins/wrapped) outperforming BTC over trailing 90d. >=75 alt season, <25 BTC season. Official keyless endpoint confirmed working (2026-07-27): `GET https://pro-api.coinmarketcap.com/public-api/v1/altcoin-season-index/latest` -> `{"altcoin_index": 51, ...}`. Historical: `/public-api/v1/altcoin-season-index/historical`. Fallback with key: CoinGlass `/api/index/altcoin-season`.
- **No scraping/screenshots/OCR** — official JSON endpoint exists.
- Implementation: `src/services/altseason_service.py`, fetch 1x/day, cache JSON (macro_data_service pattern), attach `cmc_altseason_index` to `analysis_data` + Telegram line. Acceptance checks: parse a fixed JSON fixture, verify 51/100 parsing, and return `unknown/stale` on timeout, malformed data, or stale cache.
- Separate from regime labeler: it measures alt-vs-BTC breadth (cross-sectional), the labeler measures BTC's own structure. Orthogonal axes; keep as independent fields, do not merge into one score.

## 8. Auto-signal pipeline (deterministic, silent)

Goal: forward-test the deterministic strategy at scale and fill cohort stats. No LLM — a fixed measuring instrument.

- **Trigger**: `b_volume_alerts.py` `scan_exchange` after alert qualification (`:242–246`) and before `send_telegram_message` (`:284`). `src/services/volume_alerts.py` is formatting-only, not a trigger source.
- **On alert**: run deterministic strategy only (`deterministic_strategy.py`; skip the LLM fallback paths at `telegram_bot_handler.py:924/958`), save suggestion with `source='auto'`. No Telegram message per signal. Signal generation must be independent of Telegram send success.
- **Dedup (mandatory)**: skip if (symbol, exchange) has a PENDING `source='auto'` suggestion; post-resolution cooldown `AUTO_SIGNAL_COOLDOWN_HOURS` (default 12). Manual `/a` rows do not block auto rows. Reuses the alert_state cooldown pattern. Without this, 20 repeats of one price move pollute stats as "20 rows" with effective n=1.
- **Cap**: `MAX_OPEN_AUTO_SUGGESTIONS` (default 500).
- **Schema**: `suggestions` add indexed columns `source TEXT DEFAULT 'manual'` ('manual' | 'auto' | 'backfill'), `exchange_name`, `resolved_at`. Keeps manual `/a` stats unpolluted; dedup queries must not dig through analysis_data JSON.
- **Dedup mechanics**: enforce one PENDING `source='auto'` suggestion per (symbol, exchange) transactionally at insert time. Manual `/a` rows do not block auto rows; their stats remain separate. Set `PRAGMA busy_timeout=5000`, use an IMMEDIATE transaction, and add a partial unique index on `(symbol, exchange_name)` for PENDING auto rows as the hard guard. Cadence note: a WAIT stays PENDING ~24h, so with the 12h post-resolution cooldown the effective per-symbol cadence is >=36h for WAIT — intended.
- **Outcome semantics**: WAIT retains current close-at-window-end scoring (24h and ±2% threshold). LONG/SHORT use the canonical candle-based first-hit evaluator: fetch 1h klines since the last check per symbol with open suggestions, compare TP/SL against candle high/low, and expire at the window end. If one candle touches both levels, conservatively count SL first. `update_outcome()` stamps `resolved_at`.
- **performance_tracker**: replace 30-min spot sampling (misses intra-window TP/SL touches; `get_current_price` at lines 156/188) with that shared evaluator. Use per-symbol klines only for symbols with open suggestions; no ticker batching unless rate limits are actually measured. The same evaluator scores the backfill.
- Include WAIT signals; they resolve quickly under the existing 24h rules.
- **Acceptance checks**: repeated alert produces one auto row; manual and auto dedup behavior is explicit; cooldown and open-cap tests; simultaneous writers cannot create duplicate pending auto rows; WAIT close scoring and TP/SL tie-break tests; Telegram-send failure does not suppress auto-signal creation; resolved rows receive `resolved_at`.
- Files: `src/services/auto_signal_service.py` (new), hook in `b_volume_alerts.py`, `db_service.py` migration/locking, `performance_tracker.py` shared evaluator.
- Optional later: daily Telegram digest, `/cohorts` command. Not v1.

## 9. Historical backfill (instant cohort data)

`scripts/backfill_suggestions.py` — replay the deterministic strategy on historical 1h klines.

- Universe: top ~50 alert-universe symbols by volume; trailing 12 months; Kraken first.
- v1 simplification (documented): evaluate the strategy once per day per symbol at the 00:00 UTC close, instead of simulating the volume-alert trigger. Deterministic, honest, regime-joinable.
- **Evidentiary role (precise)**: the backfill measures the deterministic strategy on a **daily-close trigger** — a related but different population from the live alert-triggered pipeline (which fires intra-hour on forming-candle volume). It provides strategy-level cohort evidence; it does **not** validate the live pipeline. The live auto-signals are the forward test of the actual pipeline. Optional v2: replay the alert condition on completed 1h candles for a closer approximation.
- Outcomes scored by the shared canonical evaluator used by performance_tracker. Stamp regime label via `get_regimes_at(event_ts)` (strictly before event) + altseason (CMC `/historical`) by date.
- Store in separate table `backfill_suggestions` — never mix with live rows.
- Throttled paginated kline fetching; resumable; one-time run, repeatable per symbol.
- **Acceptance checks**: two runs over the same pinned input produce identical rows; interrupted runs resume without duplicates; `backfill_suggestions` never writes to or gets counted as live `suggestions`; known fixture produces known outcome counts.
- Output must carry caveats: past ≠ future, no fees/slippage, daily-trigger simplification.

## 10. Cohort analysis & decision rules

`scripts/cohort_report.py` — reads `suggestions` (live) and `backfill_suggestions`; prints win rate per cohort with n and ±2·√(p(1−p)/n) error bars.

- v1 granularity: direction (3 cohorts) and direction×vol×volume (12). No 36-way altseason split until n allows; altseason reported standalone (3 buckets).
- **Decision rule**: act only on large effects — ≥30-point win-rate gap with n≥20–30 per cohort. Red flags, not fine-tuning. Everything else: keep collecting. Do not treat a repair overwrite as a new observation.
- Compare like-for-like only: backfill cohorts (daily-close trigger) vs live cohorts (alert trigger) are different populations — report side by side but never use one to validate or tune the other.
- **Acceptance checks**: a small known fixture verifies cohort counts, win rates, missing labels, and error bars; report distinguishes live, backfill, and insufficient-sample cohorts.

## 11. Explicitly out of scope (v1)

- Gating/filtering LONG/SHORT suggestions on regime or altseason (contract doc forbids treating labels as entry rules).
- Per-altcoin regime labels.
- Using labels to change deterministic scoring rules.
- Telegram message per auto-signal (silent storage only).
- Simulating the exact volume-alert trigger in the backfill (daily-evaluation simplification instead).
