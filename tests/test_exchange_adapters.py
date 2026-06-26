import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.exchanges.binance import BinanceExchange
from src.exchanges.kraken import KrakenExchange
from src.exchanges.okx import OKXExchange


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


def test_okx_adapter_normalizes_symbols_and_reverses_candles(monkeypatch):
    instruments_payload = {
        'code': '0',
        'data': [
            {'instId': 'BTC-USDC', 'baseCcy': 'BTC', 'quoteCcy': 'USDC', 'state': 'live'},
            {'instId': 'BTC-EUR', 'baseCcy': 'BTC', 'quoteCcy': 'EUR', 'state': 'live'},
            {'instId': 'BTC-USD', 'baseCcy': 'BTC', 'quoteCcy': 'USD', 'state': 'live'},
            {'instId': 'ETH-BTC', 'baseCcy': 'ETH', 'quoteCcy': 'BTC', 'state': 'live'},
            {'instId': 'BTC-USDT', 'baseCcy': 'BTC', 'quoteCcy': 'USDT', 'state': 'live'},
        ],
    }
    candles_payload = {
        'code': '0',
        'data': [
            ['3000', '12', '14', '11', '13', '30', '300', '3900', '1'],
            ['2000', '10', '12', '9', '11', '20', '200', '2200', '1'],
            ['1000', '8', '10', '7', '9', '10', '100', '900', '1'],
        ],
    }
    ticker_payload = {'code': '0', 'data': [{'instId': 'BTC-USDC', 'last': '123.45'}]}

    def fake_get(url, params=None, timeout=None):
        if 'public/instruments' in url:
            return FakeResponse(instruments_payload)
        if 'market/candles' in url:
            return FakeResponse(candles_payload)
        if 'market/ticker' in url:
            return FakeResponse(ticker_payload)
        raise AssertionError(f'unexpected URL: {url}')

    monkeypatch.setattr('src.exchanges.okx.requests.get', fake_get)

    exchange = OKXExchange()

    assert [pair.symbol for pair in exchange.list_symbols('USDC')] == ['BTC-USDC']
    assert [pair.symbol for pair in exchange.list_symbols('BTC')] == ['ETH-BTC']
    assert exchange.validate_symbol('BTCUSDC') == (True, None)
    assert exchange.validate_symbol('BTC-USDT') == (False, 'invalid_symbol')
    assert exchange.trade_url('BTCUSDC') == 'https://www.okx.com/trade-spot/btc-usdc'
    assert exchange.tradingview_url('BTCUSDC') == 'https://www.tradingview.com/symbols/BTC-USDC/?exchange=OKX'

    df = exchange.fetch_klines('BTCUSDC', limit=3)
    assert list(df.columns) == ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    assert list(df['close']) == [9, 11, 13]
    assert exchange.get_current_price('BTCUSDC') == 123.45
