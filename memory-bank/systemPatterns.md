# System Patterns *Optional*

This file documents recurring patterns and standards used in the project.
It is optional, but recommended to be updated as the project evolves.
2025-08-03 17:41:51 - Log of updates made.

*

## Coding Patterns

*   **Modular Scripting**: Core functionalities are separated into distinct Python files (`b_volume_alerts.py` for data/alerts, `telegram_alerts.py` for messaging, `alert_levels_tg.py` for logic).
*   **Configuration Externalization**: Sensitive credentials (API keys, chat IDs) are stored in external JSON files (`credentials_b.json`, `credentials_telegram.json`) and excluded from version control via `.gitignore`.
*   **Error Handling**: Robust `try-except` blocks are used for external API calls (`requests.exceptions.RequestException`, `BinanceAPIException`) and data processing (`ValueError`) to ensure script resilience.
*   **Logging**: Extensive `print` statements with timestamps are used for real-time progress tracking and debugging, which are then captured by `systemd`'s journal.
*   **Data Formatting**: Numerical values (volumes) are formatted with thousand separators for readability in Telegram alerts.
*   **URL Generation**: Dynamic generation of external links (TradingView, Binance trade) based on symbol for direct access from alerts.

## Architectural Patterns

*   **Client-Server Interaction**: The `b_volume_alerts.py` script acts as a client interacting with the Binance API to fetch market data.
*   **Messaging Service Integration**: The `telegram_alerts.py` module integrates with the Telegram Bot API to send notifications, acting as a messaging client.
*   **Service Management**: `systemd` is employed as the primary service manager on Linux systems, ensuring the script runs continuously in the background, restarts automatically on exit, and provides centralized logging.
*   **Dependency Management**: `uv` and `pyproject.toml` define and manage project dependencies, ensuring a consistent and isolated environment.

## Testing Patterns

*   **Unit Testing (Implicit)**: Individual functions (e.g., `send_telegram_message` in `telegram_alerts.py`) include `if __name__ == "__main__":` blocks for standalone testing.
*   **Integration Testing**: The `run_script()` function in `b_volume_alerts.py` can be executed once immediately for quick end-to-end testing of data fetching, alert generation, and Telegram message sending.
*   **Service Behavior Testing**: `systemd`'s `Restart=always` behavior is tested by observing service restarts via `journalctl` after the script completes a single run. Temporary code modifications (e.g., limiting loop iterations) were used to speed up this testing.
[2025-08-19 13:27:42] - Centralized State Management and Side Effects

The `_synchronize_active_trades` method in `BotMonitor` now serves as the single point of truth for managing the `active_trades.json` state. This includes identifying bots to be removed (stopped/not found), performing the archiving action (`stop_and_archive_bot`), and sending initial notifications for these state changes. This reinforces the Single Responsibility Principle by encapsulating all state-modifying logic and immediate side effects related to trade synchronization within one method.