"""
Market Data Service - Fetches OHLCV data from Binance API
"""
import requests
import pandas as pd
from datetime import datetime


def fetch_klines(symbol, interval='1h', limit=100):
    """
    Fetch OHLCV klines data from Binance API.
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDC')
        interval: Time interval (e.g., '1h', '4h', '1d')
        limit: Number of candles to fetch
    
    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume
        Returns empty DataFrame on error
    """
    url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
    
    try:
        print(f"[{datetime.now()}] Fetching data for {symbol}...")
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
        ])
        
        # Convert types
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["open"] = pd.to_numeric(df["open"])
        df["high"] = pd.to_numeric(df["high"])
        df["low"] = pd.to_numeric(df["low"])
        df["close"] = pd.to_numeric(df["close"])
        df["volume"] = pd.to_numeric(df["volume"])
        
        # Keep only essential columns
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        
        print(f"[{datetime.now()}] Successfully fetched {len(df)} candles for {symbol}")
        return df
        
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now()}] Request error fetching data for {symbol}: {e}")
        return pd.DataFrame()
    except ValueError as e:
        print(f"[{datetime.now()}] Value error processing data for {symbol}: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"[{datetime.now()}] Unexpected error fetching data for {symbol}: {e}")
        return pd.DataFrame()


def get_current_price(symbol):
    """
    Get current price for a symbol.
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDC')
    
    Returns:
        float: Current price, or None on error
    """
    url = f'https://api.binance.com/api/v3/ticker/price?symbol={symbol}'
    
    try:
        print(f"[{datetime.now()}] Fetching current price for {symbol}...")
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        price = float(data['price'])
        print(f"[{datetime.now()}] Current price for {symbol}: {price}")
        return price
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now()}] Request error fetching price for {symbol}: {e}")
        return None
    except (ValueError, KeyError) as e:
        print(f"[{datetime.now()}] Error parsing price for {symbol}: {e}")
        return None
    except Exception as e:
        print(f"[{datetime.now()}] Unexpected error fetching price for {symbol}: {e}")
        return None


if __name__ == "__main__":
    print(f"[{datetime.now()}] Testing Market Data Service...")
    
    df = fetch_klines("BTCUSDC", interval="1h", limit=10)
    if not df.empty:
        print(f"\n[{datetime.now()}] Klines DataFrame for BTCUSDC:")
        print(df)
        print(f"\n[{datetime.now()}] DataFrame info:")
        print(df.info())
    else:
        print(f"[{datetime.now()}] Failed to fetch klines")
    
    price = get_current_price("BTCUSDC")
    if price is not None:
        print(f"\n[{datetime.now()}] Current price test passed: {price}")
    else:
        print(f"[{datetime.now()}] Failed to fetch current price")
