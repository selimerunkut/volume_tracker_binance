from datetime import datetime, timezone

import pandas as pd

from src.services import btc_market_context


def test_context_is_explanatory_and_uses_closed_candles(monkeypatch):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    frame = pd.DataFrame([
        {
            "end_ms": now_ms - (72 - index) * 60 * 60 * 1000,
            "o": 100.0 + index,
            "c": 100.0 + index,
            "h": 101.0 + index,
            "l": 99.0 + index,
            "v": 10.0,
        }
        for index in range(72)
    ])
    monkeypatch.setattr(btc_market_context, "_fetch_candles", lambda: frame)

    result = btc_market_context.get_btc_market_context()

    assert result["status"] == "ok"
    assert result["source"] == "Hyperliquid BTC perpetual 1h candles"
    assert result["direction"] == "bullish"
    assert "24h" in result["summary"]
    assert "EMA50" in result["summary"]
    assert result["age_minutes"] >= 0


def test_invalid_non_finite_context_is_not_reported_as_current(monkeypatch):
    frame = pd.DataFrame([
        {"end_ms": index, "o": 100.0, "c": float("inf"), "h": 101.0, "l": 99.0, "v": 10.0}
        for index in range(72)
    ])
    monkeypatch.setattr(btc_market_context, "_fetch_candles", lambda: frame)

    result = btc_market_context.get_btc_market_context()

    assert result["status"] == "unknown/stale"
    assert "invalid c values" in result["error"]


def test_stale_context_is_not_reported_as_current(monkeypatch):
    old_ms = int((datetime.now(timezone.utc).timestamp() - 6 * 60 * 60) * 1000)
    frame = pd.DataFrame([
        {"end_ms": old_ms - (72 - index) * 60 * 60 * 1000, "o": 100.0, "c": 100.0 + index,
         "h": 101.0, "l": 99.0, "v": 10.0}
        for index in range(72)
    ])
    monkeypatch.setattr(btc_market_context, "_fetch_candles", lambda: frame)

    result = btc_market_context.get_btc_market_context()

    assert result["status"] == "unknown/stale"
    assert "old" in result["error"]


def test_fetch_failure_is_explicitly_stale(monkeypatch):
    monkeypatch.setattr(
        btc_market_context,
        "_fetch_candles",
        lambda: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    result = btc_market_context.get_btc_market_context()

    assert result["status"] == "unknown/stale"
    assert "independent BTC fetch failed" in result["error"]
