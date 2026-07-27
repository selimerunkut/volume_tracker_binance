"""Deterministic strategy orchestration for /analyze."""

from __future__ import annotations

import logging
from typing import Any

from .altseason_service import get_latest as get_altseason
from .db_service import save_suggestion
from .deterministic_strategy import evaluate_strategy
from .regime_service import get_regimes_at
from .market_data_service import fetch_klines, get_current_price
from .news_service import get_latest_news
from .technical_analysis import calculate_indicators, get_latest_indicators

logger = logging.getLogger(__name__)


def normalize_exchange_name(exchange_name: str | None = "binance") -> str:
    normalized = str(exchange_name or "binance").strip().lower()
    return normalized or "binance"


def _coerce_indicators(raw_indicators: dict[str, Any]) -> dict[str, float]:
    indicators: dict[str, float] = {}
    for key, value in raw_indicators.items():
        if value is None:
            continue
        indicators[key] = float(value)
    return indicators


def analyze_and_suggest(symbol: str, exchange_name: str = "binance") -> dict[str, Any]:
    """Analyze a symbol with deterministic rules and persist the result."""
    exchange_name = normalize_exchange_name(exchange_name)
    symbol = str(symbol).upper().strip()

    try:
        current_price = get_current_price(symbol, exchange_name=exchange_name)
        klines = fetch_klines(symbol, interval="1h", limit=250, exchange_name=exchange_name)
        if klines is None or klines.empty:
            return {
                "error": (
                    f"Failed to fetch market data for {symbol} on {exchange_name}. "
                    "Is it a valid symbol for that exchange?"
                )
            }

        indicator_frame = calculate_indicators(klines)
        raw_indicators = get_latest_indicators(indicator_frame)
        indicators = _coerce_indicators(raw_indicators)
        strategy = evaluate_strategy(indicators, current_price)
        news_items = get_latest_news(limit=5)

        analysis_data = {
            "exchange_name": exchange_name,
            "current_price": current_price,
            "action": strategy["action"],
            "confidence": strategy["confidence"],
            "entry": strategy["entry"],
            "tp": strategy["tp"],
            "sl": strategy["sl"],
            "indicators": indicators,
            "score": strategy["score"],
            "rule_ids": strategy["rule_ids"],
            "news_items": news_items,
        }
        try:
            regimes = get_regimes_at()
            analysis_data["btc_market_regime"] = {
                venue: {
                    key: value for key, value in regime.items()
                    if key in {"status", "direction", "raw_direction", "volatility", "volume_tag", "date"}
                }
                for venue, regime in regimes.items()
            }
        except Exception as regime_error:
            logger.warning("BTC regime lookup failed: %s", regime_error)
            analysis_data["btc_market_regime"] = {
                "okx": {"status": "unknown/stale"},
                "kraken": {"status": "unknown/stale"},
            }
        try:
            analysis_data["cmc_altseason_index"] = get_altseason()
        except Exception as altseason_error:
            logger.warning("Altseason lookup failed: %s", altseason_error)
            analysis_data["cmc_altseason_index"] = {"status": "unknown/stale", "altcoin_index": None}

        suggestion_id = save_suggestion(
            symbol=symbol,
            strategy_type=strategy["action"],
            entry_price=strategy["entry"],
            take_profit=strategy["tp"],
            stop_loss=strategy["sl"],
            reasoning=strategy["reasoning"],
            analysis_data=analysis_data,
        )
        return {**strategy, "suggestion_id": suggestion_id, "analysis_data": analysis_data}
    except Exception as exc:
        logger.error(
            "Deterministic analysis failed for %s on %s: %s",
            symbol,
            exchange_name,
            exc,
        )
        return {"error": str(exc)}
