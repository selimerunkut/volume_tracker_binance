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
from datetime import datetime
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional, Callable

from telegram_messenger import TelegramMessenger
from hummingbot_integration import HummingbotManager
from trade_storage import TradeStorage
from bot_status_handler import BotStatusHandler
from log_processor import LogProcessor
from telegram_notifier import TelegramNotifier

load_dotenv()


class BotMonitor:
    """
    Monitors Hummingbot instances, checks their status, and sends notifications.
    Adheres to S.O.L.I.D. principles by delegating responsibilities.
    """
    def __init__(self,
                 hummingbot_manager: HummingbotManager,
                 trade_storage: TradeStorage,
                 notifier: TelegramNotifier,
                 bot_status_handler: BotStatusHandler,
                 log_processor: LogProcessor,
                 check_interval_seconds: int = 10,
                 time_provider: Callable[[], datetime] = datetime.now):
        self._hummingbot_manager = hummingbot_manager
        self._trade_storage = trade_storage
        self._notifier = notifier
        self._bot_status_handler = bot_status_handler
        self._log_processor = log_processor
        self._check_interval_seconds = check_interval_seconds
        self._time_provider = time_provider

    async def _synchronize_active_trades(self) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Synchronizes the local active_trades.json with the actual running bots from Hummingbot API.
        Returns the updated list of active trades and the bot status data.
        """
        # 1. Get all currently running bots from Hummingbot API
        # The get_all_bot_statuses method returns a dictionary with 'status' and 'data' keys.
        # We need to extract the list of bot statuses from the 'data' key.
        all_bot_statuses_response = await self._hummingbot_manager.get_all_bot_statuses()
        # The 'data' key contains a dictionary where keys are instance names and values are bot status dictionaries.
        # We need to iterate over the values of this dictionary.
        print(f"DEBUG: _synchronize_active_trades - all_bot_statuses_response: {all_bot_statuses_response}")
        all_bot_statuses_data = all_bot_statuses_response.get('data', {})
        print(f"DEBUG: _synchronize_active_trades - all_bot_statuses_data: {all_bot_statuses_data}")
        # The instance_name is the KEY in the data dictionary, not a field in each bot status
        # Only consider bots that are currently 'running' for synchronization
        running_bot_names = {
            name for name, details in all_bot_statuses_data.items()
            if details.get('status') == 'running'
        }
        print(f"DEBUG: _synchronize_active_trades - running_bot_names: {running_bot_names}")
        running_bot_details = all_bot_statuses_data  # The data dict already maps instance_name -> bot_status
        print(f"DEBUG: _synchronize_active_trades - running_bot_details: {running_bot_details}")

        # 2. Load existing active trades from local storage
        active_trades = self._trade_storage.load_trades()
        print(f"DEBUG: _synchronize_active_trades - active_trades (before adding): {active_trades}")
        active_trade_names = {trade.get('instance_name') for trade in active_trades if trade.get('instance_name')}
        print(f"DEBUG: _synchronize_active_trades - active_trade_names: {active_trade_names}")

        # 3. Identify and add newly started bots to local storage
        bots_to_add = running_bot_names - active_trade_names
        for instance_name in bots_to_add:
            print(f"New bot '{instance_name}' detected. Fetching full details and adding to active trades.")
            
            # Make a targeted API call to get full bot details including configuration
            success, full_bot_details_response = await self._hummingbot_manager.get_bot_status(instance_name)
            
            if success and full_bot_details_response:
                # Extract details from the full response
                # Assuming these details are directly under the bot's main status object
                trading_pair = full_bot_details_response.get('trading_pair', 'UNKNOWN')
                order_amount_usd = full_bot_details_response.get('order_amount_usd', 0)
                trailing_stop_loss_delta = full_bot_details_response.get('trailing_stop_loss_delta', 0)
                take_profit_delta = full_bot_details_response.get('take_profit_delta', 0)
                fixed_stop_loss_delta = full_bot_details_response.get('fixed_stop_loss_delta', 0)

                new_trade_data = {
                    "instance_name": instance_name,
                    "chat_id": self._notifier._messenger.TELEGRAM_CHAT_ID,
                    "trading_pair": trading_pair,
                    "order_amount_usd": order_amount_usd,
                    "trailing_stop_loss_delta": trailing_stop_loss_delta,
                    "take_profit_delta": take_profit_delta,
                    "fixed_stop_loss_delta": fixed_stop_loss_delta
                }
            else:
                print(f"WARNING: Could not fetch full details for new bot '{instance_name}'. Adding with default values.")
                new_trade_data = {
                    "instance_name": instance_name,
                    "chat_id": self._notifier._messenger.TELEGRAM_CHAT_ID,
                    "trading_pair": 'UNKNOWN',
                    "order_amount_usd": 0,
                    "trailing_stop_loss_delta": 0,
                    "take_profit_delta": 0,
                    "fixed_stop_loss_delta": 0
                }
            active_trades.append(new_trade_data) # Add to the in-memory list
            print(f"DEBUG: _synchronize_active_trades - Added new_trade_data: {new_trade_data}")
            print(f"DEBUG: _synchronize_active_trades - active_trades (after adding): {active_trades}")
            # Optionally, send a notification that a new bot started

        # Save the updated list back to storage
        self._trade_storage.save_trades(active_trades)

        # Return the updated list of active trades AND the bot status data with logs
        print(f"DEBUG: _synchronize_active_trades - Returning active_trades: {active_trades}")
        return active_trades, all_bot_statuses_data

    async def _process_active_trades(self, active_trades: List[Dict[str, Any]], bot_statuses_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Processes each active trade, handles notifications, and archives completed bots.
        Returns a new list containing only the trades that should remain active.
        """
        trades_to_keep = []
        print(f"DEBUG: Entering _process_active_trades with {len(active_trades)} active trades.")
        for trade in active_trades:
            instance_name = trade.get('instance_name')
            chat_id = trade.get('chat_id')
            if not instance_name:
                print(f"DEBUG: Skipping trade with missing instance_name: {trade}")
                continue

            try:
                status_response_data = bot_statuses_data.get(instance_name, {})
                print(f"DEBUG: Full status_response_data structure for {instance_name}: {status_response_data}")
                
                general_logs = status_response_data.get('general_logs', [])
                error_logs = status_response_data.get('error_logs', [])
                bot_actual_status = status_response_data.get('status')

                print(f"Bot '{instance_name}' actual status: {bot_actual_status}")
                print(f"DEBUG: general_logs length: {len(general_logs)}")

                await self._log_processor.parse_trade_logs_and_notify(chat_id, instance_name, general_logs)

                print(f"DEBUG: Bot '{instance_name}' status is '{bot_actual_status}'.")

                if bot_actual_status == "running":
                    print(f"DEBUG: Calling handle_running_bot for {instance_name}")
                    await self._bot_status_handler.handle_running_bot(trade, instance_name, status_response_data)
                    trades_to_keep.append(trade)
                elif bot_actual_status == "stopped":
                    stop_reason = await self._log_processor.determine_stop_reason(general_logs, error_logs)
                    if stop_reason == "Trade Completed":
                        print(f"DEBUG: Bot '{instance_name}' stopped due to 'Trade Completed'. Archiving and removing.")
                        await self._hummingbot_manager.stop_and_archive_bot(instance_name)
                        self._trade_storage.remove_trade_entry(instance_name)
                        print(f"DEBUG: Calling handle_stopped_bot for {instance_name} (Trade Completed)")
                        await self._bot_status_handler.handle_stopped_bot(trade, instance_name, status_response_data)
                    else:
                        print(f"DEBUG: Bot '{instance_name}' stopped for reason: '{stop_reason}'. Keeping in active trades for monitoring.")
                        print(f"DEBUG: Calling handle_stopped_bot for {instance_name} (Not Trade Completed)")
                        await self._bot_status_handler.handle_stopped_bot(trade, instance_name, status_response_data)
                        trades_to_keep.append(trade)
                elif bot_actual_status == "success":
                    print(f"DEBUG: Bot '{instance_name}' status is 'success' - checking for trade completion.")
                    stop_reason = await self._log_processor.determine_stop_reason(general_logs, error_logs)
                    if stop_reason == "Trade Completed":
                        print(f"DEBUG: Bot '{instance_name}' completed successfully with trades. Archiving and removing.")
                        await self._hummingbot_manager.stop_and_archive_bot(instance_name)
                        self._trade_storage.remove_trade_entry(instance_name)
                        print(f"DEBUG: Calling handle_stopped_bot for {instance_name} (Success with Trade Completed)")
                        await self._bot_status_handler.handle_stopped_bot(trade, instance_name, status_response_data)
                    else:
                        print(f"DEBUG: Bot '{instance_name}' has 'success' status but no 'Trade Completed' log. Keeping for now.")
                        trades_to_keep.append(trade)
                elif bot_actual_status == "not_found":
                    print(f"DEBUG: Bot '{instance_name}' not found. Archiving and removing.")
                    await self._hummingbot_manager.stop_and_archive_bot(instance_name)
                    self._trade_storage.remove_trade_entry(instance_name)
                    print(f"DEBUG: Calling handle_not_found_bot for {instance_name}")
                    await self._bot_status_handler.handle_not_found_bot(trade, instance_name)
                else:
                    print(f"DEBUG: Unknown bot status for '{instance_name}': {bot_actual_status}. Keeping in active trades.")
                    trades_to_keep.append(trade)

            except Exception as e:
                error_message = f"Error checking status for bot '{instance_name}': {e}"
                print(error_message)
                await self._notifier.notify(
                    chat_id,
                    message=error_message,
                    message_type="error"
                )
                trades_to_keep.append(trade)

        return trades_to_keep

    async def run(self):
        """Runs the main monitoring loop."""
        print("Hummingbot Bot Monitor started...")
        try:
            while True:
                print(f"[{self._time_provider()}] Checking active bots...")

                active_trades, bot_statuses_data = await self._synchronize_active_trades()

                if not active_trades:
                    print("No active trades found after synchronization.")
                else:
                    active_trades = await self._process_active_trades(active_trades, bot_statuses_data)
                    self._trade_storage.save_trades(active_trades)

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
    notifier_instance = TelegramNotifier(TelegramMessenger())
    log_processor_instance = LogProcessor(notifier=notifier_instance)
    
    bot_status_handler_instance = BotStatusHandler(
        notifier=notifier_instance,
        hummingbot_manager=hummingbot_manager,
        log_processor=log_processor_instance,
        time_provider=datetime.now
    )

    monitor = BotMonitor(
        hummingbot_manager=hummingbot_manager,
        trade_storage=trade_storage_instance,
        notifier=notifier_instance,
        bot_status_handler=bot_status_handler_instance,
        log_processor=log_processor_instance,
        time_provider=datetime.now
    )
    await monitor.run()

if __name__ == '__main__':
    try:
        asyncio.run(main_entry_point())
    except KeyboardInterrupt:
        print("Bot Monitor stopped by user via KeyboardInterrupt.")
    except Exception as e:
        print(f"An unexpected error occurred during main execution: {e}")