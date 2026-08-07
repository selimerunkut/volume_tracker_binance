from datetime import datetime, timezone

import pytest

from src.services import db_service, regime_service


def test_hyperliquid_is_a_configured_optional_regime_venue():
    assert "hyperliquid" in regime_service.VENUES
    assert regime_service.SOURCE_ENV["hyperliquid"] == "REGIME_SOURCE_FEATHER_HYPERLIQUID"


def test_stale_validation_preserves_source_age(monkeypatch, tmp_path):
    monkeypatch.setattr(db_service, "DB_PATH", str(tmp_path / "regime.db"))
    db_service.init_db()
    conn = db_service.get_connection()
    conn.execute(
        """
        INSERT INTO regime_labels
        (venue, instrument, timeframe, date, direction, raw_direction,
         volatility, volume_tag, computed_at, contract_sha256,
         validation_result, source_rows, source_first_ts, source_last_ts,
         source_completed_through, source_sha256)
        VALUES ('kraken', 'BTC/USDC', '1h', '2026-07-29', 'range_or_transition',
                'range_or_transition', 'normal_or_low', 'normal_or_low',
                '2026-08-01T00:00:00+00:00', 'contract', 'complete', 1000,
                '2025-01-01T00:00:00+00:00', '2026-07-29T23:00:00+00:00',
                '2026-07-29T00:00:00+00:00', 'source')
        """
    )
    conn.commit()
    conn.close()
    regime_service._write_validation_status(
        "kraken",
        "unknown/stale",
        "complete",
        completed_through="2026-07-29T00:00:00+00:00",
        source_sha256="source",
    )
    result = regime_service.get_regimes_at()
    assert result["kraken"]["status"] == "unknown/stale"
    assert result["kraken"]["source_completed_through"] == "2026-07-29T00:00:00+00:00"
    assert result["kraken"]["source_age_days"] >= 0


def test_failed_venue_cannot_serve_old_labels_as_live(monkeypatch, tmp_path):
    monkeypatch.setattr(db_service, "DB_PATH", str(tmp_path / "regime.db"))
    db_service.init_db()
    conn = db_service.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO regime_labels
            (venue, instrument, timeframe, date, direction, raw_direction,
             volatility, volume_tag, computed_at, contract_sha256,
             validation_result, source_rows, source_first_ts, source_last_ts,
             source_completed_through, source_sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "okx", "BTC/USDC", "1h", "2026-08-06", "structural_bull",
                "structural_bull", "normal_or_low", "normal_or_low",
                "2026-08-10T00:00:00+00:00", "contract", "complete", 1000,
                "2026-01-01T00:00:00+00:00", "2026-08-06T23:00:00+00:00",
                "2026-08-06T00:00:00+00:00", "source",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(regime_service, "_source_path", lambda venue: "missing.feather")

    def fail_label_file(*args, **kwargs):
        raise ValueError("current protection-window gap")

    monkeypatch.setattr(regime_service, "label_file", fail_label_file)
    with pytest.raises(ValueError, match="current protection-window gap"):
        regime_service.run_venue("okx", now=datetime(2026, 8, 10, 12, tzinfo=timezone.utc))

    result = regime_service.get_regimes_at()
    assert result["okx"]["status"] == "unknown/stale"
    assert "current protection-window gap" in result["okx"]["error"]
