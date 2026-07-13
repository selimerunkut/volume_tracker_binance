# EUR Volume Conversion Design

## Goal

Evaluate OKX EUR-quoted volume alerts against the existing USD threshold instead of dropping every EUR pair when `EUR-USDT` is unavailable.

## Scope

- Convert EUR quote volume to USD before applying `volume_alert_min_current_quote_usd`.
- Reuse one cached EUR/USD rate across a scan run.
- Preserve the current fail-closed behavior when no trustworthy rate is available.
- Do not add a dependency, external FX provider, Telegram FX command, or persistent FX configuration in this change.

## Evidence

- The OKX API v5 public-instruments documentation defines `instId`, `baseCcy`, `quoteCcy`, and `state` for spot instruments and allows the live catalog to be discovered without authentication.
- A live query to the same EEA endpoint used by this project on 2026-07-13 returned `USDT-EUR` and `USDC-EUR` as live spot instruments. It returned no live direct `EUR-USD`, `EUR-USDT`, or `EUR-USDC` instrument.
- Live ticker snapshots returned approximately `0.8744 EUR/USDT` and `0.8751 EUR/USDC`. Therefore one EUR was approximately `1 / 0.8744 = 1.1436` USDT or `1 / 0.8751 = 1.1427` USDC at that time.
- The current implementation only asks OKX for `EUR-USDT`, which is not a live instrument in that catalog. This directly explains the `no USD conversion for EUR` skips.
- OKX documentation: <https://www.okx.com/docs-v5/en/#public-data-rest-api-get-instruments>

## Design

`OKXExchange.quote_to_usd_rate()` will discover an exchange-native conversion rate from the live spot instruments. For EUR, it will try the currently available inverse instruments in deterministic order: `USDT-EUR`, then `USDC-EUR`. The conversion uses `1 / askPx`, because `askPx` is the EUR amount required to buy one unit of the stablecoin and is conservative for an alert-entry liquidity threshold.

The scanner will cache the resolved rate by quote asset for the duration of one exchange scan so hundreds of EUR symbols do not trigger hundreds of identical ticker requests. This scan-local cache needs no expiry mechanism and cannot become stale across scans. Stable quote assets retain the existing `1.0` behavior.

If every candidate is missing, invalid, non-finite, or non-positive, the adapter returns `None`. The scanner keeps its existing fail-closed behavior and logs that USD conversion is unavailable; it does not guess that EUR equals USD.

## Data Flow

1. The scanner requests the quote-to-USD rate for the first EUR symbol and stores it in a scan-local cache.
2. The adapter probes `USDT-EUR`, followed by `USDC-EUR`, and returns the inverse ask price from the first valid ticker.
3. Native EUR candle volumes and 24-hour quote volume are multiplied by that rate.
4. The existing `$50,000` filter is applied to the USD-equivalent current candle volume.
5. Any resulting alert continues to show USD-denominated volume and liquidity fields.

## Validation

- A valid `USDT-EUR` ask price is inverted.
- `USDC-EUR` is used when `USDT-EUR` is unavailable or invalid.
- Invalid candidate prices are ignored.
- All unavailable candidates return `None` and preserve fail-closed filtering.
- Repeated conversions use the cache and do not repeat ticker calls.
- Existing adapter and volume-alert tests remain green.

## Deferred Options

An external reference-rate provider or manually configured fallback can be added later if OKX removes both usable EUR cross-pairs. It is intentionally excluded while the exchange itself provides sufficient live conversion markets.
