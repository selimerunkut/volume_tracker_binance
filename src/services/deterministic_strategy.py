"""Deterministic strategy policy for exchange-specific /analyze output."""

from __future__ import annotations

import math
from typing import Mapping

REQUIRED_INDICATORS = (
    "rsi",
    "macd",
    "macd_signal",
    "ema_50",
    "bb_lower",
    "bb_upper",
)


def _number(values: Mapping[str, object], key: str) -> float:
    if key not in values:
        raise ValueError(f"Missing indicator: {key}")

    value = float(values[key])
    if not math.isfinite(value):
        raise ValueError(f"Non-finite indicator: {key}")
    return value


def _target_price(price: float, percent: float) -> float:
    return round(price * (1 + percent / 100), 2)


def _confidence(score: int, action: str) -> int:
    if action in {"LONG", "SHORT"}:
        return min(90, 50 + 10 * abs(score))
    return max(50, 70 - 10 * abs(score))


def evaluate_strategy(indicators: Mapping[str, object], current_price: float) -> dict:
    """Return a deterministic strategy decision from indicators and price."""
    price = float(current_price)
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Current price must be a positive finite number")

    values = {key: _number(indicators, key) for key in REQUIRED_INDICATORS}

    score = 0
    rule_ids: list[str] = []
    reasons: list[str] = []

    rsi = values["rsi"]
    if rsi <= 30:
        score += 2
        rule_ids.append("rsi_oversold")
        reasons.append(f"RSI is {rsi:.2f}, at or below the oversold threshold of 30 (+2).")
    elif rsi >= 70:
        score -= 2
        rule_ids.append("rsi_overbought")
        reasons.append(f"RSI is {rsi:.2f}, at or above the overbought threshold of 70 (-2).")
    else:
        rule_ids.append("rsi_neutral")
        reasons.append(f"RSI is {rsi:.2f}, between 30 and 70 (0).")

    macd = values["macd"]
    macd_signal = values["macd_signal"]
    if macd > macd_signal:
        score += 1
        rule_ids.append("macd_bullish")
        reasons.append(f"MACD {macd:.4f} is above its signal {macd_signal:.4f} (+1).")
    elif macd < macd_signal:
        score -= 1
        rule_ids.append("macd_bearish")
        reasons.append(f"MACD {macd:.4f} is below its signal {macd_signal:.4f} (-1).")
    else:
        rule_ids.append("macd_neutral")
        reasons.append(f"MACD equals its signal at {macd:.4f} (0).")

    ema_50 = values["ema_50"]
    if price > ema_50:
        score += 1
        rule_ids.append("price_above_ema50")
        reasons.append(f"Price {price:.8f} is above EMA(50) {ema_50:.8f} (+1).")
    elif price < ema_50:
        score -= 1
        rule_ids.append("price_below_ema50")
        reasons.append(f"Price {price:.8f} is below EMA(50) {ema_50:.8f} (-1).")
    else:
        rule_ids.append("price_at_ema50")
        reasons.append(f"Price equals EMA(50) at {price:.8f} (0).")

    bb_lower = values["bb_lower"]
    bb_upper = values["bb_upper"]
    if price <= bb_lower:
        score += 1
        rule_ids.append("price_at_or_below_lower_band")
        reasons.append(f"Price is at or below the lower Bollinger Band {bb_lower:.8f} (+1).")
    elif price >= bb_upper:
        score -= 1
        rule_ids.append("price_at_or_above_upper_band")
        reasons.append(f"Price is at or above the upper Bollinger Band {bb_upper:.8f} (-1).")
    else:
        rule_ids.append("price_inside_bands")
        reasons.append("Price is inside the Bollinger Bands (0).")

    if score >= 3:
        action = "LONG"
        reason_tail = "LONG requires at least +3."
    elif score <= -3:
        action = "SHORT"
        reason_tail = "SHORT requires at most -3."
    else:
        action = "WAIT"
        reason_tail = "WAIT requires a score between -2 and +2."

    confidence = _confidence(score, action)
    entry = price
    if action == "LONG":
        tp = _target_price(price, 4)
        sl = _target_price(price, -2)
    elif action == "SHORT":
        tp = _target_price(price, -4)
        sl = _target_price(price, 2)
    else:
        tp = price
        sl = price

    reasoning = " ".join(reasons + [f"Total score: {score:+d}; {reason_tail}"])

    return {
        "action": action,
        "confidence": confidence,
        "entry": entry,
        "tp": tp,
        "sl": sl,
        "reasoning": reasoning,
        "score": score,
        "rule_ids": rule_ids,
    }
