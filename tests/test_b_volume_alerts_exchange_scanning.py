from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import b_volume_alerts


class FakeExchange:
    def __init__(self, name, symbols):
        self.name = name
        self.display_name = name.upper()
        self._symbols = symbols
        self.fetch_calls = []
        self.list_calls = []

    def list_symbols(self, quote_asset=None):
        self.list_calls.append(quote_asset)
        return [
            SimpleNamespace(
                symbol=symbol,
                display_symbol=symbol,
                base_asset=symbol[:-3],
                quote_asset=quote_asset or 'USDC',
            )
            for symbol in self._symbols.get(quote_asset, [])
        ]

    def fetch_klines(self, symbol, interval='1h', limit=100):
        self.fetch_calls.append((symbol, interval, limit))
        return SimpleNamespace(
            empty=False,
            __len__=lambda self=None: 10,
        )

    def tradingview_url(self, symbol):
        return f'https://example.test/chart/{self.name}/{symbol}'

    def trade_url(self, symbol):
        return f'https://example.test/trade/{self.name}/{symbol}'


def test_create_alert_message_uses_exchange_adapter_urls():
    exchange = SimpleNamespace(
        display_name='KRAKEN',
        tradingview_url=lambda symbol: f'https://example.test/chart/{symbol}',
        trade_url=lambda symbol: f'https://example.test/trade/{symbol}',
    )
    alert_message = b_volume_alerts.create_alert_message(
        {'curr_volume': 10, 'prev_volume_mean': 5, 'level': 'HIGH'},
        11,
        12,
        9,
        100.0,
        110.0,
        'BTCUSD',
        exchange,
    )

    assert alert_message['exchange'] == 'KRAKEN'
    assert alert_message['chart_url'] == 'https://example.test/chart/BTCUSD'
    assert alert_message['trade_url'] == 'https://example.test/trade/BTCUSD'


def test_run_script_scans_only_selected_exchange(monkeypatch):
    sent_messages = []
    scan_log = []
    saved_states = {}

    fake_binance = FakeExchange('binance', {'USDC': ['BTCUSDC'], 'BTC': ['ETHBTC']})
    fake_kraken = FakeExchange('kraken', {'USD': ['BTCUSD'], 'BTC': ['ETHBTC']})

    monkeypatch.setattr(b_volume_alerts, 'get_alert_exchange_selection', lambda chat_id: {'mode': 'selected', 'exchanges': ['kraken']})
    monkeypatch.setattr(b_volume_alerts, 'get_exchanges_for_scope', lambda scope: [fake_kraken])
    monkeypatch.setattr(b_volume_alerts.permissions_service, 'get_allowed_symbols', lambda: None)
    monkeypatch.setattr(b_volume_alerts, 'get_setting', lambda key, default='True': 'True')
    monkeypatch.setattr(b_volume_alerts, 'load_alert_state', lambda: {})
    monkeypatch.setattr(b_volume_alerts, 'save_alert_state', lambda state: saved_states.update(state))
    monkeypatch.setattr(b_volume_alerts.time, 'sleep', lambda seconds: None)

    class FakeSymbolManager:
        def get_excluded_symbols(self):
            return set()

        def is_symbol_excluded(self, symbol):
            return False

    monkeypatch.setattr(b_volume_alerts, 'SymbolManager', FakeSymbolManager)

    def fake_get_volume_alert_details(curr_volume, prev_volume_mean, last_completed_hour_volume, open_price, close_price, symbol, timeframe, exchange_name):
        scan_log.append((symbol, exchange_name))
        return [{
            'symbol': symbol,
            'level': 'HIGH',
            'curr_volume': curr_volume,
            'prev_volume_mean': prev_volume_mean,
        }]

    monkeypatch.setattr(b_volume_alerts, 'get_volume_alert_details', fake_get_volume_alert_details)
    monkeypatch.setattr(b_volume_alerts, 'send_telegram_message', lambda alert_message, include_restrict_button=False, dry_run=False: sent_messages.append(alert_message) or True)

    class FakeFrame:
        empty = False

        def __len__(self):
            return 10

        def __getitem__(self, key):
            data = {
                'volume': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                'open': [100] * 10,
                'close': [110] * 10,
            }
            return SimpleNamespace(iloc=SimpleNamespace(__getitem__=lambda self, idx: data[key][idx]))

    def fake_fetch_klines(symbol, interval='1h', limit=10):
        return __import__('pandas').DataFrame({
            'timestamp': range(10),
            'open': [100] * 10,
            'high': [111] * 10,
            'low': [99] * 10,
            'close': [110] * 10,
            'volume': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        })

    fake_kraken.fetch_klines = fake_fetch_klines
    fake_binance.fetch_klines = fake_fetch_klines

    b_volume_alerts.run_script(dry_run=False)

    assert scan_log == [('BTCUSD', 'KRAKEN'), ('ETHBTC', 'KRAKEN')]
    assert all(message['exchange'] == 'KRAKEN' for message in sent_messages)
    assert saved_states


