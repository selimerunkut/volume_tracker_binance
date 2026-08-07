"""Persistence and lookup orchestration for per-venue BTC regimes."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import pandas as pd

from .db_service import get_connection, init_db
from .regime_labeler import current_snapshot, label_file

logger = logging.getLogger(__name__)

VENUES = ("okx", "kraken")
SOURCE_ENV = {
    "okx": "REGIME_SOURCE_FEATHER_OKX",
    "kraken": "REGIME_SOURCE_FEATHER_KRAKEN",
}
# Temporary source-data exception. Remove after the Q2 2026 Kraken history file
# fills 2026-04-03 through the first complete post-gap day.
TEMPORARY_IGNORED_DATES = {
    "kraken": set(pd.date_range("2026-04-02", "2026-06-02", freq="D", tz="UTC")) | {pd.Timestamp("2025-11-01", tz="UTC")},
    "okx": set(),
}


def _source_path(venue):
    value = os.getenv(SOURCE_ENV[venue])
    if not value:
        raise RuntimeError(f"{SOURCE_ENV[venue]} is not configured")
    return value


def _write_validation_status(venue, status, validation_result, *, completed_through=None,
                             source_sha256=None, error=None, validated_at=None):
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO regime_validation_status
                (venue, status, validation_result, validated_at,
                 source_completed_through, source_sha256, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(venue) DO UPDATE SET
                  status=excluded.status,
                  validation_result=excluded.validation_result,
                  validated_at=excluded.validated_at,
                  source_completed_through=excluded.source_completed_through,
                  source_sha256=excluded.source_sha256,
                  error=excluded.error
                """ ,
                (venue, status, validation_result,
                 validated_at or datetime.now(timezone.utc).isoformat(),
                 completed_through, source_sha256, error),
            )
    finally:
        conn.close()


def run_venue(venue, require_freshness=True, now=None):
    venue = venue.lower()
    init_db()
    now = now or datetime.now(timezone.utc)
    try:
        path = _source_path(venue)
        # Historical calculation may bypass artifact-age rejection, but it
        # never bypasses current-week gap validation in build_daily.
        labels, metadata = label_file(
            path,
            venue,
            require_freshness=False,
            now=now,
            ignored_dates=TEMPORARY_IGNORED_DATES.get(venue, set()),
        )
    except Exception as exc:
        _write_validation_status(venue, "unknown/stale", "failed", error=str(exc))
        raise
    if TEMPORARY_IGNORED_DATES.get(venue):
        metadata["validation_result"] = "complete_with_temporary_gap_exclusion"
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
    source_age_days = max(0, (now.date() - pd.Timestamp(metadata["source_completed_through"]).date()).days)
    snapshot["source_age_days"] = source_age_days
    live_status = "ok" if source_age_days <= 7 else "unknown/stale"
    _write_validation_status(
        venue, live_status, metadata["validation_result"],
        completed_through=metadata["source_completed_through"],
        source_sha256=metadata["source_sha256"],
    )
    if require_freshness and live_status != "ok":
        snapshot = {"status": "unknown/stale", "source_age_days": source_age_days,
                    "source_completed_through": metadata["source_completed_through"]}
    logger.info("Regime %s calculated through %s: %s", venue, metadata["source_completed_through"], snapshot)
    return snapshot


def run_all(require_freshness=True):
    init_db()
    results = {}
    for venue in VENUES:
        try:
            results[venue] = run_venue(venue, require_freshness=require_freshness)
        except Exception as exc:
            logger.warning("Regime %s failed closed: %s", venue, exc)
            results[venue] = {"status": "unknown/stale", "error": str(exc)}
    if all(results.get(venue, {}).get("status") == "ok" for venue in VENUES):
        if results["okx"].get("direction") != results["kraken"].get("direction"):
            logger.warning("Cross-venue BTC regime divergence: %s", results)
    return results


def get_regimes_at(event_ts=None):
    """Return labels strictly before an event timestamp, never a future label.

    Explicit historical timestamps use stored provenance. A live lookup also
    enforces the seven-day source freshness contract.
    """
    init_db()
    live_lookup = event_ts is None
    if event_ts is None:
        event_ts = datetime.now(timezone.utc)
    event_iso = event_ts.isoformat() if hasattr(event_ts, "isoformat") else str(event_ts)
    result = {}
    conn = get_connection()
    try:
        for venue in VENUES:
            validation = conn.execute(
                "SELECT * FROM regime_validation_status WHERE venue = ?", (venue,)
            ).fetchone() if live_lookup else None
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
            elif live_lookup and (validation is None or validation["status"] != "ok"):
                result[venue] = {"status": "unknown/stale"}
                if validation and validation["error"]:
                    result[venue]["error"] = validation["error"]
            else:
                result[venue] = dict(row)
                if live_lookup:
                    completed = pd.Timestamp(row["source_completed_through"])
                    age_days = (pd.Timestamp.now(tz="UTC").normalize() - completed.normalize()).days
                    if age_days > 7:
                        result[venue] = {
                            "status": "unknown/stale",
                            "source_age_days": age_days,
                            "source_completed_through": row["source_completed_through"],
                        }
                        continue
                    result[venue]["source_age_days"] = age_days
                result[venue]["status"] = "ok"
    finally:
        conn.close()
    return result


def get_current_regimes():
    return get_regimes_at()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run_all())
