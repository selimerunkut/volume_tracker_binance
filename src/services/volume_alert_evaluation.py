"""Measurement helpers for volume-alert forward-return studies.

These helpers use completed candle closes at or before each requested horizon.
They intentionally keep one matched event cohort across all horizons.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean, median


def _utc_naive(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _candle_timestamp(candle):
    value = candle["timestamp"] if isinstance(candle, dict) else candle.timestamp
    return _utc_naive(value)


def _candle_close(candle):
    value = candle["close"] if isinstance(candle, dict) else candle.close
    return float(value)


def select_completed_close(candles, target, interval=timedelta(hours=1)):
    """Select the latest candle close known by ``target``.

    Candle timestamps represent candle opens. A candle is usable only after its
    interval has completed. This avoids using a candle close from the future.
    """
    target = _utc_naive(target)
    eligible = [
        candle for candle in candles
        if _candle_timestamp(candle) + interval <= target
    ]
    if not eligible:
        return None
    endpoint = max(eligible, key=_candle_timestamp)
    if target - (_candle_timestamp(endpoint) + interval) > interval * 1.5:
        return None
    return endpoint


def calculate_forward_return(event, candles, horizon_hours, interval=timedelta(hours=1)):
    """Return the close-to-entry percentage for one event and horizon."""
    detected_at = _utc_naive(event["detected_at"])
    entry_price = float(event["entry_price"])
    if entry_price <= 0:
        return None
    endpoint = select_completed_close(
        candles,
        detected_at + timedelta(hours=horizon_hours),
        interval=interval,
    )
    if endpoint is None:
        return None
    return (float(_candle_close(endpoint)) - entry_price) / entry_price * 100


def evaluate_matched_events(events, candles_by_key, horizons):
    """Evaluate only events complete at every requested horizon.

    This prevents each holding period from silently using a different eligible
    sample. ``candles_by_key`` is keyed by ``(exchange_name, symbol)``.
    """
    horizons = tuple(sorted(set(int(horizon) for horizon in horizons)))
    records = []
    for event in events:
        key = (event["exchange_name"], event["symbol"])
        candles = candles_by_key.get(key, ())
        returns = {
            horizon: calculate_forward_return(event, candles, horizon)
            for horizon in horizons
        }
        if all(value is not None for value in returns.values()):
            records.append({"event": event, "returns": returns})
    return records


def summarize_returns(values, cost_percent=0.2):
    values = [float(value) for value in values]
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean_percent": mean(values),
        "median_percent": median(values),
        "positive_percent": 100 * sum(value > 0 for value in values) / len(values),
        "net_positive_percent": 100 * sum(value > cost_percent for value in values) / len(values),
        "mean_net_percent": mean(values) - cost_percent,
    }


def compare_baselines(records, horizon, cost_percent=0.2):
    """Compare every-alert, current LONG filter, and cash on one cohort."""
    all_values = [record["returns"][horizon] for record in records]
    filtered_values = [
        record["returns"][horizon]
        for record in records
        if str(record["event"].get("strategy_action", "")).upper() == "LONG"
    ]
    return {
        "every_alert": summarize_returns(all_values, cost_percent),
        "current_long_filter": summarize_returns(filtered_values, cost_percent),
        "cash": summarize_returns([0.0] * len(all_values), cost_percent),
    }
