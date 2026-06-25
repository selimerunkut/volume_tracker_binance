from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from alert_levels_tg import get_volume_alert_details


def test_get_volume_alert_details_supports_binance_and_kraken():
    binance_details = get_volume_alert_details(1000, 10, 20, 100, 110, 'BTCUSDC', '1h', 'BINANCE')
    kraken_details = get_volume_alert_details(1000, 10, 20, 100, 110, 'BTCUSD', '1h', 'KRAKEN')

    assert binance_details and binance_details[0]['symbol'] == 'BTCUSDC'
    assert 'exchange=BINANCE' in binance_details[0]['chart_url']

    assert kraken_details and kraken_details[0]['symbol'] == 'BTCUSD'
    assert 'exchange=KRAKEN' in kraken_details[0]['chart_url']
