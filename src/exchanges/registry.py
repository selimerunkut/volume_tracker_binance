"""Exchange registry."""

from __future__ import annotations

from .binance import BinanceExchange
from .kraken import KrakenExchange

_EXCHANGES = {
    'binance': BinanceExchange,
    'kraken': KrakenExchange,
}


def get_exchange(name):
    normalized = (name or 'binance').lower()
    try:
        return _EXCHANGES[normalized]()
    except KeyError as exc:
        raise ValueError(f"Unsupported exchange: {name}") from exc


def get_supported_exchange_names():
    return list(_EXCHANGES.keys())


def get_exchanges_for_scope(scope):
    if scope is None:
        return [get_exchange('binance')]

    if isinstance(scope, dict):
        if scope.get('mode') == 'all':
            return [get_exchange(name) for name in get_supported_exchange_names()]
        scope = scope.get('exchanges', [])

    if isinstance(scope, str):
        if scope.lower() == 'all':
            return [get_exchange(name) for name in get_supported_exchange_names()]
        scope = [scope]

    normalized = []
    for exchange_name in scope:
        candidate = str(exchange_name).lower()
        if candidate in _EXCHANGES and candidate not in normalized:
            normalized.append(candidate)

    if not normalized:
        return [get_exchange('binance')]

    return [get_exchange(name) for name in normalized]
