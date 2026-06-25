import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.exchanges.binance import BinanceExchange
from src.exchanges.kraken import KrakenExchange


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


def test_binance_adapter_shapes_klines(monkeypatch):
    payload = [
        [1, '100', '110', '90', '105', '12.5', 2, '0', 0, '0', '0', '0'],
        [2, '105', '115', '95', '110', '14.0', 3, '0', 0, '0', '0', '0'],
    ]

    monkeypatch.setattr(
        'src.exchanges.binance.requests.get',
        lambda *args, **kwargs: FakeResponse(payload),
    )

    df = BinanceExchange().fetch_klines('BTCUSDC', limit=2)

    assert list(df.columns) == ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    assert len(df) == 2
    assert pd.api.types.is_numeric_dtype(df['close'])


def test_kraken_adapter_shapes_klines(monkeypatch):
    payload = {
        'result': {
            'XXBTZUSD': [
                [1, '100', '110', '90', '105', '100.0', '12.5', 2],
                [2, '105', '115', '95', '110', '101.0', '14.0', 3],
            ],
            'last': 2,
        }
    }

    monkeypatch.setattr(
        'src.exchanges.kraken.requests.get',
        lambda *args, **kwargs: FakeResponse(payload),
    )

    df = KrakenExchange().fetch_klines('BTCUSD', limit=2)

    assert list(df.columns) == ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    assert len(df) == 2
    assert pd.api.types.is_numeric_dtype(df['volume'])


def test_kraken_adapter_filters_quote_assets_from_wsname(monkeypatch):
    payload = {
        'result': {
            'XXBTZUSD': {
                'wsname': 'BTC/USD',
                'altname': 'BTCUSD',
                'base': 'XBT',
                'quote': 'ZUSD',
            },
            'XXBTZBTC': {
                'wsname': 'BTC/BTC',
                'altname': 'ETHXBT',
                'base': 'XBT',
                'quote': 'XXBT',
            },
        }
    }

    monkeypatch.setattr(
        'src.exchanges.kraken.requests.get',
        lambda *args, **kwargs: FakeResponse(payload),
    )

    exchange = KrakenExchange()
    usd_pairs = exchange.list_symbols('USD')
    btc_pairs = exchange.list_symbols('BTC')

    assert [pair.symbol for pair in usd_pairs] == ['BTCUSD']
    assert [pair.symbol for pair in btc_pairs] == ['ETHXBT']
