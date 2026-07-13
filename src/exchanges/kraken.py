"""Kraken exchange adapter."""

from __future__ import annotations

import datetime

import pandas as pd
import requests
from functools import lru_cache

from src.services.volume_alerts import generate_trade_url, generate_tradingview_url
from src.services.quote_value_service import rate_from_bid_ask

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
    request_timeout = 10

    def _asset_pairs(self):
        response = requests.get('https://api.kraken.com/0/public/AssetPairs', timeout=self.request_timeout)
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

    @lru_cache(maxsize=1)
    def _conversion_pairs(self):
        response = requests.get('https://api.kraken.com/0/public/AssetPairs', timeout=self.request_timeout)
        response.raise_for_status()
        return response.json().get('result', {})

    def fetch_klines(self, symbol, interval='1h', limit=100):
        interval_map = {'1h': 60, '4h': 240, '1d': 1440}
        kraken_interval = interval_map.get(interval, 60)
        url = f'https://api.kraken.com/0/public/OHLC?pair={symbol}&interval={kraken_interval}'
        try:
            print(f"[{datetime.datetime.now()}] Fetching data for {symbol} on Kraken...")
            response = requests.get(url, timeout=self.request_timeout)
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
            df['quote_volume'] = df['volume'] * df['vwap'].where(df['vwap'] > 0, df['close'])
            return df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'quote_volume']]
        except Exception as exc:
            print(f"[{datetime.datetime.now()}] Unexpected error fetching Kraken klines for {symbol}: {exc}")
            return pd.DataFrame()

    def get_current_price(self, symbol):
        url = f'https://api.kraken.com/0/public/Ticker?pair={symbol}'
        try:
            response = requests.get(url, timeout=self.request_timeout)
            response.raise_for_status()
            payload = response.json()['result']
            pair_key = next(iter(payload.keys()))
            return float(payload[pair_key]['c'][0])
        except Exception:
            return None

    def fetch_order_book(self, symbol, limit=50):
        response = requests.get(
            'https://api.kraken.com/0/public/Depth',
            params={'pair': symbol, 'count': limit},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()['result']
        book = payload[next(iter(payload))]
        return {
            'bids': [(float(row[0]), float(row[1])) for row in book.get('bids', [])],
            'asks': [(float(row[0]), float(row[1])) for row in book.get('asks', [])],
        }

    def fetch_24h_quote_volume(self, symbol):
        response = requests.get(
            'https://api.kraken.com/0/public/Ticker',
            params={'pair': symbol},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()['result']
        ticker = payload[next(iter(payload))]
        return float(ticker['v'][1]) * float(ticker['p'][1])

    def quote_to_usd_rate(self, quote_asset):
        asset = str(quote_asset).upper().replace('BTC', 'XBT')
        if asset in {'USD', 'USDC', 'USDT'}:
            return 1.0
        pairs = self._conversion_pairs()
        candidates = []
        for key, item in pairs.items():
            status = str(item.get('status', 'online')).lower()
            if status != 'online':
                continue
            base = str(item.get('base', '')).upper().replace('XXBT', 'XBT').replace('XBT', 'XBT')
            quote = str(item.get('quote', '')).upper().replace('ZUSD', 'USD').replace('XXBT', 'XBT').replace('XBT', 'XBT')
            altname = str(item.get('altname') or key).upper()
            if base == asset and quote in {'USD', 'USDT', 'USDC'}:
                candidates.append((altname, False))
            elif quote == asset and base in {'USD', 'USDT', 'USDC'}:
                candidates.append((altname, True))
        candidates.sort(key=lambda entry: (entry[1], entry[0]))
        for pair, inverse in candidates:
            try:
                response = requests.get(
                    'https://api.kraken.com/0/public/Ticker',
                    params={'pair': pair}, timeout=self.request_timeout,
                )
                response.raise_for_status()
                payload = response.json().get('result', {})
                ticker = payload[next(iter(payload))]
                return rate_from_bid_ask(ticker['b'][0], ticker['a'][0], inverse=inverse)
            except (KeyError, StopIteration, ValueError, TypeError):
                continue
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
