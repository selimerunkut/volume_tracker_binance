"""
Market Data Service - Fetches OHLCV data from Binance API
"""
import requests
import pandas as pd
from datetime import datetime

from src.exchanges.registry import get_exchange


def fetch_klines(symbol, interval='1h', limit=100, exchange_name='binance'):
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
    exchange = get_exchange(exchange_name)
    return exchange.fetch_klines(symbol, interval=interval, limit=limit)


def get_current_price(symbol, exchange_name='binance'):
    """
    Get current price for a symbol.
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDC')
    
    Returns:
        float: Current price, or None on error
    """
    exchange = get_exchange(exchange_name)
    return exchange.get_current_price(symbol)


def validate_trading_pair(symbol, exchange_name='binance'):
    exchange = get_exchange(exchange_name)
    return exchange.validate_symbol(symbol)


def _validate_symbol_with_ticker(symbol):
    url = f'https://api.binance.com/api/v3/ticker/price?symbol={symbol}'

    try:
        response = requests.get(url)
        if response.status_code == 400:
            return False, "invalid_symbol"
        response.raise_for_status()
        return True, None
    except requests.exceptions.RequestException as exc:
        if hasattr(exc, 'response') and exc.response is not None and exc.response.status_code == 400:
            return False, "invalid_symbol"
        return False, str(exc)


def get_top_volume_pairs(limit=20, quote_asset='USDC'):
    url = 'https://api.binance.com/api/v3/ticker/24hr'
    
    try:
        print(f"[{datetime.now()}] Fetching 24h ticker data...")
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        pairs = []
        for item in data:
            symbol = item['symbol']
            if symbol.endswith(quote_asset):
                pairs.append({
                    'symbol': symbol,
                    'volume': float(item['quoteVolume'])
                })
        
        pairs.sort(key=lambda x: x['volume'], reverse=True)
        
        return pairs[:limit]
        
    except Exception as e:
        print(f"[{datetime.now()}] Error fetching top volume pairs: {e}")
        return []


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
