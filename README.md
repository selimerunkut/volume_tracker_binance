# Binance Volume Tracker & AI Strategy Advisor

This project tracks cryptocurrency volume on Binance and sends alerts based on predefined volume levels. It also includes an **AI-powered Strategy Advisor** that analyzes market data, technical indicators, and news to suggest trading strategies with a self-improving learning loop.

## Features

### Volume Tracker
- Fetches real-time volume data for USDC pairs on Binance.
- Calculates current volume against historical mean volume.
- Generates alerts for significant volume changes.
- Sends detailed alerts to Telegram, including:
    - Symbol and exchange
    - Current and previous 24h mean volumes (formatted as integers)
    - Alert level
    - Links to TradingView chart
    - Links to Binance trade page

### AI Strategy Advisor (New)
- **Smart Analysis**: Uses LLM (via OpenRouter) to analyze technical indicators (RSI, MACD, Bollinger Bands, EMA) and crypto news.
- **Memory & Learning**: Tracks all suggestions and evaluates outcomes to learn from past performance.
- **WAIT Strategy Support**: Even "WAIT" recommendations are tracked and scored based on price movement.
- **Detailed Context**: View full analysis details including technical indicators, news sources, and past performance influence.

### Telegram Bot Commands
- `/analyze <SYMBOL>` - Get AI-generated trading strategy with Entry, TP, SL, and confidence score.
- `/history` - View performance statistics (wins, losses, win rate, average PnL).
- `/list_restricted` - List all restricted trading pairs.
- `/unrestrict <SYMBOL>` - Unrestrict a specific pair.
- Dynamic pair restriction from alert messages via inline buttons.

## Setup

## Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-repo/volume_tracker_binance.git
    cd volume_tracker_binance
    ```

2.  **Install dependencies using uv:**
    ```bash
    uv sync
    ```
    (Note: Dependencies are managed via `pyproject.toml`.)

3.  **Configure Credentials:**
    Create `credentials_b.json` in the project root directory. This file will store both your Binance API credentials and Telegram bot credentials.

    `credentials_b.json`:
    ```json
    {
      "Binance_api_key": "YOUR_BINANCE_API_KEY",
      "Binance_secret_key": "YOUR_BINANCE_SECRET_KEY",
      "telegram_bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
      "telegram_chat_id": "YOUR_TELEGRAM_CHAT_ID",
      "telegram_bot_token_test": "YOUR_TEST_BOT_TOKEN",
      "telegram_chat_id_test": "YOUR_TEST_CHAT_ID",
      "llm_api_key": "YOUR_OPENROUTER_API_KEY",
      "llm_base_url": "https://openrouter.ai/api/v1",
      "llm_model": "google/gemini-2.0-flash-lite-preview-02-05:free"
    }
    ```
    **Important:** 
    - Ensure the keys for Telegram credentials are exactly `telegram_bot_token` and `telegram_chat_id` (lowercase 't').
    - For AI strategy advisor, get an API key from [OpenRouter](https://openrouter.ai/) (free tier available).
    - The `llm_model` can be changed to any OpenRouter-supported model.

4.  **Run the Application:**
    The application consists of two main components that should be run concurrently:

    a.  **Run the Telegram Bot Handler** (includes AI Strategy Advisor):
        ```bash
        python telegram_bot_handler.py
        ```
        This starts the Telegram bot with all features:
        - Volume alert management with inline buttons
        - AI strategy analysis (`/analyze` command)
        - Performance tracking (`/history` command)
        - Background job that evaluates suggestion outcomes every 30 minutes

    b.  **Run the Volume Alert Script** (optional, separate process):
        ```bash
        python b_volume_alerts.py
        ```
        This script continuously monitors volume and sends alerts independently.
        **Note:** The volume alerts are separate from the AI strategy advisor and run as a different process.

    **Quick Start (Development):**
    ```bash
    # Terminal 1: Start the Telegram bot (includes all AI features)
    python telegram_bot_handler.py
    
    # Terminal 2: Start volume monitoring (optional)
    python b_volume_alerts.py
    ```

## Telegram Bot Commands

### AI Strategy Advisor Commands

*   `/analyze <SYMBOL>` - Get AI-generated trading strategy for any symbol.
    ```
    🤖 Strategy for BTCUSDC
    
    Action: LONG (Confidence: 75%)
    Entry: 65000.0
    TP: 70000.0
    SL: 62000.0
    
    Reasoning: RSI shows oversold conditions with positive MACD divergence. 
    Recent institutional adoption news supports bullish sentiment.
    [📜 View Analysis Details]
    ```
    The "View Analysis Details" button reveals:
    - Technical indicators (RSI, MACD, Bollinger Bands, EMA values)
    - News headlines used in analysis
    - Past performance on this symbol
    - Lessons from previous failures

*   `/history` - Show AI strategy performance statistics.
    ```
    📊 Performance History
    
    Total Analysis: 42
    Wins: 28
    Losses: 14
    Win Rate: 66.7%
    Avg PnL: 3.24%
    ```

### Volume Alert Management Commands

*   `/help` - Show a list of available commands.
    ```
    Available commands:
    /start - Start the bot
    /help - Show this help message
    /analyze <SYMBOL> - Get AI strategy for a symbol
    /history - Show trading performance stats
    /list_restricted - List all restricted trading pairs
    /unrestrict <SYMBOL> - Unrestrict a specific trading pair
    ```

*   `/list_restricted` - List all currently restricted trading pairs.
    ```
    Restricted pairs:
    BATUSDC
    ELFBTC
    MATICBTC
    SNTBTC
    ```

*   `/unrestrict <SYMBOL>` - Unrestrict a specific trading pair. Replace `<SYMBOL>` with the actual trading pair (e.g., `/unrestrict ELFBTC`).
    ```
    Successfully unrestricted ELFBTC.
    ```

## Scheduling with Systemd on Ubuntu

To run the services as background processes on an Ubuntu system, you can use `systemd`. This provides robust process management, including automatic restarts and centralized logging.

### Option 1: AI Strategy Advisor Bot (Recommended)

This service runs the Telegram bot with all AI features including the background performance tracker.

Create `/etc/systemd/system/binance-strategy-bot.service`:

```bash
sudo nano /etc/systemd/system/binance-strategy-bot.service
```

Add the following content:

```ini
[Unit]
Description=Binance AI Strategy Advisor Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/your/volume_tracker_binance
ExecStart=/path/to/your/volume_tracker_binance/.venv/bin/python /path/to/your/volume_tracker_binance/telegram_bot_handler.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable binance-strategy-bot.service
sudo systemctl start binance-strategy-bot.service
```

**Check status and logs:**
```bash
sudo systemctl status binance-strategy-bot.service
sudo journalctl -u binance-strategy-bot.service -f
```

### Option 2: Volume Tracker Only

If you only need volume alerts without AI features:

Create `/etc/systemd/system/binance-volume-tracker.service`:

```ini
[Unit]
Description=Binance Volume Tracker
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/your/volume_tracker_binance
ExecStart=/path/to/your/volume_tracker_binance/.venv/bin/python /path/to/your/volume_tracker_binance/b_volume_alerts.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable binance-volume-tracker.service
sudo systemctl start binance-volume-tracker.service
```

### Running Both Services

To run both the AI Strategy Advisor AND the Volume Tracker simultaneously:

```bash
# Start both services
sudo systemctl start binance-strategy-bot.service
sudo systemctl start binance-volume-tracker.service

