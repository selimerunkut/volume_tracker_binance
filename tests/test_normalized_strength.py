import pandas as pd

from src.services.normalized_strength import evaluate_normalized_strength


def _frame(rows=120):
    values = []
    for index in range(rows):
        price = 100.0 + (index % 12) * 0.2
        values.append({
            "close": price,
            "rsi": 45.0 + (index % 10),
            "macd": (index % 9) * 0.03,
            "macd_signal": (index % 7) * 0.02,
            "ema_50": price - ((index % 8) - 3) * 0.05,
            "bb_lower": price - 2.0,
            "bb_middle": price,
            "bb_upper": price + 2.0,
        })
    return pd.DataFrame(values)


def test_normalized_strength_is_shadow_only_and_bounded():
    result = evaluate_normalized_strength(_frame())

    assert result["status"] == "ok"
    assert result["action"] in {"LONG", "SHORT", "WAIT"}
    assert result["normalization_window"] == 100
    assert -1 <= result["components"]["rsi"] <= 1
    assert -1 <= result["components"]["macd"] <= 1
    assert -1 <= result["components"]["ema_50"] <= 1
    assert -1 <= result["components"]["bollinger"] <= 1


def test_normalized_strength_requires_past_history():
    result = evaluate_normalized_strength(_frame(20))

    assert result["status"] == "unavailable"
    assert "history" in result["missing"]
