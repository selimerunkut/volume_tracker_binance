import requests
import json
import sys # Import sys to access command-line arguments
from symbol_manager import SymbolManager
import pandas as pd
import datetime
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from alert_levels_tg import get_volume_alert_details
from telegram_alerts import send_telegram_message
from telegram_alerts import TELEGRAM_CHAT_ID
from src.exchanges.registry import get_exchanges_for_scope
from src.services.alert_preferences import get_alert_exchange_selection
from src.services.volume_alerts import build_volume_alert_message
from src.services.binance_permissions_service import permissions_service
from src.services.db_service import get_setting


# File to store the state of sent alerts
STATE_FILE = 'alert_state.json'
COOLDOWN_PERIOD_HOURS = 1 # Cooldown period in hours to prevent duplicate alerts
CLEANUP_PERIOD_DAYS = 1 # Days after which to remove old alert entries

def load_alert_state():
    """
    Loads the last_alert_timestamps from a JSON file and cleans up old entries.
    """
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            # Convert string timestamps back to datetime objects
            loaded_timestamps = {}
            for key_str, alert_data in state.items():
                try:
                    exchange_name, symbol, level = key_str.split('___')
                except ValueError:
                    print(f"[{datetime.datetime.now()}] Skipping legacy or malformed alert state key: {key_str}")
                    continue
                loaded_timestamps[(exchange_name, symbol, level)] = {
                    'timestamp': datetime.datetime.fromisoformat(alert_data['timestamp']),
                    'volume': float(alert_data['volume'])
                }
            print(f"[{datetime.datetime.now()}] Loaded alert state from {STATE_FILE}.")

            # Clean up old entries
            now = datetime.datetime.now()
            cutoff = now - datetime.timedelta(days=CLEANUP_PERIOD_DAYS)
            cleaned_timestamps = {}
            removed_count = 0
            for key, alert_data in loaded_timestamps.items():
                if alert_data['timestamp'] > cutoff:
                    cleaned_timestamps[key] = alert_data
                else:
                    removed_count += 1
            
            if removed_count > 0:
                print(f"[{datetime.datetime.now()}] Cleaned up {removed_count} old alert(s) older than {CLEANUP_PERIOD_DAYS} days.")
                # Save the cleaned state back to the file immediately
                save_alert_state(cleaned_timestamps)

            return cleaned_timestamps
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
            f"{exchange_name}___{symbol}___{level}": {
                'timestamp': data['timestamp'].isoformat(),
                'volume': data['volume']
            }
            for (exchange_name, symbol, level), data in timestamps.items()
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(serializable_timestamps, f, indent=4)
        print(f"[{datetime.datetime.now()}] Saved alert state to {STATE_FILE}.")
    except Exception as e:
        print(f"[{datetime.datetime.now()}] Error saving alert state: {e}")


def get_scan_quote_assets(exchange_name):
    exchange_name = (exchange_name or '').lower()
    if exchange_name == 'kraken':
        return ['USD', 'BTC']
    return ['USDC', 'BTC']


def get_filtered_symbols(exchange, quote_asset, excluded_symbols):
    """
    Fetches exchange symbols through the adapter and filters by quote asset,
    excluding leveraged tokens and restricted symbols.
    """
    pairs = exchange.list_symbols(quote_asset=quote_asset)
    filtered_pairs = [
        item.symbol for item in pairs
        if item.symbol not in excluded_symbols
        and 'UP' not in item.symbol
        and 'DOWN' not in item.symbol
        and 'BEAR' not in item.symbol
        and 'BULL' not in item.symbol
    ]
    return filtered_pairs


def create_alert_message(
    alert_detail,
    last_2h_volume,
    last_4h_volume,
    last_completed_hour_volume,
    open_price,
    close_price,
    symbol,
    exchange,
):
   """
   Constructs the alert message dictionary.
   """
   return build_volume_alert_message(
       alert_detail,
       last_2h_volume,
       last_4h_volume,
       last_completed_hour_volume,
       open_price,
       close_price,
       symbol,
        exchange=exchange.display_name,
        chart_url=exchange.tradingview_url(symbol),
        trade_url=exchange.trade_url(symbol),
    )

