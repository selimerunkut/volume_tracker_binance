import math

import pytest

from src.services.deterministic_strategy import evaluate_strategy


def snapshot(**overrides):
    values = {
        "rsi": 50.0,
        "macd": 0.0,
        "macd_signal": 0.0,
        "ema_50": 100.0,
        "bb_lower": 90.0,
        "bb_upper": 110.0,
    }
    values.update(overrides)
    return values


def test_long_short_wait_and_repeatability():
    result = evaluate_strategy(
        snapshot(rsi=28.0, macd=1.0, macd_signal=0.5, ema_50=95.0),
        current_price=100.0,
    )
    assert result == {
        "action": "LONG",
        "confidence": 90,
        "entry": 100.0,
        "tp": 104.0,
        "sl": 98.0,
        "reasoning": (
            "RSI is 28.00, at or below the oversold threshold of 30 (+2). "
            "MACD 1.0000 is above its signal 0.5000 (+1). "
            "Price 100.00000000 is above EMA(50) 95.00000000 (+1). "
            "Price is inside the Bollinger Bands (0). Total score: +4; LONG requires at least +3."
        ),
        "score": 4,
        "rule_ids": [
            "rsi_oversold",
            "macd_bullish",
            "price_above_ema50",
            "price_inside_bands",
        ],
    }

    result = evaluate_strategy(
        snapshot(rsi=75.0, macd=-1.0, macd_signal=-0.5, ema_50=105.0, bb_upper=99.0),
        current_price=100.0,
    )
    assert result["action"] == "SHORT"
    assert result["confidence"] == 90
    assert result["tp"] == 96.0
    assert result["sl"] == 102.0
    assert result["score"] == -5

    result = evaluate_strategy(
        snapshot(rsi=50.0, macd=1.0, macd_signal=0.5, ema_50=105.0),
        current_price=100.0,
    )
    assert result["action"] == "WAIT"
    assert result["confidence"] == 70
    assert result["entry"] == result["tp"] == result["sl"] == 100.0

    indicators = snapshot(rsi=61.35, macd=0.002, macd_signal=0.001, ema_50=99.0)
    first = evaluate_strategy(indicators, 100.0)
    second = evaluate_strategy(dict(indicators), 100.0)
    assert first == second


def test_validation_errors():
    with pytest.raises(ValueError, match="Missing indicator: rsi"):
        evaluate_strategy(
            {key: value for key, value in snapshot().items() if key != "rsi"},
            100.0,
        )

    with pytest.raises(ValueError, match="Non-finite indicator: macd"):
        evaluate_strategy(snapshot(macd=math.nan), 100.0)

    with pytest.raises(ValueError, match="Current price must be a positive finite number"):
        evaluate_strategy(snapshot(), 0)
