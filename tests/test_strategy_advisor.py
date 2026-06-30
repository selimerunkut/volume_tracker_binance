from __future__ import annotations

import pandas as pd

from src.services import strategy_advisor


def _frame():
    return pd.DataFrame(
        [
            {
                "close": 101.5,
                "rsi": 55.0,
                "macd": 0.1,
                "macd_signal": 0.05,
                "bb_upper": 110.0,
                "bb_lower": 90.0,
                "ema_50": 100.0,
                "ema_200": 95.0,
            }
        ]
    )


def test_analyze_and_suggest_uses_requested_exchange(monkeypatch):
    observed = {}

    def fake_get_current_price(symbol, exchange_name='binance'):
        observed['price_exchange'] = exchange_name
        return 101.5

    def fake_fetch_klines(symbol, interval='1h', limit=250, exchange_name='binance'):
        observed['klines_exchange'] = exchange_name
        return _frame()

    def fake_get_latest_indicators(df):
        return {
            'rsi': 55.0,
            'macd': 0.1,
            'macd_signal': 0.05,
            'ema_50': 100.0,
            'bb_lower': 90.0,
            'bb_upper': 110.0,
        }

    monkeypatch.setattr(strategy_advisor, 'get_current_price', fake_get_current_price)
    monkeypatch.setattr(strategy_advisor, 'fetch_klines', fake_fetch_klines)
    monkeypatch.setattr(strategy_advisor, 'calculate_indicators', lambda klines: klines)
    monkeypatch.setattr(strategy_advisor, 'get_latest_indicators', fake_get_latest_indicators)
    monkeypatch.setattr(strategy_advisor, 'get_latest_news', lambda limit=5: [{'title': 'News A', 'source': 'Feed', 'url': 'https://example.test/a'}])

    saved = {}

    def fake_save_suggestion(**kwargs):
        saved.update(kwargs)
        return 42

    monkeypatch.setattr(strategy_advisor, 'save_suggestion', fake_save_suggestion)

    result = strategy_advisor.analyze_and_suggest('BTCUSD', exchange_name='kraken')

    assert observed['price_exchange'] == 'kraken'
    assert observed['klines_exchange'] == 'kraken'
    assert result['suggestion_id'] == 42
    assert saved['analysis_data']['exchange_name'] == 'kraken'
    assert saved['analysis_data']['current_price'] == 101.5
    assert saved['analysis_data']['confidence'] == result['confidence']
    assert saved['analysis_data']['news_items'][0]['url'] == 'https://example.test/a'


def test_analyze_and_suggest_keeps_news_out_of_signal(monkeypatch):
    outcomes = []

    def fake_get_current_price(symbol, exchange_name='binance'):
        return 100.0

    def fake_fetch_klines(symbol, interval='1h', limit=250, exchange_name='binance'):
        return _frame()

    def fake_get_latest_indicators(df):
        return {
            'rsi': 28.0,
            'macd': 1.0,
            'macd_signal': 0.5,
            'ema_50': 95.0,
            'bb_lower': 90.0,
            'bb_upper': 110.0,
        }

    def fake_get_latest_news(limit=5):
        outcomes.append(limit)
        return [{'title': 'Different headline', 'source': 'Feed', 'url': 'https://example.test/b'}]

    def fake_save_suggestion(**kwargs):
        return 7

    monkeypatch.setattr(strategy_advisor, 'get_current_price', fake_get_current_price)
    monkeypatch.setattr(strategy_advisor, 'fetch_klines', fake_fetch_klines)
    monkeypatch.setattr(strategy_advisor, 'calculate_indicators', lambda klines: klines)
    monkeypatch.setattr(strategy_advisor, 'get_latest_indicators', fake_get_latest_indicators)
    monkeypatch.setattr(strategy_advisor, 'get_latest_news', fake_get_latest_news)
    monkeypatch.setattr(strategy_advisor, 'save_suggestion', fake_save_suggestion)

    first = strategy_advisor.analyze_and_suggest('SAFEUSD', exchange_name='okx')
    second = strategy_advisor.analyze_and_suggest('SAFEUSD', exchange_name='okx')

    assert first['action'] == second['action'] == 'LONG'
    assert first['confidence'] == second['confidence']
    assert first['reasoning'] == second['reasoning']
    assert outcomes == [5, 5]


def test_strategy_advisor_has_no_llm_dependency():
    source = open(strategy_advisor.__file__, encoding='utf-8').read()
    forbidden = ('openai', 'OpenRouter', 'construct_prompt', 'get_llm_client')
    assert all(name not in source for name in forbidden)
