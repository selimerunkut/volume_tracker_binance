"""Silent deterministic forward-signal generation from volume alerts."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from .db_service import get_connection, init_db
from .deterministic_strategy import evaluate_strategy
from .market_data_service import fetch_klines, get_current_price
from .technical_analysis import calculate_indicators, get_latest_indicators

logger = logging.getLogger(__name__)
AUTO_SIGNAL_COOLDOWN_HOURS = float(os.getenv("AUTO_SIGNAL_COOLDOWN_HOURS", "12"))
MAX_OPEN_AUTO_SUGGESTIONS = int(os.getenv("MAX_OPEN_AUTO_SUGGESTIONS", "500"))


def create_auto_signal(symbol, exchange_name):
    """Evaluate and persist one alert without sending a second Telegram message."""
    init_db()
    symbol = str(symbol).upper().strip()
    exchange_name = str(exchange_name).lower().strip()
    price = get_current_price(symbol, exchange_name=exchange_name)
    klines = fetch_klines(symbol, interval="1h", limit=250, exchange_name=exchange_name)
    if price is None or klines is None or klines.empty:
        return None
    indicators = get_latest_indicators(calculate_indicators(klines))
    strategy = evaluate_strategy(indicators, price)
    now = datetime.now()
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        open_count = conn.execute(
            "SELECT COUNT(*) FROM suggestions WHERE source='auto' AND status='PENDING'"
        ).fetchone()[0]
        if open_count >= MAX_OPEN_AUTO_SUGGESTIONS:
            logger.warning("Auto-signal open cap reached (%s)", MAX_OPEN_AUTO_SUGGESTIONS)
            conn.rollback()
            return None
        pending = conn.execute(
            """SELECT 1 FROM suggestions
               WHERE symbol=? AND exchange_name=? AND source='auto' AND status='PENDING'
               LIMIT 1""",
            (symbol, exchange_name),
        ).fetchone()
        if pending:
            conn.rollback()
            return None
        cooldown = conn.execute(
            """SELECT created_at, resolved_at FROM suggestions
               WHERE symbol=? AND exchange_name=? AND source='auto'
               ORDER BY id DESC LIMIT 1""",
            (symbol, exchange_name),
        ).fetchone()
        if cooldown:
            timestamp = cooldown[1] or cooldown[0]
            try:
                if now - datetime.fromisoformat(timestamp) < timedelta(hours=AUTO_SIGNAL_COOLDOWN_HOURS):
                    conn.rollback()
                    return None
            except (TypeError, ValueError):
                logger.warning("Ignoring malformed auto-signal timestamp for %s", symbol)
        analysis_data = {
            "exchange_name": exchange_name,
            "source": "auto",
            "current_price": price,
            "indicators": {key: float(value) for key, value in indicators.items() if value is not None},
            "action": strategy["action"],
            "confidence": strategy["confidence"],
            "score": strategy["score"],
            "rule_ids": strategy["rule_ids"],
        }
        cursor = conn.execute(
            """INSERT INTO suggestions
               (timestamp, symbol, strategy_type, entry_price, take_profit, stop_loss,
                reasoning, analysis_data, source, exchange_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'auto', ?)""",
            (
                now.isoformat(), symbol, strategy["action"], strategy["entry"], strategy["tp"],
                strategy["sl"], strategy["reasoning"], __import__("json").dumps(analysis_data), exchange_name,
            ),
        )
        conn.commit()
        logger.info("Saved auto signal #%s for %s on %s", cursor.lastrowid, symbol, exchange_name)
        return {**strategy, "suggestion_id": cursor.lastrowid, "analysis_data": analysis_data}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
