import asyncio
import logging
from datetime import datetime
from .market_data_service import fetch_klines
from .technical_analysis import calculate_indicators
from .strategy_signals import evaluate_hourly_strategy, evaluate_daily_strategy
from .watchlist_manager import WatchlistManager

logger = logging.getLogger(__name__)

class SignalService:
    def __init__(self, bot_context=None, chat_id=None, watchlist_manager=None):
        self.bot_context = bot_context
        self.chat_id = chat_id
        self.watchlist_manager = watchlist_manager or WatchlistManager()
        self.last_signals = {}

    async def check_signals(self, timeframe='1h'):
        self.watchlist_manager.refresh()
        symbols = self.watchlist_manager.get_watchlist()
        if not symbols:
            return

        for symbol in symbols:
            try:
                df = fetch_klines(symbol, interval=timeframe, limit=100)
                if df.empty:
                    continue
                
                df = calculate_indicators(df)
                
                if timeframe == '1h':
                    signal = evaluate_hourly_strategy(df)
                else:
                    signal = evaluate_daily_strategy(df)
                
                if signal != 'WAIT':
                    last_key = (symbol, timeframe)
                    if self.last_signals.get(last_key) != signal:
                        self.last_signals[last_key] = signal
                        await self.notify_signal(symbol, timeframe, signal)
                else:
                    self.last_signals[(symbol, timeframe)] = 'WAIT'
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error checking {timeframe} signals for {symbol}: {e}")

    async def notify_signal(self, symbol, timeframe, signal):
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
            await self.bot_context.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Failed to send signal notification: {e}")
