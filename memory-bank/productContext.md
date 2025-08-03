# Product Context

This file provides a high-level overview of the project and the expected product that will be created. Initially it is based upon projectBrief.md (if provided) and all other available project-related information in the working directory. This file is intended to be updated as the project evolves, and should be used to inform all other modes of the project's goals and context.
2025-08-03 17:41:29 - Log of updates made will be appended as footnotes to the end of this file.

*

## Project Goal

*   To track cryptocurrency volume on Binance and send real-time alerts to Telegram for significant volume changes.

## Key Features

*   Fetches real-time volume data for USDC and BTC pairs from Binance.
*   Calculates current volume against historical mean volume (last 24 hours).
*   Generates alerts for predefined volume levels.
*   Sends detailed, formatted alerts to Telegram, including symbol, exchange, current/mean volumes, alert level, TradingView chart links, and Binance trade links.
*   Uses `systemd` for robust service management and continuous execution on Linux systems.

## Overall Architecture

*   **Core Logic**: Python scripts (`b_volume_alerts.py`, `telegram_alerts.py`, `alert_levels_tg.py`) handle data fetching, alert generation, and message sending.
*   **Dependency Management**: `uv` is used with `pyproject.toml` to manage project dependencies (`requests`, `pandas`, `python-binance`, `schedule`, `numpy`).
*   **Configuration**: API keys and chat IDs are stored in `credentials_b.json` and `credentials_telegram.json` (ignored by Git).
*   **Execution Environment**: Designed to run as a `systemd` service on Linux (e.g., Ubuntu) for background operation, automatic restarts, and centralized logging.
*   **External APIs**: Interacts with Binance API for market data and Telegram Bot API for sending alerts.