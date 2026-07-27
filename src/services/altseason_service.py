"""CoinMarketCap Altcoin Season Index fetch and stale-safe cache."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import requests

ENDPOINT = "https://pro-api.coinmarketcap.com/public-api/v1/altcoin-season-index/latest"
CACHE_FILE = os.getenv("ALTSEASON_CACHE_FILE", "altseason_cache.json")
CACHE_HOURS = 26


def _unknown(reason):
    return {"status": "unknown/stale", "error": reason, "altcoin_index": None}


def _read_cache():
    try:
        with open(CACHE_FILE, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(payload):
    temporary = f"{CACHE_FILE}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    os.replace(temporary, CACHE_FILE)


def parse_payload(payload):
    value = payload.get("altcoin_index") if isinstance(payload, dict) else None
    if value is None and isinstance(payload, dict):
        value = (payload.get("data") or {}).get("altcoin_index")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return _unknown("malformed altseason response")
    if not 0 <= value <= 100:
        return _unknown("altseason index outside 0..100")
    bucket = "btc_season" if value < 25 else "alt_season" if value >= 75 else "neutral"
    return {"status": "ok", "altcoin_index": value, "bucket": bucket}


def get_latest(force=False):
    cached = _read_cache()
    now = datetime.now(timezone.utc)
    if not force and cached:
        try:
            fetched_at = datetime.fromisoformat(cached["fetched_at"])
            if now - fetched_at < timedelta(hours=CACHE_HOURS):
                return cached["value"]
        except (KeyError, TypeError, ValueError):
            pass
    try:
        response = requests.get(ENDPOINT, timeout=10)
        response.raise_for_status()
        value = parse_payload(response.json())
        if value["status"] == "ok":
            _write_cache({"fetched_at": now.isoformat(), "value": value})
            return value
        return value if cached is None else cached.get("value", value)
    except Exception as exc:
        if cached and isinstance(cached.get("value"), dict):
            stale = dict(cached["value"])
            stale.update({"status": "unknown/stale", "error": str(exc)})
            return stale
        return _unknown(str(exc))


if __name__ == "__main__":
    print(get_latest())
