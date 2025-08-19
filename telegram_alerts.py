# telegram_alerts.py
import aiohttp # Import aiohttp for asynchronous HTTP requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import json
import datetime # Import datetime for timestamping error messages

# Load Telegram bot token and chat ID from credentials_b.json
def load_telegram_credentials():
    try:
        with open('credentials_b.json', 'r') as f:
            credentials = json.load(f)
            return credentials.get('telegram_bot_token'), credentials.get('telegram_chat_id')
    except FileNotFoundError:
        print(f"[{datetime.datetime.now()}] credentials_b.json not found. Please create it with 'telegram_bot_token' and 'telegram_chat_id'.")
        return None, None
    except json.JSONDecodeError as e:
        print(f"[{datetime.datetime.now()}] Error decoding credentials_b.json: {e}")
        return None, None

TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID = load_telegram_credentials()

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print(f"[{datetime.datetime.now()}] Telegram bot token or chat ID not found. Alerts will not be sent.")

from typing import Union, Dict, Any, Optional # Import Union, Dict, Any, Optional

async def send_telegram_message(chat_id: str, message_content: Union[str, Dict[str, Any]], include_restrict_button: bool = False, dry_run: bool = False):
    # Use the globally loaded TELEGRAM_BOT_TOKEN
    bot_token = TELEGRAM_BOT_TOKEN
    
    message_text = ""
    symbol = None

    if isinstance(message_content, str):
        message_text = message_content
    elif isinstance(message_content, dict):
        # Original volume alert logic
        symbol = message_content.get('symbol')
        curr_volume = int(message_content.get('curr_volume', 0))
        prev_volume_mean = int(message_content.get('prev_volume_mean', 0))
        level = message_content.get('level', 'UNKNOWN')
        chart_url = message_content.get('chart_url', '')
        binance_trade_url = message_content.get('binance_trade_url', '')
        last_2h_volume = int(message_content.get('last_2h_volume', 0))
        last_4h_volume = int(message_content.get('last_4h_volume', 0))
        last_1h_volume = int(message_content.get('last_1h_volume', 0))
        open_price = message_content.get('open_price', 'N/A')
        close_price = message_content.get('close_price', 'N/A')

        message_text = (
            f"🚨 *Volume Alert - {symbol}* 🚨\n"
            f"📊 Current Volume: {curr_volume:,}\n"
            f"📈 Previous 6h Mean Volume: {prev_volume_mean:,}\n"
            f"🕐 Last 1h Volume: {last_1h_volume:,}\n"
            f"🕒 Last 2h Volume: {last_2h_volume:,}\n"
            f"🕓 Last 4h Volume: {last_4h_volume:,}\n"
            f"💹 Last 1h Vol\\. candle Prices, Open: {open_price}, Close: {close_price}\n" # Escaped dot for MarkdownV2
            f"🔥 Alert Level: *{level}*\n"
            f"🔗 {chart_url}\n"
            f"🔗 {binance_trade_url}"
        )
    else:
        print(f"[{datetime.datetime.now()}] Invalid message_content type: {type(message_content)}. Expected str or dict.")
        return False

    # No change needed here, the message_text is constructed above

    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    
    payload = {
        'chat_id': chat_id, # Use the passed chat_id
        'text': message_text,
        'parse_mode': 'MarkdownV2', # Changed to MarkdownV2 for better formatting control
        'disable_web_page_preview': True
    }

    if include_restrict_button and symbol:
        keyboard = [[InlineKeyboardButton(f"Restrict {symbol}", callback_data=f"restrict_{symbol}")]]
        reply_markup = InlineKeyboardMarkup(keyboard).to_json()
        payload['reply_markup'] = reply_markup
    
    if dry_run:
        print(f"[{datetime.datetime.now()}] DRY RUN: Telegram message would have been sent to {chat_id}. Message details: {message_text}")
        return True # Indicate success for dry run
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
                response_json = await response.json()
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        # response_json is already obtained above
        if response_json.get("ok"):
            print(f"[{datetime.datetime.now()}] Telegram message sent successfully to {chat_id}.")
            return True
        else:
            print(f"[{datetime.datetime.now()}] Failed to send Telegram message to {chat_id}. Error: {response_json.get('description')}")
            return False
    except aiohttp.ClientError as e:
        print(f"[{datetime.datetime.now()}] Network error sending Telegram message to {chat_id}: {e}")
        return False
    except ValueError as e:
        print(f"[{datetime.datetime.now()}] JSON decoding error for Telegram API response to {chat_id}: {e}")
        return False
    except Exception as e:
        print(f"[{datetime.datetime.now()}] An unexpected error occurred while sending Telegram message to {chat_id}: {e}")
        return False

if __name__ == "__main__":
    # Example test message for the updated function
    test_chat_id = "YOUR_TEST_CHAT_ID"  # Replace with a valid chat ID for testing

    # Example 1: Simple message
    print(f"Attempting to send simple test message to '{test_chat_id}'")
    asyncio.run(send_telegram_message(test_chat_id, "Hello from the updated `send_telegram_message` function!"))

    # Example 2: Volume alert message
    test_alert_message = {
        'exchange': 'BINANCE',
        'symbol': 'TEST/USDT',
        'curr_volume': 183717.2,
        'prev_volume_mean': 33930.8652173913,
        'last_1h_volume': 99999,
        'last_2h_volume': 123456,
        'last_4h_volume': 789012,
        'level': 'HIGH',
        'chart_url': 'https://www.tradingview.com/symbols/TESTUSDT/?exchange=BINANCE',
        'binance_trade_url': 'https://www.binance.com/en/trade/TEST_USDT',
        'open_price': '1.00',
        'close_price': '1.05'
    }
    print(f"\nAttempting to send volume alert test message for '{test_alert_message['symbol']}' to '{test_chat_id}'")
    asyncio.run(send_telegram_message(test_chat_id, test_alert_message, include_restrict_button=True))