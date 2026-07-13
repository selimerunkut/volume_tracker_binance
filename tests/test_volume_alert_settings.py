from src.services.volume_alerts import (
    DEFAULT_VOLUME_MIN_QUOTE_USD,
    parse_volume_min_quote_usd,
)


def test_default_threshold_is_fifty_thousand():
    assert DEFAULT_VOLUME_MIN_QUOTE_USD == 50_000


def test_threshold_parser_accepts_positive_whole_dollars():
    assert parse_volume_min_quote_usd('75000') == 75_000


def test_threshold_parser_rejects_unsafe_values():
    for value in ('0', '-1', '1.5', '50k', '', True):
        try:
            parse_volume_min_quote_usd(value)
        except ValueError:
            continue
        raise AssertionError(f'{value!r} should be rejected')
