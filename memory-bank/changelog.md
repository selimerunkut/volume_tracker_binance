# Changelog


## 2025-08-19

-   **Feature:** Enhanced bot status monitoring and added Telegram `/status` command.
    -   Implemented granular automatic status updates in `bot_monitor.py` with PnL and open order info.
    -   Added `/status` Telegram command in `telegram_bot_handler.py` to query bot status.
-   **Feature:** Updated environment configuration and enhanced Telegram bot credential handling for test mode.
-   **Feature:** Implemented bot monitoring and fixed Telegram notifications/replies.
    -   `bot_monitor.py` for checking Hummingbot instance statuses and "Trade Completed" notifications.
    -   `trade_storage.py` for persistent storage of active bot configurations.
    -   Fixed `AttributeError` in `telegram_bot_handler.py` for `reply_text`.

## 2025-08-18

-   **Feature:** Implemented Hummingbot Integration Module.
    -   Introduced `hummingbot_integration.py` with `HummingbotManager` for API interactions, bot creation/deployment, status, and stopping.
    -   Added `hummingbot-api-client`, `aiohttp`, `python-dotenv` dependencies.

## 2025-08-17

-   **Feature:** Added architecture diagram and detailed flowcharts for Hummingbot Telegram integration.

## 2025-08-06

-   **Fix:** Resolved display and dry-run issues in volume alerts.
    -   Corrected `open_price` and `close_price` display in Telegram alerts (fixed "0.0000" issue).
    -   Enhanced dry-run functionality in `telegram_alerts.py`.
-   **Fix:** Conversion error in Telegram message.
-   **Feature:** Included Open and Close prices of the last completed hourly volume candle in alert messages.
-   **Feature:** Implemented bullish volume filtering for alerts.
    -   Alerts now only trigger for "bullish" candles (`close_price > open_price`).

## 2025-08-04

-   **Refactor:** Commented debug outputs.
-   **Feature:** Implemented Telegram bot for dynamic restricted pair management and fixed alert error.
    -   Fixed 'tuple indices must be integers or slices, not str' error in `telegram_alerts.py`.
    -   Implemented `telegram_bot_handler.py` for `/help`, `/list_restricted`, `/unrestrict` commands.
    -   Introduced `symbol_manager.py` for managing excluded symbols.

## 2025-08-03

-   **Feature:** Added 2-hour and 4-hour volume to alert messages.
-   **Fix:** Resolved duplicate Telegram alerts and refactored for DRY.
    -   Implemented file-based persistent state for sent alerts.
    -   Refactored symbol filtering and alert message construction.
-   **Docs:** Updated `README.md`.
-   **Chore:** Added server setup file.
-   **Chore:** Updated `.gitignore`.
-   **Fix:** Fixed `pyproject.toml`.
-   **Fix:** Added `datetime` import and changed Telegram `parse_mode` to HTML.
-   **Refactor:** Improved Telegram alert number formatting and clarified systemd service setup.

## 2025-08-02

-   Added Binance trade URL to Telegram alerts.
-   Formatted `curr_volume` and `prev_volume_mean` as integers in Telegram alerts.
-   Updated `README.md` with new features and setup instructions.
-   Created `memory-bank` directory and `changelog.md`.

[2025-08-20 19:45:15] - **Fix**: Resolved premature bot archiving and ensured correct archiving upon trade completion. Refactored `BotMonitor` to reuse comprehensive bot status data from `get_all_bot_statuses` to ensure accurate log processing and trade completion detection. Verified multi-bot handling.

## 2025-08-21

-   **Feature:** Implemented robust PnL retrieval and Telegram notification for completed Hummingbot trades.
    -   **`hummingbot_integration.py`**:
        -   Added retry mechanism for database discovery in `get_bot_pnl_after_completion` to handle archiving delays.
        -   Ensured full database path is used for PnL retrieval.
        -   Improved error handling for API responses, including specific handling for missing `TradeFill` table.
    -   **`telegram_messenger.py`**:
        -   Corrected PnL data extraction from nested API responses for Telegram messages.
    -   **`bot_monitor.py`**:
        -   Ensured `pnl_data` is always initialized and passed to status handlers.
        -   Refined conditional archiving logic.
    -   **`simulate_trade_logs.py`**:
        -   Configured to use real Hummingbot API for PnL and archiving calls when credentials are provided.
        -   Updated simulation data and assertions for accurate testing of PnL flow.