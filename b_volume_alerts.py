import requests
import json
import pandas as pd
from binance.client import Client
import datetime
import schedule
import time
from alert_levels_tg import get_volume_alert_details
from telegram_alerts import send_telegram_message  # Import the Telegram alert function


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

def run_script():
    print(f"[{datetime.datetime.now()}] Starting run_script...")
    # Load Binance credentials
    with open('credentials_b.json') as f:
        credentials = json.load(f)
    api_key = credentials['Binance_api_key']
    api_secret = credentials['Binance_secret_key']
    client = Client(api_key, api_secret)
    
    # Fetch symbols for analysis
    # Define specific symbols for testing
    # Note: Binance symbols typically do not use underscores (e.g., SAHARUSDC, SOPHUSDC, HEIUSDC)
    #usdc_pairs = ["SAHAR_USDC", "SOPH_USDC", "HEI_USDC"] # Example pairs provided by user
    # If you want to revert to fetching all USDC pairs, uncomment the lines below
    symbols = client.get_exchange_info()['symbols']
    
    usdc_pairs = [s['symbol'] for s in symbols if (s['quoteAsset'] == 'USDC') and 'UPUSDC' not in s['symbol']
                   and 'DOWNUSDC' not in s['symbol'] and 'BEARUSDC' not in s['symbol'] and 'BULLUSDC' not in s['symbol']]
    
    btc_pairs = [s['symbol'] for s in symbols if (s['quoteAsset'] == 'BTC') and 'UPBTC' not in s['symbol']
                   and 'DOWNBTC' not in s['symbol'] and 'BEARBTC' not in s['symbol'] and 'BULLBTC' not in s['symbol']]
                   
    all_pairs = usdc_pairs + btc_pairs
    
    print(f"[{datetime.datetime.now()}] Fetched {len(usdc_pairs)} USDC pairs and {len(btc_pairs)} BTC pairs. Total: {len(all_pairs)} pairs.")
    
    for symbol in all_pairs:
        interval = '1h'
        limit = 25 # This specifies the number of historical klines (candlesticks) to fetch from the Binance API.
                   # A limit of 25 for '1h' interval means it fetches the last 25 hours of data.
        url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
        print(f"[{datetime.datetime.now()}] Fetching data for {symbol}...")
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "close_time", "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df["volume"] = pd.to_numeric(df["volume"])
            
            if len(df) > 2:
                curr_volume = df['volume'].iloc[-2]
                past_24_hours = df.iloc[:-2]['volume'].astype(float)
                prev_volume_mean = past_24_hours.mean()

                # Calculate last 2-hour and 4-hour volumes
                # Ensure there are enough data points for these calculations
                last_2h_volume = df['volume'].iloc[-3:-1].sum() if len(df) >= 3 else 0
                last_4h_volume = df['volume'].iloc[-5:-1].sum() if len(df) >= 5 else 0

                print(f"[{datetime.datetime.now()}] {symbol}: Current Volume = {curr_volume}, Previous 24h Mean Volume = {prev_volume_mean}, Last 2h Volume = {last_2h_volume}, Last 4h Volume = {last_4h_volume}")
                
                alert_details_list = get_volume_alert_details(curr_volume, prev_volume_mean, symbol, '1h', 'BINANCE')

                if alert_details_list:
                    print(f"[{datetime.datetime.now()}] Alerts generated for {symbol}: {len(alert_details_list)}")
                else:
                    print(f"[{datetime.datetime.now()}] No alerts for {symbol}.")
                    
            for alert_detail in alert_details_list:
                tradingview_url = generate_tradingview_url(alert_detail['symbol'])
                binance_trade_url = generate_binance_trade_url(alert_detail['symbol'])

                alert_message = {
                    'exchange': 'BINANCE',
                    'symbol': alert_detail['symbol'],
                    'curr_volume': alert_detail['curr_volume'],
                    'prev_volume_mean': alert_detail['prev_volume_mean'],
                    'level': alert_detail['level'],
                    'last_2h_volume': last_2h_volume,
                    'last_4h_volume': last_4h_volume,
                    'chart_url': tradingview_url,
                    'binance_trade_url': binance_trade_url
                }
                print(f"[{datetime.datetime.now()}] Sending Telegram message for {symbol} (Level: {alert_detail['level']})...")
                send_telegram_message(alert_message)

        except requests.exceptions.RequestException as e:
            print(f"[{datetime.datetime.now()}] Error fetching data for {symbol}: {e}")
        except ValueError as e:
            print(f"[{datetime.datetime.now()}] Error processing data for {symbol}: {e}")
        except Exception as e:
            print(f"[{datetime.datetime.now()}] An unexpected error occurred for {symbol}: {e}")

# # Schedule the script to run at the specified times
# for hour in range(24):
#     schedule.every().day.at("{:02d}:01".format(hour)).do(run_script)
#     print(f"[{datetime.datetime.now()}] Scheduled run_script at {hour:02d}:01 daily.")

# print(f"[{datetime.datetime.now()}] Starting scheduler. Press Ctrl+C to stop.")
# # Run the scheduled tasks indefinitely
# while True:
#     schedule.run_pending()
#     time.sleep(1)

if __name__ == "__main__":
    # This block will run the script once immediately for testing purposes.
    # You can remove this block after successful testing.
    run_script()
