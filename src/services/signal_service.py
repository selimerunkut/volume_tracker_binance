import asyncio
import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from .market_data_service import fetch_klines, get_current_price
from .technical_analysis import calculate_indicators
from .strategy_signals import (
    evaluate_hourly_strategy,
    evaluate_daily_strategy,
    describe_hourly_signal,
    describe_daily_signal,
)
from .watchlist_manager import WatchlistManager
from .db_service import save_signal_trade, get_last_signal_trade

logger = logging.getLogger(__name__)
SIGNAL_COOLDOWN_SECONDS = 3600


def normalize_exchange_name(exchange_name='binance'):
    return (exchange_name or 'binance').strip().lower() or 'binance'

class SignalService:
    def __init__(self, bot_context=None, chat_id=None, watchlist_manager=None, exchange_name='binance'):
        self.bot_context = bot_context
        self.chat_id = chat_id
        self.watchlist_manager = watchlist_manager or WatchlistManager()
        self.exchange_name = normalize_exchange_name(exchange_name)
        self.last_signals = {}
        self.signal_contexts = {}

    async def check_signals(self, timeframe='1h', exchange_name=None):
        exchange_name = normalize_exchange_name(exchange_name or self.exchange_name)
        self.watchlist_manager.refresh()
        if hasattr(self.watchlist_manager, 'get_watchlists'):
            watchlists = self.watchlist_manager.get_watchlists()
        else:
            symbols = self.watchlist_manager.get_watchlist()
            watchlists = {exchange_name: symbols} if symbols else {}

        if not watchlists:
            return

        for exchange_name, symbols in watchlists.items():
            if not symbols:
                continue

            for symbol in symbols:
                try:
                    df = fetch_klines(symbol, interval=timeframe, limit=100, exchange_name=exchange_name)
                    if df.empty:
                        continue
                    
                    df = calculate_indicators(df)
                    if timeframe == '1h':
                        signal = evaluate_hourly_strategy(df)
                        explanation = describe_hourly_signal(df, signal)
                    else:
                        signal = evaluate_daily_strategy(df)
                        explanation = describe_daily_signal(df, signal)

                    if signal != 'WAIT':
                        now = datetime.now()
                        dedup_key = f"{exchange_name}:{symbol}:{timeframe}:{signal}"
                        try:
                            last_signal = get_last_signal_trade(symbol, timeframe, signal, dedup_key=dedup_key)
                        except TypeError:
                            last_signal = get_last_signal_trade(symbol, timeframe, signal)
                        if last_signal:
                            prev_entry = datetime.fromisoformat(last_signal['entry_ts'])
                            if (now - prev_entry).total_seconds() < SIGNAL_COOLDOWN_SECONDS:
                                logger.info(f"Skipping duplicate {signal} signal for {exchange_name.upper()} {symbol} {timeframe} (cooldown)")
                                continue
                        entry_price = await asyncio.to_thread(get_current_price, symbol, exchange_name=exchange_name)
                        if entry_price is None:
                            logger.warning(f"Cannot persist {signal} signal for {exchange_name.upper()} {symbol}: entry price unavailable")
                        else:
                            signal_type = 'hourly' if timeframe == '1h' else 'daily'
                            save_signal_trade(symbol, timeframe, signal_type, signal, entry_price, explanation, dedup_key)
                        last_key = (exchange_name, symbol, timeframe)
                        if self.last_signals.get(last_key) != signal:
                            self.last_signals[last_key] = signal
                            self.record_signal_context(symbol, timeframe, signal, explanation, exchange_name=exchange_name)
                            await self.notify_signal(symbol, timeframe, signal, explanation)
                    else:
                        self.last_signals[(exchange_name, symbol, timeframe)] = 'WAIT'
                    
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Error checking {timeframe} signals for {exchange_name.upper()} {symbol}: {e}")

    async def notify_signal(self, symbol, timeframe, signal, explanation):
        if not self.bot_context or not self.chat_id:
            logger.info(f"SIGNAL: {symbol} [{timeframe}] -> {signal}")
            return

        emoji = "🚀" if signal == "LONG" else "📉" if signal == "SHORT" else "🏁"
        message = (
            f"{emoji} <b>New {timeframe} Signal Detected!</b>\n\n"
            f"Symbol: <code>{symbol}</code>\n"
            f"Action: <b>{signal}</b>\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Use /analyze {symbol} for deep AI strategy."
        )
        
        try:
            keyboard = [
                [InlineKeyboardButton("🧾 Signal details", callback_data=f"signal_details|{symbol}|{timeframe}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await self.bot_context.bot.send_message(
                chat_id=self.chat_id,
                text=message + "\n\nTap the button below to see why this signal fired.",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send signal notification: {e}")

    def record_signal_context(self, symbol, timeframe, signal, explanation, exchange_name=None):
        context = {
            "signal": signal,
            "generated_at": datetime.now(),
            "explanation": explanation or "Signal generated from the configured strategy without additional details."
        }
        self.signal_contexts[(symbol, timeframe)] = context
        if exchange_name:
            self.signal_contexts[(exchange_name, symbol, timeframe)] = context

    def get_signal_context(self, symbol, timeframe, exchange_name=None):
        if exchange_name:
            return self.signal_contexts.get((exchange_name, symbol, timeframe))
        return self.signal_contexts.get((symbol, timeframe))
