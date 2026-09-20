import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services import db_service, performance_tracker


def setup_module(module):
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.close()
    module.temp_db_path = temp_file.name
    db_service.DB_PATH = module.temp_db_path
    db_service.init_db()


def teardown_module(module):
    if os.path.exists(module.temp_db_path):
        os.unlink(module.temp_db_path)


def _clear_signal_table():
    conn = db_service.get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM signal_trades')
    conn.commit()
    conn.close()


def _clear_volume_alert_event_table():
    conn = db_service.get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM volume_alert_events')
    conn.commit()
    conn.close()


def test_volume_alert_event_captures_delivery_outcome():
    _clear_volume_alert_event_table()
    event_id = db_service.save_volume_alert_event(
        detected_at='2026-09-20T12:00:00+00:00',
        candle_start='2026-09-20T12:00:00+00:00',
        candle_elapsed_seconds=15.0,
        exchange_name='kraken',
        symbol='SUIUSD',
        timeframe='1h',
        level='500%+',
        curr_volume=78674.0,
        prev_volume_mean=13125.0,
        last_completed_hour_volume=8341.0,
        last_2h_volume=13912.0,
        last_4h_volume=39002.0,
        open_price=0.1617,
        close_price=0.1634,
    )

    db_service.update_volume_alert_event(
        event_id,
        auto_signal_id=42,
        auto_signal_status='created',
        send_status='sent',
    )

    conn = db_service.get_connection()
    row = conn.execute(
        'SELECT * FROM volume_alert_events WHERE id = ?',
        (event_id,),
    ).fetchone()
    conn.close()

    assert row['exchange_name'] == 'kraken'
    assert row['symbol'] == 'SUIUSD'
    assert row['level'] == '500%+'
    assert row['curr_volume'] == 78674.0
    assert row['auto_signal_id'] == 42
    assert row['auto_signal_status'] == 'created'
    assert row['send_status'] == 'sent'


def test_signal_save_and_retrieve():
    _clear_signal_table()
    entry_ts = datetime.now().isoformat()
    signal_id = db_service.save_signal_trade(
        symbol='BTCUSDC',
        timeframe='1h',
        signal_type='hourly',
        action='LONG',
        entry_price=123.45,
        explanation='test signal',
        dedup_key='BTCUSDC_1h_LONG',
        entry_ts=entry_ts
    )

    assert signal_id is not None
    assert signal_id > 0

    last = db_service.get_last_signal_trade('BTCUSDC', '1h', 'LONG')
    assert last is not None
    assert last['id'] == signal_id
    assert last['explanation'] == 'test signal'
    assert last['entry_ts'] == entry_ts


def test_pending_signals_and_outcome():
    _clear_signal_table()
    signal_id = db_service.save_signal_trade(
        symbol='ETHUSDC',
        timeframe='1d',
        signal_type='daily',
        action='SHORT',
        entry_price=200.0,
        explanation='daily short',
        dedup_key='ETHUSDC_1d_SHORT'
    )

    pending = db_service.get_pending_signal_trades()
    assert len(pending) == 1
    assert pending[0]['id'] == signal_id

    db_service.update_signal_trade_outcome(signal_id, 'WIN', 5.5)
    pending_after = db_service.get_pending_signal_trades()
    assert len(pending_after) == 0


def test_evaluate_signal_trade():
    cases = [
        ('LONG', 103.0, 'WIN'),
        ('LONG', 96.0, 'LOSS'),
        ('SHORT', 95.0, 'WIN'),
        ('SHORT', 107.0, 'LOSS'),
        ('LONG', 101.0, 'EXPIRED'),
    ]

    entry_ts = (datetime.now() - timedelta(hours=25)).isoformat()
    for action, current_price, expected_status in cases:
        signal = {
            'entry_price': 100.0,
            'entry_ts': entry_ts,
            'action': action,
        }
        status, pnl = performance_tracker.evaluate_signal_trade(signal, current_price)
        assert status == expected_status
        if expected_status != 'PENDING':
            assert isinstance(pnl, float)
