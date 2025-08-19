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
[2025-08-18 19:15:32] - Decided to refactor `main` method in `hummingbot_integration.py` to use `argparse` for example selection, mirroring the structure and usage patterns of `hummingbot_api_manager.py`. This ensures consistency and ease of testing.
[2025-08-19 10:26:00] - **Decision:** PnL and Open Order data for running bots will be extracted from `general_logs` messages using regex.
**Rationale:** The `performance` field in the `get_bot_status` API response is currently empty, and no other structured JSON fields provide this data. Log messages are the only available source for this information.
**Implementation Details:** Regular expressions are used to parse relevant strings from the `msg` field of log entries to extract PnL (e.g., "PnL: X.XXX YYY") and Open Orders (e.g., "Open orders: Z").
[2025-08-19 11:54:26] - Decision: Refactor `BotMonitor` to inject a time provider for `datetime.now()`.
Rationale: The user's feedback highlighted difficulty in testing time-dependent logic due to direct calls to `datetime.now()`. Injecting a time provider (e.g., a function or an object with a `now()` method) will decouple `BotMonitor` from the global `datetime` module, making it easier to mock time in tests and improving adherence to Dependency Inversion Principle (DIP) and Single Responsibility Principle (SRP). This directly addresses concerns about code testability and quality.
Implications:
- Modify `BotMonitor.__init__` to accept `time_provider`.
- Update `_handle_running_bot` to use `self._time_provider()`.
- Adjust `main_entry_point` to pass `datetime.datetime.now` as the default `time_provider`.
- Update `tests/test_bot_monitor.py` to pass a mock `time_provider` and control its return values for time-dependent tests.
[2025-08-19 13:27:05] - Centralized Bot Removal and Notification Logic in `_synchronize_active_trades`

**Decision:** Centralized the logic for identifying, removing, archiving, and sending initial notifications for stopped/not-found Hummingbot instances within the `_synchronize_active_trades` method of `BotMonitor` in `bot_monitor.py`.

**Rationale:** Previously, `_handle_stopped_bot` and `_handle_not_found_bot` were responsible for archiving and notifying. However, `_synchronize_active_trades` was already removing these bots from the active list, leading to a race condition and incorrect test assertions. Centralizing this logic ensures a single source of truth for state changes and simplifies testing.

**Implications:** `_handle_stopped_bot` and `_handle_not_found_bot` are now primarily for notifications if a bot's status changes *after* synchronization but before the next cycle, or if `get_bot_status` returns a specific stopped/not-found status for a bot still in the active list. Test assertions for stopped/not-found bots now target `_synchronize_active_trades`'s effects (calling `stop_and_archive_bot` and `save_trades` with the modified list).
[2025-08-19 14:05:51] - **Decision:** Ensure `HummingbotManager.get_all_bot_statuses` in `hummingbot_integration.py` consistently returns a dictionary with a 'data' key, even when an API error occurs.
**Rationale:** The `BotMonitor._synchronize_active_trades` method expects `get_all_bot_statuses` to return a dictionary with a 'data' key. Currently, on exceptions, `get_all_bot_statuses` returns an empty list (`[]`), which causes a `'list' object has no attribute 'get'` error in `BotMonitor` when it attempts to call `.get('data', {})` on the list. By returning `{"status": "error", "data": {}}` (or similar structured error response) on exceptions, we ensure a consistent return type, preventing runtime errors in dependent modules.
**Implications:** This change will require modifying the `except` blocks in `get_all_bot_statuses` in `hummingbot_integration.py`.