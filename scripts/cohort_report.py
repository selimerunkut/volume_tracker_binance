#!/usr/bin/env python3
"""Report live and backfill outcome cohorts without tuning the strategy."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3

from src.services.db_service import DB_PATH


def _rows(conn, table):
    rows = conn.execute(
        f"SELECT strategy_type, status, analysis_data FROM {table} WHERE status IN ('WIN','LOSS','EXPIRED')"
    ).fetchall()
    output = []
    for strategy, status, raw in rows:
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            data = {}
        regimes = data.get("btc_market_regime") or {}
        regime = regimes.get("okx") or regimes.get("kraken") or {}
        output.append({
            "direction": strategy,
            "status": status,
            "volatility": regime.get("volatility", "unknown"),
            "volume_tag": regime.get("volume_tag", "unknown"),
            "altseason": (data.get("cmc_altseason_index") or {}).get("bucket", "unknown"),
        })
    return output


def report(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    try:
        result = {}
        for table in ("suggestions", "backfill_suggestions"):
            try:
                rows = _rows(conn, table)
            except sqlite3.OperationalError:
                rows = []
            groups = {}
            for row in rows:
                key = (row["direction"], row["volatility"], row["volume_tag"])
                groups.setdefault(key, []).append(row)
            result[table] = []
            for key, group in sorted(groups.items()):
                n = len(group)
                wins = sum(row["status"] == "WIN" for row in group)
                p = wins / n if n else 0
                error = 2 * math.sqrt(p * (1 - p) / n) if n else None
                result[table].append({"direction": key[0], "volatility": key[1], "volume_tag": key[2],
                                      "n": n, "wins": wins, "win_rate": p, "error": error,
                                      "sample_status": "insufficient_sample" if n < 20 else "eligible"})
        return result
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()
    print(json.dumps(report(args.db), indent=2, sort_keys=True))
