from datetime import datetime, timedelta, timezone
import sqlite3

import pandas as pd

from scripts.policy_report import report
from src.services.deterministic_strategy import evaluate_strategy
from src.services.performance_tracker import UNEVALUABLE, evaluate_candle_path_detailed


def _suggestion(action="WAIT"):
    return {
        "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_type": action,
        "entry_price": 100.0,
        "take_profit": 104.0 if action == "LONG" else 96.0,
        "stop_loss": 98.0 if action == "LONG" else 102.0,
    }


def _candles(hours, close=100.0, high=101.0, low=99.0):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return pd.DataFrame([
        {"timestamp": start + timedelta(hours=hour), "high": high, "low": low, "close": close}
        for hour in hours
    ])


def test_missing_interior_candle_keeps_wait_return_but_reports_partial_coverage():
    result = evaluate_candle_path_detailed(
        _suggestion(),
        _candles([hour for hour in range(1, 25) if hour != 3], close=97.0),
        now="2026-01-02T01:00:00+00:00",
    )
    assert result["status"] == "WIN"
    assert result["raw_return_percent"] == -3.0
    assert result["coverage_status"] == "PARTIAL_COVERAGE"
    assert result["missing_candles"] == 1


def test_missing_interior_candle_makes_unknown_tp_sl_path_unevaluable():
    result = evaluate_candle_path_detailed(
        _suggestion("LONG"),
        _candles([hour for hour in range(1, 25) if hour != 3], close=100.0),
        now="2026-01-02T01:00:00+00:00",
    )
    assert result["status"] == UNEVALUABLE
    assert result["pnl_percent"] is None
    assert result["coverage_status"] == "PARTIAL_COVERAGE"


def test_missing_initial_path_coverage_is_unevaluable():
    result = evaluate_candle_path_detailed(
        _suggestion("LONG"),
        _candles([24], close=100.0),
        now="2026-01-02T01:00:00+00:00",
    )
    assert result["status"] == UNEVALUABLE
    assert result["missing_candles"] == 23


def test_missing_boundary_candle_is_not_a_win():
    result = evaluate_candle_path_detailed(
        _suggestion(),
        _candles([1, 2, 3]),
        now="2026-01-02T01:00:00+00:00",
    )
    assert result["status"] == UNEVALUABLE
    assert result["coverage_status"] == "UNEVALUABLE"


def test_low_price_targets_keep_exchange_scale_and_ordering():
    result = evaluate_strategy(
        {"rsi": 28, "macd": 1, "macd_signal": 0, "ema_50": 0.005,
         "bb_lower": 0.004, "bb_upper": 0.007},
        0.006,
    )
    assert result["action"] == "LONG"
    assert result["tp"] == 0.00624
    assert result["sl"] == 0.00588


def test_policy_report_is_read_only_and_exposes_baselines(tmp_path):
    db = tmp_path / "report.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE suggestions (strategy_type TEXT, status TEXT, pnl_percent REAL, raw_return_percent REAL, analysis_data TEXT)")
    conn.execute("INSERT INTO suggestions VALUES ('WAIT', 'WIN', 2, -2, '{}')")
    conn.commit()
    conn.close()
    before = db.read_bytes()
    result = report(str(db))
    assert result["suggestions"]["always_cash"]["mean_percent"] == 0.0
    assert result["suggestions"]["always_buy"]["mean_percent"] == -2.0
    assert db.read_bytes() == before
