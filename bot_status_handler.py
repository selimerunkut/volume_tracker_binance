import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from telegram_messenger import TelegramMessenger
from hummingbot_integration import HummingbotManager
from telegram_notifier import TelegramNotifier
from log_processor import LogProcessor

class BotStatusHandler:
    """
    Handles the logic for processing and notifying about different bot statuses (running, stopped, not found).
    Delegates message sending to TelegramNotifier and log processing to LogProcessor.
    """
    def __init__(self, notifier: 'TelegramNotifier', hummingbot_manager: HummingbotManager, log_processor: LogProcessor, time_provider: Callable[[], datetime]):
        self._notifier = notifier
        self._hummingbot_manager = hummingbot_manager
        self._log_processor = log_processor
        self._time_provider = time_provider
        self._last_active_message_time: Dict[str, datetime] = {}


    async def handle_stopped_bot(self, trade: Dict[str, Any], instance_name: str, status_response: Dict[str, Any]):
        print(f"DEBUG: Entering handle_stopped_bot for {instance_name}")
        """Handles a stopped bot and sends a notification. Archiving is handled by _synchronize_active_trades."""
        chat_id = trade.get('chat_id')
        trading_pair = trade.get('trading_pair')
        general_logs = status_response.get('general_logs', [])
        error_logs = status_response.get('error_logs', [])

        print(f"Bot '{instance_name}' has stopped. Notifying...")

        stop_reason = await self._log_processor.determine_stop_reason(general_logs, error_logs)
        await self._notifier.notify(
            chat_id,
            message_type="bot_status_update",
            instance_name=instance_name,
            trading_pair=trading_pair,
            status="stopped",
            stop_reason=stop_reason
        )
        self._last_active_message_time.pop(instance_name, None)

    async def handle_running_bot(self, trade: Dict[str, Any], instance_name: str, status_response: Dict[str, Any]):
        """Handles a running bot and sends periodic updates."""
        chat_id = trade.get('chat_id')
        trading_pair = trade.get('trading_pair')
        general_logs = status_response.get('general_logs', [])

        current_time = self._time_provider()
        last_sent = self._last_active_message_time.get(instance_name)

        if not last_sent or (current_time - last_sent).total_seconds() >= 300:
            log_info = await self._log_processor.parse_bot_logs_for_info(general_logs)
            await self._notifier.notify(
                chat_id,
                message_type="bot_status_update",
                instance_name=instance_name,
                trading_pair=trading_pair,
                status="running",
                pnl_info=log_info['pnl_info'],
                open_orders_info=log_info['open_orders_info']
            )
            self._last_active_message_time[instance_name] = current_time

    async def handle_not_found_bot(self, trade: Dict[str, Any], instance_name: str):
        """Handles a bot not found on the Hummingbot instance. Archiving is handled by _synchronize_active_trades."""
        chat_id = trade.get('chat_id')
        trading_pair = trade.get('trading_pair')

        print(f"Bot '{instance_name}' not found on Hummingbot instance.")
        await self._notifier.notify(
            chat_id,
            message_type="bot_not_found_alert",
            instance_name=instance_name,
            trading_pair=trading_pair
        )
        self._last_active_message_time.pop(instance_name, None)