# Draft: High-Frequency and Daily AI Strategy Signals

## Prompt Contract
**GOAL**: Add automated hourly and daily checks that send Telegram messages when specific BB (Bollinger Band Mean Reversion) and SMA (Daily Crossover) conditions are met.
**CONSTRAINT**: Alerts must ONLY be generated for a specific user-defined list of pairs. Include a feature to list high-volume Binance pairs to easily add them to this list.
**FAILURE CONDITION**: The bot spams the channel every hour when there is no valid signal, OR Binance API rate limits are hit (due to checking too many pairs too frequently or inefficient polling).

## Technical Decisions
- **Execution Architecture**: Automated background checks using `APScheduler` (already used in `telegram_bot_handler.py` for performance tracking).
- **Timeframes**: 
  - Hourly strategy: `1h` klines, Bollinger Bands (length 20, stddev 2). Signal when price crosses below lower band (LONG) or above middle band (CLOSE).
  - Daily strategy: `1d` klines, SMA (length 12). Signal when price crosses above SMA12 (LONG) or below SMA12 (SHORT).
- **Development Approach**: TDD (Test-Driven Development). We will write small, focused tests for indicator logic before implementation.
- **Task Granularity**: Strict single-file or single-concern steps.

## Scope Boundaries
- INCLUDE: New `StrategySignal` service, test suite for technical indicators, APScheduler jobs for hourly/daily checks, Telegram notification formatting, high-volume pair lookup command.
- EXCLUDE: Automated trade execution (API orders). This is purely a signaling/advisor feature.