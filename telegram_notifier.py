import datetime
from typing import Optional, Any, Dict
from telegram_messenger import TelegramMessenger

class TelegramNotifier:
    """Handles sending messages to Telegram."""
    def __init__(self, messenger: TelegramMessenger):
        self._messenger = messenger

    async def notify(self, chat_id: str, message_type: str, message: Optional[str] = None, **kwargs):
        """Sends a message to the specified Telegram chat ID based on message type."""
        if message_type == "simple":
            await self._messenger.send_simple_message(chat_id, message)
        elif message_type == "bot_status_update":
            print(f"DEBUG: Notifier received bot_status_update for {kwargs.get('instance_name')}")
            await self._messenger.send_bot_status_update(chat_id, **kwargs)
        elif message_type == "bot_not_found_alert":
            await self._messenger.send_bot_not_found_alert(chat_id, **kwargs)
        elif message_type == "trade_update":
            await self._messenger.send_trade_update(chat_id, **kwargs)
        elif message_type == "error":
            await self._messenger.send_error_message(chat_id, message)
        else:
            print(f"[{datetime.datetime.now()}] Unknown message type: {message_type}. Sending as simple message.")
            await self._messenger.send_simple_message(chat_id, message)