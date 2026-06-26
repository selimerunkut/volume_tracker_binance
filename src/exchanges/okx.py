"""OKX exchange adapter."""

from __future__ import annotations

import datetime
from functools import lru_cache

import pandas as pd
import requests

from src.services.volume_alerts import generate_tradingview_url

from .base import ExchangeSymbol


class OKXExchange:
    name = 'okx'
    display_name = 'OKX'
    base_url = 'https://eea.okx.com'
    allowed_quote_assets = ('USDC', 'EUR', 'USD', 'BTC')
    request_timeout = 10
    _interval_map = {'1h': '1H', '4h': '4H', '1d': '1D'}

    def _request(self, path, params=None):
        url = f'{self.base_url}{path}'
        return requests.get(url, params=params, timeout=self.request_timeout)

    def _instrument_rows(self):
        response = self._request('/api/v5/public/instruments', params={'instType': 'SPOT'})
        response.raise_for_status()
        payload = response.json()
        return payload.get('data', []) or []

    @lru_cache(maxsize=1)
    def _instruments(self):
        instruments = []
        for item in self._instrument_rows():
            if str(item.get('state', '')).lower() != 'live':
                continue

            inst_id = str(item.get('instId') or '').strip().upper()
            base_asset = str(item.get('baseCcy') or '').strip().upper()
            quote_asset = str(item.get('quoteCcy') or '').strip().upper()
            if not inst_id or quote_asset not in self.allowed_quote_assets:
                continue

            instruments.append(
                ExchangeSymbol(
                    symbol=inst_id,
                    display_symbol=inst_id,
                    base_asset=base_asset,
                    quote_asset=quote_asset,
                )
            )

        instruments.sort(key=lambda pair: pair.symbol)
        return instruments

    def _normalize_symbol(self, symbol):
        candidate = str(symbol or '').strip().upper().replace(' ', '')
        if not candidate:
            return None

        direct_candidate = candidate.replace('/', '-')
        if '-' in direct_candidate:
            quote_asset = direct_candidate.rsplit('-', 1)[-1]
            if quote_asset not in self.allowed_quote_assets:
                return None
            return direct_candidate

        for quote_asset in sorted(self.allowed_quote_assets, key=len, reverse=True):
            if candidate.endswith(quote_asset) and len(candidate) > len(quote_asset):
                return f"{candidate[:-len(quote_asset)]}-{quote_asset}"

        return None

    def fetch_klines(self, symbol, interval='1h', limit=100):
        normalized_symbol = self._normalize_symbol(symbol)
        if not normalized_symbol:
            return pd.DataFrame()

        bar = self._interval_map.get(str(interval).lower(), str(interval).upper())
        try:
            print(f"[{datetime.datetime.now()}] Fetching data for {normalized_symbol} on OKX...")
            response = self._request(
                '/api/v5/market/candles',
                params={'instId': normalized_symbol, 'bar': bar, 'limit': limit},
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get('data', []) or []
            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(
                rows,
                columns=[
                    'timestamp',
                    'open',
                    'high',
                    'low',
                    'close',
                    'volume',
                    'volCcy',
                    'volCcyQuote',
                    'confirm',
                ],
            )
            df['timestamp'] = pd.to_datetime(pd.to_numeric(df['timestamp'], errors='coerce'), unit='ms', utc=True).dt.tz_localize(None)
            for column in ['open', 'high', 'low', 'close', 'volume']:
                df[column] = pd.to_numeric(df[column])
            df = df.sort_values('timestamp').reset_index(drop=True)
            return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        except Exception as exc:
            print(f"[{datetime.datetime.now()}] Unexpected error fetching OKX klines for {normalized_symbol}: {exc}")
            return pd.DataFrame()

    def get_current_price(self, symbol):
        normalized_symbol = self._normalize_symbol(symbol)
        if not normalized_symbol:
            return None

        try:
            response = self._request('/api/v5/market/ticker', params={'instId': normalized_symbol})
            response.raise_for_status()
            payload = response.json()
            data = payload.get('data', []) or []
            if not data:
                return None
            return float(data[0]['last'])
        except Exception:
            return None

    def validate_symbol(self, symbol):
        normalized_symbol = self._normalize_symbol(symbol)
        if not normalized_symbol:
            return False, 'invalid_symbol'

        try:
            response = self._request('/api/v5/market/ticker', params={'instId': normalized_symbol})
            response.raise_for_status()
            payload = response.json()
            data = payload.get('data', []) or []
            if not data:
                return False, 'invalid_symbol'
            if str(payload.get('code', '0')) != '0':
                return False, 'invalid_symbol'
            return True, None
        except Exception as exc:
            return False, str(exc)

    def list_symbols(self, quote_asset=None):
        try:
            quote_candidate = None if quote_asset is None else str(quote_asset).replace('XBT', 'BTC').upper()
            if quote_candidate is not None and quote_candidate not in self.allowed_quote_assets:
                return []

            return [
                item
                for item in self._instruments()
                if quote_candidate is None or item.quote_asset == quote_candidate
            ]
        except Exception:
            return []

    def tradingview_url(self, symbol):
        normalized_symbol = self._normalize_symbol(symbol) or str(symbol).replace('/', '-').upper()
        return generate_tradingview_url(normalized_symbol, self.display_name)

    def trade_url(self, symbol):
        normalized_symbol = self._normalize_symbol(symbol)
        if not normalized_symbol:
            return None
        return f'https://www.okx.com/trade-spot/{normalized_symbol.lower()}'
