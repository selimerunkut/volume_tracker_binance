"""Shared helpers for volume alert payloads and Telegram rendering."""

from __future__ import annotations


def generate_tradingview_url(symbol, exchange='BINANCE'):
    exchange_name = (exchange or 'BINANCE').upper()
    return f"https://www.tradingview.com/symbols/{symbol}/?exchange={exchange_name}"


def generate_trade_url(symbol, exchange='BINANCE'):
    exchange_name = (exchange or 'BINANCE').upper()
    if exchange_name == 'BINANCE':
        if symbol.endswith('USDC'):
            base_asset = symbol[:-4]
            return f"https://www.binance.com/en/trade/{base_asset}_USDC"
        if symbol.endswith('BTC'):
            base_asset = symbol[:-3]
            return f"https://www.binance.com/en/trade/{base_asset}_BTC"
        return f"https://www.binance.com/en/trade/{symbol}"

    return None


def build_volume_alert_message(
    alert_detail,
    last_2h_volume,
    last_4h_volume,
    last_completed_hour_volume,
    open_price,
    close_price,
    symbol,
    exchange='BINANCE',
    chart_url=None,
    trade_url=None,
):
    """Build the alert payload once so exchange branches do not duplicate it."""
    chart_link = chart_url or generate_tradingview_url(symbol, exchange)
    trade_link = trade_url or generate_trade_url(symbol, exchange)
    exchange_name = (exchange or 'BINANCE').upper()

    return {
        'exchange': exchange_name,
        'symbol': symbol,
        'curr_volume': alert_detail['curr_volume'],
        'prev_volume_mean': alert_detail['prev_volume_mean'],
        'level': alert_detail['level'],
        'last_2h_volume': last_2h_volume,
        'last_4h_volume': last_4h_volume,
        'last_1h_volume': last_completed_hour_volume,
        'open_price': f"{open_price:.8f}",
        'close_price': f"{close_price:.8f}",
        'chart_url': chart_link,
        'trade_url': trade_link,
        'binance_trade_url': trade_link if exchange_name == 'BINANCE' else None,
    }


def render_volume_alert_text(alert_message, include_exchange=False):
    """Render the Telegram text once so transport code stays thin."""
    symbol = alert_message['symbol']
    exchange = (alert_message.get('exchange') or 'BINANCE').upper()
    curr_volume = int(alert_message['curr_volume'])
    prev_volume_mean = int(alert_message['prev_volume_mean'])
    level = alert_message['level']
    chart_url = alert_message['chart_url']
    trade_url = alert_message.get('trade_url')
    last_2h_volume = int(alert_message['last_2h_volume'])
    last_4h_volume = int(alert_message['last_4h_volume'])
    last_1h_volume = int(alert_message['last_1h_volume'])
    open_price = alert_message['open_price']
    close_price = alert_message['close_price']
    if not trade_url and exchange == 'BINANCE':
        trade_url = alert_message.get('binance_trade_url')
    if not trade_url:
        trade_url = 'N/A'

    header_exchange = f" - {exchange}" if include_exchange else ""
    return (
        f"🚨 *Volume Alert{header_exchange} - {symbol}* 🚨\n"
        f"📊 Current Volume: {curr_volume:,}\n"
        f"📈 Previous 6h Mean Volume: {prev_volume_mean:,}\n"
        f"🕐 Last 1h Volume: {last_1h_volume:,}\n"
        f"🕒 Last 2h Volume: {last_2h_volume:,}\n"
        f"🕓 Last 4h Volume: {last_4h_volume:,}\n"
        f"💹 Last 1h Vol. candle Prices, Open: {open_price}, Close: {close_price}\n"
        f"🔥 Alert Level: *{level}*\n"
        f"🔗 {chart_url}\n"
        f"🔗 {trade_url}"
    )
