# EUR Volume Conversion Design

## Goal

Evaluate OKX EUR-quoted volume alerts against the existing USD threshold instead of dropping every EUR pair when `EUR-USDT` is unavailable.

## Scope

- Convert EUR quote volume to USD before applying `volume_alert_min_current_quote_usd`.
- Reuse one cached EUR/USD rate across a scan run.
- Preserve the current fail-closed behavior when no trustworthy rate is available.
- Do not add a dependency, external FX provider, Telegram FX command, or persistent FX configuration in this change.

## Design

`OKXExchange.quote_to_usd_rate()` will discover an exchange-native conversion rate from a small ordered list of direct and inverse spot instruments. Direct candidates are `EUR-USDT`, `EUR-USDC`, and `EUR-USD`; inverse candidates are `USDT-EUR`, `USDC-EUR`, and `USD-EUR`. Inverse prices are converted with `1 / price`.

The resolved rate is cached on the adapter for a bounded interval so hundreds of EUR symbols do not trigger hundreds of identical ticker requests. Stable quote assets retain the existing `1.0` behavior.

If every candidate is missing, invalid, non-finite, or non-positive, the adapter returns `None`. The scanner keeps its existing fail-closed behavior and logs that USD conversion is unavailable; it does not guess that EUR equals USD.

## Data Flow

1. The scanner requests the quote-to-USD rate once for an EUR symbol.
2. The adapter returns a valid cached rate or probes the ordered candidate list.
3. Native EUR candle volumes and 24-hour quote volume are multiplied by that rate.
4. The existing `$50,000` filter is applied to the USD-equivalent current candle volume.
5. Any resulting alert continues to show USD-denominated volume and liquidity fields.

## Validation

- A direct EUR/stablecoin price is returned unchanged.
- An inverse stablecoin/EUR price is inverted.
- Invalid candidate prices are ignored.
- All unavailable candidates return `None` and preserve fail-closed filtering.
- Repeated conversions use the cache and do not repeat ticker calls.
- Existing adapter and volume-alert tests remain green.

## Deferred Options

An external reference-rate provider or manually configured fallback can be added later if OKX exposes no usable EUR cross-pair. That is intentionally excluded until live instrument evidence shows it is necessary.
