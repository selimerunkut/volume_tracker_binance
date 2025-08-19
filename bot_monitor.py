"""
bot_monitor.py

This script serves as the main executable for the Hummingbot monitoring service.
It is designed to be run as a standalone process (e.g., via a cron job, systemd service, or Docker entrypoint)
rather than being imported as a module by other Python scripts.

Its primary function is to continuously monitor Hummingbot instances, check their operational status,
and send real-time notifications and alerts via Telegram based on predefined conditions.

The internal structure of this script has been refactored to adhere to S.O.L.I.D., DRY, KISS, YAGNI,
Convention over Configuration, Composition over Inheritance, and Law of Demeter principles,
improving modularity, maintainability, and testability.
"""
import asyncio
import os
import re
import json
from datetime import datetime
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional, Callable # Added Callable

# Assuming telegram_alerts.py is in the same directory or accessible via PYTHONPATH
from telegram_messenger import TelegramMessenger # Import TelegramMessenger
from hummingbot_integration import HummingbotManager
from trade_storage import TradeStorage

# Load environment variables from .env file
load_dotenv()

class TelegramNotifier:
    """Handles sending messages to Telegram."""
    def __init__(self, messenger: TelegramMessenger):
        self._messenger = messenger

    async def notify(self, chat_id: str, message_type: str, message: Optional[str] = None, **kwargs):
        """Sends a message to the specified Telegram chat ID based on message type."""
        if message_type == "simple":
            await self._messenger.send_simple_message(chat_id, message)
        elif message_type == "bot_status_update":
            await self._messenger.send_bot_status_update(chat_id, **kwargs)
        elif message_type == "bot_not_found_alert":
            await self._messenger.send_bot_not_found_alert(chat_id, **kwargs)
        elif message_type == "error":
            await self._messenger.send_error_message(chat_id, message)
        else:
            print(f"[{datetime.datetime.now()}] Unknown message type: {message_type}. Sending as simple message.")
            await self._messenger.send_simple_message(chat_id, message)


