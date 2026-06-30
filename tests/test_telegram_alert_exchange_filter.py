import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services import db_service
from src.services.alert_preferences import should_send_alert_for_scope


def _prepare_temp_db():
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.close()
    db_service.DB_PATH = temp_file.name
    db_service.init_db()
    db_service.set_setting("volume_alerts_enabled", "True")
    return temp_file.name


def _load_telegram_alerts_module():
    credentials_path = Path('credentials_b.json')
    created_credentials = False
    if not credentials_path.exists():
        credentials_path.write_text(
            json.dumps(
                {
                    "telegram_bot_token": "test-token",
                    "telegram_chat_id": "123",
                }
            )
        )
        created_credentials = True

    try:
        sys.modules.pop('telegram_alerts', None)
        return importlib.import_module('telegram_alerts'), created_credentials
    finally:
        if created_credentials and credentials_path.exists():
            credentials_path.unlink()


def _sample_alert(exchange):
    return {
        'exchange': exchange,
        'symbol': 'BTCUSDC',
        'curr_volume': 123456.0,
        'prev_volume_mean': 45678.0,
        'last_1h_volume': 11111.0,
        'last_2h_volume': 22222.0,
        'last_4h_volume': 33333.0,
        'level': 'HIGH',
        'chart_url': 'https://example.com/chart',
        'trade_url': 'https://example.com/trade',
        'binance_trade_url': 'https://example.com/binance-trade',
        'open_price': '1.0',
        'close_price': '1.1',
    }


def test_send_telegram_message_skips_unselected_exchange():
    temp_db = _prepare_temp_db()
    try:
        telegram_alerts, _ = _load_telegram_alerts_module()
        telegram_alerts.get_alert_exchange_selection = lambda chat_id: {'mode': 'selected', 'exchanges': ['kraken']}

        assert telegram_alerts.send_telegram_message(_sample_alert('BINANCE'), dry_run=True) is False
    finally:
        if os.path.exists(temp_db):
            os.unlink(temp_db)


def test_send_telegram_message_allows_selected_exchange():
    temp_db = _prepare_temp_db()
    try:
        telegram_alerts, _ = _load_telegram_alerts_module()
        telegram_alerts.get_alert_exchange_selection = lambda chat_id: {'mode': 'selected', 'exchanges': ['binance', 'kraken']}

        assert telegram_alerts.send_telegram_message(_sample_alert('KRAKEN'), dry_run=True) is True
    finally:
        if os.path.exists(temp_db):
            os.unlink(temp_db)


def test_volume_alert_restrict_keyboard_also_reuses_analyze_callback():
    temp_db = _prepare_temp_db()
    try:
        telegram_alerts, _ = _load_telegram_alerts_module()
        telegram_alerts.get_alert_exchange_selection = lambda chat_id: {'mode': 'all', 'exchanges': []}

        captured_payload = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"ok": True}

        def fake_post(url, json):
            captured_payload.update(json)
            return FakeResponse()

        telegram_alerts.requests.post = fake_post

        assert telegram_alerts.send_telegram_message(
            _sample_alert('BINANCE'),
            include_restrict_button=True,
            dry_run=False,
        ) is True

        reply_markup = json.loads(captured_payload['reply_markup'])
        keyboard = reply_markup['inline_keyboard']
        assert keyboard == [
            [{'text': 'Restrict BTCUSDC', 'callback_data': 'restrict_BTCUSDC'}],
            [{'text': '🔍 Analyze BTCUSDC', 'callback_data': 'menu_analyze_BTCUSDC'}],
        ]
    finally:
        if os.path.exists(temp_db):
            os.unlink(temp_db)


def test_should_deliver_exchange_alert_matches_scope():
    temp_db = _prepare_temp_db()
    try:
        telegram_alerts, _ = _load_telegram_alerts_module()

        assert should_send_alert_for_scope('KRAKEN', {'mode': 'all', 'exchanges': []}) is True
        assert should_send_alert_for_scope('BINANCE', {'mode': 'all', 'exchanges': []}) is True
        assert should_send_alert_for_scope('KRAKEN', {'mode': 'selected', 'exchanges': ['kraken']}) is True
        assert should_send_alert_for_scope('BINANCE', {'mode': 'selected', 'exchanges': ['binance']}) is True
        assert should_send_alert_for_scope('KRAKEN', {'mode': 'selected', 'exchanges': ['binance']}) is False
        assert should_send_alert_for_scope('BINANCE', {'mode': 'selected', 'exchanges': ['kraken']}) is False
    finally:
        if os.path.exists(temp_db):
            os.unlink(temp_db)
