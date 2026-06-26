import os
import sqlite3
import tempfile
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services import db_service
from src.services.alert_preferences import (
    get_alert_exchange_selection,
    get_chat_setting,
    normalize_alert_exchange_selection,
    set_alert_exchange_selection,
    set_chat_setting,
)


def _prepare_temp_db():
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.close()
    db_service.DB_PATH = temp_file.name
    db_service.init_db()
    return temp_file.name


def test_alert_selection_defaults_and_normalization():
    assert normalize_alert_exchange_selection(None) == {'mode': 'all', 'exchanges': []}
    assert normalize_alert_exchange_selection('all') == {'mode': 'all', 'exchanges': []}
    assert normalize_alert_exchange_selection('kraken') == {'mode': 'selected', 'exchanges': ['kraken']}
    assert normalize_alert_exchange_selection('okx') == {'mode': 'selected', 'exchanges': ['okx']}
    assert normalize_alert_exchange_selection(['binance', 'kraken', 'binance']) == {'mode': 'selected', 'exchanges': ['binance', 'kraken']}
    assert normalize_alert_exchange_selection(['binance', 'kraken', 'okx']) == {'mode': 'all', 'exchanges': []}
    assert normalize_alert_exchange_selection('coinbase') == {'mode': 'all', 'exchanges': []}


def test_chat_settings_round_trip():
    temp_db = _prepare_temp_db()
    try:
        assert get_chat_setting('123', 'missing', default='fallback') == 'fallback'
        assert db_service.get_chat_setting('123', 'missing', default='fallback') == 'fallback'
        assert set_chat_setting('123', 'foo', {'bar': 1}) == {'bar': 1}
        assert get_chat_setting('123', 'foo') == {'bar': 1}
        assert db_service.set_chat_setting('123', 'direct', 'value') == 'value'
        assert db_service.get_chat_setting('123', 'direct') == 'value'
    finally:
        if os.path.exists(temp_db):
            os.unlink(temp_db)


def test_alert_exchange_selection_round_trip():
    temp_db = _prepare_temp_db()
    try:
        assert get_alert_exchange_selection('123') == {'mode': 'all', 'exchanges': []}
        assert set_alert_exchange_selection('123', 'kraken') == {'mode': 'selected', 'exchanges': ['kraken']}
        assert get_alert_exchange_selection('123') == {'mode': 'selected', 'exchanges': ['kraken']}
        assert set_alert_exchange_selection('123', ['binance', 'kraken']) == {'mode': 'selected', 'exchanges': ['binance', 'kraken']}
        assert get_alert_exchange_selection('123') == {'mode': 'selected', 'exchanges': ['binance', 'kraken']}
        assert set_alert_exchange_selection('123', ['binance', 'kraken', 'okx']) == {'mode': 'all', 'exchanges': []}
        assert get_alert_exchange_selection('123') == {'mode': 'all', 'exchanges': []}
        assert set_alert_exchange_selection('123', 'all') == {'mode': 'all', 'exchanges': []}
        assert get_alert_exchange_selection('123') == {'mode': 'all', 'exchanges': []}
        assert set_alert_exchange_selection('123', 'coinbase') == {'mode': 'all', 'exchanges': []}
        assert get_alert_exchange_selection('123') == {'mode': 'all', 'exchanges': []}
    finally:
        if os.path.exists(temp_db):
            os.unlink(temp_db)