class BotMonitor:
    """
    Monitors Hummingbot instances, checks their status, and sends notifications.
    Adheres to S.O.L.I.D. principles by delegating responsibilities.
    """
    def __init__(self,
                 hummingbot_manager: HummingbotManager,
                 trade_storage: TradeStorage,
                 notifier: TelegramNotifier,
                 check_interval_seconds: int = 60,
                 time_provider: Callable[[], datetime] = datetime.now): # Added time_provider
        self._hummingbot_manager = hummingbot_manager
        self._trade_storage = trade_storage
        self._notifier = notifier
        self._check_interval_seconds = check_interval_seconds
        self._time_provider = time_provider # Store the time provider
        self._last_active_message_time: Dict[str, datetime] = {}

    async def _parse_bot_logs_for_info(self, general_logs: List[Dict[str, Any]]) -> Dict[str, str]:
        """Parses general logs for PnL and Open Orders information."""
        pnl_info = "PnL: N/A"
        open_orders_info = "Open Orders: N/A"

        for log_entry in reversed(general_logs):
            msg = log_entry.get('msg', '')
            pnl_match = re.search(r"PnL: ([\d\.\-]+ [A-Z]+)", msg)
            open_orders_match = re.search(r"Open Orders: (\d+)", msg)

            if pnl_match:
                pnl_info = f"PnL: {pnl_match.group(1)}"
            if open_orders_match:
                open_orders_info = f"Open Orders: {open_orders_match.group(1)}"

            if pnl_match and open_orders_match:
                break
        return {"pnl_info": pnl_info, "open_orders_info": open_orders_info}

    async def _determine_stop_reason(self, general_logs: List[Dict[str, Any]], error_logs: List[Dict[str, Any]]) -> str:
        """Determines the reason for a bot stopping based on logs."""
        stop_reason = "Unknown Reason"
        for log_entry in reversed(general_logs):
            msg = log_entry.get('msg', '').lower()
            if "fixed stop loss hit" in msg or "take profit hit" in msg or "all positions closed" in msg:
                stop_reason = "Trade Completed"
                break
            elif "stopping the strategy" in msg:
                stop_reason = "Manual Stop/Strategy Stopped"
                break

        if error_logs and stop_reason == "Unknown Reason":
            for log_entry in reversed(error_logs):
                msg = log_entry.get('msg', '').lower()
                if "error" in msg or "exception" in msg:
                    stop_reason = f"Error: {msg[:100]}..."
                    break
        return stop_reason

    async def _handle_stopped_bot(self, trade: Dict[str, Any], instance_name: str, status_response: Dict[str, Any]):
        """Handles a stopped bot and sends a notification. Archiving is handled by _synchronize_active_trades."""
        chat_id = trade.get('chat_id')
        trading_pair = trade.get('trading_pair')
        general_logs = status_response.get('data', {}).get('general_logs', [])
        error_logs = status_response.get('data', {}).get('error_logs', [])

        print(f"Bot '{instance_name}' has stopped. Notifying...")
        # Archiving and removal from active_trades.json is now handled by _synchronize_active_trades
        # await self._hummingbot_manager.stop_and_archive_bot(instance_name) # Removed
        # print(f"Bot '{instance_name}' stopped and archived.") # Removed

        stop_reason = await self._determine_stop_reason(general_logs, error_logs)
        message = (
            f"🔔 Bot Status Update 🔔\n"
            f"Bot: `{instance_name}`\n"
            f"Pair: `{trading_pair}`\n"
            f"Status: Stopped ({stop_reason})."
        )
        await self._notifier.notify(
            chat_id,
            message_type="bot_status_update",
            instance_name=instance_name,
            trading_pair=trading_pair,
            status="stopped",
            stop_reason=stop_reason
        )
        self._last_active_message_time.pop(instance_name, None)

    async def _handle_running_bot(self, trade: Dict[str, Any], instance_name: str, status_response: Dict[str, Any]):
        """Handles a running bot and sends periodic updates."""
        chat_id = trade.get('chat_id')
        trading_pair = trade.get('trading_pair')
        general_logs = status_response.get('data', {}).get('general_logs', [])

        current_time = self._time_provider() # Use the injected time provider
        last_sent = self._last_active_message_time.get(instance_name)

        if not last_sent or (current_time - last_sent).total_seconds() >= 300:
            log_info = await self._parse_bot_logs_for_info(general_logs)
            message = (
                f"🟢 Bot is Active 🟢\n"
                f"Bot: `{instance_name}`\n"
                f"Pair: `{trading_pair}`\n"
                f"{log_info['pnl_info']}\n"
                f"{log_info['open_orders_info']}\n"
                f"Status: Running."
            )
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

    async def _handle_not_found_bot(self, trade: Dict[str, Any], instance_name: str):
        """Handles a bot not found on the Hummingbot instance. Archiving is handled by _synchronize_active_trades."""
        chat_id = trade.get('chat_id')
        trading_pair = trade.get('trading_pair')

        print(f"Bot '{instance_name}' not found on Hummingbot instance.")
        # Archiving and removal from active_trades.json is now handled by _synchronize_active_trades
        # # self._trade_storage.remove_trade(instance_name) # Removed
        message = (
            f"⚠️ Bot Not Found! ⚠️\n"
            f"Bot: `{instance_name}`\n"
            f"Pair: `{trading_pair}`\n"
            f"Status: Not found on Hummingbot instance."
        )
        await self._notifier.notify(
            chat_id,
            message_type="bot_not_found_alert",
            instance_name=instance_name,
            trading_pair=trading_pair
        )
        self._last_active_message_time.pop(instance_name, None)

    async def _synchronize_active_trades(self) -> List[Dict[str, Any]]:
        """
        Synchronizes the local active_trades.json with the actual running bots from Hummingbot API.
        Returns the updated list of active trades.
        """
        # 1. Get all currently running bots from Hummingbot API
        # The get_all_bot_statuses method returns a dictionary with 'status' and 'data' keys.
        # We need to extract the list of bot statuses from the 'data' key.
        all_bot_statuses_response = await self._hummingbot_manager.get_all_bot_statuses()
        # The 'data' key contains a dictionary where keys are instance names and values are bot status dictionaries.
        # We need to iterate over the values of this dictionary.
        all_bot_statuses_data = all_bot_statuses_response.get('data', {})
        all_bot_statuses = list(all_bot_statuses_data.values())
        running_bot_names = {bot_status.get('instance_name') for bot_status in all_bot_statuses if bot_status.get('instance_name')}
        running_bot_details = {bot_status.get('instance_name'): bot_status for bot_status in all_bot_statuses if bot_status.get('instance_name')}

        # 2. Load existing active trades from local storage
        active_trades = self._trade_storage.load_trades()
        active_trade_names = {trade.get('instance_name') for trade in active_trades if trade.get('instance_name')}

        # 3. Identify and remove stopped/non-existent bots from local storage
        bots_to_remove = active_trade_names - running_bot_names
        # Create a new list for trades that should remain active
        updated_active_trades = []
        for trade in active_trades:
            instance_name = trade.get('instance_name')
            if instance_name in bots_to_remove:
                print(f"Bot '{instance_name}' is no longer running or not found. Removing from active trades.")
                # Retrieve the full trade object for notification
                original_trade_data = next((t for t in active_trades if t.get('instance_name') == instance_name), None)
                if original_trade_data:
                    # Archive the bot
                    await self._hummingbot_manager.stop_and_archive_bot(instance_name)
                    
                    # Send notification for stopped/not-found bot
                    message = (
                        f"🔔 Bot Status Update 🔔\n"
                        f"Bot: `{instance_name}`\n"
                        f"Pair: `{original_trade_data.get('trading_pair', 'UNKNOWN')}`\n"
                        f"Status: Stopped (Removed from active trades)." # Simplified reason
                    )
                    await self._notifier.notify(
                        original_trade_data.get('chat_id'),
                        message_type="bot_status_update",
                        instance_name=instance_name,
                        trading_pair=original_trade_data.get('trading_pair', 'UNKNOWN'),
                        status="stopped",
                        stop_reason="Removed from active trades"
                    )
                    self._last_active_message_time.pop(instance_name, None)
            else:
                updated_active_trades.append(trade)

        # 4. Identify and add newly started bots to local storage
        bots_to_add = running_bot_names - active_trade_names
        for instance_name in bots_to_add:
            print(f"New bot '{instance_name}' detected. Adding to active trades.")
            bot_detail = running_bot_details.get(instance_name, {})
            # Extract relevant trade data from bot_detail
            # This assumes the 'data' key exists and contains the necessary info
            trade_data_from_api = bot_detail.get('data', {})
            new_trade_data = {
                "instance_name": instance_name,
                "chat_id": self._notifier._messenger.TELEGRAM_CHAT_ID, # Use the chat ID from the messenger
                "trading_pair": trade_data_from_api.get('trading_pair', 'UNKNOWN'),
                "order_amount_usd": trade_data_from_api.get('order_amount_usd', 0),
                "trailing_stop_loss_delta": trade_data_from_api.get('trailing_stop_loss_delta', 0),
                "take_profit_delta": trade_data_from_api.get('take_profit_delta', 0),
                "fixed_stop_loss_delta": trade_data_from_api.get('fixed_stop_loss_delta', 0)
            }
            updated_active_trades.append(new_trade_data) # Add to the in-memory list
            # Optionally, send a notification that a new bot started

        # Save the fully synchronized list back to storage
        self._trade_storage.save_trades(updated_active_trades)

        # Return the updated list of active trades
        return updated_active_trades

    async def _process_active_trades(self, active_trades: List[Dict[str, Any]]):
        """
        Processes each active trade by checking its status and handling accordingly.
        """
        for trade in active_trades:
            instance_name = trade.get('instance_name')
            if not instance_name:
                print(f"Skipping trade with missing instance_name: {trade}")
                continue

            try:
                success, status_response_data = await self._hummingbot_manager.get_bot_status(instance_name)
                if not success:
                    print(f"Failed to get status for bot '{instance_name}': {status_response_data.get('error', 'Unknown error')}")
                    continue

                bot_actual_status = status_response_data.get('data', {}).get('status')
                print(f"Bot '{instance_name}' actual status: {bot_actual_status}")

                if bot_actual_status == "stopped":
                    # Notification for stopped bot is now handled by _synchronize_active_trades
                    # if it was removed from the active_trades list.
                    # This branch would only be hit if a bot stopped *after* synchronization
                    # but before the next cycle, and was still in the active_trades list.
                    # In this case, we still want to notify.
                    await self._handle_stopped_bot(trade, instance_name, status_response_data)
                elif bot_actual_status == "running":
                    await self._handle_running_bot(trade, instance_name, status_response_data)
                elif bot_actual_status == "not_found":
                    # Notification for not found bot is now handled by _synchronize_active_trades
                    # if it was removed from the active_trades list.
                    # Similar to stopped bots, this branch handles cases where it's still in the list.
                    await self._handle_not_found_bot(trade, instance_name)
                else:
                    print(f"Unknown bot status for '{instance_name}': {bot_actual_status}")

            except Exception as e:
                error_message = f"Error checking status for bot '{instance_name}': {e}"
                print(error_message)
                # Send an error alert to the chat_id
                await self._notifier.notify(
                    trade.get('chat_id'),
                    message=error_message,
                    message_type="error"
                )

    async def run(self):
        """Runs the main monitoring loop."""
        print("Hummingbot Bot Monitor started...")
        try:
            while True:
                print(f"[{self._time_provider()}] Checking active bots...")

                active_trades = await self._synchronize_active_trades()

                if not active_trades:
                    print("No active trades found after synchronization.")
                else:
                    await self._process_active_trades(active_trades)

                await asyncio.sleep(self._check_interval_seconds)
        except asyncio.CancelledError:
            print("Bot Monitor task cancelled.")
        except Exception as e:
            print(f"An error occurred in the bot monitor: {e}")
        finally:
            print("Closing Hummingbot API client session...")
            await self._hummingbot_manager.close_client()
            print("Bot Monitor stopped.")

