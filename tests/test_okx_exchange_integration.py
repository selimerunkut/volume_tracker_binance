from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import b_volume_alerts
import telegram_bot_handler
from src.exchanges.okx import OKXExchange
from src.exchanges.registry import get_exchange, get_exchanges_for_scope, get_supported_exchange_names
from src.services import market_data_service


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


def _patch_okx_http(monkeypatch):
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


def test_okx_is_exposed_through_registry_ui_and_service(monkeypatch):
    _patch_okx_http(monkeypatch)

    assert 'okx' in get_supported_exchange_names()
    assert [exchange.name for exchange in get_exchanges_for_scope('all')] == ['binance', 'kraken', 'okx']
    assert get_exchange('okx').name == 'okx'

    exchange = OKXExchange()

    assert [pair.symbol for pair in exchange.list_symbols('USDC')] == ['BTC-USDC']
    assert exchange.validate_symbol('BTCUSDC') == (True, None)
    assert exchange.validate_symbol('BTC-USDT') == (False, 'invalid_symbol')

    df = market_data_service.fetch_klines('BTCUSDC', exchange_name='okx')
    assert list(df.columns) == ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    assert list(df['close']) == [9, 11, 13]
    assert market_data_service.get_current_price('BTCUSDC', exchange_name='okx') == 123.45
    assert market_data_service.validate_trading_pair('BTCUSDC', exchange_name='okx') == (True, None)

    assert b_volume_alerts.get_scan_quote_assets('okx') == ['USDC', 'EUR', 'USD', 'BTC']

    markup = telegram_bot_handler.build_alert_scope_markup({'mode': 'selected', 'exchanges': ['okx']}, view='multiple')
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert '☑ OKX' in labels

    observed = {}

    async def fake_analyze_and_suggest(symbol, exchange_name='binance'):
        observed['analysis'] = (symbol, exchange_name)
        return {'action': 'WAIT', 'confidence': 100, 'reasoning': 'ok'}

    monkeypatch.setattr(telegram_bot_handler, 'analyze_and_suggest', fake_analyze_and_suggest)

    async def fake_edit_message_text(text, reply_markup=None, parse_mode=None):
        observed['edited_text'] = text

    async def fake_answer():
        return None

    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123),
        effective_message=SimpleNamespace(reply_text=lambda *args, **kwargs: None),
        callback_query=SimpleNamespace(
            data='scope|analyze|set|single|okx',
            message=SimpleNamespace(chat=SimpleNamespace(id=123)),
            answer=fake_answer,
            edit_message_text=fake_edit_message_text,
            calls=[],
        ),
        message=SimpleNamespace(reply_text=lambda *args, **kwargs: None),
    )
    context = SimpleNamespace(user_data={'pending_action': 'analyze', 'pending_symbol': 'BTCUSDC'})

    asyncio.run(telegram_bot_handler.scope_callback(update, context))

    assert observed['analysis'] == ('BTCUSDC', 'okx')
    assert 'OKX' in observed['edited_text']


def test_okx_scanner_would_keep_okx_specific_urls_and_symbol_scope(monkeypatch):
    _patch_okx_http(monkeypatch)

    exchange = OKXExchange()
    alert_message = b_volume_alerts.create_alert_message(
        {'curr_volume': 10, 'prev_volume_mean': 5, 'level': 'HIGH'},
        11,
        12,
        9,
        100.0,
        110.0,
        'BTC-USDC',
        exchange,
    )

    assert alert_message['exchange'] == 'OKX'
    assert alert_message['chart_url'].endswith('?exchange=OKX')
    assert alert_message['trade_url'] == 'https://www.okx.com/trade-spot/btc-usdc'
    assert alert_message['binance_trade_url'] is None

    sent_messages = []

    class FakeSymbolManager:
        def get_excluded_symbols(self):
            return set()

        def is_symbol_excluded(self, symbol):
            return False

    fake_okx = SimpleNamespace(
        name='okx',
        display_name='OKX',
        list_symbols=lambda quote_asset=None: [
            SimpleNamespace(symbol='BTC-USDC', display_symbol='BTC-USDC', base_asset='BTC', quote_asset='USDC')
        ] if quote_asset == 'USDC' else [],
        fetch_klines=lambda symbol, interval='1h', limit=10: pd.DataFrame(
            {
                'timestamp': pd.to_datetime([1, 2, 3], unit='s'),
                'open': [100, 101, 102],
                'high': [110, 111, 112],
                'low': [90, 91, 92],
                'close': [105, 106, 107],
                'volume': [1, 2, 3],
            }
        ),
        tradingview_url=lambda symbol: f'https://www.tradingview.com/symbols/{symbol}/?exchange=OKX',
        trade_url=lambda symbol: f'https://www.okx.com/trade-spot/{symbol.lower()}',
    )

    monkeypatch.setattr(b_volume_alerts, 'get_exchanges_for_scope', lambda scope: [fake_okx])
    monkeypatch.setattr(b_volume_alerts, 'get_alert_exchange_selection', lambda chat_id: {'mode': 'selected', 'exchanges': ['okx']})
    monkeypatch.setattr(b_volume_alerts.permissions_service, 'get_allowed_symbols', lambda: None)
    monkeypatch.setattr(b_volume_alerts, 'get_setting', lambda key, default='True': 'True')
    monkeypatch.setattr(b_volume_alerts, 'load_alert_state', lambda: {})
    monkeypatch.setattr(b_volume_alerts, 'save_alert_state', lambda state: None)
    monkeypatch.setattr(b_volume_alerts.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(b_volume_alerts, 'SymbolManager', FakeSymbolManager)
    monkeypatch.setattr(
        b_volume_alerts,
        'get_volume_alert_details',
        lambda curr_volume, prev_volume_mean, last_completed_hour_volume, open_price, close_price, symbol, timeframe, exchange_name: [
            {'symbol': symbol, 'level': 'HIGH', 'curr_volume': curr_volume, 'prev_volume_mean': prev_volume_mean}
        ],
    )
    monkeypatch.setattr(
        b_volume_alerts,
        'send_telegram_message',
        lambda alert_message, include_restrict_button=False, dry_run=False: sent_messages.append(alert_message) or True,
    )

    b_volume_alerts.run_script(dry_run=True)

    assert sent_messages
    assert all(message['exchange'] == 'OKX' for message in sent_messages)
