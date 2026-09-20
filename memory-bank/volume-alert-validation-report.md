# Volume-alert validation report

Date: 2026-09-20

## Scope

This validates the volume-alert follow-up trade idea: enter long after a qualifying volume alert and compare the entry price with later exchange market data.

The server does not retain a dedicated table of the exact Telegram volume-alert messages. The available durable proxy is `suggestions` rows with `source='auto'`. These rows are created by `create_auto_signal()` when a volume alert qualifies, before the Telegram send. They are therefore an event proxy, not proof that every corresponding Telegram message was delivered.

## Cohort

- Auto-signal rows: 2,575
- Mature rows with at least 24 hours elapsed: 2,530
- Exchanges: Kraken and OKX
- Event range: 2026-07-27 through 2026-09-19
- Rows with a recoverable 24-hour candle endpoint: 1,891 (74.7%)
  - Kraken: 1,098 of 1,737
  - OKX: 793 of 793

Kraken's public OHLC endpoint only returned roughly the latest 720 hourly candles, so older Kraken events could not be reconstructed. OKX historical candles were fetched successfully after rate-limited retries.

## Gross forward returns

Returns are close-to-close from the stored auto-signal entry price. They exclude fees, spread, slippage, and any execution delay.

| Horizon | Observations | Mean | Median | Positive | Positive after illustrative 0.2% cost |
|---|---:|---:|---:|---:|---:|
| 1h | 1,845 | -0.213% | -0.048% | 44.39% | 37.45% |
| 4h | 1,854 | +0.060% | -0.073% | 44.34% | 38.30% |
| 6h | 1,865 | +0.061% | -0.076% | 44.13% | 38.93% |
| 24h | 1,891 | +0.451% | -0.090% | 45.06% | 41.83% |

The positive 24-hour mean is driven by large outliers. The median is negative and fewer than half of the entries were profitable before costs.

## By exchange, 24-hour return

- Kraken: 1,098 observations; mean +0.169%, median -0.396%, positive 41.07%.
- OKX: 793 observations; mean +0.842%, median +0.023%, positive 50.57%; positive after the illustrative 0.2% cost 46.78%.

## Risk path

Across 1,889 observations with a measurable 24-hour candle path:

- Maximum favorable excursion: mean +7.38%, median +3.07%.
- Maximum adverse excursion: mean -4.67%, median -2.65%.

Volume alerts often had subsequent upside somewhere in the 24-hour path, but drawdowns were also large. A trade rule needs an explicit entry, stop, target, and time exit; the alert alone is not enough.

## Strategy overlay

The deterministic strategy stored with the auto events was `WAIT` for 1,882 of the 1,891 fetched cohort rows; only 1 was `LONG` and 8 were `SHORT`. It is not a valid substitute for testing the volume alert as a long entry. The volume-alert cohort should be evaluated independently of that later strategy label.

## Conclusion

The available evidence does **not** show a reliable standalone long-entry edge:

- Short-term returns were slightly negative.
- The 24-hour median was negative.
- The gross positive rate was only 45.06%.
- A small illustrative trading cost reduced the positive rate to 41.83%.
- The mean was positive mainly because of outliers.

This is a preliminary validation, not a complete historical Telegram study. It cannot compare alert levels such as 500%, 700%, and 1000% because those raw alert fields are not stored in `suggestions`. It also cannot prove message delivery. Exact threshold-level analysis requires a Telegram export or a new durable volume-alert event table.

## Recommended next measurement

Persist every qualifying volume event before sending, including exchange, symbol, timestamp, alert level, current volume, six-hour baseline, open/close, and send result. Then run a matched baseline by symbol and hour, and report results separately by alert level and exchange with fees and slippage applied.
