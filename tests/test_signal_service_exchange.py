from __future__ import annotations

import asyncio
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.signal_service import SignalService


class FakeWatchlistManager:
    def __init__(self, symbols):
        self._symbols = symbols

    def refresh(self):
        return None

    def get_watchlist(self):
        return self._symbols


def _fake_indicators():
    return pd.DataFrame([{'close': 101.0, 'rsi': 55.0, 'macd': 0.1, 'macd_signal': 0.05}])


def test_check_signals_uses_requested_exchange(monkeypatch):
    observed = {}

    def fake_fetch_klines(symbol, interval='1h', limit=100, exchange_name='binance'):
        observed['fetch_exchange'] = exchange_name
        return _fake_indicators()

    def fake_get_current_price(symbol, exchange_name='binance'):
        observed['price_exchange'] = exchange_name
        return 101.0

    monkeypatch.setattr('src.services.signal_service.fetch_klines', fake_fetch_klines)
    monkeypatch.setattr('src.services.signal_service.get_current_price', fake_get_current_price)
    monkeypatch.setattr('src.services.signal_service.calculate_indicators', lambda df: df)
    monkeypatch.setattr('src.services.signal_service.evaluate_hourly_strategy', lambda df: 'LONG')
    monkeypatch.setattr('src.services.signal_service.describe_hourly_signal', lambda df, signal: 'hourly explanation')
    monkeypatch.setattr('src.services.signal_service.get_last_signal_trade', lambda symbol, timeframe, signal: None)

    saved = {}

    def fake_save_signal_trade(symbol, timeframe, signal_type, action, entry_price, explanation=None, dedup_key=None, entry_ts=None):
        saved.update(
            symbol=symbol,
            timeframe=timeframe,
            signal_type=signal_type,
            action=action,
            entry_price=entry_price,
            explanation=explanation,
            dedup_key=dedup_key,
        )
        return 1

    monkeypatch.setattr('src.services.signal_service.save_signal_trade', fake_save_signal_trade)

    service = SignalService(chat_id=None, watchlist_manager=FakeWatchlistManager(['BTCUSDC']))
    asyncio.run(service.check_signals(timeframe='1h', exchange_name='kraken'))

    assert observed['fetch_exchange'] == 'kraken'
    assert observed['price_exchange'] == 'kraken'
    assert saved['symbol'] == 'BTCUSDC'
    assert saved['action'] == 'LONG'


def test_check_signals_keeps_binance_default(monkeypatch):
    observed = {}

    def fake_fetch_klines(symbol, interval='1h', limit=100, exchange_name='binance'):
        observed['fetch_exchange'] = exchange_name
        return _fake_indicators()

    def fake_get_current_price(symbol, exchange_name='binance'):
        observed['price_exchange'] = exchange_name
        return 101.0

    monkeypatch.setattr('src.services.signal_service.fetch_klines', fake_fetch_klines)
    monkeypatch.setattr('src.services.signal_service.get_current_price', fake_get_current_price)
    monkeypatch.setattr('src.services.signal_service.calculate_indicators', lambda df: df)
    monkeypatch.setattr('src.services.signal_service.evaluate_hourly_strategy', lambda df: 'LONG')
    monkeypatch.setattr('src.services.signal_service.describe_hourly_signal', lambda df, signal: 'hourly explanation')
    monkeypatch.setattr('src.services.signal_service.get_last_signal_trade', lambda symbol, timeframe, signal: None)
    monkeypatch.setattr('src.services.signal_service.save_signal_trade', lambda *args, **kwargs: 1)

    service = SignalService(chat_id=None, watchlist_manager=FakeWatchlistManager(['BTCUSDC']))
    asyncio.run(service.check_signals(timeframe='1h'))

    assert observed['fetch_exchange'] == 'binance'
    assert observed['price_exchange'] == 'binance'
