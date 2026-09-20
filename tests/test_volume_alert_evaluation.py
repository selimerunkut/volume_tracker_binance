from datetime import datetime, timedelta, timezone

from src.services.volume_alert_evaluation import (
    calculate_forward_return,
    calculate_forward_return_minutes,
    compare_baselines,
    deduplicate_alert_events,
    evaluate_matched_events,
    select_completed_close,
)


def _candles(count=6):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "timestamp": start + timedelta(hours=hour),
            "close": 100.0 + hour,
        }
        for hour in range(count)
    ]


def _event(event_id, detected_at="2026-01-01T00:17:00+00:00", action="WAIT"):
    return {
        "id": event_id,
        "detected_at": detected_at,
        "exchange_name": "kraken",
        "symbol": "SUIUSD",
        "entry_price": 100.0,
        "strategy_action": action,
    }


def test_select_completed_close_never_uses_future_candle_close():
    endpoint = select_completed_close(
        _candles(),
        "2026-01-01T01:17:00+00:00",
    )
    assert endpoint["timestamp"] == datetime(2026, 1, 1, 0, tzinfo=timezone.utc)
    assert endpoint["close"] == 100.0


def test_forward_return_uses_last_completed_candle():
    result = calculate_forward_return(_event(1), _candles(), 2)
    assert result == 1.0


def test_short_horizon_uses_completed_five_minute_candles():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [
        {"timestamp": start + timedelta(minutes=5 * index), "close": 100.0 + index}
        for index in range(8)
    ]
    event = _event(1, detected_at="2026-01-01T00:02:00+00:00")

    immediate = calculate_forward_return_minutes(event, candles, hold_minutes=15)
    delayed = calculate_forward_return_minutes(
        event, candles, entry_delay_minutes=5, hold_minutes=15
    )

    assert immediate == 2.0
    assert delayed == 3.0
    assert calculate_forward_return_minutes(
        event,
        candles,
        hold_minutes=30,
        as_of="2026-01-01T00:20:00+00:00",
    ) is None


def test_matched_evaluation_uses_same_events_for_all_horizons():
    events = [
        _event(1),
        {**_event(2, detected_at="2026-01-01T01:17:00+00:00", action="LONG"),
         "candle_start": "2026-01-01T01:00:00+00:00"},
    ]
    candles = {("kraken", "SUIUSD"): _candles()}
    records = evaluate_matched_events(events, candles, [1, 2, 3])

    assert [record["event"]["id"] for record in records] == [1, 2]
    assert all(set(record["returns"]) == {1, 2, 3} for record in records)


def test_repeated_scans_of_one_candle_are_one_outcome_observation():
    events = [
        {**_event(1), "candle_start": "2026-01-01T00:00:00+00:00", "level": "500%+"},
        {**_event(2, detected_at="2026-01-01T00:30:00+00:00"), "candle_start": "2026-01-01T00:00:00+00:00", "level": "500%+"},
        {**_event(3, detected_at="2026-01-01T00:30:00+00:00"), "candle_start": "2026-01-01T00:00:00+00:00", "level": "1500%+"},
    ]

    unique = deduplicate_alert_events(events)

    assert [event["id"] for event in unique] == [1, 3]


def test_matched_evaluation_excludes_event_missing_any_horizon():
    events = [_event(1)]
    candles = {("kraken", "SUIUSD"): _candles(1)}
    assert evaluate_matched_events(events, candles, [1, 2, 3]) == []


def test_maturity_gate_excludes_events_without_a_completed_horizon():
    events = [_event(1)]
    candles = {("kraken", "SUIUSD"): _candles()}

    assert evaluate_matched_events(
        events,
        candles,
        [1],
        as_of="2026-01-01T00:30:00+00:00",
    ) == []
    assert evaluate_matched_events(
        events,
        candles,
        [1],
        as_of="2026-01-01T01:30:00+00:00",
    )


def test_baselines_share_the_same_eligible_cohort():
    events = [
        {**_event(1, action="LONG"), "normalized_action": "LONG", "candle_start": "2026-01-01T00:00:00+00:00"},
        {**_event(2, action="WAIT"), "normalized_action": "WAIT", "candle_start": "2026-01-01T01:00:00+00:00"},
    ]
    candles = {("kraken", "SUIUSD"): _candles()}
    records = evaluate_matched_events(events, candles, [1])
    baselines = compare_baselines(records, 1, cost_percent=0.2)

    assert baselines["every_alert"]["n"] == 2
    assert baselines["current_long_filter"]["n"] == 2
    assert baselines["current_long_filter"]["trades"] == 1
    assert baselines["normalized_long_filter"]["n"] == 2
    assert baselines["normalized_long_filter"]["trades"] == 1
    assert baselines["cash"]["n"] == 2
    assert baselines["cash"]["trades"] == 0
    assert baselines["cash"]["mean_percent"] == 0.0
    assert baselines["cash"]["mean_net_percent"] == 0.0
