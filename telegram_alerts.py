# telegram_alerts.py
import requests
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

def send_telegram_message(alert_message, include_restrict_button=False):
    # Use the globally loaded TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
    bot_token = TELEGRAM_BOT_TOKEN
    chat_id = TELEGRAM_CHAT_ID

    symbol = alert_message['symbol']
    curr_volume = int(alert_message['curr_volume']) # Format as integer
    prev_volume_mean = int(alert_message['prev_volume_mean']) # Format as integer
    level = alert_message['level']
    chart_url = alert_message['chart_url']
    binance_trade_url = alert_message['binance_trade_url']
    last_2h_volume = int(alert_message['last_2h_volume']) # Format as integer
    last_4h_volume = int(alert_message['last_4h_volume']) # Format as integer
    last_1h_volume = int(alert_message['last_1h_volume']) # Format as integer

    message_text = (
        f"🚨 *Volume Alert - {symbol}* 🚨\n"
        f"📊 Current Volume: {curr_volume:,}\n"
        f"📈 Previous 6h Mean Volume: {prev_volume_mean:,}\n"
        f"🕐 Last 1h Volume: {last_1h_volume:,}\n" # Add last 1h volume
        f"🕒 Last 2h Volume: {last_2h_volume:,}\n"
        f"🕓 Last 4h Volume: {last_4h_volume:,}\n"
        f"🔥 Alert Level: *{level}*\n"
        f"🔗 {chart_url}\n"
        f"🔗 {binance_trade_url}"
    )

    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message_text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }

    if include_restrict_button and symbol:
        keyboard = [[InlineKeyboardButton(f"Restrict {symbol}", callback_data=f"restrict_{symbol}")]]
        reply_markup = InlineKeyboardMarkup(keyboard).to_json()
        payload['reply_markup'] = reply_markup
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        response_json = response.json()
        if response_json.get("ok"):
            print(f"[{datetime.datetime.now()}] Telegram message sent successfully for {symbol}.")
            return True
        else:
            print(f"[{datetime.datetime.now()}] Failed to send Telegram message for {symbol}. Error: {response_json.get('description')}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.datetime.now()}] Network error sending Telegram message for {symbol}: {e}")
        return False
    except ValueError as e:
        print(f"[{datetime.datetime.now()}] JSON decoding error for Telegram API response for {symbol}: {e}")
        return False
    except Exception as e:
        print(f"[{datetime.datetime.now()}] An unexpected error occurred while sending Telegram message for {symbol}: {e}")
        return False

if __name__ == "__main__":
    # Example test message for the updated function (no longer needs to check 'ok' field here)
    test_alert_message = {
        'exchange': 'BINANCE',
        'symbol': 'TESTUSDC',
        'curr_volume': 183717.2,
        'prev_volume_mean': 33930.8652173913,
        'last_1h_volume': 99999, # Example value for testing
        'last_2h_volume': 123456, # Example value for testing
        'last_4h_volume': 789012, # Example value for testing
        'level': 'HIGH',
        'chart_url': 'https://www.tradingview.com/symbols/TESTUSDC/?exchange=BINANCE',
        'binance_trade_url': 'https://www.binance.com/en/trade/TEST_USDC'
    }
    print(f"Attempting to send test alert message for '{test_alert_message['symbol']}'")
    send_telegram_message(test_alert_message) # The function now prints its own success/failure