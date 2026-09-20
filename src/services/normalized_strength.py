"""Shadow-only normalized indicator strength scoring.

This module does not alter the live deterministic strategy. It records a
candidate entry filter so it can be evaluated on a later held-out cohort.
"""

from __future__ import annotations

import math

import pandas as pd

NORMALIZED_WINDOW = 100
LONG_THRESHOLD = 2.5
SHORT_THRESHOLD = -2.5
_EPSILON = 1e-12


def _clip(value, lower=-1.0, upper=1.0):
    return max(lower, min(upper, float(value)))


def _past_scale(values):
    numeric = pd.to_numeric(values, errors="coerce").dropna().tail(NORMALIZED_WINDOW)
    if len(numeric) < 20:
        return None
    scale = float(numeric.std(ddof=0))
    return scale if math.isfinite(scale) and scale > _EPSILON else None


def _mean_reversion_rsi_strength(rsi):
    if rsi <= 30:
        return _clip((30 - rsi) / 20)
    if rsi >= 70:
        return _clip(-(rsi - 70) / 20)
    return 0.0


def evaluate_normalized_strength(indicator_frame):
    """Return a shadow score using only information available before the latest row.

    The component directions intentionally preserve the current policy's
    mean-reversion interpretation: oversold/lower-band conditions are positive
    and overbought/upper-band conditions are negative.
    """
    required = {
        "rsi", "macd", "macd_signal", "ema_50", "bb_lower", "bb_middle",
        "bb_upper", "close",
    }
    missing = sorted(required.difference(indicator_frame.columns))
    if missing or len(indicator_frame) < 21:
        return {"status": "unavailable", "missing": missing or ["history"]}

    latest = indicator_frame.iloc[-1]
    past = indicator_frame.iloc[:-1]
    price = float(latest["close"])
    values = {key: float(latest[key]) for key in required}
    if not all(math.isfinite(value) for value in values.values()) or price <= 0:
        return {"status": "unavailable", "missing": ["finite_latest_values"]}

    macd_delta = past["macd"] - past["macd_signal"]
    ema_delta = past["close"] - past["ema_50"]
    macd_scale = _past_scale(macd_delta)
    ema_scale = _past_scale(ema_delta)
    if macd_scale is None or ema_scale is None:
        return {"status": "unavailable", "missing": ["past_scale"]}

    rsi_component = _mean_reversion_rsi_strength(values["rsi"])
    macd_component = math.tanh((values["macd"] - values["macd_signal"]) / macd_scale)
    ema_component = math.tanh((price - values["ema_50"]) / ema_scale)
    band_width = values["bb_upper"] - values["bb_lower"]
    if not math.isfinite(band_width) or band_width <= _EPSILON:
        return {"status": "unavailable", "missing": ["bollinger_width"]}
    bollinger_component = _clip(
        (values["bb_middle"] - price) / (band_width / 2),
    )

    score = 2 * rsi_component + macd_component + ema_component + bollinger_component
    if score >= LONG_THRESHOLD:
        action = "LONG"
    elif score <= SHORT_THRESHOLD:
        action = "SHORT"
    else:
        action = "WAIT"

    return {
        "status": "ok",
        "action": action,
        "score": round(score, 8),
        "components": {
            "rsi": round(rsi_component, 8),
            "macd": round(macd_component, 8),
            "ema_50": round(ema_component, 8),
            "bollinger": round(bollinger_component, 8),
        },
        "normalization_window": min(NORMALIZED_WINDOW, len(past)),
        "thresholds": {"long": LONG_THRESHOLD, "short": SHORT_THRESHOLD},
    }
