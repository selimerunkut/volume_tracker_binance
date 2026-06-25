"""
Probe Kraken public market-data endpoints for the multi-exchange alert plan.

This is an implementation-planning verification script, not production code. It checks
that Kraken's unauthenticated REST API can supply the data shape needed by the
current Binance volume-alert flow:
- tradable pair discovery with base/quote assets
- 1h OHLC candles with timestamp/open/high/low/close/volume
- current/last price from ticker data
- enough candles for the current alert math window

Run:
    uv run python helper_test_scripts/check_kraken_api_data_needs.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import requests

BASE_URL = "https://api.kraken.com/0/public"
TIMEOUT_SECONDS = 20
MIN_CANDLES_FOR_ALERT_MATH = 9
TARGET_QUOTES = ("USD", "USDC", "BTC")
PREFERRED_SAMPLE_PAIRS = ("BTC/USD", "ETH/BTC", "SOL/USD", "ETH/USD")


def request_kraken(endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{BASE_URL}/{endpoint}"
    response = requests.get(url, params=params or {}, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("error") or []
    if errors:
        raise RuntimeError(f"Kraken API returned errors for {endpoint}: {errors}")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"Kraken API returned no result object for {endpoint}: {payload}")
    return result


def numeric(value: Any) -> float:
    return float(value)


def choose_sample_pair(pairs: dict[str, dict[str, Any]]) -> str:
    for pair in PREFERRED_SAMPLE_PAIRS:
        details = pairs.get(pair)
        if details and details.get("status") == "online":
            return pair
    for pair, details in pairs.items():
        if details.get("quote") in TARGET_QUOTES and details.get("status") == "online":
            return pair
    raise RuntimeError("No online sample pair found for target quotes")


def summarize_asset_pairs() -> tuple[dict[str, dict[str, Any]], dict[str, int], dict[str, str]]:
    pairs = request_kraken("AssetPairs", {"assetVersion": 1})
    quote_counts = {quote: 0 for quote in TARGET_QUOTES}
    sample_by_quote: dict[str, str] = {}

    for pair, details in pairs.items():
        if details.get("status") != "online":
            continue
        quote = details.get("quote")
        if quote in quote_counts:
            quote_counts[quote] += 1
            sample_by_quote.setdefault(quote, pair)

    slash_key_count = sum(1 for pair in pairs if "/" in pair)
    if slash_key_count == 0:
        raise RuntimeError("assetVersion=1 did not return slash-separated display pair keys")

    for pair, details in list(pairs.items())[:20]:
        if "base" not in details or "quote" not in details:
            raise RuntimeError(f"AssetPairs entry missing base/quote: {pair} -> {details}")

    return pairs, quote_counts, sample_by_quote


def probe_ohlc(pair: str) -> dict[str, Any]:
    result = request_kraken("OHLC", {"pair": pair, "interval": 60, "assetVersion": 1})
    data_keys = [key for key in result.keys() if key != "last"]
    if len(data_keys) != 1:
        raise RuntimeError(f"Expected one OHLC data key for {pair}, got {data_keys}")
    data_key = data_keys[0]
    rows = result[data_key]
    if len(rows) < MIN_CANDLES_FOR_ALERT_MATH:
        raise RuntimeError(f"Need at least {MIN_CANDLES_FOR_ALERT_MATH} candles for alert math, got {len(rows)}")

    latest = rows[-1]
    if len(latest) != 8:
        raise RuntimeError(f"Expected OHLC row length 8, got {len(latest)}: {latest}")

    converted_latest = {
        "timestamp": datetime.fromtimestamp(int(latest[0]), tz=timezone.utc).isoformat(),
        "open": numeric(latest[1]),
        "high": numeric(latest[2]),
        "low": numeric(latest[3]),
        "close": numeric(latest[4]),
        "vwap": numeric(latest[5]),
        "volume": numeric(latest[6]),
        "count": int(latest[7]),
    }

    return {
        "requested_pair": pair,
        "result_pair_key": data_key,
        "candles_returned": len(rows),
        "has_last_cursor": "last" in result,
        "latest_candle": converted_latest,
    }


def probe_ticker(pair: str) -> dict[str, Any]:
    result = request_kraken("Ticker", {"pair": pair, "assetVersion": 1})
    if not result:
        raise RuntimeError(f"Ticker returned empty result for {pair}")
    data_key = next(iter(result.keys()))
    ticker = result[data_key]
    last_price = numeric(ticker["c"][0])
    base_volume_24h = numeric(ticker["v"][1])
    vwap_24h = numeric(ticker["p"][1])
    approx_quote_volume_24h = base_volume_24h * vwap_24h
    return {
        "requested_pair": pair,
        "result_pair_key": data_key,
        "last_price": last_price,
        "base_volume_24h": base_volume_24h,
        "vwap_24h": vwap_24h,
        "approx_quote_volume_24h": approx_quote_volume_24h,
    }


def main() -> int:
    checked_at = datetime.now(timezone.utc).isoformat()
    pairs, quote_counts, sample_by_quote = summarize_asset_pairs()
    sample_pair = choose_sample_pair(pairs)
    ohlc = probe_ohlc(sample_pair)
    ticker = probe_ticker(sample_pair)

    summary = {
        "checked_at_utc": checked_at,
        "base_url": BASE_URL,
        "asset_pairs": {
            "total_pairs": len(pairs),
            "online_target_quote_counts": quote_counts,
            "sample_by_quote": sample_by_quote,
        },
        "selected_sample_pair": sample_pair,
        "ohlc_probe": ohlc,
        "ticker_probe": ticker,
        "data_need_verdict": {
            "public_api_reachable": True,
            "auth_required_for_market_data": False,
            "pair_discovery_supported": True,
            "base_quote_filtering_supported": True,
            "one_hour_ohlc_supported": True,
            "ohlc_supports_alert_math_window": ohlc["candles_returned"] >= MIN_CANDLES_FOR_ALERT_MATH,
            "ticker_current_price_supported": ticker["last_price"] > 0,
            "kraken_native_quote_volume_available": False,
            "kraken_quote_volume_workaround": "Use OHLC base volume for alert math; approximate 24h quote volume as ticker v[1] * p[1] only for top-volume menus.",
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
