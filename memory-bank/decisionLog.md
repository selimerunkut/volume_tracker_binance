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