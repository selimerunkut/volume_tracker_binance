import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest

from src.services.quote_value_service import rate_from_bid_ask, to_usd_quote_value


def test_to_usd_quote_value_handles_stables_and_native_rates():
    assert to_usd_quote_value(100, 'USDC', 1) == 100
    assert to_usd_quote_value(2, 'BTC', 62000) == 124000
    assert to_usd_quote_value(100, 'EUR', 1.08) == pytest.approx(108)


@pytest.mark.parametrize('value, rate', [(-1, 1), (1, 0), (1, math.nan), ('bad', 1)])
def test_to_usd_quote_value_rejects_invalid_numbers(value, rate):
    with pytest.raises(ValueError):
        to_usd_quote_value(value, 'EUR', rate)


def test_rate_from_bid_ask_uses_conservative_side():
    assert rate_from_bid_ask('1.08', '1.09') == pytest.approx(1.08)
    assert rate_from_bid_ask('1.08', '1.09', inverse=True) == pytest.approx(1 / 1.09)
