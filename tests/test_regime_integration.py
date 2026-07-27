from datetime import datetime, timedelta

import pandas as pd

from src.services.performance_tracker import evaluate_candle_path


def suggestion(action="LONG"):
    return {
        "created_at": datetime.now().replace(microsecond=0).isoformat(),
        "strategy_type": action,
        "entry_price": 100.0,
        "take_profit": 104.0 if action == "LONG" else 96.0,
        "stop_loss": 98.0 if action == "LONG" else 102.0,
    }


def test_candle_evaluator_is_conservative_when_both_levels_touch():
    item = suggestion()
    created = datetime.fromisoformat(item["created_at"])
    candles = pd.DataFrame([{"timestamp": created + timedelta(hours=1), "high": 105, "low": 97, "close": 100}])
    assert evaluate_candle_path(item, candles, now=created + timedelta(hours=2)) == ("LOSS", -2.0)


def test_wait_uses_close_at_window_end():
    item = suggestion("WAIT")
    created = datetime.fromisoformat(item["created_at"])
    candles = pd.DataFrame([{"timestamp": created + timedelta(hours=24), "high": 103, "low": 99, "close": 103}])
    status, pnl = evaluate_candle_path(item, candles, now=created + timedelta(hours=25))
    assert status == "LOSS"
    assert pnl == -3.0
