"""Kraken exchange adapter."""

from __future__ import annotations

import datetime

import pandas as pd
import requests

from src.services.volume_alerts import generate_trade_url, generate_tradingview_url

from .base import ExchangeSymbol


def _normalize_pair_name(pair_name):
    return pair_name.replace('/', '').replace('XBT', 'BTC').upper()


def _normalize_kraken_asset_name(asset_name):
    if not asset_name:
        return ''
    return asset_name.replace('XBT', 'BTC').upper()


def _kraken_trade_slug(symbol):
    normalized = symbol.replace('/', '').replace('XBT', 'BTC').upper()
    quote_suffixes = ('USDT', 'USDC', 'USD', 'EUR', 'GBP', 'CAD', 'AUD', 'CHF', 'JPY', 'BTC', 'ETH')
    for suffix in quote_suffixes:
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            base_asset = normalized[:-len(suffix)]
            return f"{base_asset.lower()}-{suffix.lower()}"
    return normalized.lower()


class KrakenExchange:
    name = 'kraken'
    display_name = 'KRAKEN'

    def _asset_pairs(self):
        response = requests.get('https://api.kraken.com/0/public/AssetPairs')
        response.raise_for_status()
        result = response.json()['result']
        pairs = []
        for key, value in result.items():
            display_symbol = value.get('wsname') or value.get('altname') or key
            if '/' in display_symbol:
                base, quote = display_symbol.split('/', 1)
            else:
                base = value.get('base') or ''
                quote = value.get('quote') or ''
            pairs.append(
                ExchangeSymbol(
                    symbol=value.get('altname', key).upper(),
                    display_symbol=display_symbol.replace('XBT', 'BTC'),
                    base_asset=_normalize_kraken_asset_name(base),
                    quote_asset=_normalize_kraken_asset_name(quote),
                )
            )
        return pairs

    def fetch_klines(self, symbol, interval='1h', limit=100):
        interval_map = {'1h': 60, '4h': 240, '1d': 1440}
        kraken_interval = interval_map.get(interval, 60)
        url = f'https://api.kraken.com/0/public/OHLC?pair={symbol}&interval={kraken_interval}'
        try:
            print(f"[{datetime.datetime.now()}] Fetching data for {symbol} on Kraken...")
            response = requests.get(url)
            response.raise_for_status()
            payload = response.json()['result']
            pair_key = next(key for key in payload.keys() if key != 'last')
            rows = payload[pair_key][-limit:]
            df = pd.DataFrame(rows, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'
            ])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            for col in ['open', 'high', 'low', 'close', 'vwap', 'volume']:
                df[col] = pd.to_numeric(df[col])
            return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        except Exception as exc:
            print(f"[{datetime.datetime.now()}] Unexpected error fetching Kraken klines for {symbol}: {exc}")
            return pd.DataFrame()

    def get_current_price(self, symbol):
        url = f'https://api.kraken.com/0/public/Ticker?pair={symbol}'
        try:
            response = requests.get(url)
            response.raise_for_status()
            payload = response.json()['result']
            pair_key = next(iter(payload.keys()))
            return float(payload[pair_key]['c'][0])
        except Exception:
            return None

    def validate_symbol(self, symbol):
        try:
            pairs = {item.symbol for item in self._asset_pairs()}
            if _normalize_pair_name(symbol) in pairs or symbol.upper() in pairs:
                return True, None
            return False, "invalid_symbol"
        except Exception as exc:
            return False, str(exc)

    def list_symbols(self, quote_asset=None):
        pairs = self._asset_pairs()
        if quote_asset is None:
            return pairs
        normalized_quote = quote_asset.replace('XBT', 'BTC').upper()
        return [pair for pair in pairs if pair.quote_asset == normalized_quote]

    def tradingview_url(self, symbol):
        return generate_tradingview_url(symbol, self.display_name)

    def trade_url(self, symbol):
        return f"https://pro.kraken.com/app/trade/{_kraken_trade_slug(symbol)}"
