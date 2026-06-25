# Product Context

This file provides a high-level overview of the project and the expected product that will be created. Initially it is based upon projectBrief.md (if provided) and all other available project-related information in the working directory. This file is intended to be updated as the project evolves, and should be used to inform all other modes of the project's goals and context.
2025-08-03 17:41:29 - Log of updates made will be appended as footnotes to the end of this file.

*

## Project Goal

*   To track cryptocurrency volume on Binance and Kraken and send real-time alerts to Telegram for significant volume changes, while keeping the menu modular enough to add more exchanges later.

## Key Features

*   Fetches real-time volume data for Binance and Kraken pairs through a shared exchange registry.
*   Calculates current volume against historical mean volume (last 24 hours).
*   Generates alerts for predefined volume levels.
*   Sends detailed, formatted alerts to Telegram, including symbol, exchange, current/mean volumes, alert level, TradingView chart links, and exchange-specific trade links when supported.
*   Lets the Telegram user choose alert scope as a single exchange, multiple exchanges, or all exchanges.
*   Uses `systemd` for robust service management and continuous execution on Linux systems.

## Overall Architecture

*   **Core Logic**: Python scripts (`b_volume_alerts.py`, `telegram_alerts.py`, `alert_levels_tg.py`) handle data fetching, alert generation, and message sending.
*   **Exchange Layer**: `src/exchanges/registry.py` routes work to the Binance or Kraken adapter, and alert scope is persisted per chat so the same menu can govern current and future exchanges.
*   **Dependency Management**: `uv` is used with `pyproject.toml` to manage project dependencies (`requests`, `pandas`, `python-binance`, `numpy`).
*   **Configuration**: API keys and chat IDs are stored in `credentials_b.json` (ignored by Git), with exchange selection stored in the application database.
*   **Execution Environment**: Designed to run as a `systemd` service on Linux (e.g., Ubuntu) for background operation, automatic restarts, and centralized logging.
*   **External APIs**: Interacts with Binance and Kraken APIs for market data and Telegram Bot API for sending alerts.
[2025-08-03 20:36:35] - Added new features: Telegram bot integration for dynamic management of restricted trading pairs (restrict via button, list via command, unrestrict via command). Refactoring of existing code for better structure and maintainability.
[2026-06-25] - Added chat-scoped exchange scope selection and Kraken support while preserving Binance behavior as the default path.

## Future Enhancements

*   **Improved Volume Surge Calculation**:
    *   Consider using Weighted Moving Average (WMA) or Exponential Moving Average (EMA) for `prev_volume_mean` to provide a more responsive and robust baseline.
    *   Explore Volume Profile Analysis to compare current volume against typical volume distribution for specific times of day, offering more nuanced surge detection.
