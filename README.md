# Binance Volume Tracker

This project tracks cryptocurrency volume on Binance and sends alerts based on predefined volume levels.

## Features

- Fetches real-time volume data for USDC pairs on Binance.
- Calculates current volume against historical mean volume.
- Generates alerts for significant volume changes.
- Sends detailed alerts to Telegram, including:
    - Symbol and exchange
    - Current and previous 24h mean volumes (formatted as integers)
    - Alert level
    - Links to TradingView chart
    - Links to Binance trade page

## Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-repo/CEX_volume_tracker_B.git
    cd CEX_volume_tracker_B
    ```

2.  **Install dependencies using uv:**
    ```bash
    uv sync
    ```
    (Note: Dependencies are managed via `pyproject.toml`.)

3.  **Configure Credentials:**
    Create `credentials_b.json` and `credentials_telegram.json` in the project root directory.

    `credentials_b.json`:
    ```json
    {
      "Binance_api_key": "YOUR_BINANCE_API_KEY",
      "Binance_secret_key": "YOUR_BINANCE_SECRET_KEY"
    }
    ```

    `credentials_telegram.json`:
    ```json
    {
      "Telegram_bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
      "Telegram_chat_id": "YOUR_TELEGRAM_CHAT_ID"
    }
    ```

4.  **Run the script:**
    ```bash
    python b_volume_alerts.py
    ```
    The script is configured to run once immediately for testing purposes. For scheduled runs, uncomment the scheduling block in `b_volume_alerts.py`.

## Project Structure

-   `b_volume_alerts.py`: Main script for fetching data, calculating alerts, and sending messages.
-   `alert_levels_tg.py`: Defines logic for volume alert levels.
-   `telegram_alerts.py`: Handles sending messages to Telegram.
-   `credentials_b.json`: Stores Binance API credentials (ignored by `.gitignore`).
-   `credentials_telegram.json`: Stores Telegram bot credentials (ignored by `.gitignore`).
-   `.gitignore`: Specifies files and directories to be ignored by Git.
-   `memory-bank/`: Contains project documentation and changelog.

## Changelog

Refer to `memory-bank/changelog.md` for a detailed history of changes.