# Check both services
sudo systemctl status binance-strategy-bot.service
sudo systemctl status binance-volume-tracker.service

# View combined logs
sudo journalctl -u binance-strategy-bot.service -u binance-volume-tracker.service -f
```

### Service Management Commands

```bash
# Start a service
sudo systemctl start binance-strategy-bot.service

# Stop a service
sudo systemctl stop binance-strategy-bot.service

# Restart a service
sudo systemctl restart binance-strategy-bot.service

# View logs
sudo journalctl -u binance-strategy-bot.service -f

# View logs since last boot
sudo journalctl -u binance-strategy-bot.service --since today
```

## Deployment Automation (Server)

After a git pull on the server, run:

```bash
./scripts/deploy_after_pull.sh
```

To automatically run this after every `git pull`, install the post-merge hook once:

```bash
./scripts/install_post_merge_hook.sh
```

The hook runs `uv sync` and restarts both systemd services after each merge/pull.

## Project Structure

-   `b_volume_alerts.py`: Main script for fetching data, calculating alerts, and sending messages.
-   `alert_levels_tg.py`: Defines logic for volume alert levels.
-   `telegram_alerts.py`: Handles sending messages to Telegram, now with inline button support.
-   `symbol_manager.py`: Manages the loading, saving, adding, and removing of restricted trading pairs.
-   `telegram_bot_handler.py`: Handles all Telegram bot commands and callback queries for dynamic pair management.
-   `credentials_b.json`: Stores Binance API credentials and Telegram bot credentials (ignored by `.gitignore`).
-   `.gitignore`: Specifies files and directories to be ignored by Git.
-   `memory-bank/`: Contains project documentation and changelog.

## Changelog

Refer to `memory-bank/changelog.md` for a detailed history of changes.
