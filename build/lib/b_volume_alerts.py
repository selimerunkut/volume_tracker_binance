import requests
import json
import sys # Import sys to access command-line arguments
from symbol_manager import SymbolManager
import pandas as pd
from binance.client import Client
import datetime
import time
from alert_levels_tg import get_volume_alert_details
from telegram_alerts import send_telegram_message  # Import the Telegram alert function

# File to store the state of sent alerts
STATE_FILE = 'alert_state.json'
COOLDOWN_PERIOD_HOURS = 1 # Cooldown period in hours to prevent duplicate alerts

def load_alert_state():
    """Loads the last_alert_timestamps from a JSON file."""
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            # Convert string timestamps back to datetime objects
            loaded_timestamps = {}
            for key_str, alert_data in state.items():
                symbol, level = key_str.split('___')
                loaded_timestamps[(symbol, level)] = {
                    'timestamp': datetime.datetime.fromisoformat(alert_data['timestamp']),
                    'volume': float(alert_data['volume'])
                }
            print(f"[{datetime.datetime.now()}] Loaded alert state from {STATE_FILE}.")
            return loaded_timestamps
    except FileNotFoundError:
        print(f"[{datetime.datetime.now()}] Alert state file not found. Starting with empty state.")
        return {}
    except json.JSONDecodeError as e:
        print(f"[{datetime.datetime.now()}] Error decoding alert state file: {e}. Starting with empty state.")
        return {}
    except Exception as e:
        print(f"[{datetime.datetime.now()}] An unexpected error occurred while loading alert state: {e}. Starting with empty state.")
        return {}

