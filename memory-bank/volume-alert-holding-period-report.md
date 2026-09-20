# Volume-alert holding-period analysis

Date: 2026-09-20

## Question

After a qualifying volume alert, how long should a long trade be held? This analysis searches hourly holding periods from 1 to 48 hours using the same server auto-signal proxy cohort as the volume-alert validation.

## Method

- Source: server `suggestions` rows with `source='auto'`.
- Entry: stored auto-signal entry price and timestamp.
- Exit: nearest exchange hourly close at each holding horizon.
- Exchanges: Kraken and OKX.
- Transaction-cost sensitivity: 0.2 percentage points round trip. This is illustrative, not the configured fee for a specific account.
- Coin-specific results require at least 15 observations.

The auto rows are not an exact Telegram archive. They are created before the Telegram send and do not retain the original alert percentage or full alert payload.

## Coverage

- Auto events: 2,580
- Mature for a 48-hour measurement: 2,463
- Exchange-symbol groups fetched: 467
- Rows with a 48-hour endpoint: 1,881

Kraken's public OHLC endpoint only exposed approximately the latest 720 hourly candles, so older Kraken events could not be evaluated at every horizon.

## Overall results

| Hold | Mean | Median | Positive | Positive after 0.2% cost |
|---:|---:|---:|---:|---:|
| 1h | -0.221% | -0.048% | 44.29% | 37.31% |
| 4h | +0.048% | -0.071% | 44.33% | 38.16% |
| 6h | +0.053% | -0.078% | 44.12% | 38.76% |
| 12h | +0.117% | -0.069% | 45.52% | 40.44% |
| 18h | +0.516% | **-0.020%** | 47.41% | 42.84% |
| 24h | +0.459% | -0.082% | 45.20% | 41.96% |
| 36h | +0.605% | -0.096% | 45.88% | 42.50% |
| 48h | +1.099% | -0.103% | 45.45% | **42.96%** |

## Interpretation

There is no robust profitable holding period in the current data:

- 18 hours is the least-bad overall horizon by median return, but its median is still negative and only 42.84% clears the illustrative cost.
- 48 hours has the highest cost-adjusted positive rate, but it is only 42.96% and has a worse median.
- The positive means are driven by outliers. They should not be used as the main selection metric.
- Kraken was negative by median at every tested horizon.
- OKX was closest to neutral around 20–24 hours, but the cost-adjusted positive rate remained below 50%.

## Coin-specific candidates

These are research candidates, not production recommendations. They were selected after testing many exchange-symbol/horizon combinations, so they are vulnerable to selection bias.

| Exchange | Symbol | Best hold | Observations | Median | Positive after cost |
|---|---|---:|---:|---:|---:|
| OKX | SOL-USDC | 21h | 15 | +0.721% | 53.33% |
| OKX | BTC-USDC | 6h | 15 | +0.650% | 60.00% |
| OKX | ETH-USDC | 37h | 17 | +0.481% | 52.94% |
| OKX | BTC-EUR | 5h | 15 | +0.337% | 53.33% |
| OKX | ETH-BTC | 19h | 17 | +0.336% | 52.94% |
| OKX | SOL-BTC | 16h | 19 | +0.237% | 52.63% |

No candidate has enough evidence for a live coin-specific rule. The sample sizes are small, and the candidates were selected after looking at the same data.

## Decision

Do **not** hard-code a holding period yet. If a temporary shadow-test default is required, record 18 hours as the overall research candidate, not as a claimed edge. Keep the trade virtual until a new, held-out cohort confirms the result.

For future validation, store the original volume-alert event fields and run a walk-forward test: choose a holding period using an earlier period, then evaluate it on a later period. Require a minimum sample per coin and include actual fees, spread, and slippage.
