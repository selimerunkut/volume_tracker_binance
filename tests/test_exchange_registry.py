import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.exchanges.registry import get_exchange, get_exchanges_for_scope, get_supported_exchange_names


def test_registry_lists_supported_exchanges():
    assert get_supported_exchange_names() == ['binance', 'kraken', 'okx']


def test_registry_resolves_scope_variants():
    assert [exchange.name for exchange in get_exchanges_for_scope('binance')] == ['binance']
    assert [exchange.name for exchange in get_exchanges_for_scope('all')] == ['binance', 'kraken', 'okx']
    assert [exchange.name for exchange in get_exchanges_for_scope({'mode': 'selected', 'exchanges': ['kraken', 'binance']})] == ['kraken', 'binance']
    assert [exchange.name for exchange in get_exchanges_for_scope('coinbase')] == ['binance']
    assert [exchange.name for exchange in get_exchanges_for_scope('okx')] == ['okx']


def test_get_exchange_rejects_unknown_names():
    try:
        get_exchange('coinbase')
    except ValueError as exc:
        assert 'Unsupported exchange' in str(exc)
    else:
        raise AssertionError('Expected ValueError for unsupported exchange')
