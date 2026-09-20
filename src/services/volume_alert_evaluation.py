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
    entry_value = event.get("entry_price", event.get("close_price"))
    if entry_value is None:
        return None
    entry_price = float(entry_value)
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


def calculate_forward_return_minutes(
    event,
    candles,
    entry_delay_minutes=0,
    hold_minutes=30,
    interval=timedelta(minutes=5),
):
    """Evaluate a short-horizon trade using completed fine-grained candles.

    A zero-delay entry uses the captured event price. A delayed entry uses the
    latest completed candle close at the delayed entry time. The exit also uses
    the latest completed close at or before the requested holding boundary.
    """
    detected_at = _utc_naive(event["detected_at"])
    delay = timedelta(minutes=entry_delay_minutes)
    entry_time = detected_at + delay
    if entry_delay_minutes:
        entry_candle = select_completed_close(candles, entry_time, interval=interval)
        if entry_candle is None:
            return None
        entry_price = _candle_close(entry_candle)
    else:
        entry_value = event.get("entry_price", event.get("close_price"))
        if entry_value is None:
            return None
        entry_price = float(entry_value)
    if entry_price <= 0:
        return None

    exit_candle = select_completed_close(
        candles,
        entry_time + timedelta(minutes=hold_minutes),
        interval=interval,
    )
    if exit_candle is None:
        return None
    return (_candle_close(exit_candle) - entry_price) / entry_price * 100


def deduplicate_alert_events(events):
    """Keep one observation per exchange/symbol/candle/level.

    The scanner may inspect the same forming candle several times while a
    cooldown suppresses delivery. Raw rows remain intact for auditability;
    outcome studies must not count those repeated observations as trades.
    """
    unique = {}
    for event in sorted(events, key=lambda item: str(item.get("detected_at", ""))):
        key = (
            event.get("exchange_name"),
            event.get("symbol"),
            event.get("timeframe", "1h"),
            event.get("candle_start") or event.get("detected_at"),
            event.get("level"),
        )
        unique.setdefault(key, event)
    return list(unique.values())


def evaluate_matched_events(events, candles_by_key, horizons, as_of=None):
    """Evaluate one deduplicated cohort complete at every requested horizon.

    ``as_of`` is required by production reports to prevent a missing endpoint
    from being mistaken for a mature observation. ``candles_by_key`` is keyed
    by ``(exchange_name, symbol)``.
    """
    horizons = tuple(sorted(set(int(horizon) for horizon in horizons)))
    maturity_time = _utc_naive(as_of) if as_of is not None else None
    records = []
    for event in deduplicate_alert_events(events):
        detected_at = _utc_naive(event["detected_at"])
        if maturity_time is not None and detected_at + timedelta(hours=max(horizons)) > maturity_time:
            continue
        key = (event["exchange_name"], event["symbol"])
        candles = candles_by_key.get(key, ())
        returns = {
            horizon: calculate_forward_return(event, candles, horizon)
            for horizon in horizons
        }
        if all(value is not None for value in returns.values()):
            records.append({"event": event, "returns": returns})
    return records


def summarize_returns(values, cost_percent=0.2, executed=None):
    """Summarize policy returns, charging costs only on executed rows."""
    values = [float(value) for value in values]
    if executed is None:
        executed = [True] * len(values)
    executed = [bool(value) for value in executed]
    if len(values) != len(executed):
        raise ValueError("values and executed must have the same length")
    if not values:
        return {"n": 0, "trades": 0}

    net_values = [
        value - cost_percent if is_executed else value
        for value, is_executed in zip(values, executed)
    ]
    trade_values = [value for value, is_executed in zip(values, executed) if is_executed]
    trade_net_values = [value - cost_percent for value in trade_values]
    return {
        "n": len(values),
        "trades": len(trade_values),
        "mean_percent": mean(values),
        "median_percent": median(values),
        "positive_percent": 100 * sum(value > 0 for value in values) / len(values),
        "net_positive_percent": 100 * sum(value > 0 for value in net_values) / len(net_values),
        "mean_net_percent": mean(net_values),
        "trade_only": {
            "n": len(trade_values),
            "mean_percent": mean(trade_values) if trade_values else None,
            "median_percent": median(trade_values) if trade_values else None,
            "mean_net_percent": mean(trade_net_values) if trade_values else None,
        },
    }


def _filter_policy(records, horizon, action_key):
    values = []
    executed = []
    missing_scores = 0
    for record in records:
        action = record["event"].get(action_key)
        is_long = str(action or "").upper() == "LONG"
        if action is None:
            missing_scores += 1
        executed.append(is_long)
        values.append(record["returns"][horizon] if is_long else 0.0)
    return values, executed, missing_scores


def compare_baselines(records, horizon, cost_percent=0.2):
    """Compare four policies on identical rows and keep trade-only stats."""
    all_values = [record["returns"][horizon] for record in records]
    all_executed = [True] * len(all_values)
    current_values, current_executed, current_missing = _filter_policy(
        records, horizon, "strategy_action"
    )
    normalized_values, normalized_executed, normalized_missing = _filter_policy(
        records, horizon, "normalized_action"
    )
    return {
        "every_alert": summarize_returns(all_values, cost_percent, all_executed),
        "current_long_filter": {
            **summarize_returns(current_values, cost_percent, current_executed),
            "missing_score_count": current_missing,
        },
        "normalized_long_filter": {
            **summarize_returns(normalized_values, cost_percent, normalized_executed),
            "missing_score_count": normalized_missing,
        },
        "cash": summarize_returns([0.0] * len(all_values), 0.0, [False] * len(all_values)),
    }
