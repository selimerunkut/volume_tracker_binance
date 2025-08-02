# telegram_alerts.py
import requests
import json
import datetime # Import datetime for timestamping error messages

def load_telegram_credentials():
    with open('credentials_telegram.json') as f:
        credentials = json.load(f)
    return credentials

def send_telegram_message(alert_message):
    credentials = load_telegram_credentials()
    bot_token = credentials['Telegram_bot_token']
    chat_id = credentials['Telegram_chat_id']

    symbol = alert_message['symbol']
    curr_volume = int(alert_message['curr_volume']) # Format as integer
    prev_volume_mean = int(alert_message['prev_volume_mean']) # Format as integer
    level = alert_message['level']
    chart_url = alert_message['chart_url']
    binance_trade_url = alert_message['binance_trade_url']

    message_text = (
        f"🚨 *Volume Alert - {symbol}* 🚨\n"
        f"📊 Current Volume: `{curr_volume:,}`\n"
        f"📈 Previous 24h Mean Volume: `{prev_volume_mean:,}`\n"
        f"🔥 Alert Level: *{level}*\n"
        f"🔗 {chart_url}\n"
        f"🔗 {binance_trade_url}"
    )

    send_text = f'https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={chat_id}&parse_mode=HTML&text={message_text}&disable_web_page_preview=True'
    
    try:
        response = requests.get(send_text)
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
        'level': 'HIGH',
        'chart_url': 'https://www.tradingview.com/symbols/TESTUSDC/?exchange=BINANCE',
        'binance_trade_url': 'https://www.binance.com/en/trade/TEST_USDC'
    }
    print(f"Attempting to send test alert message for '{test_alert_message['symbol']}'")
    send_telegram_message(test_alert_message) # The function now prints its own success/failure