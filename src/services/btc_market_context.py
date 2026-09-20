"""Independent, current BTC market context for Telegram analysis."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import time

import pandas as pd
import requests

HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"
SOURCE_NAME = "Hyperliquid BTC perpetual 1h candles"
MAX_DATA_AGE_MINUTES = 120
CANDLE_INTERVAL_MS = 60 * 60 * 1000


def _percent(new, old):
    return (float(new) / float(old) - 1.0) * 100.0


def _fetch_candles(hours=72):
    now_ms = int(time.time() * 1000)
    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": "BTC",
            "interval": "1h",
            "startTime": now_ms - hours * 60 * 60 * 1000,
        },
    }
    response = requests.post(HYPERLIQUID_INFO_URL, json=payload, timeout=15)
    response.raise_for_status()
    rows = response.json()
    frame = pd.DataFrame(rows)
    required = {"t", "T", "o", "c", "h", "l", "v"}
    if frame.empty or not required.issubset(frame.columns):
        raise ValueError("Hyperliquid returned no usable BTC candles")

    frame["start_ms"] = pd.to_numeric(frame["t"], errors="coerce")
    frame["end_ms"] = pd.to_numeric(frame["T"], errors="coerce")
    for column in ("o", "c", "h", "l", "v"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["start_ms", "end_ms", "o", "c", "h", "l", "v"])
    frame = frame[(frame["end_ms"] <= now_ms) & (frame["o"] > 0) & (frame["c"] > 0) & (frame["h"] > 0) & (frame["l"] > 0)]
    frame = frame.sort_values("end_ms").drop_duplicates("end_ms")
    gaps = frame["start_ms"].diff().dropna()
    if not gaps.empty and (gaps.sub(CANDLE_INTERVAL_MS).abs() > 1000).any():
        raise ValueError("Hyperliquid BTC candles have an hourly cadence gap")
    if len(frame) < 30:
        raise ValueError(f"Hyperliquid returned only {len(frame)} closed BTC candles")
    return frame.reset_index(drop=True)


def get_btc_market_context():
    """Return a short, explanatory context from independently fetched BTC data."""
    try:
        frame = _fetch_candles()
        closes = frame["c"].astype(float)
        volumes = frame["v"].astype(float)
        price = float(closes.iloc[-1])
        return_6h = _percent(closes.iloc[-1], closes.iloc[-7])
        return_24h = _percent(closes.iloc[-1], closes.iloc[-25])
        ema20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
        hourly_returns = closes.pct_change().dropna().tail(24)
        realized_volatility = float(hourly_returns.std(ddof=0) * math.sqrt(24) * 100)
        recent_volume = float(volumes.tail(6).sum())
        prior_six_avg = float(volumes.iloc[-30:-6].sum() / 4)
        volume_ratio = recent_volume / prior_six_avg if prior_six_avg > 0 else 1.0

        if return_24h >= 1.0 and price >= ema50:
            direction = "bullish"
        elif return_24h <= -1.0 and price <= ema50:
            direction = "bearish"
        else:
            direction = "range/transition"

        if realized_volatility >= 2.0:
            volatility = "high"
        elif realized_volatility <= 0.75:
            volatility = "normal/low"
        else:
            volatility = "normal"

        if volume_ratio >= 1.5:
            volume_tag = "expanded"
        elif volume_ratio <= 0.67:
            volume_tag = "reduced"
        else:
            volume_tag = "normal"

        as_of = datetime.fromtimestamp(float(frame.iloc[-1]["end_ms"]) / 1000, tz=timezone.utc)
        age_minutes = max(0, int((datetime.now(timezone.utc) - as_of).total_seconds() / 60))
        if age_minutes > MAX_DATA_AGE_MINUTES:
            return {
                "status": "unknown/stale",
                "source": SOURCE_NAME,
                "as_of": as_of.isoformat(),
                "age_minutes": age_minutes,
                "error": f"latest closed BTC candle is {age_minutes} minutes old",
            }
        summary = (
            f"BTC is {direction}: {return_24h:+.2f}% over 24h and {return_6h:+.2f}% over 6h; "
            f"price is {'above' if price >= ema50 else 'below'} EMA50; "
            f"volatility is {volatility} ({realized_volatility:.2f}% dailyized) and volume is {volume_tag} "
            f"({volume_ratio:.2f}x its recent baseline)."
        )
        return {
            "status": "ok",
            "source": SOURCE_NAME,
            "direction": direction,
            "volatility": volatility,
            "volume_tag": volume_tag,
            "price": price,
            "return_6h_percent": round(return_6h, 3),
            "return_24h_percent": round(return_24h, 3),
            "ema20": round(ema20, 2),
            "ema50": round(ema50, 2),
            "realized_volatility_percent": round(realized_volatility, 3),
            "volume_ratio": round(volume_ratio, 3),
            "as_of": as_of.isoformat(),
            "age_minutes": age_minutes,
            "summary": summary,
        }
    except Exception as exc:
        return {
            "status": "unknown/stale",
            "source": SOURCE_NAME,
            "error": f"independent BTC fetch failed: {type(exc).__name__}",
        }