def save_alert_state(timestamps):
    """Saves the last_alert_timestamps to a JSON file."""
    try:
        # Convert datetime objects to string timestamps for JSON serialization
        serializable_timestamps = {
            f"{symbol}___{level}": {
                'timestamp': data['timestamp'].isoformat(),
                'volume': data['volume']
            }
            for (symbol, level), data in timestamps.items()
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(serializable_timestamps, f, indent=4)
        print(f"[{datetime.datetime.now()}] Saved alert state to {STATE_FILE}.")
    except Exception as e:
        print(f"[{datetime.datetime.now()}] Error saving alert state: {e}")


def generate_tradingview_url(symbol):
    # TradingView URL format
    return f"https://www.tradingview.com/symbols/{symbol}/?exchange=BINANCE"

def generate_binance_trade_url(symbol):
    # Binance trade URL format
    # Example: https://www.binance.com/en/trade/AUCTION_USDC
    # The symbol from the client.get_exchange_info() is already in the correct format (e.g., "AUCTIONUSDC")
    # We need to insert an underscore before the quote asset (USDC)
    if symbol.endswith('USDC'):
        base_asset = symbol[:-4]
        return f"https://www.binance.com/en/trade/{base_asset}_USDC"
    elif symbol.endswith('BTC'):
        base_asset = symbol[:-3]
        return f"https://www.binance.com/en/trade/{base_asset}_BTC"
    return f"https://www.binance.com/en/trade/{symbol}"

def create_alert_message(alert_detail, last_2h_volume, last_4h_volume, last_completed_hour_volume, open_price, close_price, symbol):
   """
   Constructs the alert message dictionary.
   """
   tradingview_url = generate_tradingview_url(symbol)
   binance_trade_url = generate_binance_trade_url(symbol)

   return {
       'exchange': 'BINANCE',
       'symbol': symbol,
       'curr_volume': alert_detail['curr_volume'],
       'prev_volume_mean': alert_detail['prev_volume_mean'],
       'level': alert_detail['level'],
       'last_2h_volume': last_2h_volume,
       'last_4h_volume': last_4h_volume,
       'last_1h_volume': last_completed_hour_volume, # Add last 1h volume
       'open_price': f"{open_price:.8f}", # Format as string with high precision
       'close_price': f"{close_price:.8f}", # Format as string with high precision
       'chart_url': tradingview_url,
       'binance_trade_url': binance_trade_url
   }

def is_duplicate_alert(symbol, level, curr_volume):
    """
    Checks if an alert for the given symbol and level was sent within the cooldown period,
    and if the current volume is not a significant new surge.
    """
    key = (symbol, level)
    print(f"[{datetime.datetime.now()}] DEBUG: Checking for duplicate alert for key: {key}")
    if key in last_alert_timestamps:
        alert_data = last_alert_timestamps[key]
        last_sent_time = alert_data['timestamp']
        last_sent_volume = alert_data['volume']
        time_since_last_alert = datetime.datetime.now() - last_sent_time
        print(f"[{datetime.datetime.now()}] DEBUG: Last sent time for {key}: {last_sent_time}, Last sent volume: {last_sent_volume}, Time since: {time_since_last_alert}")

        if time_since_last_alert < datetime.timedelta(hours=COOLDOWN_PERIOD_HOURS):
            # If within cooldown, check if current volume is significantly higher than the last sent volume
            # Define "significantly higher" as 10% for now, this can be adjusted
            if curr_volume <= last_sent_volume * 1.10:
                print(f"[{datetime.datetime.now()}] DEBUG: Duplicate alert detected for {key} (within cooldown and not significantly higher volume). Skipping.")
                return True
            else:
                print(f"[{datetime.datetime.now()}] DEBUG: New surge detected for {key} (volume significantly higher). Proceeding despite cooldown.")
                return False # Not a duplicate, proceed
        else:
            print(f"[{datetime.datetime.now()}] DEBUG: Cooldown period expired for {key}. Proceeding.")
            return False # Cooldown expired, proceed
    print(f"[{datetime.datetime.now()}] DEBUG: No previous alert detected for {key}. Proceeding.")
    return False

def get_filtered_symbols(client, quote_asset):
    """
    Fetches all symbols from Binance and filters them by quote asset,
    excluding leveraged tokens.
    """
    symbols = client.get_exchange_info()['symbols']
    filtered_pairs = [
        s['symbol'] for s in symbols
        if (s['quoteAsset'] == quote_asset)
        and 'UP' not in s['symbol']
        and 'DOWN' not in s['symbol']
        and 'BEAR' not in s['symbol']
        and 'BULL' not in s['symbol']
    ]
    return filtered_pairs

def run_script(dry_run=False):
    # Load the persistent alert state at the beginning of the script run
    global last_alert_timestamps
    last_alert_timestamps = load_alert_state()
    print(f"[{datetime.datetime.now()}] Starting run_script...")
    # Load Binance credentials
    with open('credentials_b.json') as f:
        credentials = json.load(f)
    api_key = credentials['Binance_api_key']
    api_secret = credentials['Binance_secret_key']
    client = Client(api_key, api_secret)
    
    # Fetch symbols for analysis using the new helper function
    symbol_manager = SymbolManager()
    excluded_symbols = symbol_manager.get_excluded_symbols()

    usdc_pairs = [s for s in get_filtered_symbols(client, 'USDC') if s not in excluded_symbols]
    btc_pairs = [s for s in get_filtered_symbols(client, 'BTC') if s not in excluded_symbols]
                   
    all_pairs = usdc_pairs + btc_pairs
    
    print(f"[{datetime.datetime.now()}] Fetched {len(usdc_pairs)} USDC pairs and {len(btc_pairs)} BTC pairs. Total: {len(all_pairs)} pairs.")
    
    for symbol in all_pairs:
        interval = '1h'
        limit = 10 # Fetch enough data for current volume and a 6-hour mean (last 7 candles)
                   # A limit of 10 for '1h' interval means it fetches the last 10 hours of data.
        url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
        print(f"[{datetime.datetime.now()}] Fetching data for {symbol}...")
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            #print(f"[{datetime.datetime.now()}] DEBUG: Type of klines data: {type(data)}")
            #print(f"[{datetime.datetime.now()}] DEBUG: Klines data: {data}") # Uncomment for full data inspection if needed
            df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "close_time", "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df["open"] = pd.to_numeric(df["open"])
            df["close"] = pd.to_numeric(df["close"])
            df["volume"] = pd.to_numeric(df["volume"])
            
            # Debugging: Print DataFrame head and dtypes to inspect data after conversion
            # print(f"[{datetime.datetime.now()}] DEBUG: DataFrame head for {symbol}:\n{df.head()}")
            # print(f"[{datetime.datetime.now()}] DEBUG: DataFrame dtypes for {symbol}:\n{df.dtypes}")

            if len(df) > 2:
                # Current volume is the volume of the currently forming candle
                curr_volume = df['volume'].iloc[-1]
                # Volume of the last completed hour
                last_completed_hour_volume = df['volume'].iloc[-2]
                # Calculate the mean of the 6 hours before the last completed hour
                # This means taking candles from index -8 up to (but not including) -2
                prev_volume_mean = df['volume'].iloc[-8:-2].mean()

                # Calculate last 2-hour and 4-hour volumes
                # Ensure there are enough data points for these calculations
                last_2h_volume = df['volume'].iloc[-3:-1].sum() if len(df) >= 3 else 0
                last_4h_volume = df['volume'].iloc[-5:-1].sum() if len(df) >= 5 else 0

                print(f"[{datetime.datetime.now()}] {symbol}: Current Volume = {curr_volume}, Previous 6h Mean Volume = {prev_volume_mean}, Last 2h Volume = {last_2h_volume}, Last 4h Volume = {last_4h_volume}")
                
                open_price = df['open'].iloc[-1]
                close_price = df['close'].iloc[-1]
                alert_details_list = get_volume_alert_details(curr_volume, prev_volume_mean, last_completed_hour_volume, open_price, close_price, symbol, '1h', 'BINANCE')

                if alert_details_list:
                    print(f"[{datetime.datetime.now()}] Alerts generated for {symbol}: {len(alert_details_list)}")
                else:
                    print(f"[{datetime.datetime.now()}] No alerts for {symbol}.")
                    
            for alert_detail in alert_details_list:
                symbol = alert_detail['symbol']
                level = alert_detail['level']
                
                # Check if the symbol is in the restricted list before proceeding
                if symbol_manager.is_symbol_excluded(symbol):
                    print(f"[{datetime.datetime.now()}] Skipping alert for restricted symbol: {symbol}")
                    continue

                if is_duplicate_alert(symbol, level, curr_volume):
                    # The DEBUG print inside is_duplicate_alert is sufficient
                    continue # Skip sending this alert

                else: # Only proceed if it's NOT a duplicate
                    alert_message = create_alert_message(alert_detail, last_2h_volume, last_4h_volume, last_completed_hour_volume, open_price, close_price, symbol)
                    print(f"[{datetime.datetime.now()}] Sending Telegram message for {symbol} (Level: {level})...")
                    # Always call send_telegram_message, let it handle dry_run internally
                    if send_telegram_message(alert_message, include_restrict_button=True, dry_run=dry_run):
                        # Update the timestamp for this alert and save the state ONLY if actually sent (not dry_run)
                        if not dry_run:
                            time.sleep(1)
                            last_alert_timestamps[(symbol, level)] = {
                                'timestamp': datetime.datetime.now(),
                                'volume': curr_volume
                            }
                            print(f"[{datetime.datetime.now()}] DEBUG: Alert sent and timestamp updated for {symbol} (Level: {level}).")
                            save_alert_state(last_alert_timestamps)
                    

        except requests.exceptions.RequestException as e:
            print(f"[{datetime.datetime.now()}] Error fetching data for {symbol}: {e}")
        except ValueError as e:
            print(f"[{datetime.datetime.now()}] Error processing data for {symbol}: {e}")
        except Exception as e:
            print(f"[{datetime.datetime.now()}] An unexpected error occurred for {symbol}: {e}")


if __name__ == "__main__":
    # Check for a dry-run argument
    is_dry_run = '--dry-run' in sys.argv
    if is_dry_run:
        print(f"[{datetime.datetime.now()}] Running in DRY-RUN mode. Telegram messages will not be sent.")
    
    run_script(dry_run=is_dry_run)
