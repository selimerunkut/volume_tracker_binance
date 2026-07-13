# Liquidity-Aware Volume Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Keep the existing volume-alert format, filter alerts by configurable USD-equivalent volume, and show whether market entries of $3,000, $5,000, or $10,000 are likely to move the live order book.

**Architecture:** Use a cheap two-stage pipeline. Normalize candle quote volume and apply the absolute-volume, baseline, and surge gates first; fetch the 24-hour ticker and order book only for a qualified alert. Store one global minimum-volume setting in the existing SQLite `settings` table and expose only a simple Telegram query/set command.

**Tech Stack:** Python, pandas, requests, existing exchange adapters, existing SQLite settings helpers, python-telegram-bot, pytest.

## Global Constraints

- Default threshold: `$50,000` of current/forming 1-hour USD-equivalent quote volume.
- Telegram control surface: `/volume_min` reads the threshold; `/volume_min 75000` changes it.
- Only the configured `TELEGRAM_CHAT_ID` may use this global-setting command.
- Accept positive whole-dollar values only. Do not add aliases such as `50k`, a reset command, a settings menu, per-user values, or configurable liquidity bands.
- Read the threshold once at the start of each scan and pass it into exchange workers. A Telegram update applies on the next scan.
- Preserve the existing header, alert level, price line, URLs, restrict button, and analyze button.
- Keep base `volume` for existing consumers and add `quote_volume`; do not silently redefine the existing field.
- Add no dependency and place no trades.

## Research-Based Conversion Matrix

This plan applies to all exchanges currently registered by the signal tool. It does not add Hyperliquid.

| Exchange | Scanned quote assets | Conversion markets verified in the live public catalog on 2026-07-13 |
| --- | --- | --- |
| Binance | `USDC`, `BTC` | `BTCUSDT`, then `BTCUSDC`, both `TRADING` via `/api/v3/exchangeInfo`. |
| Kraken | `USD`, `BTC` | `XBTUSD`, then `XBTUSDT`, both `online` via `/0/public/AssetPairs`; Kraken internal codes are normalized from `XXBT`/`ZUSD`. |
| OKX | `USDC`, `EUR`, `USD`, `BTC` | `BTC-USDT`, then `BTC-USDC`; `USDT-EUR`, then `USDC-EUR` inverse markets via `/api/v5/public/instruments`. |

Conversion is exchange-specific behind the shared `quote_to_usd_rate(quote_asset)` interface. Direct `ASSET-STABLE` markets use a conservative bid; inverse `STABLE-ASSET` markets use `1 / ask`. Binance bid/ask comes from `bookTicker`; Kraken uses ticker `b`/`a`; OKX uses ticker bid/ask. Stable quotes retain the existing 1:1 USD assumption. The scanner caches one rate per quote asset for each exchange scan, including failed lookups, and fails closed if no exact active conversion market is available.

For OKX SPOT 24-hour ticker enrichment, read `volCcy24h` (quote-currency volume) from `/api/v5/market/ticker`. Keep `volCcyQuote` for candle quote volume only; these fields are not interchangeable.

