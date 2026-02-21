# Decision Log

This file records architectural and implementation decisions using a list format.
2025-08-03 17:41:46 - Log of updates made.

*

## Decision

*   **Project Structure**: Maintain a flat project structure instead of migrating to `src-layout`.

## Rationale

*   User preference for simplicity and to avoid unnecessary refactoring for a project of this size.

## Implementation Details

*   Explicitly defined `py-modules = ["b_volume_alerts", "telegram_alerts"]` in `pyproject.toml` under `[tool.setuptools]` to resolve `setuptools` "Multiple top-level modules discovered" error during `uv sync`.
*   **Scheduling Mechanism**: Utilize `systemd` for script scheduling and service management instead of `cron` or an internal `schedule` loop.
*   **Rationale**: `systemd` offers more robust process management, including automatic restarts (`Restart=always`) and centralized logging (`StandardOutput=journal`, `StandardError=journal`), which is superior for a long-running background service.
*   **Implementation Details**:
    *   A `binance-volume-tracker.service` file was created and configured in `setup_bot_server.sh` to be placed in `/etc/systemd/system/`.
    *   `ExecStart` path was set to `/root/volume_tracker_binance/.venv/bin/python /root/volume_tracker_binance/b_volume_alerts.py`.
    *   `Restart=always` was explicitly set to ensure continuous execution by restarting the script after each run.
    *   `README.md` was updated with detailed `systemd` setup instructions.
[2025-08-03 18:04:54] - Decision: Implement duplicate alert message prevention.
Rationale: User feedback indicates duplicate alerts for the same volume increase are being sent, leading to spam. A simple solution is preferred.
Implementation Details:
    - Use an in-memory dictionary to track recently sent alerts (symbol, alert level, timestamp).
    - Implement a cooldown period (e.g., 4 hours) to prevent re-sending the same alert within that timeframe.
    - This approach is simple and avoids new dependencies, though it will not persist across script restarts.
[2025-08-03 18:08:31] - Decision: Revise duplicate alert message prevention to use file-based persistence.
Rationale: The previous in-memory solution is not suitable for a script managed by `systemd` with `Restart=always`, as the in-memory state is lost upon script exit and restart, leading to duplicate alerts.
Implementation Details:
    - Store `last_alert_timestamps` in a JSON file to persist state across script restarts.
    - Load the state from the file at script startup.
    - Save the state to the file after each alert is sent.
    - Implement error handling for file operations (read/write).
[2025-08-03 20:36:45] - **Decision:** Introduce a Telegram bot for dynamic management of restricted trading pairs and refactor the existing codebase for improved structure and maintainability.
**Rationale:** The previous static `restricted_pairs.json` file required manual updates. A Telegram bot will provide a more interactive and user-friendly way to manage excluded pairs directly from the chat interface, including restricting via inline buttons, listing, and un-restricting via commands. Refactoring is necessary to accommodate the new bot functionality and improve overall code organization.
**Implementation Details:**
- A new Python module (e.g., `telegram_bot_handler.py`) will be created to handle Telegram bot interactions (commands and callbacks).
- `telegram_alerts.py` will be modified to support sending inline keyboard buttons with alert messages.
- `b_volume_alerts.py` will be refactored to separate concerns, potentially introducing a `SymbolManager` class or similar to handle loading and filtering symbols, which the bot can also interact with.
- `restricted_pairs.json` will continue to store the excluded symbols, but its management will be automated via the bot.
[2025-08-06 14:09:00] - Decision: Filter volume alerts to only trigger on "bullish" candles.
Rationale: User feedback indicated that alerts were being triggered for high volume on downward price movements ("bearish" candles), which is not desired. The goal is to focus on volume surges that accompany upward price movements.
Implementation Details:
    - Modified `b_volume_alerts.py` to extract `open` and `close` prices of the current candle.
    - Passed `open_price` and `close_price` to `get_volume_alert_details` in `alert_levels_tg.py`.
    - Added a condition `close_price > open_price` in `get_volume_alert_details` to ensure alerts are only generated for candles where the closing price is higher than the opening price.
[2026-02-21 13:10:00] - **Decision**: Use dynamic symbol buttons in the main menu.
**Rationale**: Hardcoding symbols like BTC/ETH limits flexibility. Showing the last 5 analyzed pairs makes it easier for users to re-run common analyses without typing.
**Implementation Details**:
    - Created `get_last_analyzed_symbols` in `db_service.py`.
    - Updated `get_main_menu_markup` in `telegram_bot_handler.py` to fetch these symbols at runtime.
[2026-02-21 13:15:00] - **Decision**: Implement robust "command-less" symbol recognition.
**Rationale**: Users often type symbols directly instead of using `/analyze` or replying to prompts. A more flexible message handler improves UX significantly.
**Implementation Details**:
    - Added logic to `debug_message_handler` to detect 3-12 character uppercase strings as symbols.
    - Simplified criteria to be more inclusive while avoiding command collisions.