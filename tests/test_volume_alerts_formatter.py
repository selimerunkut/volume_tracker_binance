import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.volume_alerts import build_volume_alert_message, render_volume_alert_text


def test_build_volume_alert_message_keeps_compatibility_aliases():
    alert_detail = {
        'curr_volume': 183717.2,
        'prev_volume_mean': 33930.8652173913,
        'level': 'HIGH',
    }

    message = build_volume_alert_message(
        alert_detail,
        last_2h_volume=123456,
        last_4h_volume=789012,
        last_completed_hour_volume=99999,
        open_price=100.1234,
        close_price=110.5678,
        symbol='TESTUSDC',
        exchange='BINANCE',
    )

    assert message['exchange'] == 'BINANCE'
    assert message['symbol'] == 'TESTUSDC'
    assert message['trade_url'] == 'https://www.binance.com/en/trade/TEST_USDC'
    assert message['binance_trade_url'] == message['trade_url']
    assert message['chart_url'] == 'https://www.tradingview.com/symbols/TESTUSDC/?exchange=BINANCE'


def test_render_volume_alert_text_supports_exchange_specific_header():
    alert_message = {
        'exchange': 'KRAKEN',
        'symbol': 'BTCUSD',
        'curr_volume': 1000,
        'prev_volume_mean': 100,
        'level': 'HIGH',
        'last_1h_volume': 900,
        'last_2h_volume': 2000,
        'last_4h_volume': 4000,
        'open_price': '100.00000000',
        'close_price': '110.00000000',
        'chart_url': 'https://example.test/chart/BTCUSD',
        'trade_url': 'https://example.test/trade/BTCUSD',
    }

    text = render_volume_alert_text(alert_message, include_exchange=True)

    assert 'Volume Alert - KRAKEN - BTCUSD' in text
    assert 'Current Volume: 1,000' in text
    assert '🔗 https://example.test/trade/BTCUSD' in text


def test_build_volume_alert_message_uses_exchange_specific_trade_links():
    alert_detail = {
        'curr_volume': 5000,
        'prev_volume_mean': 1000,
        'level': 'HIGH',
    }

    message = build_volume_alert_message(
        alert_detail,
        last_2h_volume=2000,
        last_4h_volume=3000,
        last_completed_hour_volume=1500,
        open_price=100.0,
        close_price=110.0,
        symbol='BTCUSD',
        exchange='KRAKEN',
        trade_url='https://pro.kraken.com/app/trade/btc-usd',
    )

    assert message['trade_url'] == 'https://pro.kraken.com/app/trade/btc-usd'
    assert message['binance_trade_url'] is None


def test_render_volume_alert_text_keeps_legacy_binance_fallback():
    alert_message = {
        'exchange': 'BINANCE',
        'symbol': 'TESTUSDC',
        'curr_volume': 1000,
        'prev_volume_mean': 100,
        'level': 'HIGH',
        'last_1h_volume': 900,
        'last_2h_volume': 2000,
        'last_4h_volume': 4000,
        'open_price': '100.00000000',
        'close_price': '110.00000000',
        'chart_url': 'https://www.tradingview.com/symbols/TESTUSDC/?exchange=BINANCE',
        'binance_trade_url': 'https://www.binance.com/en/trade/TEST_USDC',
    }

    text = render_volume_alert_text(alert_message, include_exchange=False)

    assert 'https://www.binance.com/en/trade/TEST_USDC' in text


def test_render_volume_alert_text_does_not_fallback_to_binance_for_non_binance():
    alert_message = {
        'exchange': 'KRAKEN',
        'symbol': 'BTCUSD',
        'curr_volume': 1000,
        'prev_volume_mean': 100,
        'level': 'HIGH',
        'last_1h_volume': 900,
        'last_2h_volume': 2000,
        'last_4h_volume': 4000,
        'open_price': '100.00000000',
        'close_price': '110.00000000',
        'chart_url': 'https://example.test/chart/BTCUSD',
        'binance_trade_url': 'https://www.binance.com/en/trade/BTC_USD',
    }

    text = render_volume_alert_text(alert_message, include_exchange=True)

    assert 'Volume Alert - KRAKEN - BTCUSD' in text
    assert 'https://www.binance.com/en/trade/BTC_USD' not in text
    assert '🔗 N/A' in text


def test_render_volume_alert_text_preserves_binance_default_visible_behavior():
    alert_message = {
        'exchange': 'BINANCE',
        'symbol': 'TESTUSDC',
        'curr_volume': 1000,
        'prev_volume_mean': 100,
        'level': 'HIGH',
        'last_1h_volume': 900,
        'last_2h_volume': 2000,
        'last_4h_volume': 4000,
        'open_price': '100.00000000',
        'close_price': '110.00000000',
        'chart_url': 'https://www.tradingview.com/symbols/TESTUSDC/?exchange=BINANCE',
        'trade_url': 'https://www.binance.com/en/trade/TEST_USDC',
        'binance_trade_url': 'https://www.binance.com/en/trade/TEST_USDC',
    }

    text = render_volume_alert_text(alert_message, include_exchange=False)

    assert 'Volume Alert - TESTUSDC' in text
    assert 'Volume Alert - BINANCE' not in text
    assert 'https://www.binance.com/en/trade/TEST_USDC' in text


if __name__ == "__main__":
    test_build_volume_alert_message_keeps_compatibility_aliases()
    test_render_volume_alert_text_supports_exchange_specific_header()
    test_render_volume_alert_text_preserves_binance_default_visible_behavior()
    print("All volume alert formatter tests passed!")
