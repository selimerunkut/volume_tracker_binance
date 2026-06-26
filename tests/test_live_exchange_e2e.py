from __future__ import annotations

import os

import pandas as pd
import pytest

from src.exchanges.registry import get_exchange, get_supported_exchange_names
from src.services.market_data_service import fetch_klines, get_current_price


LIVE_API_E2E_ENABLED = os.getenv('RUN_LIVE_API_E2E') == '1'

pytestmark = pytest.mark.skipif(
    not LIVE_API_E2E_ENABLED,
    reason='Set RUN_LIVE_API_E2E=1 to run live exchange e2e tests against public APIs.',
)


LIVE_EXCHANGE_CASES = {
    'binance': {
        'quote_asset': 'USDC',
        'preferred_symbols': ('BTCUSDC', 'ETHUSDC', 'SOLUSDC'),
    },
    'kraken': {
        'quote_asset': 'USD',
        'preferred_symbols': ('BTCUSD', 'ETHUSD', 'XBTUSD'),
    },
    'okx': {
        'quote_asset': 'USDC',
        'preferred_symbols': ('BTCUSDC', 'ETHUSDC', 'SOLUSDC'),
    },
}


def _pick_live_symbol(exchange_name, exchange):
    case = LIVE_EXCHANGE_CASES[exchange_name]
    quote_asset = case['quote_asset']
    pairs = exchange.list_symbols(quote_asset)
    assert pairs, f'{exchange_name} returned no live symbols for quote asset {quote_asset}'

    available_symbols = {pair.symbol for pair in pairs}
    for preferred_symbol in case['preferred_symbols']:
        if preferred_symbol in available_symbols:
            return preferred_symbol

    return pairs[0].symbol


def _assert_live_klines(df, exchange_name, symbol):
    assert isinstance(df, pd.DataFrame), f'{exchange_name} returned {type(df)!r} for {symbol}'
    assert not df.empty, f'{exchange_name} returned no klines for {symbol}'
    assert list(df.columns) == ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    assert df['timestamp'].is_monotonic_increasing, f'{exchange_name} klines are not ordered oldest-to-newest for {symbol}'
    for column in ['open', 'high', 'low', 'close', 'volume']:
        assert pd.api.types.is_numeric_dtype(df[column]), f'{exchange_name} column {column} is not numeric for {symbol}'


@pytest.mark.e2e
@pytest.mark.parametrize('exchange_name', get_supported_exchange_names())
def test_live_public_api_roundtrip_for_every_supported_exchange(exchange_name):
    exchange = get_exchange(exchange_name)
    symbol = _pick_live_symbol(exchange_name, exchange)

    available_symbols = {pair.symbol for pair in exchange.list_symbols(LIVE_EXCHANGE_CASES[exchange_name]['quote_asset'])}
    assert symbol in available_symbols, f'{exchange_name} did not list {symbol} in its live symbol catalog'

    current_price = get_current_price(symbol, exchange_name=exchange_name)
    assert current_price is not None, f'{exchange_name} did not return a current price for {symbol}'
    assert current_price > 0, f'{exchange_name} returned a non-positive price for {symbol}: {current_price}'

    df = fetch_klines(symbol, interval='1h', limit=2, exchange_name=exchange_name)
    _assert_live_klines(df, exchange_name, symbol)

    trade_url = exchange.trade_url(symbol)
    chart_url = exchange.tradingview_url(symbol)
    assert trade_url, f'{exchange_name} did not generate a trade URL for {symbol}'
    assert chart_url, f'{exchange_name} did not generate a chart URL for {symbol}'
