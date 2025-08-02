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

## Scheduling with Systemd on Ubuntu

To run the `b_volume_alerts.py` script periodically and manage it as a service on an Ubuntu system, you can use `systemd`. This provides more robust process management, including automatic restarts and better logging.

### 1. Create a Systemd Service File

Create a new file named `binance-volume-tracker.service` in the `/etc/systemd/system/` directory.

```bash
sudo nano /etc/systemd/system/binance-volume-tracker.service
```

Add the following content to the file:

```ini
[Unit]
Description=Binance Volume Tracker Script
After=network.target

[Service]
User=your_username
WorkingDirectory=/root/volume_tracker_binance/b_volume_alerts.py
ExecStart=/root/volume_tracker_binance/.venv/bin/python /root/volume_tracker_binance/b_volume_alerts.py
Restart=always
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```
*   Replace `your_username` with your actual Ubuntu username.
*   Replace `/path/to/your/CEX_volume_tracker_B` with the actual absolute path to your project directory.
*   `ExecStart`: Ensure `/usr/bin/python3` is the correct path to your Python 3 interpreter (you can find it by running `which python3`).
*   `Restart=always`  ensures the script restarts all the time after it finishes its run, it a continuous execution


### 2. Reload Systemd and Enable the Service

After creating the service file, reload the systemd daemon to recognize the new service, and then enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable binance-volume-tracker.service
sudo systemctl start binance-volume-tracker.service
```

### 3. Check Service Status and Logs

You can check the status of your service and view its logs using:

```bash
sudo systemctl status binance-volume-tracker.service
sudo journalctl -u binance-volume-tracker.service -f
```

This will set up the script to run as a systemd service, ensuring it restarts on failure and provides centralized logging.

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