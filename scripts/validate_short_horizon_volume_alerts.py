"""Validate short-horizon returns after the persisted auto volume-alert proxy.

This is an analysis-only script. It does not modify live scoring or trading.
It uses the durable ``suggestions(source='auto')`` rows because those rows are
created immediately after alert qualification and before Telegram delivery.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from src.services.volume_alert_evaluation import (
    calculate_forward_return_minutes,
)

HORIZONS_MINUTES = (15, 30, 45, 60, 120, 180)
ENTRY_DELAYS_MINUTES = (0, 5)
CANDLE_INTERVAL = timedelta(minutes=5)
COST_PERCENT = 0.2


def parse_utc(value):
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_events(db_path):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT id, timestamp, exchange_name, symbol, entry_price,
                   strategy_type
            FROM suggestions
            WHERE source = 'auto'
            ORDER BY timestamp, id
            """
        ).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in rows]


def request_json(session, url, params, retries=6):
    for attempt in range(retries):
        response = session.get(url, params=params, timeout=30)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        time.sleep(min(2 ** attempt, 30))
    response.raise_for_status()
    return response.json()


def fetch_okx_candles(session, event, target):
    target_ms = int(target.timestamp() * 1000)
    payload = request_json(
        session,
        "https://eea.okx.com/api/v5/market/history-candles",
        {"instId": event["symbol"], "bar": "5m", "limit": "100", "after": str(target_ms)},
    )
    if payload.get("code") != "0":
        raise RuntimeError(payload)
    candles = []
    for row in payload.get("data", []):
        if len(row) < 5:
            continue
        if len(row) >= 9 and str(row[8]) not in {"", "1"}:
            continue
        candles.append(
            {
                "timestamp": datetime.fromtimestamp(
                    int(row[0]) / 1000, timezone.utc
                ).isoformat(),
                "close": float(row[4]),
            }
        )
    return candles


def fetch_kraken_trades(session, event, end):
    start = parse_utc(event["timestamp"])
    since = int(start.timestamp() * 1_000_000_000)
    end_seconds = end.timestamp()
    trades = []
    last_since = None
    for _ in range(20):
        payload = request_json(
            session,
            "https://api.kraken.com/0/public/Trades",
            {"pair": event["symbol"], "since": str(since)},
        )
        if payload.get("error"):
            raise RuntimeError(payload["error"])
        result = payload.get("result") or {}
        rows = next((value for key, value in result.items() if key != "last"), [])
        for row in rows:
            timestamp = float(row[2])
            if timestamp <= end_seconds:
                trades.append(
                    {
                        "timestamp": datetime.fromtimestamp(
                            timestamp, timezone.utc
                        ).isoformat(),
                        "close": float(row[0]),
                    }
                )
        last = int(result.get("last", 0))
        if not rows or last <= since or last == last_since:
            break
        last_since = last
        if max(float(row[2]) for row in rows) >= end_seconds:
            break
        since = last
    return aggregate_kraken_trades(trades)


def aggregate_kraken_trades(trades):
    buckets = {}
    for trade in trades:
        timestamp = parse_utc(trade["timestamp"])
        bucket_seconds = int(timestamp.timestamp()) // 300 * 300
        bucket = datetime.fromtimestamp(bucket_seconds, timezone.utc)
        buckets[bucket.isoformat()] = trade["close"]
    return [
        {"timestamp": timestamp, "close": close}
        for timestamp, close in sorted(buckets.items())
    ]


