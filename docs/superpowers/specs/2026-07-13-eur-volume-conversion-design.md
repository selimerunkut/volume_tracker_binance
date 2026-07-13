# Universal Quote-to-USD Volume Conversion Design

## Goal

Evaluate quote-denominated volume against the existing USD alert threshold for every currently supported exchange: Binance, Kraken, and OKX.

## Scope

- Convert non-stable quote volume to USD before applying `volume_alert_min_current_quote_usd`.
- Keep stable quotes (`USD`, `USDC`, `USDT`) at the existing 1:1 USD assumption.
- Give each exchange adapter responsibility for discovering its own valid conversion markets and symbol syntax.
- Cache one resolved rate per quote asset for the duration of an exchange scan.
- Preserve fail-closed behavior when no trustworthy conversion market exists.
- Do not add Hyperliquid, external FX providers, new dependencies, Telegram FX commands, or persistent FX configuration.

## Research Evidence

The repository currently registers only Binance, Kraken, and OKX in `src/exchanges/registry.py`. The active volume scan quote assets are:

| Exchange | Current scan quotes | Live conversion evidence checked 2026-07-13 |
| --- | --- | --- |
| Binance | `USDC`, `BTC` | `BTCUSDT` and `BTCUSDC` are `TRADING` in `/api/v3/exchangeInfo`. |
| Kraken | `USD`, `BTC` | `XBTUSD` (`altname: XBTUSD`) and `XBTUSDT` are `online` in `/0/public/AssetPairs`. Kraken uses internal asset codes such as `XXBT` and `ZUSD`, while `altname`/`wsname` expose tradable pair names. |
| OKX | `USDC`, `EUR`, `USD`, `BTC` | Live SPOT instruments include `BTC-USDT`, `BTC-USDC`, `USDT-EUR`, and `USDC-EUR`. No direct `EUR-USDT` instrument was returned. |

The current adapters already expose `quote_to_usd_rate`, but each assumes a single hardcoded pair. That is why OKX asks for nonexistent `EUR-USDT`, and why OKX's `BTC-USDT` probe is rejected by its current symbol normalizer. Binance and Kraken happen to work for BTC today, but they have no fallback or catalog validation.

Official references:

- Binance Spot exchange information: <https://developers.binance.com/docs/binance-spot-api-docs/rest-api/general-endpoints#exchange-information>
- Kraken tradable asset pairs: <https://docs.kraken.com/api/docs/rest-api/get-tradable-asset-pairs/>
- Kraken ticker information: <https://docs.kraken.com/api/docs/rest-api/get-ticker-information/>
- OKX public instruments: <https://www.okx.com/docs-v5/en/#public-data-rest-api-get-instruments>

For OKX SPOT 24-hour ticker volume, use the ticker response's `volCcy24h` field,
which is the quote-currency volume. `volCcyQuote` is the quote-volume field used
by OKX candle responses and must not be substituted for the 24-hour ticker
field. Add a regression fixture for this distinction.

## Shared Contract

Keep `ExchangeAdapter.quote_to_usd_rate(quote_asset)` as the scanner-facing interface, returning a positive finite USD rate or `None`.

The scanner maintains a local `{quote_asset: rate}` cache per exchange scan. It
resolves a quote asset once, reuses that value for all candles and 24-hour
volume enrichment, and caches failures as `None` for the remainder of the scan
so an unavailable conversion cannot cause one request per symbol. It logs the
exchange, quote asset, and attempted conversion markets when resolution fails.

The conversion helper applies the same market-side rules everywhere:

- Direct market `ASSET-STABLE`: use the bid price as a conservative value for selling the quote asset.
- Inverse market `STABLE-ASSET`: use `1 / ask price` as a conservative value for buying the stablecoin with the quote asset.
- Ignore missing, non-numeric, non-finite, or non-positive prices.
- Stable quote assets retain the current 1:1 assumption.

## Exchange Adapter Resolution

Adapters discover live markets using their existing public instrument metadata,
then query a ticker only for the best candidate. Candidate preference is
deterministic and favors USDT, then USDC, then USD. Discovery must match the
exact base/quote pair and an active status (`TRADING` on Binance, `online` on
Kraken, and `state=live` plus `instType=SPOT` on OKX); constructing a symbol
string without catalog validation is not sufficient.

- Binance: discover direct `ASSETUSDT`, `ASSETUSDC`, or `ASSETUSD`, then inverse equivalents if needed. Use `exchangeInfo` status to reject non-trading symbols. Fetch valuation sides from `bookTicker` (`bidPrice`/`askPrice`), not from instrument metadata.
- Kraken: discover direct or inverse pairs from `AssetPairs`, using `altname`/`wsname` and Kraken's asset-code mappings (`XBT`/`XXBT`, `ZUSD`). Treat `XBTUSDT` as catalog-driven fallback rather than a guaranteed market. Fetch valuation sides from ticker `b` (bid) and `a` (ask); do not use last trade `c` for conversion.
- OKX: discover live SPOT instruments from `public/instruments`. For BTC, prefer `BTC-USDT`, then `BTC-USDC`; for EUR, use `USDT-EUR`, then `USDC-EUR`, inverting the ask price. Fetch bid/ask from the ticker response and do not route conversion instruments through the current `allowed_quote_assets` list. Cache the instrument catalog for the scan.

This keeps exchange-specific API details inside adapters while the scanner and threshold logic remain exchange-agnostic.

## Data Flow

1. The scanner reads the configured USD threshold once.
2. For each exchange, it resolves and caches conversion rates by quote asset.
3. Native candle quote volume is converted to USD using the cached rate.
4. The existing baseline and minimum-current-volume gates run on USD values.
5. The same rate converts 24-hour quote volume for alert enrichment.
6. If conversion is unavailable, the pair is skipped with a precise diagnostic; no unconverted alert is emitted.

## Validation

- Unit-test the shared direct/inverse bid/ask math.
- Test Binance discovery and BTC fallback behavior.
- Test Kraken asset-code normalization and BTC direct/fallback behavior.
- Test OKX BTC direct and EUR inverse behavior, including the current live pair directions.
- Test OKX `volCcy24h` ticker parsing separately from candle `volCcyQuote` parsing.
- Test invalid ticker data and unavailable markets remain fail-closed.
- Test exact market/status matching, malformed catalogs, and no-candidate behavior.
- Test scan-local caching prevents repeated conversion ticker requests and caches failed lookups.
- Test direct conversion uses bid, inverse conversion uses `1 / ask`, and invalid bid/ask data remains fail-closed.
- Run the existing adapter, volume-alert, and live-public-API tests where network access is available.

## Deferred

If a future exchange exposes a quote asset with no stablecoin or USD market, add that adapter's documented conversion route when the exchange is actually enabled. Do not silently use `quote == USD` or an external fallback without explicit evidence and a displayed estimate warning. Treat the stablecoin-at-`$1` rule as an accepted approximation; it can misstate USD value during a depeg, which is outside this scope.
