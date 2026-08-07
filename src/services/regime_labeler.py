"""Causal BTC structural-regime labels for a single exchange artifact."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("date", "open", "high", "low", "close", "volume")
VENUE_CONTRACTS = {
    "okx": "fixed-stake-structural-regime-contract-v1-okx",
    "kraken": "fixed-stake-structural-regime-contract-v1-kraken",
}
MIN_DAILY_ROWS = 120  # enough warm-up for rv75 while allowing live feeds with limited history


def _utc_now():
    return datetime.now(timezone.utc)


def _contract_hash(venue):
    contract = {
        "contract_id": VENUE_CONTRACTS[venue],
        "venue": venue,
        "instrument": "BTC/USDC",
        "timeframe": "1h",
        "timezone": "UTC",
        "algorithm": "fixed-stake-structural-regime-contract-v1",
    }
    return hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()


def _ols_t(log_prices):
    y = np.asarray(log_prices, dtype=float)
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    residual = y - (intercept + slope * x)
    s2 = (residual @ residual) / (len(y) - 2)
    denominator = (x - x.mean()) @ (x - x.mean())
    se = math.sqrt(s2 / denominator) if s2 > 0 else 0
    tstat = float(slope / se) if se else (0.0 if slope == 0 else math.copysign(float("inf"), slope))
    return float(slope), tstat


def load_validated_1h(path, venue, require_freshness=True, now=None, max_age_days=7):
    """Read and validate one venue's immutable Freqtrade Feather artifact."""
    venue = str(venue).lower()
    if venue not in VENUE_CONTRACTS:
        raise ValueError(f"unsupported regime venue: {venue}")
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    before = source.stat()
    frame = pd.read_feather(source)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("source Feather changed while it was being read")
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"missing required Feather columns: {missing}")
    frame = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    if frame["date"].isna().any():
        raise ValueError("source contains invalid timestamps")
    if not frame["date"].is_monotonic_increasing or frame["date"].duplicated().any():
        raise ValueError("hourly input unordered or duplicated")
    for column in REQUIRED_COLUMNS[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    values = frame.loc[:, REQUIRED_COLUMNS[1:]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("OHLCV values must be finite and non-negative")
    if require_freshness:
        now = now or _utc_now()
        now_timestamp = pd.Timestamp(now)
        if now_timestamp.tzinfo is None:
            now_timestamp = now_timestamp.tz_localize("UTC")
        else:
            now_timestamp = now_timestamp.tz_convert("UTC")
        daily_counts = frame.assign(_day=frame["date"].dt.normalize()).groupby("_day").size()
        completed_days = daily_counts[daily_counts == 24]
        latest_completed = completed_days.index.max() if not completed_days.empty else None
        cutoff = (now_timestamp - pd.Timedelta(days=max_age_days)).normalize()
        if latest_completed is None or latest_completed < cutoff:
            raise ValueError(f"source Feather is older than {max_age_days} days")
    return frame


def build_daily(frame, allowed_incomplete_dates=(), ignored_dates=(), now=None,
                max_tolerated_gap_days=7):
    """Build daily candles, tolerating only short, wholly historical gaps.

    A gap touching the inclusive protection window (UTC today minus seven days
    through today) is never silently tolerated.  Longer historical gaps must
    be explicitly adjudicated.  No rows are created for tolerated gaps.
    """
    def normalize(values):
        result = set()
        for value in values:
            timestamp = pd.Timestamp(value)
            timestamp = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
            result.add(timestamp.normalize())
        return result

    allowed = normalize(allowed_incomplete_dates)
    ignored = normalize(ignored_dates)
    now_timestamp = pd.Timestamp(now or _utc_now())
    now_timestamp = now_timestamp.tz_localize("UTC") if now_timestamp.tzinfo is None else now_timestamp.tz_convert("UTC")
    protection_start = now_timestamp.normalize() - pd.Timedelta(days=7)
    hourly = frame.set_index("date").sort_index()
    counts = hourly.resample("1D", label="left", closed="left").size()
    # Never label a forming or partial trailing day.  A partial day in the
    # protected recent window is a live-data defect, not a tolerable gap.
    if len(counts) and counts.iloc[-1] < 24:
        trailing_day = counts.index[-1].normalize()
        if trailing_day >= protection_start and trailing_day <= now_timestamp.normalize():
            raise ValueError(f"current protection-window gap: {trailing_day.date()} ({int(counts.iloc[-1])} candles)")
        hourly = hourly[hourly.index < counts.index[-1]]
        counts = hourly.resample("1D", label="left", closed="left").size()
    incomplete = set(counts.index[counts != 24])
    daily = hourly.resample("1D", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    daily = daily[~daily.index.isin(allowed | ignored)]
    if daily.empty:
        raise ValueError("at least completed daily candles are required")
    expected = pd.date_range(daily.index.min(), daily.index.max(), freq="1D", tz="UTC")
    missing = set(expected.difference(daily.index))
    gaps = sorted(incomplete | missing)
    tolerated_gaps = set()
    if gaps:
        gap_runs = []
        run = [gaps[0]]
        for day in gaps[1:]:
            if (day - run[-1]).days == 1:
                run.append(day)
            else:
                gap_runs.append(run)
                run = [day]
        gap_runs.append(run)
        for run in gap_runs:
            if any(protection_start <= day <= now_timestamp.normalize() for day in run):
                raise ValueError(f"current protection-window gap: {run[0].date()}..{run[-1].date()}")
            if len(run) > max_tolerated_gap_days and not set(run).issubset(allowed | ignored):
                raise ValueError(f"missing daily candles: {run[:10]}")
            tolerated_gaps.update(run)
    if tolerated_gaps:
        daily = daily[~daily.index.isin(tolerated_gaps)]
    if len(daily) < MIN_DAILY_ROWS:
        raise ValueError(f"at least {MIN_DAILY_ROWS} completed daily candles are required")
    return daily


def compute_labels(daily):
    """Apply the frozen causal algorithm without venue-specific changes."""
    x = daily.copy()
    log_returns = np.log(x["close"]).diff()
    for period in (7, 14, 28):
        x[f"return_{period}"] = x["close"].pct_change(period)
    x["sma28"] = x["close"].rolling(28).mean()
    x["slope28"] = np.nan
    x["tstat28"] = np.nan
    for index in range(27, len(x)):
        slope, tstat = _ols_t(np.log(x["close"].iloc[index - 27:index + 1]))
        x.iloc[index, x.columns.get_loc("slope28")] = slope
        x.iloc[index, x.columns.get_loc("tstat28")] = tstat
    x["rv28"] = log_returns.rolling(28).std()
    x["rv75"] = x["rv28"].shift(1).rolling(365, min_periods=60).quantile(0.75)
    x["volume_ratio90"] = x["volume"].shift(1) / x["volume"].shift(1).rolling(90, min_periods=30).median()
    x["volatility"] = np.where(x["rv28"] >= x["rv75"], "high", "normal_or_low")
    x["volume_tag"] = np.where(x["volume_ratio90"] >= 1.5, "expanded", "normal_or_low")
    bull = (
        (x["return_7"] > 0) & (x["return_14"] > 0) & (x["return_28"] > 0)
        & (x["close"] > x["sma28"]) & (x["slope28"] > 0) & (x["tstat28"] >= 2)
    )
    bear = (
        (x["return_7"] < 0) & (x["return_14"] < 0) & (x["return_28"] < 0)
        & (x["close"] < x["sma28"]) & (x["slope28"] < 0) & (x["tstat28"] <= -2)
    )
    raw = np.where(bull, "structural_bull", np.where(bear, "structural_bear", "range_or_transition"))
    state = []
    current = "range_or_transition"
    run = []
    previous = None
    for timestamp, raw_value in zip(x.index, raw):
        if previous is not None and (timestamp - previous).days > 1:
            current = "range_or_transition"
            run = []
        run = (run + [raw_value])[-3:]
        if len(run) == 3 and run[-1] in ("structural_bull", "structural_bear") and all(value == run[-1] for value in run):
            current = run[-1]
        elif current in ("structural_bull", "structural_bear") and raw_value != current:
            current = "range_or_transition"
        state.append(current)
        previous = timestamp
    x["raw_direction"] = raw
    x["direction"] = state
    x["timestamp"] = x.index
    return x.reset_index(drop=True)


def label_file(path, venue, require_freshness=True, now=None, allowed_incomplete_dates=(), ignored_dates=()):
    source = Path(path)
    frame = load_validated_1h(source, venue, require_freshness=require_freshness, now=now)
    daily = build_daily(
        frame,
        allowed_incomplete_dates=allowed_incomplete_dates,
        ignored_dates=ignored_dates,
        now=now,
    )
    labels = compute_labels(daily)
    return labels, {
        "venue": venue,
        "instrument": "BTC/USDC",
        "timeframe": "1h",
        "source_path": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_rows": len(frame),
        "source_first_ts": frame["date"].min().isoformat(),
        "source_last_ts": frame["date"].max().isoformat(),
        "source_completed_through": labels["timestamp"].max().isoformat(),
        "contract_sha256": _contract_hash(venue),
        "validation_result": "complete",
    }


def current_snapshot(labels):
    if labels is None or labels.empty:
        return {"status": "unknown/stale"}
    row = labels.iloc[-1]
    return {
        "status": "ok",
        "date": pd.Timestamp(row["timestamp"]).isoformat(),
        "direction": row["direction"],
        "raw_direction": row["raw_direction"],
        "volatility": row["volatility"],
        "volume_tag": row["volume_tag"],
    }