def summarize(values, executed, cost_percent=COST_PERCENT):
    net = [value - cost_percent if flag else 0.0 for value, flag in zip(values, executed)]
    trades = [value for value, flag in zip(values, executed) if flag]
    trade_net = [value - cost_percent for value in trades]
    if not values:
        return {"n": 0, "trades": 0}
    return {
        "n": len(values),
        "trades": len(trades),
        "mean_net_per_row_percent": sum(net) / len(net),
        "median_net_per_row_percent": sorted(net)[len(net) // 2],
        "total_net_percent": sum(net),
        "trade_mean_gross_percent": sum(trades) / len(trades) if trades else None,
        "trade_mean_net_percent": sum(trade_net) / len(trade_net) if trade_net else None,
        "trade_positive_after_cost_percent": (
            100 * sum(value > 0 for value in trade_net) / len(trade_net)
            if trade_net
            else None
        ),
    }


def evaluate_policy(records, horizon, action):
    values = [record["returns"][action][horizon] for record in records]
    if action == "every_alert":
        executed = [True] * len(values)
    elif action == "current_long":
        executed = [record["event"]["strategy_type"] == "LONG" for record in records]
    else:
        executed = [False] * len(values)
    return summarize(values, executed)


def main():
    db_path = os.environ.get("VOLUME_ALERT_DB", "trading_memory.db")
    output_path = Path(
        os.environ.get(
            "VOLUME_ALERT_SHORT_OUTPUT",
            "memory-bank/short-horizon-volume-alert-report.json",
        )
    )
    as_of = datetime.now(timezone.utc)
    events = load_events(db_path)
    max_window = timedelta(minutes=max(HORIZONS_MINUTES) + max(ENTRY_DELAYS_MINUTES))
    mature_events = [
        event
        for event in events
        if parse_utc(event["timestamp"]) + max_window <= as_of
    ]

    session = requests.Session()
    records = []
    errors = []
    for index, event in enumerate(mature_events, start=1):
        detected_at = parse_utc(event["timestamp"])
        target = detected_at + max_window
        try:
            if event["exchange_name"].lower() == "okx":
                candles = fetch_okx_candles(session, event, target)
            elif event["exchange_name"].lower() == "kraken":
                candles = fetch_kraken_trades(session, event, target)
            else:
                raise RuntimeError(f"unsupported exchange: {event['exchange_name']}")
            returns = {}
            for delay in ENTRY_DELAYS_MINUTES:
                returns[delay] = {
                    horizon: calculate_forward_return_minutes(
                        {
                            "detected_at": event["timestamp"],
                            "entry_price": event["entry_price"],
                        },
                        candles,
                        entry_delay_minutes=delay,
                        hold_minutes=horizon,
                        interval=CANDLE_INTERVAL,
                        as_of=as_of,
                    )
                    for horizon in HORIZONS_MINUTES
                }
            records.append({"event": event, "returns": returns})
        except Exception as exc:
            errors.append(
                {
                    "id": event["id"],
                    "exchange": event["exchange_name"],
                    "symbol": event["symbol"],
                    "error": str(exc),
                }
            )
        if index % 100 == 0:
            print(f"processed={index}/{len(mature_events)} errors={len(errors)}", flush=True)

    coverage = {}
    for delay in ENTRY_DELAYS_MINUTES:
        coverage[delay] = {
            horizon: sum(
                record["returns"][delay][horizon] is not None for record in records
            )
            for horizon in HORIZONS_MINUTES
        }

    matched_both = [
        record
        for record in records
        if all(
            record["returns"][delay][horizon] is not None
            for delay in ENTRY_DELAYS_MINUTES
            for horizon in HORIZONS_MINUTES
        )
    ]
    summaries = {}
    for delay in ENTRY_DELAYS_MINUTES:
        summaries[str(delay)] = {
            str(horizon): {
                policy: evaluate_policy(
                    [
                        {
                            "event": record["event"],
                            "returns": {
                                "every_alert": record["returns"][delay],
                                "current_long": record["returns"][delay],
                            },
                        }
                        for record in matched_both
                    ],
                    horizon,
                    policy,
                )
                for policy in ("every_alert", "current_long")
            }
            for horizon in HORIZONS_MINUTES
        }

    artifact = {
        "as_of": as_of.isoformat(),
        "source": "suggestions where source='auto'",
        "raw_events": len(events),
        "mature_3h_events": len(mature_events),
        "fetched_records": len(records),
        "matched_all_delays_and_horizons": len(matched_both),
        "entry_delays_minutes": ENTRY_DELAYS_MINUTES,
        "holding_periods_minutes": HORIZONS_MINUTES,
        "candle_interval_minutes": 5,
        "cost_percent_per_executed_trade": COST_PERCENT,
        "costs_on_abstentions": False,
        "live_behavior_changed": False,
        "coverage": coverage,
        "summaries_on_common_cohort": summaries,
        "errors": errors,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2) + "\n")
    print(json.dumps(artifact, indent=2))


if __name__ == "__main__":
    main()
