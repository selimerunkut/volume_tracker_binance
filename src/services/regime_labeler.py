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


def load_validated_1h(path, venue, require_freshness=True, now=None):
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
        previous_day = (now_timestamp - pd.Timedelta(days=1)).normalize()
        if frame["date"].max().normalize() < previous_day:
            raise ValueError("source Feather is stale")
    return frame


def build_daily(frame, allowed_incomplete_dates=()):
    """Construct completed UTC daily candles and fail closed on any unadjudicated gap."""
    allowed = {pd.Timestamp(value).tz_localize("UTC") if pd.Timestamp(value).tzinfo is None else pd.Timestamp(value).tz_convert("UTC") for value in allowed_incomplete_dates}
    allowed = {value.normalize() for value in allowed}
    hourly = frame.set_index("date").sort_index()
    counts = hourly.resample("1D", label="left", closed="left").size()
    if len(counts) and counts.iloc[-1] < 24:
        hourly = hourly[hourly.index < counts.index[-1]]
        counts = hourly.resample("1D", label="left", closed="left").size()
    incomplete = counts[(counts != 24) & ~counts.index.isin(allowed)]
    if len(incomplete):
        details = ", ".join(f"{idx.date()}={int(count)}" for idx, count in incomplete.head(10).items())
        raise ValueError(f"incomplete daily candles: {details}")
    daily = hourly.resample("1D", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    if allowed:
        daily = daily[~daily.index.isin(allowed)]
    expected = pd.date_range(daily.index.min(), daily.index.max(), freq="1D", tz="UTC")
    missing = expected.difference(daily.index).difference(pd.DatetimeIndex(list(allowed), tz="UTC"))
    if len(missing):
        raise ValueError(f"missing daily candles: {missing[:10].tolist()}")
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


def label_file(path, venue, require_freshness=True, now=None, allowed_incomplete_dates=()):
    source = Path(path)
    frame = load_validated_1h(source, venue, require_freshness=require_freshness, now=now)
    daily = build_daily(frame, allowed_incomplete_dates=allowed_incomplete_dates)
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
