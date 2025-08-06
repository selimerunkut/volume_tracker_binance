# Active Context

This file tracks the project's current status, including recent changes, current goals, and open questions.
2025-08-03 17:41:36 - Log of updates made.

*

## Current Focus

*   Populating the Memory Bank files with project information.

## Recent Changes

*   Initial project setup and core script development (`b_volume_alerts.py`, `telegram_alerts.py`).
*   Integration of TradingView and Binance trade URLs in Telegram alerts.
*   Implementation of number formatting with thousand separators in Telegram alerts.
*   Resolution of `ModuleNotFoundError` and `setuptools` "Multiple top-level modules" error by configuring `pyproject.toml` with `py-modules`.
*   Transition from internal scheduling/cron to `systemd` service for robust execution.
*   Updates to `README.md` and `setup_bot_server.sh` for `systemd` configuration.
*   Creation of standard Memory Bank files (`productContext.md`, `activeContext.md`, `progress.md`, `decisionLog.md`, `systemPatterns.md`).

## Open Questions/Issues

*   **Binance API Geographical Restriction**: The script encounters `BinanceAPIException: APIError(code=0): Service unavailable from a restricted location` when run from certain IP addresses (e.g., DigitalOcean **USA** servers). Solution is to run the script from europena IP addresses
*   **Systemd Service Monitoring**: While `Restart=always` is configured, continuous monitoring of `journalctl` logs is needed to ensure the service is consistently restarting and running as expected, especially after initial setup.
[2025-08-06 14:09:00] - Implemented filtering for "bullish" volume in alerts.