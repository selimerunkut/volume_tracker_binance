from datetime import datetime, timedelta, timezone

from src.services.coingecko_trending import parse_trending_payload, process_snapshot


UTC_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _payload(*coin_ids):
    return {
        "coins": [
            {
                "item": {
                    "id": coin_id,
                    "name": coin_id.title(),
                    "symbol": coin_id[:3],
                    "market_cap_rank": index + 1,
                    "data": {
                        "price_change_percentage_24h": {"usd": index + 1.25},
                        "market_cap": f"${index + 1}M",
                        "total_volume": f"${index + 2}M",
                    },
                }
            }
            for index, coin_id in enumerate(coin_ids)
        ]
    }


def test_parse_trending_payload_extracts_coin_fields():
    coins = parse_trending_payload(_payload("alpha"))

    assert coins == [
        {
            "id": "alpha",
            "name": "Alpha",
            "symbol": "ALP",
            "market_cap_rank": 1,
            "price_change_percentage_24h": 1.25,
            "market_cap": "$1M",
            "total_volume": "$2M",
        }
    ]


def test_process_snapshot_suppresses_initial_baseline_and_detects_new_coin(tmp_path):
    state_file = str(tmp_path / "trending.json")
    initial = parse_trending_payload(_payload("alpha", "beta"))

    new_coins, digest_due = process_snapshot(initial, path=state_file, now=UTC_NOW)
    assert new_coins == []
    assert digest_due is True

    updated = parse_trending_payload(_payload("alpha", "beta", "gamma"))
    new_coins, digest_due = process_snapshot(
        updated,
        path=state_file,
        now=UTC_NOW + timedelta(minutes=10),
    )
    assert [coin["id"] for coin in new_coins] == ["gamma"]
    assert digest_due is False


def test_process_snapshot_schedules_digest_every_hour(tmp_path):
    state_file = str(tmp_path / "trending.json")
    coins = parse_trending_payload(_payload("alpha"))
    process_snapshot(coins, path=state_file, now=UTC_NOW)

    _, digest_due = process_snapshot(
        coins,
        path=state_file,
        now=UTC_NOW + timedelta(hours=1),
    )
    assert digest_due is True