Primary API references: [Binance exchange information](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/general-endpoints#exchange-information), [Kraken tradable asset pairs](https://docs.kraken.com/api/docs/rest-api/get-tradable-asset-pairs/), and [OKX public instruments](https://www.okx.com/docs-v5/en/#public-data-rest-api-get-instruments).

---

## User-Visible Contract

The signal remains familiar, with explicit units and a short liquidity section:

```text
🚨 *Volume Alert - OKX - EXAMPLE-USDC* 🚨
📊 Current 1h Quote Volume: $62,400
📈 Previous 6h Mean Quote Volume: $3,900
🕐 Previous Completed 1h: $7,200
🕒 Previous Completed 2h: $11,900
🕓 Previous Completed 4h: $19,800
💹 Current 1h candle Prices, Open: 0.07237000, Close: 0.07240000
🔥 Alert Level: *1500%+*
💧 24h Quote Volume: $1,840,000
📚 Est. buy slippage: $3k 0.08% | $5k 0.14% | $10k 0.36%
⚠️ Liquidity: MODERATE — $10k entry may move the price materially
🔗 https://www.tradingview.com/...
🔗 https://www.okx.com/trade-spot/...
```

- If all sizes are low risk, render `✅ Liquidity: GOOD`.
- If depth is unavailable, send the otherwise-valid surge alert with `⚠️ Liquidity estimate unavailable`.
- Never describe missing depth as safe.
- The supplied `2Z-USDC` example is filtered: `4,786 × ~$0.0724 = ~$346`, below the default threshold.
- The supplied `AAVE-USD` example is filtered because its current quote volume is below the threshold and its six-hour baseline has insufficient non-zero activity.

## Shared Interfaces

Add these constants and pure validation helper to `src/services/volume_alerts.py` so the scanner and Telegram handler do not duplicate setting rules:

```python
VOLUME_MIN_SETTING_KEY = "volume_alert_min_current_quote_usd"
DEFAULT_VOLUME_MIN_QUOTE_USD = 50_000

def parse_volume_min_quote_usd(value):
    """Return a positive integer number of USD, or raise ValueError."""
```

Exchange candle frames retain OHLC and base `volume` and add numeric `quote_volume`:

- Binance: native kline `quote_asset_volume`.
- OKX: native `volCcyQuote`.
- Kraken: `volume * vwap`, falling back to `volume * close` only when VWAP is absent.

Order-book adapters return:

```python
{"bids": [(price, base_quantity), ...], "asks": [(price, base_quantity), ...]}
```

Asks are cheapest-first and bids highest-first. The simulator consumes asks only because this feature estimates entries, not exits.

## Acceptance Criteria

1. The threshold defaults to `$50,000`, persists through the existing settings table, and can be read or changed through `/volume_min`.
2. Invalid values and unauthorized chats cannot change the setting.
3. The scanner reads the threshold once per run; sub-threshold candidates make no 24-hour ticker, order-book, or Telegram calls.
4. Surge calculations use USD-equivalent quote volume on Binance, Kraken, and OKX, require at least three non-zero candles in the six-candle baseline, and cannot trigger from an exact-zero mean.
5. Existing percentage levels (`500%+`, `700%+`, `1000%+`, `1500%+`) and the positive-price-candle condition remain unchanged.
6. Qualified alerts retain the existing structure and add 24-hour quote volume plus estimated buy slippage for `$3k`, `$5k`, and `$10k`.
7. Empty, malformed, or insufficient depth cannot crash scanning and is never labeled safe.
8. Base-volume behavior used by strategy analysis remains unchanged.
9. Focused tests, the full non-live suite, a dry run, and opt-in live API checks pass or report a concrete external blocker.

## Task 1: Normalize Candle Quote Volume

**Files:**

- Modify: `src/exchanges/base.py`
- Modify: `src/exchanges/binance.py`
- Modify: `src/exchanges/kraken.py`
- Modify: `src/exchanges/okx.py`
- Test: `tests/test_exchange_adapters.py`
- Test: `tests/test_live_exchange_e2e.py`

- [ ] Add failing fixture assertions for exact `quote_volume` mappings on all three exchanges and for preserved numeric base `volume`.
- [ ] Run `uv run pytest -q tests/test_exchange_adapters.py`; expect failures for missing `quote_volume`.
- [ ] Add only the new `quote_volume` column and document it in `ExchangeAdapter`; do not add a second candle-completion abstraction.
- [ ] Preserve OKX chronological order and all existing OHLC fields.
- [ ] Run `uv run pytest -q tests/test_exchange_adapters.py tests/test_market_data_service_exchange.py`; expect passes.

## Task 2: Convert Native Quote Values to USD

**Files:**

- Create: `src/services/quote_value_service.py`
- Test: `tests/test_quote_value_service.py`
- Modify: `b_volume_alerts.py`

**Interface:**

```python
def to_usd_quote_value(native_quote_value, quote_asset, usd_rate):
    """Pure multiplication with positive finite-number validation."""
```

- [ ] Test stable quotes (`USD`, `USDC`, `USDT`) at rate `1.0`, BTC/EUR conversion, invalid inputs, missing rates, direct-bid and inverse-`1 / ask` math, and one cached conversion lookup per exchange/quote asset per scan.
- [ ] Run `uv run pytest -q tests/test_quote_value_service.py`; expect failure before implementation.
- [ ] Keep `ExchangeSymbol.quote_asset` in the scan input instead of reducing pairs to symbol strings.
- [ ] Add one shared direct/inverse bid/ask conversion helper with finite-positive validation.
- [ ] Implement Binance market discovery from `exchangeInfo`; require exact base/quote matching and `TRADING` status; prefer `ASSETUSDT`, then `ASSETUSDC`, then `ASSETUSD`, with inverse fallbacks; fetch bid/ask from `bookTicker`.
- [ ] Implement Kraken market discovery from `AssetPairs`, require exact normalized base/quote and `online` status, including `XBT`/`XXBT` and `ZUSD` normalization; treat `XBTUSDT` as a catalog-discovered fallback and use ticker `b`/`a`.
- [ ] Implement OKX SPOT market discovery from a cached `public/instruments` catalog; require `instType=SPOT`, exact base/quote, and `state=live`; support BTC direct markets and EUR inverse markets without routing conversion symbols through the scanned-quote allowlist.
- [ ] Cache one resolved conversion rate per exchange and quote asset for the scan, including `None` failures.
- [ ] Log and skip a candidate when its required conversion rate is unavailable; never compare native BTC/EUR values with a dollar threshold.
- [ ] Run `uv run pytest -q tests/test_quote_value_service.py tests/test_b_volume_alerts_exchange_scanning.py`; expect passes.

## Task 3: Apply the Configurable Volume and Baseline Gates

**Files:**

- Modify: `src/services/volume_alerts.py`
- Modify: `b_volume_alerts.py`
- Modify: `alert_levels_tg.py`
- Test: `tests/test_alert_levels_tg.py`
- Test: `tests/test_b_volume_alerts_exchange_scanning.py`

- [ ] Test the two supplied failure modes, a valid over-threshold surge, fewer than three non-zero baseline candles, an exact-zero mean, and invalid stored settings.
- [ ] Run the two focused test files and confirm the new cases fail.
- [ ] Implement `parse_volume_min_quote_usd`; accept integer strings or integers greater than zero and reject booleans, decimals, zero, negatives, and non-numeric values.
- [ ] In `run_script`, call `get_setting(VOLUME_MIN_SETTING_KEY, DEFAULT_VOLUME_MIN_QUOTE_USD)` once. On invalid stored data, log and use the default without rewriting the database.
- [ ] Pass the parsed threshold to `scan_exchange`; apply it before percentage evaluation and before any expensive endpoint call.
- [ ] Calculate the current, previous mean, previous 1h, previous 2h, and previous 4h values from USD-equivalent `quote_volume`.
- [ ] Keep the existing four surge levels and positive-candle condition.
- [ ] Run `uv run pytest -q tests/test_alert_levels_tg.py tests/test_b_volume_alerts_exchange_scanning.py`; expect passes.

## Task 4: Add the Telegram Threshold Command

**Files:**

- Modify: `telegram_bot_handler.py`
- Modify: `src/services/volume_alerts.py`
- Test: `tests/test_volume_alert_settings.py`

**Command behavior:**

```text
/volume_min
Minimum current 1h quote volume: $50,000

/volume_min 75000
Minimum current 1h quote volume updated to $75,000. Effective on the next scan.
```

- [ ] Test query-without-write, valid persistence through `set_setting`, invalid input without write, extra arguments without write, and rejection when `effective_chat.id` differs from `TELEGRAM_CHAT_ID`.
- [ ] Run `uv run pytest -q tests/test_volume_alert_settings.py`; expect failure because the command is not registered.
- [ ] Implement one handler using the shared key, default, and parser; do not add a menu, callbacks, aliases, or reset path.
- [ ] Register `CommandHandler("volume_min", volume_min_command)` and add the command to `/help`.
- [ ] Run `uv run pytest -q tests/test_volume_alert_settings.py`; expect passes.

## Task 5: Preserve and Clarify the Alert Format

**Files:**

- Modify: `src/services/volume_alerts.py`
- Modify: `telegram_alerts.py` only if the existing payload transport requires it
- Test: `tests/test_volume_alerts_formatter.py`
- Test: `tests/test_telegram_alert_exchange_filter.py`

- [ ] Add exact formatter assertions for the existing header, price line, level, links, buttons, and the new dollar-denominated labels.
- [ ] Run the focused formatter tests and confirm failure before changing rendering.
- [ ] Replace ambiguous volume labels with the labels in the user-visible contract and format values with `$` plus thousands separators.
- [ ] Preserve internal compatibility keys only where an existing caller still consumes them.
- [ ] Run `uv run pytest -q tests/test_volume_alerts_formatter.py tests/test_telegram_alert_exchange_filter.py`; expect passes.

## Task 6: Add 24-Hour Volume and Entry-Impact Analysis

**Files:**

- Modify: `src/exchanges/base.py`
- Modify: `src/exchanges/binance.py`
- Modify: `src/exchanges/kraken.py`
- Modify: `src/exchanges/okx.py`
- Create: `src/services/liquidity_analysis.py`
- Test: `tests/test_exchange_adapters.py`
- Test: `tests/test_liquidity_analysis.py`
- Test: `tests/test_live_exchange_e2e.py`

**Simulator interface:**

```python
def estimate_market_buy(asks, quote_notional):
    """Return VWAP, slippage_pct, filled_notional, consumed_levels, and insufficient_depth."""
```

- [ ] Test normalized/sorted books, exchange errors, single- and multi-level fills, partial fills, empty/malformed books, and notionals `3000`, `5000`, and `10000`.
- [ ] Run adapter and liquidity tests; expect failures for missing interfaces.
- [ ] Implement public `fetch_order_book` and `fetch_24h_quote_volume` methods on each adapter using existing request/time-out patterns.
- [ ] Implement one ask-side traversal. Do not add sell/exit simulation, fee modeling, authenticated endpoints, or historical depth storage.
- [ ] Calculate slippage against the best ask. Keep raw metrics and use fixed product heuristics for display bands: `GOOD < 0.25%`, `MODERATE < 0.75%`, `HIGH < 1.50%`, `SEVERE >= 1.50%` or insufficient depth. Document these bands as heuristics, not exchange or research guarantees.
- [ ] Run `uv run pytest -q tests/test_exchange_adapters.py tests/test_liquidity_analysis.py`; expect passes.

## Task 7: Enrich Qualified Alerts Only

**Files:**

- Modify: `b_volume_alerts.py`
- Modify: `src/services/volume_alerts.py`
- Test: `tests/test_b_volume_alerts_exchange_scanning.py`
- Test: `tests/test_volume_alerts_formatter.py`

- [ ] Add mock call-count tests proving that sub-threshold, weak-baseline, and non-surge candidates make zero ticker/depth calls.
- [ ] Add tests proving one qualified candidate makes one 24-hour call and one depth call, then renders all three entry sizes.
- [ ] Fetch enrichment only after all cheap gates pass and before duplicate-alert state is written.
- [ ] If ticker or depth fails, keep the valid surge alert and render the specific unavailable field without changing cooldown behavior.
- [ ] Run `uv run pytest -q tests/test_b_volume_alerts_exchange_scanning.py tests/test_volume_alerts_formatter.py`; expect passes.

## Task 8: Document and Verify

**Files:**

- Modify: `README.md`

- [ ] Document `/volume_min`, its default, whole-dollar validation, next-scan timing, and examples.
- [ ] Document that current 1-hour volume is forming, stablecoins are treated as `$1`, and order-book estimates exclude fees and can change before execution.
- [ ] Run focused tests:

```bash
uv run pytest -q \
  tests/test_exchange_adapters.py \
  tests/test_quote_value_service.py \
  tests/test_alert_levels_tg.py \
  tests/test_b_volume_alerts_exchange_scanning.py \
  tests/test_volume_alert_settings.py \
  tests/test_volume_alerts_formatter.py \
  tests/test_liquidity_analysis.py
```

- [ ] Run `uv run pytest -q`.
- [ ] Run `uv run python b_volume_alerts.py --dry-run` and confirm no Telegram message is sent.
- [ ] Run `RUN_LIVE_API_E2E=1 uv run pytest -q -m e2e tests/test_live_exchange_e2e.py` and report exchange/network blockers explicitly.
- [ ] Run `git diff --check` and inspect the scoped diff before reporting completion.

## Deliberate Non-Goals (YAGNI)

- No per-chat or per-exchange volume thresholds.
- No Telegram settings wizard, inline keyboard, command aliases, or reset command.
- No configurable `$3k/$5k/$10k` trade sizes or risk bands.
- No sell-side/exit simulation, fees, authenticated trading, market orders, depth history, or predictive price-impact model.
- No stablecoin depeg feed; USD, USDC, and USDT are treated as `$1` for this alert filter, with the accepted risk that this approximation can be wrong during a depeg.

## Completion Evidence

- The two supplied low-quality alerts are rejected by regression tests.
- Telegram command tests prove read, valid update, invalid rejection, and chat authorization.
- Mock call counts prove expensive liquidity requests happen only after all alert gates pass.
- Deterministic order-book fixtures prove `$3k`, `$5k`, and `$10k` slippage arithmetic.
- Formatter assertions prove the existing signal structure remains recognizable.
- Full non-live tests pass; live checks pass or have a documented external blocker.