async def main_entry_point():
    """Entry point for the bot monitor application."""
    hummingbot_api_url = os.getenv("HUMMINGBOT_API_URL", "http://localhost:8000")
    hummingbot_api_username = os.getenv("USERNAME")
    hummingbot_api_password = os.getenv("PASSWORD")

    if not all([hummingbot_api_url, hummingbot_api_username, hummingbot_api_password]):
        print("Error: Missing Hummingbot API credentials in .env file.")
        return

    hummingbot_manager = HummingbotManager(
        api_base_url=hummingbot_api_url,
        api_username=hummingbot_api_username,
        api_password=hummingbot_api_password
    )
    await hummingbot_manager.initialize_client()

    trade_storage_instance = TradeStorage()
    notifier_instance = TelegramNotifier(TelegramMessenger()) # Pass an instance of TelegramMessenger
    # Ensure the notifier uses the correct chat ID for its operations
    # This might require modifying TelegramNotifier or send_telegram_message if they don't already use a global/injected chat ID.
    # For now, assuming send_telegram_message handles it based on the chat_id passed to notify.

    monitor = BotMonitor(
        hummingbot_manager=hummingbot_manager,
        trade_storage=trade_storage_instance,
        notifier=notifier_instance,
        time_provider=datetime.now # Pass the default time provider
    )
    await monitor.run()

if __name__ == '__main__':
    try:
        asyncio.run(main_entry_point())
    except KeyboardInterrupt:
        print("Bot Monitor stopped by user via KeyboardInterrupt.")
    except Exception as e:
        print(f"An unexpected error occurred during main execution: {e}")