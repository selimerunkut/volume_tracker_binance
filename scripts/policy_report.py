#!/usr/bin/env python3
"""Read-only comparison of the saved policy against simple baselines.

The report never updates the database.  "Always buy" uses the raw 24-hour
market return when the evaluator recorded one; rows without that return are
reported as unavailable rather than treated as zero.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from statistics import fmean

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.db_service import DB_PATH


TERMINAL_STATUSES = {"WIN", "LOSS", "EXPIRED", "UNEVALUABLE"}


def _rows(conn, table):
    try:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    except sqlite3.OperationalError:
        return []
    output = []
    for row in rows:
        item = dict(row)
        try:
            data = json.loads(item.get("analysis_data") or "{}")
        except (TypeError, json.JSONDecodeError):
            data = {}
        raw_return = item.get("raw_return_percent")
        if raw_return is None:
            raw_return = data.get("raw_return_percent")
        item["raw_return_percent"] = raw_return
        output.append(item)
    return output


def _summary(values):
    values = [float(value) for value in values if value is not None]
    return {
        "n": len(values),
        "mean_percent": round(fmean(values), 4) if values else None,
        "positive_rate": round(sum(value > 0 for value in values) / len(values), 4) if values else None,
    }


def _report_table(rows):
    terminal = [row for row in rows if row.get("status") in TERMINAL_STATUSES]
    policy_values = [row.get("pnl_percent") for row in terminal if row.get("pnl_percent") is not None]
    market_values = [row.get("raw_return_percent") for row in terminal if row.get("raw_return_percent") is not None]
    return {
        "rows": len(rows),
        "actions": {
            action: sum(str(row.get("strategy_type", "")).upper() == action for row in rows)
            for action in ("LONG", "SHORT", "WAIT")
        },
        "outcomes": {
            status: sum(row.get("status") == status for row in rows)
            for status in sorted(TERMINAL_STATUSES)
        },
        "current_policy": {
            **_summary(policy_values),
            "note": "Recorded strategy outcome; WAIT is not a traded return.",
        },
        "always_cash": _summary([0.0 for _ in market_values]),
        "always_buy": {
            **_summary(market_values),
            "unavailable": len(terminal) - len(market_values),
        },
    }


def report(db_path=DB_PATH):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return {table: _report_table(_rows(conn, table)) for table in ("suggestions", "backfill_suggestions")}
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()
    print(json.dumps(report(args.db), indent=2, sort_keys=True))
