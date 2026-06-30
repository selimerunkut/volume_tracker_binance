# Active Context

This file tracks the project's current status, including recent changes, current goals, and open questions.
2025-08-03 17:41:36 - Log of updates made.

*

## Current Focus

*   Populating the Memory Bank files with project information.

*   Implementation of the **Deterministic Strategy Advisor** Telegram bot with exchange-specific data and structured analysis details.
*   Multi-exchange alert support with Binance/Kraken adapters and a universal Telegram exchange-scope menu.
*   Added dynamic UI menu showing the last 5 analyzed symbols.
*   Implemented robust symbol detection from plain text messages.
*   Added typo feedback and shorthand commands (`/a`, `/anlayze`).
*   Replaced LLM-based `/analyze` output with deterministic scoring and clickable informational news links.
*   Improved error handling for invalid Binance symbols with specific corrective suggestions.
*   Fixed bot stability issues related to `NoneType` errors in callback handlers.

## Open Questions/Issues

*   **Binance API Geographical Restriction**: The script encounters `BinanceAPIException: APIError(code=0): Service unavailable from a restricted location` when run from certain IP addresses (e.g., DigitalOcean **USA** servers). Solution is to run the script from European IP addresses
*   **Kraken verification**: Public Kraken data paths should be revalidated whenever the adapter changes, especially for symbol naming and OHLC interval handling.
*   **Deterministic analysis**: `/analyze` now uses exchange-specific OHLCV and current price data plus a pure scoring policy; news headlines are informational only and should remain clickable, safe, and separate from the signal.
*   **Systemd Service Monitoring**: While `Restart=always` is configured, continuous monitoring of `journalctl` logs is needed to ensure the service is consistently restarting and running as expected, especially after initial setup.
[2025-08-06 14:09:00] - Implemented filtering for "bullish" volume in alerts.
