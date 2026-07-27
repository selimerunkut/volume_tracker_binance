#!/usr/bin/env python3
"""Replay the deterministic strategy on pinned hourly Feather inputs.

This intentionally uses a daily-close trigger and writes only backfill_suggestions.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.services.db_service import DB_PATH, get_connection, init_db
from src.services.deterministic_strategy import evaluate_strategy
from src.services.performance_tracker import evaluate_candle_path
from src.services.regime_service import get_regimes_at
from src.services.technical_analysis import calculate_indicators, get_latest_indicators


def ensure_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS backfill_suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, exchange_name TEXT NOT NULL,
        created_at TEXT NOT NULL, strategy_type TEXT NOT NULL, entry_price REAL NOT NULL,
        take_profit REAL NOT NULL, stop_loss REAL NOT NULL, reasoning TEXT,
        status TEXT NOT NULL, pnl_percent REAL, analysis_data TEXT NOT NULL,
        UNIQUE(symbol, exchange_name, created_at)
    )""")


def run(input_dir, exchange_name="kraken", db_path=DB_PATH):
    init_db()
    files = sorted(Path(input_dir).glob("*.feather"))
    if not files:
        raise FileNotFoundError(f"no Feather files in {input_dir}")
    conn = sqlite3.connect(db_path)
    try:
        ensure_table(conn)
        for path in files:
            symbol = path.stem.split("-")[0].upper()
            frame = pd.read_feather(path)
            timestamp_column = "timestamp" if "timestamp" in frame else "date"
            frame[timestamp_column] = pd.to_datetime(frame[timestamp_column], utc=True)
            frame = frame.sort_values(timestamp_column).reset_index(drop=True)
            days = frame[timestamp_column].dt.normalize().drop_duplicates()
            for day in days[:-1]:
                at_close = frame[frame[timestamp_column] <= day + pd.Timedelta(hours=23)]
                if len(at_close) < 250:
                    continue
                existing = conn.execute(
                    "SELECT 1 FROM backfill_suggestions WHERE symbol=? AND exchange_name=? AND created_at=?",
                    (symbol, exchange_name, day.isoformat()),
                ).fetchone()
                if existing:
                    continue
                indicators = get_latest_indicators(calculate_indicators(at_close.tail(250)))
                price = float(at_close.iloc[-1]["close"])
                strategy = evaluate_strategy(indicators, price)
                future = frame[(frame[timestamp_column] > day + pd.Timedelta(hours=23)) & (frame[timestamp_column] <= day + pd.Timedelta(days=2))]
                suggestion = {
                    "created_at": day.to_pydatetime().replace(tzinfo=None).isoformat(),
                    "strategy_type": strategy["action"], "entry_price": strategy["entry"],
                    "take_profit": strategy["tp"], "stop_loss": strategy["sl"],
                }
                status, pnl = evaluate_candle_path(suggestion, future.rename(columns={timestamp_column: "timestamp"}), now=day.to_pydatetime().replace(tzinfo=None) + pd.Timedelta(days=2))
                regimes = get_regimes_at(day.to_pydatetime())
                data = {"source": "backfill", "exchange_name": exchange_name, "btc_market_regime": regimes,
                        "trigger": "daily_close", "symbol": symbol}
                conn.execute(
                    """INSERT OR IGNORE INTO backfill_suggestions
                    (symbol, exchange_name, created_at, strategy_type, entry_price, take_profit,
                     stop_loss, reasoning, status, pnl_percent, analysis_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (symbol, exchange_name, suggestion["created_at"], strategy["action"], strategy["entry"],
                     strategy["tp"], strategy["sl"], strategy["reasoning"], status, pnl, json.dumps(data)),
                )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir")
    parser.add_argument("--exchange", default="kraken")
    args = parser.parse_args()
    run(args.input_dir, args.exchange)