def test_run_script_scans_all_selected_exchanges(monkeypatch):
    sent_messages = []
    scan_log = []

    fake_binance = FakeExchange('binance', {'USDC': ['BTCUSDC'], 'BTC': ['ETHBTC']})
    fake_kraken = FakeExchange('kraken', {'USD': ['BTCUSD'], 'BTC': ['ETHBTC']})

    monkeypatch.setattr(b_volume_alerts, 'get_alert_exchange_selection', lambda chat_id: {'mode': 'all', 'exchanges': []})
    monkeypatch.setattr(b_volume_alerts, 'get_exchanges_for_scope', lambda scope: [fake_binance, fake_kraken])
    monkeypatch.setattr(b_volume_alerts.permissions_service, 'get_allowed_symbols', lambda: None)
    monkeypatch.setattr(b_volume_alerts, 'get_setting', lambda key, default='True': 'True')
    monkeypatch.setattr(b_volume_alerts, 'load_alert_state', lambda: {})
    monkeypatch.setattr(b_volume_alerts, 'save_alert_state', lambda state: None)
    monkeypatch.setattr(b_volume_alerts.time, 'sleep', lambda seconds: None)

    class FakeSymbolManager:
        def get_excluded_symbols(self):
            return set()

        def is_symbol_excluded(self, symbol):
            return False

    monkeypatch.setattr(b_volume_alerts, 'SymbolManager', FakeSymbolManager)

    def fake_get_volume_alert_details(curr_volume, prev_volume_mean, last_completed_hour_volume, open_price, close_price, symbol, timeframe, exchange_name):
        scan_log.append((symbol, exchange_name))
        return [{
            'symbol': symbol,
            'level': 'HIGH',
            'curr_volume': curr_volume,
            'prev_volume_mean': prev_volume_mean,
        }]

    monkeypatch.setattr(b_volume_alerts, 'get_volume_alert_details', fake_get_volume_alert_details)
    monkeypatch.setattr(b_volume_alerts, 'send_telegram_message', lambda alert_message, include_restrict_button=False, dry_run=False: sent_messages.append(alert_message) or True)
    monkeypatch.setattr(b_volume_alerts, 'pd', __import__('pandas'))

    def fake_fetch_klines(symbol, interval='1h', limit=10):
        return __import__('pandas').DataFrame({
            'timestamp': range(10),
            'open': [100] * 10,
            'high': [111] * 10,
            'low': [99] * 10,
            'close': [110] * 10,
            'volume': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        })

    fake_binance.fetch_klines = fake_fetch_klines
    fake_kraken.fetch_klines = fake_fetch_klines

    b_volume_alerts.run_script(dry_run=True)

    assert ('BTCUSDC', 'BINANCE') in scan_log
    assert ('BTCUSD', 'KRAKEN') in scan_log
    assert any(message['exchange'] == 'BINANCE' for message in sent_messages)
    assert any(message['exchange'] == 'KRAKEN' for message in sent_messages)


def test_run_script_emits_alerts_for_binance_and_kraken(monkeypatch):
    sent_messages = []
    saved_states = {}

    fake_binance = FakeExchange('binance', {'USDC': ['BTCUSDC']})
    fake_kraken = FakeExchange('kraken', {'USD': ['BTCUSD']})

    monkeypatch.setattr(b_volume_alerts, 'get_alert_exchange_selection', lambda chat_id: {'mode': 'all', 'exchanges': []})
    monkeypatch.setattr(b_volume_alerts, 'get_exchanges_for_scope', lambda scope: [fake_binance, fake_kraken])
    monkeypatch.setattr(b_volume_alerts.permissions_service, 'get_allowed_symbols', lambda: None)
    monkeypatch.setattr(b_volume_alerts, 'get_setting', lambda key, default='True': 'True')
    monkeypatch.setattr(b_volume_alerts, 'load_alert_state', lambda: {})
    monkeypatch.setattr(b_volume_alerts, 'save_alert_state', lambda state: saved_states.update(state))
    monkeypatch.setattr(b_volume_alerts.time, 'sleep', lambda seconds: None)

    class FakeSymbolManager:
        def get_excluded_symbols(self):
            return set()

        def is_symbol_excluded(self, symbol):
            return False

    monkeypatch.setattr(b_volume_alerts, 'SymbolManager', FakeSymbolManager)

    def fake_fetch_klines(symbol, interval='1h', limit=10):
        return __import__('pandas').DataFrame({
            'timestamp': range(10),
            'open': [100] * 10,
            'high': [111] * 10,
            'low': [99] * 10,
            'close': [110] * 10,
            'volume': [1, 1, 1, 1, 1, 1, 1, 20, 20, 1000],
        })

    fake_binance.fetch_klines = fake_fetch_klines
    fake_kraken.fetch_klines = fake_fetch_klines

    monkeypatch.setattr(
        b_volume_alerts,
        'send_telegram_message',
        lambda alert_message, include_restrict_button=False, dry_run=False: sent_messages.append(alert_message) or True,
    )

    b_volume_alerts.run_script(dry_run=False)

    assert any(message['exchange'] == 'BINANCE' for message in sent_messages)
    assert any(message['exchange'] == 'KRAKEN' for message in sent_messages)
    assert any(message['symbol'] == 'BTCUSDC' for message in sent_messages)
    assert any(message['symbol'] == 'BTCUSD' for message in sent_messages)
    assert saved_states
