from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.services.regime_labeler import build_daily, compute_labels, load_validated_1h


def make_hourly(days=430):
    timestamps = pd.date_range("2024-01-01", periods=days * 24, freq="h", tz="UTC")
    close = np.linspace(100, 140, len(timestamps))
    frame = pd.DataFrame({
        "date": timestamps,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": np.ones(len(timestamps)) * 100,
    })
    return frame


def test_labeler_reference_fixture_parity():
    path = "/Users/semacair/dev/.external/freqtrade-stuff-evaluation/f6c38def0b2fe01d8d42e47740cdeab53511527b/x7-okx-history/data/okx/BTC_USDC-1h.feather"
    try:
        frame = pd.read_feather(path)
    except (FileNotFoundError, ImportError):
        pytest.skip("reference fixture is not available")
    labels = compute_labels(build_daily(
        load_validated_1h(path, "okx", require_freshness=False),
        allowed_incomplete_dates=["2024-06-25", "2025-08-20", "2025-08-21"],
    ))
    row = labels[labels["timestamp"] == pd.Timestamp("2026-07-19", tz="UTC")].iloc[0]
    assert row["direction"] == "range_or_transition"
    assert row["raw_direction"] == "structural_bull"
    assert row["volatility"] == "normal_or_low"
    assert row["volume_tag"] == "expanded"


def test_no_lookahead():
    first = compute_labels(build_daily(make_hourly()))
    changed = make_hourly()
    changed.loc[changed.index >= len(changed) - 24, "close"] *= 10
    second = compute_labels(build_daily(changed))
    assert first.iloc[:-1][["direction", "volatility", "volume_tag"]].equals(
        second.iloc[:-1][["direction", "volatility", "volume_tag"]]
    )


def test_strict_before_event():
    labels = compute_labels(build_daily(make_hourly()))
    event = labels.iloc[-1]["timestamp"] + pd.Timedelta(hours=12)
    assert labels[labels.timestamp < event]["timestamp"].max() == labels.iloc[-1]["timestamp"]
    event_inside = labels.iloc[-1]["timestamp"] + pd.Timedelta(hours=1)
    assert labels[labels.timestamp < event_inside]["timestamp"].max() == labels.iloc[-1]["timestamp"]


def test_short_historical_gap_is_tolerated_and_resets_state():
    frame = make_hourly()
    labels = compute_labels(build_daily(frame))
    assert set(labels["direction"]).issubset({"structural_bull", "range_or_transition", "structural_bear"})
    gap_start = frame["date"].dt.normalize().iloc[100 * 24]
    with_gap = frame[frame["date"].dt.normalize() != gap_start].reset_index(drop=True)
    daily = build_daily(with_gap)
    assert gap_start not in daily.index
    assert len(daily) == 429


def test_recent_gap_is_rejected_even_when_short():
    frame = make_hourly()
    now = pd.Timestamp("2026-08-10 12:00", tz="UTC")
    shift = now.normalize() - pd.Timedelta(days=1) - frame["date"].dt.normalize().max()
    frame["date"] = frame["date"] + shift
    gap_start = now.normalize() - pd.Timedelta(days=3)
    with_gap = frame[frame["date"].dt.normalize() != gap_start].reset_index(drop=True)
    with pytest.raises(ValueError, match="current protection-window gap"):
        build_daily(with_gap, now=now)
    with pytest.raises(ValueError, match="current protection-window gap"):
        build_daily(with_gap, now=now, allowed_incomplete_dates=[gap_start])


def test_gaps_longer_than_seven_days_are_rejected():
    frame = make_hourly()
    gap_start = frame["date"].dt.normalize().iloc[100 * 24]
    gap_dates = pd.date_range(gap_start, periods=8, freq="D", tz="UTC")
    with_gap = frame[~frame["date"].dt.normalize().isin(gap_dates)].reset_index(drop=True)
    with pytest.raises(ValueError, match="missing daily candles"):
        build_daily(with_gap)


def test_reject_invalid_input(tmp_path):
    frame = make_hourly(20)
    frame.loc[1, "date"] = frame.loc[0, "date"]
    path = tmp_path / "bad.feather"
    frame.to_feather(path)
    with pytest.raises(ValueError, match="unordered or duplicated"):
        load_validated_1h(path, "okx", require_freshness=False)


def test_reject_wrong_venue():
    with pytest.raises(ValueError, match="unsupported"):
        load_validated_1h(make_hourly(), "binance", require_freshness=False)


def test_partial_day_is_not_labeled():
    frame = make_hourly()
    frame = frame.iloc[:-10]
    daily = build_daily(frame)
    assert daily.index.max().date() == (frame["date"].max() - pd.Timedelta(days=1)).date()


def test_deterministic_output():
    frame = make_hourly()
    assert compute_labels(build_daily(frame)).equals(compute_labels(build_daily(frame)))


def test_timezone_and_finite_validation(tmp_path):
    frame = make_hourly()
    frame.loc[0, "close"] = np.nan
    path = tmp_path / "bad.feather"
    frame.to_feather(path)
    with pytest.raises(ValueError, match="finite"):
        load_validated_1h(path, "okx", require_freshness=False)


def test_short_historical_incomplete_day_is_tolerated():
    frame = make_hourly()
    day = frame.loc[100 * 24, "date"].normalize()
    frame = frame.drop(frame.index[100 * 24:100 * 24 + 2]).reset_index(drop=True)
    assert len(build_daily(frame)) == 429
    assert len(build_daily(frame, allowed_incomplete_dates=[day])) == 429


def test_week_old_source_is_accepted(tmp_path):
    frame = make_hourly()
    path = tmp_path / "weekly.feather"
    frame.to_feather(path)
    now = frame["date"].max() + pd.Timedelta(days=7)
    assert not load_validated_1h(path, "okx", now=now, max_age_days=7).empty


def test_historical_gap_resets_daily_series():
    frame = make_hourly()
    ignored_day = frame.loc[100 * 24, "date"].normalize()
    frame = frame.drop(frame.index[100 * 24:100 * 24 + 24]).reset_index(drop=True)
    daily = build_daily(frame)
    assert ignored_day not in daily.index
    assert len(daily) == 429
    assert ignored_day not in build_daily(frame, ignored_dates=[ignored_day]).index
