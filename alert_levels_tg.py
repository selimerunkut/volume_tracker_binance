from src.services.volume_alerts import generate_tradingview_url


def get_volume_alert_details(curr_volume, prev_volume_mean, last_completed_hour_volume, open_price, close_price, symbol, interval, exchange):
    details = []
    exchange_name = (exchange or '').upper()
    chart_url = f"{generate_tradingview_url(symbol, exchange_name)}&interval={interval}"

    # New condition: current volume must also be greater than the last completed hour's volume
    if close_price > open_price and curr_volume > last_completed_hour_volume and curr_volume > prev_volume_mean * 15:
        details.append({
            "level": "1500%+",
            "curr_volume": curr_volume,
            "prev_volume_mean": prev_volume_mean,
            "symbol": symbol,
            "interval": interval,
            "chart_url": chart_url
        })
    elif close_price > open_price and curr_volume > last_completed_hour_volume and curr_volume > prev_volume_mean * 10:
        details.append({
            "level": "1000%+",
            "curr_volume": curr_volume,
            "prev_volume_mean": prev_volume_mean,
            "symbol": symbol,
            "interval": interval,
            "chart_url": chart_url
        })
    elif close_price > open_price and curr_volume > last_completed_hour_volume and curr_volume > prev_volume_mean * 7:
        details.append({
            "level": "700%+",
            "curr_volume": curr_volume,
            "prev_volume_mean": prev_volume_mean,
            "symbol": symbol,
            "interval": interval,
            "chart_url": chart_url
        })
    elif close_price > open_price and curr_volume > last_completed_hour_volume and curr_volume > prev_volume_mean * 5:
        details.append({
            "level": "500%+",
            "curr_volume": curr_volume,
            "prev_volume_mean": prev_volume_mean,
            "symbol": symbol,
            "interval": interval,
            "chart_url": chart_url
        })

    return details
