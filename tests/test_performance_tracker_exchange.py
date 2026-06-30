from __future__ import annotations

from datetime import datetime, timedelta

from src.services import performance_tracker


def test_track_performance_uses_stored_exchange_for_each_suggestion(monkeypatch):
    suggestions = [
        {
            'id': 1,
            'symbol': 'SAFEUSD',
            'strategy_type': 'LONG',
            'entry_price': 100.0,
            'take_profit': 104.0,
            'stop_loss': 98.0,
            'created_at': (datetime.now() - timedelta(hours=25)).isoformat(),
            'analysis_data': {'exchange_name': 'kraken'},
        },
        {
            'id': 2,
            'symbol': 'SAFEUSD',
            'strategy_type': 'WAIT',
            'entry_price': 100.0,
            'take_profit': 100.0,
            'stop_loss': 100.0,
            'created_at': (datetime.now() - timedelta(hours=25)).isoformat(),
            'analysis_data': {'exchange_name': 'okx'},
        },
    ]

    price_calls = []
    updates = []

    monkeypatch.setattr(performance_tracker, 'get_pending_suggestions', lambda: suggestions)
    monkeypatch.setattr(performance_tracker, 'get_pending_signal_trades', lambda: [])
    monkeypatch.setattr(
        performance_tracker,
        'get_current_price',
        lambda symbol, exchange_name='binance': price_calls.append((symbol, exchange_name)) or 101.0,
    )
    monkeypatch.setattr(
        performance_tracker,
        'update_outcome',
        lambda suggestion_id, status, pnl_percent=None: updates.append((suggestion_id, status, pnl_percent)),
    )

    performance_tracker.track_performance()

    assert price_calls == [('SAFEUSD', 'kraken'), ('SAFEUSD', 'okx')]
    assert updates[0][0] == 1
