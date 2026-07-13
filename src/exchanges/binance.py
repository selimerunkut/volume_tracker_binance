"""Binance exchange adapter."""

from __future__ import annotations

import datetime

import pandas as pd
import requests
from functools import lru_cache

from src.services.binance_permissions_service import permissions_service
from src.services.volume_alerts import generate_trade_url, generate_tradingview_url
from src.services.quote_value_service import rate_from_bid_ask

from .base import ExchangeSymbol


def _build_klines_df(data):
    df = pd.DataFrame(
        data,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume",
            "ignore",
        ],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["open"] = pd.to_numeric(df["open"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])
    df["close"] = pd.to_numeric(df["close"])
    df["volume"] = pd.to_numeric(df["volume"])
    df["quote_volume"] = pd.to_numeric(df["quote_asset_volume"])
    return df[["timestamp", "open", "high", "low", "close", "volume", "quote_volume"]]


class BinanceExchange:
    name = 'binance'
    display_name = 'BINANCE'
    request_timeout = 10

    def fetch_klines(self, symbol, interval='1h', limit=100):
        url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
        try:
            print(f"[{datetime.datetime.now()}] Fetching data for {symbol} on Binance...")
            response = requests.get(url, timeout=self.request_timeout)
            if response.status_code == 400:
                print(f"[{datetime.datetime.now()}] Invalid symbol or parameter error for {symbol} (HTTP 400)")
                return pd.DataFrame()
            response.raise_for_status()
            return _build_klines_df(response.json())
        except Exception as exc:
            print(f"[{datetime.datetime.now()}] Unexpected error fetching Binance klines for {symbol}: {exc}")
            return pd.DataFrame()

    def get_current_price(self, symbol):
        url = f'https://api.binance.com/api/v3/ticker/price?symbol={symbol}'
        try:
            response = requests.get(url, timeout=self.request_timeout)
            if response.status_code == 400:
                return None
            response.raise_for_status()
            return float(response.json()['price'])
        except Exception:
            return None

    def fetch_order_book(self, symbol, limit=50):
        response = requests.get(
            'https://api.binance.com/api/v3/depth',
            params={'symbol': symbol, 'limit': limit},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return {
            'bids': [(float(price), float(quantity)) for price, quantity in payload.get('bids', [])],
            'asks': [(float(price), float(quantity)) for price, quantity in payload.get('asks', [])],
        }

    def fetch_24h_quote_volume(self, symbol):
        response = requests.get(
            'https://api.binance.com/api/v3/ticker/24hr',
            params={'symbol': symbol},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        return float(response.json()['quoteVolume'])

    @lru_cache(maxsize=1)
    def _spot_symbols(self):
        response = requests.get('https://api.binance.com/api/v3/exchangeInfo', timeout=self.request_timeout)
        response.raise_for_status()
        return response.json().get('symbols', [])

    def quote_to_usd_rate(self, quote_asset):
        asset = str(quote_asset).upper()
        if asset in {'USD', 'USDC', 'USDT'}:
            return 1.0
        symbols = {
            str(item.get('symbol', '')).upper(): item
            for item in self._spot_symbols()
            if str(item.get('status', '')).upper() == 'TRADING'
        }
        candidates = [
            (f'{asset}USDT', False), (f'{asset}USDC', False), (f'{asset}USD', False),
            (f'USDT{asset}', True), (f'USDC{asset}', True), (f'USD{asset}', True),
        ]
        for symbol, inverse in candidates:
            item = symbols.get(symbol)
            base = str(item.get('baseAsset', '')).upper() if item else ''
            quote = str(item.get('quoteAsset', '')).upper() if item else ''
            if item and ((not inverse and base == asset and quote in {'USDT', 'USDC', 'USD'})
                         or (inverse and quote == asset and base in {'USDT', 'USDC', 'USD'})):
                try:
                    return rate_from_bid_ask(
                        *self._book_bid_ask(symbol), inverse=inverse,
                    )
                except (ValueError, KeyError):
                    continue
        return None

    def _book_bid_ask(self, symbol):
        response = requests.get(
            'https://api.binance.com/api/v3/ticker/bookTicker',
            params={'symbol': symbol}, timeout=self.request_timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data.get('bidPrice'), data.get('askPrice')

    def validate_symbol(self, symbol):
        permission_result = permissions_service.can_trade_symbol(symbol)
        if permission_result is not None:
            return permission_result

        url = f'https://api.binance.com/api/v3/ticker/price?symbol={symbol}'
        try:
            response = requests.get(url, timeout=self.request_timeout)
            if response.status_code == 400:
                return False, "invalid_symbol"
            response.raise_for_status()
            return True, None
        except Exception as exc:
            return False, str(exc)

    def list_symbols(self, quote_asset=None):
        url = 'https://api.binance.com/api/v3/exchangeInfo'
        response = requests.get(url, timeout=self.request_timeout)
        response.raise_for_status()
        symbols = response.json()['symbols']

        filtered_pairs = [
            ExchangeSymbol(
                symbol=item['symbol'],
                display_symbol=item['symbol'],
                base_asset=item['baseAsset'],
                quote_asset=item['quoteAsset'],
            )
            for item in symbols
            if str(item.get('status', 'TRADING')).upper() == 'TRADING'
            and (quote_asset is None or item['quoteAsset'] == quote_asset)
            and 'UP' not in item['symbol']
            and 'DOWN' not in item['symbol']
            and 'BEAR' not in item['symbol']
            and 'BULL' not in item['symbol']
        ]
        return filtered_pairs

    def tradingview_url(self, symbol):
        return generate_tradingview_url(symbol, self.display_name)

    def trade_url(self, symbol):
        return generate_trade_url(symbol, self.display_name)
