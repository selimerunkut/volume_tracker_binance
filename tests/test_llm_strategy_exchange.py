from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services import llm_strategy


def _fake_llm_client(response_payload):
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=json.dumps(response_payload)
                            )
                        )
                    ]
                )
            )
        )
    )


def test_analyze_and_suggest_uses_requested_exchange(monkeypatch):
    observed = {}

    def fake_get_current_price(symbol, exchange_name='binance'):
        observed['price_exchange'] = exchange_name
        return 101.5

    def fake_fetch_klines(symbol, interval='1h', limit=100, exchange_name='binance'):
        observed['klines_exchange'] = exchange_name
        return pd.DataFrame(
            [{'close': 101.5, 'rsi': 55.0, 'macd': 0.1, 'macd_signal': 0.05, 'bb_upper': 110.0, 'bb_lower': 90.0, 'ema_50': 100.0, 'ema_200': 95.0}]
        )

    monkeypatch.setattr(llm_strategy, 'get_current_price', fake_get_current_price)
    monkeypatch.setattr(llm_strategy, 'fetch_klines', fake_fetch_klines)
    monkeypatch.setattr(llm_strategy, 'calculate_indicators', lambda klines: klines)
    monkeypatch.setattr(llm_strategy, 'get_latest_news', lambda: [])
    monkeypatch.setattr(llm_strategy, 'format_macro_for_llm', lambda: 'macro summary')
    monkeypatch.setattr(llm_strategy, 'get_trade_history', lambda symbol, limit=5: [])
    monkeypatch.setattr(llm_strategy, 'get_recent_failures', lambda limit=5: [])
    monkeypatch.setattr(llm_strategy, 'get_llm_client', lambda: _fake_llm_client({
        'action': 'WAIT',
        'entry': None,
        'tp': None,
        'sl': None,
        'reasoning': 'No setup',
        'confidence': 77,
    }))
    monkeypatch.setattr(llm_strategy, 'get_llm_model', lambda: 'test-model')

    saved = {}

    def fake_save_suggestion(**kwargs):
        saved.update(kwargs)
        return 42

    monkeypatch.setattr(llm_strategy, 'save_suggestion', fake_save_suggestion)

    result = llm_strategy.analyze_and_suggest('BTCUSD', exchange_name='kraken')

    assert observed['price_exchange'] == 'kraken'
    assert observed['klines_exchange'] == 'kraken'
    assert result['suggestion_id'] == 42
    assert saved['analysis_data']['exchange_name'] == 'kraken'
    assert saved['analysis_data']['current_price'] == 101.5


def test_analyze_and_suggest_keeps_binance_default(monkeypatch):
    observed = {}

    def fake_get_current_price(symbol, exchange_name='binance'):
        observed['price_exchange'] = exchange_name
        return 101.5

    def fake_fetch_klines(symbol, interval='1h', limit=100, exchange_name='binance'):
        observed['klines_exchange'] = exchange_name
        return pd.DataFrame(
            [{'close': 101.5, 'rsi': 55.0, 'macd': 0.1, 'macd_signal': 0.05, 'bb_upper': 110.0, 'bb_lower': 90.0, 'ema_50': 100.0, 'ema_200': 95.0}]
        )

    monkeypatch.setattr(llm_strategy, 'get_current_price', fake_get_current_price)
    monkeypatch.setattr(llm_strategy, 'fetch_klines', fake_fetch_klines)
    monkeypatch.setattr(llm_strategy, 'calculate_indicators', lambda klines: klines)
    monkeypatch.setattr(llm_strategy, 'get_latest_news', lambda: [])
    monkeypatch.setattr(llm_strategy, 'format_macro_for_llm', lambda: 'macro summary')
    monkeypatch.setattr(llm_strategy, 'get_trade_history', lambda symbol, limit=5: [])
    monkeypatch.setattr(llm_strategy, 'get_recent_failures', lambda limit=5: [])
    monkeypatch.setattr(llm_strategy, 'get_llm_client', lambda: _fake_llm_client({
        'action': 'WAIT',
        'entry': None,
        'tp': None,
        'sl': None,
        'reasoning': 'No setup',
        'confidence': 77,
    }))
    monkeypatch.setattr(llm_strategy, 'get_llm_model', lambda: 'test-model')
    monkeypatch.setattr(llm_strategy, 'save_suggestion', lambda **kwargs: 43)

    result = llm_strategy.analyze_and_suggest('BTCUSDC')

    assert observed['price_exchange'] == 'binance'
    assert observed['klines_exchange'] == 'binance'
    assert result['suggestion_id'] == 43
