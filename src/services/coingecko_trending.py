"""CoinGecko trending-token polling and deduplication."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import requests

ENDPOINT = "https://api.coingecko.com/api/v3/search/trending"
STATE_FILE = os.getenv("COINGECKO_TRENDING_STATE_FILE", "coingecko_trending_state.json")
SEEN_RETENTION = timedelta(hours=48)
DIGEST_INTERVAL = timedelta(hours=1)


def _api_headers() -> dict[str, str]:
    """Return optional CoinGecko authentication headers."""
    api_key = os.getenv("COINGECKO_API_KEY")
    plan = os.getenv("COINGECKO_API_PLAN")
    if not api_key:
        try:
            with open("credentials_b.json", encoding="utf-8") as handle:
                credentials = json.load(handle)
            api_key = credentials.get("coingecko_api_key")
            plan = plan or credentials.get("coingecko_api_plan")
        except (OSError, json.JSONDecodeError):
            pass
    if not api_key:
        return {}
    header = "x-cg-pro-api-key" if (plan or "demo").lower() == "pro" else "x-cg-demo-api-key"
    return {header: api_key}


def parse_trending_payload(payload: dict) -> list[dict]:
    """Extract the coin data needed by Telegram notifications."""
    coins = []
    for entry in (payload or {}).get("coins", []):
        item = entry.get("item", {}) if isinstance(entry, dict) else {}
        coin_id = item.get("id")
        if not coin_id:
            continue
        change = (item.get("data") or {}).get("price_change_percentage_24h") or {}
        coins.append(
            {
                "id": str(coin_id),
                "name": item.get("name") or str(coin_id),
                "symbol": str(item.get("symbol") or "").upper(),
                "market_cap_rank": item.get("market_cap_rank"),
                "price_change_percentage_24h": change.get("usd"),
                "market_cap": (item.get("data") or {}).get("market_cap"),
                "total_volume": (item.get("data") or {}).get("total_volume"),
            }
        )
    return coins


def fetch_trending() -> list[dict]:
    """Fetch the current CoinGecko trending coins."""
    response = requests.get(ENDPOINT, headers=_api_headers(), timeout=10)
    response.raise_for_status()
    return parse_trending_payload(response.json())


def _read_state(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(path: str, state: dict) -> None:
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    os.replace(temporary, path)


def process_snapshot(coins: list[dict], path: str = STATE_FILE, now: datetime | None = None) -> tuple[list[dict], bool]:
    """Return newly observed coins and whether the general digest is due.

    The first successful poll establishes a baseline, so a bot restart does not
    produce a false "new token" alert for every currently trending coin.
    """
    now = now or datetime.now(timezone.utc)
    state = _read_state(path)
    seen = {}
    cutoff = now - SEEN_RETENTION
    for coin_id, timestamp in (state.get("seen") or {}).items():
        try:
            parsed = datetime.fromisoformat(timestamp)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed >= cutoff:
                seen[str(coin_id)] = parsed.isoformat()
        except (TypeError, ValueError):
            continue

    initialized = bool(state.get("initialized"))
    new_coins = [coin for coin in coins if initialized and coin["id"] not in seen]
    for coin in coins:
        seen[coin["id"]] = now.isoformat()

    digest_due = False
    last_digest = state.get("last_digest_at")
    if not last_digest:
        digest_due = True
    else:
        try:
            parsed_digest = datetime.fromisoformat(last_digest)
            if parsed_digest.tzinfo is None:
                parsed_digest = parsed_digest.replace(tzinfo=timezone.utc)
            digest_due = now - parsed_digest >= DIGEST_INTERVAL
        except (TypeError, ValueError):
            digest_due = True

    new_state = {
        "initialized": True,
        "seen": seen,
        "last_digest_at": now.isoformat() if digest_due else last_digest,
    }
    _write_state(path, new_state)
    return new_coins, digest_due


if __name__ == "__main__":
    print(fetch_trending())
