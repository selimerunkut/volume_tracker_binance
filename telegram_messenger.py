import aiohttp
import json
import datetime
import os
import asyncio
import re
from dotenv import load_dotenv
from typing import Union, Dict, Any, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup # Needed for inline buttons
import telegramify_markdown # Import the library

# Load environment variables from .env file
load_dotenv()

class TelegramMessenger:
    def __init__(self):
        self.TELEGRAM_BOT_TEST_MODE = os.getenv("TELEGRAM_BOT_TEST_MODE", "False").lower() == "true"
        self.TELEGRAM_BOT_TOKEN, self.TELEGRAM_CHAT_ID = self._load_telegram_credentials()

        if not self.TELEGRAM_BOT_TOKEN or not self.TELEGRAM_CHAT_ID:
            print(f"[{datetime.datetime.now()}] Telegram bot token or chat ID not found. Messages will not be sent.")

    def _load_telegram_credentials(self):
        try:
            with open('credentials_b.json', 'r') as f:
                credentials = json.load(f)
                if self.TELEGRAM_BOT_TEST_MODE:
                    print(f"[{datetime.datetime.now()}] Running in TEST MODE. Using test credentials for messenger.")
                    return credentials.get('telegram_bot_token_test'), credentials.get('telegram_chat_id_test')
                else:
                    print(f"[{datetime.datetime.now()}] Running in PRODUCTION MODE. Using production credentials for messenger.")
                    return credentials.get('telegram_bot_token'), credentials.get('telegram_chat_id')
        except FileNotFoundError:
            print(f"[{datetime.datetime.now()}] credentials_b.json not found. Please create it with 'telegram_bot_token' and 'telegram_chat_id'.")
            return None, None
        except json.JSONDecodeError as e:
            print(f"[{datetime.datetime.now()}] Error decoding credentials_b.json: {e}")
            return None, None


    async def _send_message(self, chat_id: str, markdown_text: str, reply_markup: Optional[str] = None, dry_run: bool = False):
        """
        Internal method to send a message to Telegram, converting Markdown to MarkdownV2.
        """
        if not self.TELEGRAM_BOT_TOKEN or not self.TELEGRAM_CHAT_ID:
            print(f"[{datetime.datetime.now()}] Telegram bot token or chat ID not configured. Message not sent.")
            return False

        # Convert the Markdown text to Telegram's MarkdownV2 format
        telegram_markdown_v2_text = telegramify_markdown.markdownify(markdown_text)

        url = f'https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/sendMessage'
        
        payload = {
            'chat_id': chat_id,
            'text': telegram_markdown_v2_text,
            'parse_mode': 'MarkdownV2',
            'disable_web_page_preview': True
        }

        if reply_markup:
            payload['reply_markup'] = reply_markup
        
        if dry_run:
            print(f"[{datetime.datetime.now()}] DRY RUN: Telegram message would have been sent to {chat_id}. Message details: {message_text}")
            return True
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    response.raise_for_status()
                    response_json = await response.json()
            if response_json.get("ok"):
                print(f"[{datetime.datetime.now()}] Telegram message sent successfully to {chat_id}.")
                return True
            else:
                print(f"[{datetime.datetime.now()}] Failed to send Telegram message to {chat_id}. Error: {response_json.get('description')}")
                return False
        except aiohttp.ClientError as e:
            print(f"[{datetime.datetime.now()}] Network error sending Telegram message to {chat_id}: {e}")
            return False
        except ValueError as e:
            print(f"[{datetime.datetime.now()}] JSON decoding error for Telegram API response to {chat_id}: {e}")
            return False
        except Exception as e:
            print(f"[{datetime.datetime.now()}] An unexpected error occurred while sending Telegram message to {chat_id}: {e}")
            return False

    async def send_simple_message(self, chat_id: str, message: str, dry_run: bool = False):
        """Sends a simple text message."""
        # The message is already expected to be in Markdown format, markdownify will handle escaping
        return await self._send_message(chat_id, message, dry_run=dry_run)

    async def send_bot_deployed_confirmation(self, chat_id: str, instance_name: str, trading_pair: str, order_amount_usd: float, trailing_stop_loss_delta: float, take_profit_delta: float, fixed_stop_loss_delta: float, dry_run: bool = False):
        """Sends a confirmation message for a newly deployed bot."""
        message = (
            f"✅ Bot Deployed Successfully! ✅\n"
            f"Instance: `{instance_name}`\n"
            f"Pair: `{trading_pair}`\n"
            f"Amount: `${order_amount_usd}`\n"
            f"TrailingStopLoss: `{trailing_stop_loss_delta}`\n"
            f"TakeProfit: `{take_profit_delta}`\n"
            f"FixedStopLoss: `{fixed_stop_loss_delta}`\n"
            f"Monitoring will begin shortly."
        )
        return await self._send_message(chat_id, message, dry_run=dry_run)

    async def send_bot_status_update(self, chat_id: str, instance_name: str, trading_pair: str, status: str, pnl_info: Optional[Dict[str, Any]] = None, open_orders_info: str = "Open Orders: N/A", stop_reason: Optional[str] = None, dry_run: bool = False):
        """Sends a status update for a bot."""
        status_emoji = "🟢" if status == "running" else "🔔"
        message = (
            f"{status_emoji} Bot Status Update {status_emoji}\n"
            f"Bot: `{instance_name}`\n"
            f"Pair: `{trading_pair}`\n"
            f"{self._format_pnl_info(pnl_info)}\n"
            f"{open_orders_info}\n"
            f"Status: {status}."
        )
        if stop_reason:
            message += f" ({stop_reason})"
        return await self._send_message(chat_id, message, dry_run=dry_run)

    def _format_pnl_info(self, pnl_data: Optional[Dict[str, Any]]) -> str:
        if not pnl_data:
            return "PnL: N/A"

        # Extract relevant PnL metrics and format them
        summary_data = pnl_data.get('performance', {}).get('summary', {})

        total_pnl = summary_data.get('final_net_pnl_quote', 'N/A') # Using final_net_pnl_quote as total PnL
        total_pnl_quote = summary_data.get('final_net_pnl_quote', 'N/A') # Using final_net_pnl_quote as total PnL (Quote)
        total_volume_quote = summary_data.get('total_volume_quote', 'N/A')
        total_fees_quote = summary_data.get('total_fees_quote', 'N/A')
        # Daily PnL metrics are not directly available in the summary, so we'll keep them as N/A or derive if possible
        pnl_daily_usd = 'N/A'
        pnl_daily_percent = 'N/A'

        formatted_pnl = (
            f"📊 *PnL Summary* 📊\n"
            f"  Total PnL: `{total_pnl}`\n"
            f"  Total PnL (Quote): `{total_pnl_quote}`\n"
            f"  Total Volume (Quote): `{total_volume_quote}`\n"
            f"  Total Fees (Quote): `{total_fees_quote}`\n"
            f"  Daily PnL (USD): `{pnl_daily_usd}`\n"
            f"  Daily PnL (%): `{pnl_daily_percent}`"
        )
        return formatted_pnl

    async def send_bot_not_found_alert(self, chat_id: str, instance_name: str, trading_pair: str, dry_run: bool = False):
        """Sends an alert when a bot is not found."""
        message = (
            f"⚠️ Bot Not Found! ⚠️\n"
            f"Bot: `{instance_name}`\n"
            f"Pair: `{trading_pair}`\n"
            f"Status: Not found on Hummingbot instance."
        )
        return await self._send_message(chat_id, message, dry_run=dry_run)

    async def send_error_message(self, chat_id: str, error_details: str, dry_run: bool = False):
        """Sends an error message."""
        message = f"❌ An error occurred: {error_details}"
        return await self._send_message(chat_id, message, dry_run=dry_run)

    async def send_trade_update(self, chat_id: str, instance_name: str, trading_pair: str, trade_type: str, price: float, amount: float, timestamp: str, dry_run: bool = False):
        """Sends a message for a new trade (buy/sell)."""
        trade_emoji = "🟢 BUY" if trade_type.lower() == "buy" else "🔴 SELL"
        message = (
            f"📈 New Trade Alert! 📉\n"
            f"Bot: `{instance_name}`\n"
            f"Pair: `{trading_pair}`\n"
            f"Type: `{trade_emoji}`\n"
            f"Price: `{price}`\n"
            f"Amount: `{amount}`\n"
            f"Time: `{timestamp}`"
        )
        return await self._send_message(chat_id, message, dry_run=dry_run)

