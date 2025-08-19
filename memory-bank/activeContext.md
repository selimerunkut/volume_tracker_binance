# Active Context

This file tracks the project's current status, including recent changes, current goals, and open questions.
2025-08-03 17:41:36 - Log of updates made.

*

## Current Focus

*   Enhancing bot status monitoring and adding Telegram command for status inquiry.

## Recent Changes

*   Initial project setup and core script development (`b_volume_alerts.py`, `telegram_alerts.py`).
*   Integration of TradingView and Binance trade URLs in Telegram alerts.
*   Implementation of number formatting with thousand separators in Telegram alerts.
*   Resolution of `ModuleNotFoundError` and `setuptools` "Multiple top-level modules" error by configuring `pyproject.toml` with `py-modules`.
*   Transition from internal scheduling/cron to `systemd` service for robust execution.
*   Updates to `README.md` and `setup_bot_server.sh` for `systemd` configuration.
*   Creation of standard Memory Bank files (`productContext.md`, `activeContext.md`, `progress.md`, `decisionLog.md`, `systemPatterns.md`, `architecture_diagram.md`, `changelog.md` ).

## Open Questions/Issues

*   **Binance API Geographical Restriction**: The script encounters `BinanceAPIException: APIError(code=0): Service unavailable from a restricted location` when run from certain IP addresses (e.g., DigitalOcean **USA** servers). Solution is to run the script from europena IP addresses
*   **Systemd Service Monitoring**: While `Restart=always` is configured, continuous monitoring of `journalctl` logs is needed to ensure the service is consistently restarting and running as expected, especially after initial setup.
[2025-08-06 14:09:00] - Implemented filtering for "bullish" volume in alerts.
[2025-08-18 19:15:23] - Completed implementation and testing of `hummingbot_integration.py`. The module provides an interface for managing Hummingbot instances, including creation, deployment, status checks, and stopping/archiving.
[2025-08-19 10:26:30] - Implemented granular bot status updates in `bot_monitor.py` (active, stopped reasons, PnL/open orders from logs).
[2025-08-19 10:26:30] - Added `/status` Telegram command in `telegram_bot_handler.py` for bot status inquiry (single or all active bots) and updated `/help` message.
[2025-08-19 10:26:30] - Resolved `NameError: name 're' is not defined` in `telegram_bot_handler.py` by adding `import re`.
[2025-08-19 10:26:30] - Confirmed that PnL and open order data are extracted from log messages using regex, as structured JSON fields are not currently available.
[2025-08-19 13:27:28] - Debugging and Refining Bot Monitor and Tests

**Current Focus:** Debugging and refining `bot_monitor.py` and `tests/test_bot_monitor.py`. Specifically, addressing `AssertionError`s related to `load_trades` being called twice and `stop_and_archive_bot`/`remove_trade_entry` not being asserted correctly in stopped/not-found bot scenarios.

**Recent Changes:**
*   Modified `bot_monitor.py`: `_synchronize_active_trades` now handles archiving and initial notifications for removed bots. `_handle_stopped_bot` and `_handle_not_found_bot` are simplified.
*   Attempted modification of `tests/test_bot_monitor.py`: Updated `test_no_active_trades` to explicitly mock `load_trades` return value and assert `save_trades`. Intended to update other stopped/not-found bot tests to assert `stop_and_archive_bot` and `save_trades` with the modified list, and remove redundant mock side effects. (Note: The `apply_diff` for this file failed due to a syntax error, so these changes are not yet applied).

**Open Questions/Issues:** Tests are still failing after the latest changes to `bot_monitor.py`. The core issue is still the assertion logic for stopped/not-found bots in `tests/test_bot_monitor.py`, which needs to be correctly applied.
[2025-08-19 15:33:31] - Current focus is on resolving `tests/test_bot_monitor.py` failures, specifically `AssertionError: Expected 'save_trades' to be called once. Called 0 times.` and `KeyError: 'message'` in message assertions. The `TelegramNotifier.notify` signature was adjusted to make `message` optional. Debugging `apply_diff` formatting issues.
[2025-08-19 15:36:08] - Comprehensive review of unstaged changes completed. Key changes include:
- `bot_monitor.py`: Major refactoring into `BotMonitor` class with `TelegramNotifier` and `TradeStorage` dependencies. Centralized bot removal, archiving, and initial notification logic within `_synchronize_active_trades`.
- `hummingbot_integration.py`: Added `get_all_bot_statuses` to retrieve all active bot statuses.
- `trade_storage.py`: Refactored into a `TradeStorage` class with injected file operation functions for improved testability.
- `telegram_messenger.py`: New file introduced to encapsulate Telegram messaging logic, including MarkdownV2 escaping.
- `telegram_alerts.py`: Modified to use `TELEGRAM_BOT_TEST_MODE` environment variable for credential loading and to use `TelegramMessenger`.
- `telegram_bot_handler.py`: Updated to use `TradeStorage` and `TelegramMessenger` instances.
- `tests/test_bot_monitor.py`: Significant updates to mock `TelegramMessenger` and `TradeStorage`, and to adjust assertions for message content and `save_trades` calls.