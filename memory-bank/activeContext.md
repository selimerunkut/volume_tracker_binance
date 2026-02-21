# Active Context

This file tracks the project's current status, including recent changes, current goals, and open questions.
2025-08-03 17:41:36 - Log of updates made.

*

## Current Focus

*   Populating the Memory Bank files with project information.

*   Implementation of the **AI Strategy Advisor** Telegram bot with LLM integration.
*   Added dynamic UI menu showing the last 5 analyzed symbols.
*   Implemented robust symbol detection from plain text messages.
*   Added typo feedback and shorthand commands (`/a`, `/anlayze`).
*   Improved error handling for invalid Binance symbols with specific corrective suggestions.
*   Fixed bot stability issues related to `NoneType` errors in callback handlers.

## Open Questions/Issues

*   **Binance API Geographical Restriction**: The script encounters `BinanceAPIException: APIError(code=0): Service unavailable from a restricted location` when run from certain IP addresses (e.g., DigitalOcean **USA** servers). Solution is to run the script from europena IP addresses
*   **Systemd Service Monitoring**: While `Restart=always` is configured, continuous monitoring of `journalctl` logs is needed to ensure the service is consistently restarting and running as expected, especially after initial setup.
[2025-08-06 14:09:00] - Implemented filtering for "bullish" volume in alerts.