async def send_restricted_button_message(self, chat_id: str, symbol: str, message_text: str, dry_run: bool = False):
    """Sends a message with an inline button to restrict a symbol."""
    keyboard = [[InlineKeyboardButton(f"Restrict {symbol}", callback_data=f"restrict_{symbol}")]]
    reply_markup = InlineKeyboardMarkup(keyboard).to_json()
    return await self._send_message(chat_id, message_text, reply_markup=reply_markup, dry_run=dry_run)


if __name__ == "__main__":
    messenger = TelegramMessenger()
    test_chat_id = messenger.TELEGRAM_CHAT_ID # Use the loaded test chat ID

    async def test_messages():
        print(f"Attempting to send simple test message to '{test_chat_id}'")
        await messenger.send_simple_message(test_chat_id, "Hello from the new `TelegramMessenger` class! This message has *bold* and _italic_ text. It also has `code`.")

        print(f"\nAttempting to send bot deployed confirmation to '{test_chat_id}'")
        await messenger.send_bot_deployed_confirmation(test_chat_id, "test_bot_X", "BTC-USDT", 150.0, 0.001, 0.002, 0.0005)

        print(f"\nAttempting to send bot status update (running) to '{test_chat_id}'")
        await messenger.send_bot_status_update(test_chat_id, "test_bot_Y", "ETH-USDT", "running", "PnL: 5.2 ETH", "Open Orders: 3")

        print(f"\nAttempting to send bot status update (stopped) to '{test_chat_id}'")
        await messenger.send_bot_status_update(test_chat_id, "test_bot_Z", "ADA-USDT", "stopped", stop_reason="Trade Completed")

        print(f"\nAttempting to send bot not found alert to '{test_chat_id}'")
        await messenger.send_bot_not_found_alert(test_chat_id, "non_existent_bot", "XRP-USDT")

        print(f"\nAttempting to send error message to '{test_chat_id}'")
        await messenger.send_error_message(test_chat_id, "Something went wrong with the API call.")

        print(f"\nAttempting to send trade update message to '{test_chat_id}'")
        await messenger.send_trade_update(test_chat_id, "test_bot_A", "SOL-USDT", "BUY", 150.25, 0.5, "2025-08-19 10:30:00")


    asyncio.run(test_messages())