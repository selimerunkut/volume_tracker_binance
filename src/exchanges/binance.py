"""Binance exchange adapter."""

from __future__ import annotations

import datetime

import pandas as pd
import requests

from src.services.binance_permissions_service import permissions_service
from src.services.volume_alerts import generate_trade_url, generate_tradingview_url

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
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


class BinanceExchange:
    name = 'binance'
    display_name = 'BINANCE'

    def fetch_klines(self, symbol, interval='1h', limit=100):
        url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
        try:
            print(f"[{datetime.datetime.now()}] Fetching data for {symbol} on Binance...")
            response = requests.get(url)
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
            response = requests.get(url)
            if response.status_code == 400:
                return None
            response.raise_for_status()
            return float(response.json()['price'])
        except Exception:
            return None

    def validate_symbol(self, symbol):
        permission_result = permissions_service.can_trade_symbol(symbol)
        if permission_result is not None:
            return permission_result

        url = f'https://api.binance.com/api/v3/ticker/price?symbol={symbol}'
        try:
            response = requests.get(url)
            if response.status_code == 400:
                return False, "invalid_symbol"
            response.raise_for_status()
            return True, None
        except Exception as exc:
            return False, str(exc)

    def list_symbols(self, quote_asset=None):
        url = 'https://api.binance.com/api/v3/exchangeInfo'
        response = requests.get(url)
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
            if (quote_asset is None or item['quoteAsset'] == quote_asset)
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