def scan_exchange(exchange, symbol_manager, excluded_symbols, dry_run, alerts_enabled, telegram_send_lock):
    print(f"[{datetime.datetime.now()}] Starting scan on {exchange.display_name}...")

    allowed_symbols = permissions_service.get_allowed_symbols() if exchange.name == 'binance' else None
    if allowed_symbols is True:
        allowed_symbols = None

    quote_assets = get_scan_quote_assets(exchange.name)
    exchange_pairs = []
    for quote_asset in quote_assets:
        fetched_pairs = get_filtered_symbols(exchange, quote_asset, excluded_symbols)
        exchange_pairs.extend(fetched_pairs)
        print(f"[{datetime.datetime.now()}] Fetched {len(fetched_pairs)} {quote_asset} pairs from {exchange.display_name}.")

    if exchange.name == 'binance' and allowed_symbols:
        trading_group_label = permissions_service.trading_group or 'your trading group'
        filtered_pairs = [s for s in exchange_pairs if s in allowed_symbols]
        print(f"[{datetime.datetime.now()}] {len(filtered_pairs)} of {len(exchange_pairs)} pairs match trading group {trading_group_label}.")
        exchange_pairs = filtered_pairs
    elif exchange.name == 'binance' and allowed_symbols is None:
        print(f"[{datetime.datetime.now()}] Unable to retrieve trading-group permissions; volume alerts will consider all fetched pairs.")
    elif exchange.name == 'binance' and not allowed_symbols:
        print(f"[{datetime.datetime.now()}] No tradable pairs returned for {permissions_service.trading_group or 'the trading group'}; skipping permission filtering.")

    print(f"[{datetime.datetime.now()}] Scanning {len(exchange_pairs)} pairs on {exchange.display_name}.")

    sent_alerts = []
    for symbol in exchange_pairs:
        interval = '1h'
        limit = 10 # Fetch enough data for current volume and a 6-hour mean (last 7 candles)
                   # A limit of 10 for '1h' interval means it fetches the last 10 hours of data.
        print(f"[{datetime.datetime.now()}] Fetching data for {symbol} on {exchange.display_name}...")
        try:
            df = exchange.fetch_klines(symbol, interval=interval, limit=limit)
            if df.empty:
                continue
            if len(df) <= 2:
                continue

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
            alert_details_list = get_volume_alert_details(
                curr_volume,
                prev_volume_mean,
                last_completed_hour_volume,
                open_price,
                close_price,
                symbol,
                '1h',
                exchange.display_name,
            )

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

                if is_duplicate_alert(exchange.name, symbol, level, curr_volume):
                    # The DEBUG print inside is_duplicate_alert is sufficient
                    continue # Skip sending this alert

                if not alerts_enabled:
                    print(f"[{datetime.datetime.now()}] Skipping Telegram message for {symbol} - Alerts are DISABLED in settings.")
                    continue

                alert_message = create_alert_message(
                    alert_detail,
                    last_2h_volume,
                    last_4h_volume,
                    last_completed_hour_volume,
                    open_price,
                    close_price,
                    symbol,
                    exchange,
                )

                print(f"[{datetime.datetime.now()}] Sending Telegram message for {symbol} (Level: {level})...")
                with telegram_send_lock:
                    sent = send_telegram_message(alert_message, include_restrict_button=True, dry_run=dry_run)
                    if sent and not dry_run:
                        time.sleep(1)

                if sent and not dry_run:
                    sent_alerts.append((exchange.name, symbol, level, curr_volume))
                    print(f"[{datetime.datetime.now()}] DEBUG: Alert sent for {exchange.display_name} {symbol} (Level: {level}).")
        except ValueError as e:
            print(f"[{datetime.datetime.now()}] Error processing data for {exchange.display_name} {symbol}: {e}")
        except Exception as e:
            print(f"[{datetime.datetime.now()}] An unexpected error occurred for {exchange.display_name} {symbol}: {e}")

    return sent_alerts

def is_duplicate_alert(exchange_name, symbol, level, curr_volume):
    """
    Checks if an alert for the given symbol and level was sent within the cooldown period,
    and if the current volume is not a significant new surge.
    """
    key = (exchange_name, symbol, level)
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

def run_script(dry_run=False):
    # Load the persistent alert state at the beginning of the script run
    global last_alert_timestamps
    last_alert_timestamps = load_alert_state()
    print(f"[{datetime.datetime.now()}] Starting run_script...")
    symbol_manager = SymbolManager()
    excluded_symbols = symbol_manager.get_excluded_symbols()

    selection = get_alert_exchange_selection(TELEGRAM_CHAT_ID)
    exchanges = get_exchanges_for_scope(selection)
    print(f"[{datetime.datetime.now()}] Selected exchanges: {', '.join(exchange.display_name for exchange in exchanges)}")
    alerts_enabled = get_setting("volume_alerts_enabled", "True") != "False"
    telegram_send_lock = threading.Lock()
    sent_alerts = []

    if len(exchanges) > 1:
        with ThreadPoolExecutor(max_workers=len(exchanges)) as executor:
            futures = [
                executor.submit(
                    scan_exchange,
                    exchange,
                    symbol_manager,
                    excluded_symbols,
                    dry_run,
                    alerts_enabled,
                    telegram_send_lock,
                )
                for exchange in exchanges
            ]
            for future in as_completed(futures):
                sent_alerts.extend(future.result())
    else:
        for exchange in exchanges:
            sent_alerts.extend(
                scan_exchange(
                    exchange,
                    symbol_manager,
                    excluded_symbols,
                    dry_run,
                    alerts_enabled,
                    telegram_send_lock,
                )
            )

    if sent_alerts and not dry_run:
        for exchange_name, symbol, level, curr_volume in sent_alerts:
            last_alert_timestamps[(exchange_name, symbol, level)] = {
                'timestamp': datetime.datetime.now(),
                'volume': curr_volume
            }
        save_alert_state(last_alert_timestamps)


if __name__ == "__main__":
    # Check for a dry-run argument
    is_dry_run = '--dry-run' in sys.argv
    if is_dry_run:
        print(f"[{datetime.datetime.now()}] Running in DRY-RUN mode. Telegram messages will not be sent.")
    
    run_script(dry_run=is_dry_run)
