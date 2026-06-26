from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services import market_data_service


def test_validate_trading_pair_uses_requested_exchange(monkeypatch):
    observed = {}

    class FakeExchange:
        def validate_symbol(self, symbol):
            observed['symbol'] = symbol
            return True, None

    def fake_get_exchange(exchange_name):
        observed['exchange_name'] = exchange_name
        return FakeExchange()

    monkeypatch.setattr(market_data_service, 'get_exchange', fake_get_exchange)

    assert market_data_service.validate_trading_pair('ETHBTC', exchange_name='kraken') == (True, None)
    assert observed == {'exchange_name': 'kraken', 'symbol': 'ETHBTC'}


def test_validate_trading_pair_defaults_to_binance(monkeypatch):
    observed = {}

    class FakeExchange:
        def validate_symbol(self, symbol):
            observed['symbol'] = symbol
            return False, 'invalid_symbol'

    def fake_get_exchange(exchange_name):
        observed['exchange_name'] = exchange_name
        return FakeExchange()

    monkeypatch.setattr(market_data_service, 'get_exchange', fake_get_exchange)

    assert market_data_service.validate_trading_pair('NOPE') == (False, 'invalid_symbol')
    assert observed == {'exchange_name': 'binance', 'symbol': 'NOPE'}


def test_validate_trading_pair_supports_okx(monkeypatch):
    observed = {}

    class FakeExchange:
        def validate_symbol(self, symbol):
            observed['symbol'] = symbol
            return True, None

    def fake_get_exchange(exchange_name):
        observed['exchange_name'] = exchange_name
        return FakeExchange()

    monkeypatch.setattr(market_data_service, 'get_exchange', fake_get_exchange)

    assert market_data_service.validate_trading_pair('BTC-USDC', exchange_name='okx') == (True, None)
    assert observed == {'exchange_name': 'okx', 'symbol': 'BTC-USDC'}
