"""Persistence and lookup orchestration for per-venue BTC regimes."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from .db_service import get_connection, init_db
from .regime_labeler import current_snapshot, label_file

logger = logging.getLogger(__name__)

VENUES = ("okx", "kraken")
SOURCE_ENV = {
    "okx": "REGIME_SOURCE_FEATHER_OKX",
    "kraken": "REGIME_SOURCE_FEATHER_KRAKEN",
}


def _source_path(venue):
    value = os.getenv(SOURCE_ENV[venue])
    if not value:
        raise RuntimeError(f"{SOURCE_ENV[venue]} is not configured")
    return value


def run_venue(venue, require_freshness=True):
    venue = venue.lower()
    path = _source_path(venue)
    labels, metadata = label_file(path, venue, require_freshness=require_freshness)
    computed_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        with conn:
            for _, row in labels.iterrows():
                conn.execute(
                    """
                    INSERT INTO regime_labels
                    (venue, instrument, timeframe, date, direction, raw_direction,
                     volatility, volume_tag, computed_at, contract_sha256,
                     validation_result, source_rows, source_first_ts, source_last_ts,
                     source_completed_through, source_sha256)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(venue, instrument, timeframe, date) DO UPDATE SET
                      direction=excluded.direction,
                      raw_direction=excluded.raw_direction,
                      volatility=excluded.volatility,
                      volume_tag=excluded.volume_tag,
                      computed_at=excluded.computed_at,
                      validation_result=excluded.validation_result,
                      source_rows=excluded.source_rows,
                      source_first_ts=excluded.source_first_ts,
                      source_last_ts=excluded.source_last_ts,
                      source_completed_through=excluded.source_completed_through,
                      source_sha256=excluded.source_sha256,
                      contract_sha256=excluded.contract_sha256
                    """,
                    (
                        venue, metadata["instrument"], metadata["timeframe"],
                        row["timestamp"].date().isoformat(), row["direction"],
                        row["raw_direction"], row["volatility"], row["volume_tag"],
                        computed_at, metadata["contract_sha256"], metadata["validation_result"],
                        metadata["source_rows"], metadata["source_first_ts"], metadata["source_last_ts"],
                        metadata["source_completed_through"], metadata["source_sha256"],
                    ),
                )
    finally:
        conn.close()
    snapshot = current_snapshot(labels)
    logger.info("Regime %s updated through %s: %s", venue, metadata["source_completed_through"], snapshot)
    return snapshot


def run_all(require_freshness=True):
    init_db()
    results = {}
    for venue in VENUES:
        try:
            results[venue] = run_venue(venue, require_freshness=require_freshness)
        except Exception as exc:
            logger.exception("Regime %s failed closed: %s", venue, exc)
            results[venue] = {"status": "unknown/stale", "error": str(exc)}
    if all(results.get(venue, {}).get("status") == "ok" for venue in VENUES):
        if results["okx"].get("direction") != results["kraken"].get("direction"):
            logger.warning("Cross-venue BTC regime divergence: %s", results)
    return results


def get_regimes_at(event_ts=None):
    """Return labels strictly before an event timestamp, never a future label."""
    init_db()
    if event_ts is None:
        event_ts = datetime.now(timezone.utc)
    event_iso = event_ts.isoformat() if hasattr(event_ts, "isoformat") else str(event_ts)
    result = {}
    conn = get_connection()
    try:
        for venue in VENUES:
            row = conn.execute(
                """
                SELECT * FROM regime_labels
                WHERE venue = ? AND instrument = 'BTC/USDC' AND timeframe = '1h'
                  AND date < ?
                ORDER BY date DESC LIMIT 1
                """,
                (venue, event_iso[:10]),
            ).fetchone()
            if row is None:
                result[venue] = {"status": "unknown/stale"}
            else:
                result[venue] = dict(row)
                result[venue]["status"] = "ok"
    finally:
        conn.close()
    return result


def get_current_regimes():
    return get_regimes_at(datetime.now(timezone.utc))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run_all())
