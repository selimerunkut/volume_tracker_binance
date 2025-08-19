import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import sys
import os

# Add the parent directory to the sys.path to allow imports from the project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot_monitor import BotMonitor, TelegramNotifier
from hummingbot_integration import HummingbotManager # This will be mocked
from telegram_messenger import TelegramMessenger # Import TelegramMessenger for mocking
from trade_storage import TradeStorage

class TestBotMonitor(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Mock dependencies
        # Mock the time provider
        self.mock_time_provider = MagicMock()
        self.mock_time_provider.return_value = datetime(2025, 1, 1, 10, 0, 0) # Default initial time

        # Mock TelegramMessenger and its methods
        self.mock_telegram_messenger = AsyncMock(spec=TelegramMessenger)
        self.mock_telegram_messenger.send_simple_message = AsyncMock(side_effect=self._mock_send_message)
        self.mock_telegram_messenger.send_bot_status_update = AsyncMock(side_effect=self._mock_send_message)
        self.mock_telegram_messenger.send_bot_not_found_alert = AsyncMock(side_effect=self._mock_send_message)
        self.mock_telegram_messenger.send_error_message = AsyncMock(side_effect=self._mock_send_message)
        self.mock_telegram_messenger.TELEGRAM_CHAT_ID = "12345" # Mock the chat ID for new bot addition logic

        # Initialize TelegramNotifier with the mocked TelegramMessenger
        self.telegram_notifier = TelegramNotifier(self.mock_telegram_messenger)

        # Mock other dependencies
        self.mock_hummingbot_manager = AsyncMock(spec=HummingbotManager)
        self.mock_hummingbot_manager.get_all_bot_statuses = AsyncMock(return_value={"status": "success", "data": {}}) # Default: no active bots
        
        # Mock TradeStorage instance and its methods
        self.trade_storage = MagicMock(spec=TradeStorage)
        self.trade_storage.load_trades = MagicMock(side_effect=lambda: self._active_trades_data)
        self.trade_storage.save_trades = MagicMock(side_effect=lambda trades: self._mock_save_trades(trades))

        # Initialize BotMonitor with mocks
        self.bot_monitor = BotMonitor(
            hummingbot_manager=self.mock_hummingbot_manager,
            trade_storage=self.trade_storage,
            notifier=self.telegram_notifier,
            check_interval_seconds=1, # Short interval for testing
            time_provider=self.mock_time_provider # Pass the mocked time provider
        )

        # Internal state for mocks
        self._active_trades_data = []
        self._sent_messages = [] # Reset for each test
        self.mock_hummingbot_manager.reset_mock()
        self.mock_telegram_messenger.reset_mock() # Reset the messenger mock
        self.trade_storage.reset_mock()

    def _mock_save_trades(self, trades):
        self._active_trades_data = trades

    async def _mock_send_message(self, chat_id, *args, **kwargs):
        # This mock captures all messages sent via TelegramMessenger methods
        # Store the kwargs directly for assertion
        self._sent_messages.append({"chat_id": chat_id, "kwargs": kwargs})
        print(f"MOCK TELEGRAM: Chat ID: {chat_id}, Kwargs: {kwargs}") # For debugging tests

    async def test_no_active_trades(self):
        self._active_trades_data = []
        self._sent_messages = [] # Reset for each test
        self.mock_hummingbot_manager.reset_mock()
        self.mock_telegram_messenger.reset_mock() # Corrected: Use mock_telegram_messenger
        self.trade_storage.reset_mock() # Reset the entire trade_storage mock
        self.trade_storage.load_trades.return_value = [] # Explicitly set return value for this test
        self.mock_hummingbot_manager.get_all_bot_statuses.return_value = {"status": "success", "data": {}} # Ensure it returns the correct structure

        # Patch asyncio.sleep to raise CancelledError after one iteration
        with patch('asyncio.sleep', new=AsyncMock(side_effect=asyncio.CancelledError)):
            await self.bot_monitor.run()
            self.mock_hummingbot_manager.close_client.assert_called_once()
            self.mock_hummingbot_manager.get_all_bot_statuses.assert_called_once()
            self.trade_storage.load_trades.assert_called_once()
            self.trade_storage.save_trades.assert_called_once_with([]) # Assert save_trades is called with empty list
            self.mock_hummingbot_manager.get_bot_status.assert_not_called() # No bots to check status for
            self.assertEqual(len(self._sent_messages), 0)

    async def test_bot_running_periodic_update(self):
        trade_entry = {
            'instance_name': 'test_bot_1',
            'chat_id': '12345',
            'trading_pair': 'ETH-USDT'
        }
        self._active_trades_data = [trade_entry]

        # Mock bot status response for running bot (tuple format)
        self.mock_hummingbot_manager.get_bot_status.return_value = (True, {
            'status': 'success',
            'data': {
                'status': 'running',
                'general_logs': [
                    {'msg': 'PnL: 10.5 USDT, Open Orders: 2'},
                    {'msg': 'Bot started.'}
                ],
                'error_logs': [],
                'trading_pair': 'ETH-USDT', # Added for synchronization logic
                'order_amount_usd': 100, # Added for synchronization logic
                'trailing_stop_loss_delta': 0.001, # Added for synchronization logic
                'take_profit_delta': 0.002, # Added for synchronization logic
                'fixed_stop_loss_delta': 0.0005 # Added for synchronization logic
            }
        })

        # Mock get_all_bot_statuses to simulate the bot being active
        self.mock_hummingbot_manager.get_all_bot_statuses.return_value = {
            "status": "success",
            "data": {
                'test_bot_1': { # Changed to dictionary keyed by instance_name
                    'instance_name': 'test_bot_1',
                    'status': 'running',
                    'data': { # This 'data' key is crucial for the synchronization logic
                        'status': 'running',
                        'trading_pair': 'ETH-USDT',
                        'order_amount_usd': 100,
                        'trailing_stop_loss_delta': 0.001,
                        'take_profit_delta': 0.002,
                        'fixed_stop_loss_delta': 0.0005
                    }
                }
            }
        }
        self._active_trades_data = [] # Start with empty, synchronization should add it

        # Helper to run one cycle of the monitor loop
        async def run_one_cycle():
            with patch('asyncio.sleep', new=AsyncMock(side_effect=asyncio.CancelledError)):
                await self.bot_monitor.run()

        # Helper to run one cycle of the monitor loop
        async def run_one_cycle():
            with patch('asyncio.sleep', new=AsyncMock(side_effect=asyncio.CancelledError)):
                await self.bot_monitor.run()

        # Set initial time for the first run
        initial_time = datetime(2025, 1, 1, 10, 0, 0)
        self.mock_time_provider.return_value = initial_time

        # First run: should send message
        await run_one_cycle()
        self.mock_hummingbot_manager.get_bot_status.assert_called_once_with('test_bot_1')
        self.assertEqual(len(self._sent_messages), 1)
        self.assertEqual(self._sent_messages[0]['kwargs']['instance_name'], 'test_bot_1')
        self.assertEqual(self._sent_messages[0]['kwargs']['status'], 'running')
        self.assertEqual(self._sent_messages[0]['kwargs']['pnl_info'], 'PnL: 10.5 USDT')
        self.assertEqual(self._sent_messages[0]['kwargs']['open_orders_info'], 'Open Orders: 2')
        self.mock_hummingbot_manager.get_bot_status.reset_mock()
        self._sent_messages.clear()

        # Set time for second run (within 300 seconds from the time the last message was sent)
        time_for_second_run = initial_time + timedelta(seconds=100)
        self.mock_time_provider.return_value = time_for_second_run

        # Second run within 300 seconds: should NOT send message
        await run_one_cycle()
        self.mock_hummingbot_manager.get_bot_status.assert_called_once_with('test_bot_1')
        self.assertEqual(len(self._sent_messages), 0)
        self.mock_hummingbot_manager.get_bot_status.reset_mock()

        # Set time for third run (after 300 seconds from the time the last message was sent)
        time_for_third_run = initial_time + timedelta(seconds=301)
        self.mock_time_provider.return_value = time_for_third_run

        # Third run after 300 seconds: should send message again
        await run_one_cycle()
        self.mock_hummingbot_manager.get_bot_status.assert_called_once_with('test_bot_1')
        self.assertEqual(len(self._sent_messages), 1)
        self.assertEqual(self._sent_messages[0]['kwargs']['instance_name'], 'test_bot_1')
        self.assertEqual(self._sent_messages[0]['kwargs']['status'], 'running')

    async def test_bot_stopped_trade_completed(self):
        trade_entry = {
            'instance_name': 'test_bot_2',
            'chat_id': '12345',
            'trading_pair': 'BTC-USDT'
        }
        self._active_trades_data = [trade_entry]

        self.mock_hummingbot_manager.get_bot_status.return_value = (True, {
            'status': 'success',
            'data': {
                'status': 'stopped',
                'general_logs': [
                    {'msg': 'Fixed stop loss hit.'},
                    {'msg': 'Strategy started.'}
                ],
                'error_logs': []
            }
        })
        self.mock_hummingbot_manager.get_all_bot_statuses.return_value = {"status": "success", "data": {}} # Bot is stopped, so it's not in active bots list
        self._active_trades_data = [trade_entry] # Start with it in active_trades.json

        with patch('asyncio.sleep', new=AsyncMock(side_effect=asyncio.CancelledError)):
            await self.bot_monitor.run()
            self.mock_hummingbot_manager.stop_and_archive_bot.assert_called_once_with('test_bot_2')
            self.trade_storage.save_trades.assert_called_once_with([])
            self.assertEqual(len(self._sent_messages), 1)
            self.assertEqual(self._sent_messages[0]['kwargs']['instance_name'], 'test_bot_2')
            self.assertEqual(self._sent_messages[0]['kwargs']['status'], 'stopped')
            self.assertEqual(self._sent_messages[0]['kwargs']['stop_reason'], 'Removed from active trades')
            self.assertEqual(len(self._active_trades_data), 0) # Should be removed

    async def test_bot_stopped_manual_stop(self):
        trade_entry = {
            'instance_name': 'test_bot_3',
            'chat_id': '12345',
            'trading_pair': 'XRP-USDT'
        }
        self._active_trades_data = [trade_entry]

        self.mock_hummingbot_manager.get_bot_status.return_value = (True, {
            'status': 'success',
            'data': {
                'status': 'stopped',
                'general_logs': [
                    {'msg': 'Stopping the strategy...'},
                    {'msg': 'Bot started.'}
                ],
                'error_logs': []
            }
        })
        self.mock_hummingbot_manager.get_all_bot_statuses.return_value = {"status": "success", "data": {}} # Bot is stopped, so it's not in active bots list
        self._active_trades_data = [trade_entry]

        with patch('asyncio.sleep', new=AsyncMock(side_effect=asyncio.CancelledError)):
            await self.bot_monitor.run()
            self.mock_hummingbot_manager.stop_and_archive_bot.assert_called_once_with('test_bot_3')
            self.trade_storage.save_trades.assert_called_once_with([])
            self.assertEqual(len(self._sent_messages), 1)
            self.assertEqual(self._sent_messages[0]['kwargs']['instance_name'], 'test_bot_3')
            self.assertEqual(self._sent_messages[0]['kwargs']['status'], 'stopped')
            self.assertEqual(self._sent_messages[0]['kwargs']['stop_reason'], 'Removed from active trades')
            self.assertEqual(len(self._active_trades_data), 0)

    async def test_bot_stopped_error(self):
        trade_entry = {
            'instance_name': 'test_bot_4',
            'chat_id': '12345',
            'trading_pair': 'LTC-USDT'
        }
        self._active_trades_data = [trade_entry]

        self.mock_hummingbot_manager.get_bot_status.return_value = (True, {
            'status': 'success',
            'data': {
                'status': 'stopped',
                'general_logs': [],
                'error_logs': [
                    {'msg': 'An unhandled exception occurred: DivisionByZeroError.'}
                ]
            }
        })
        self.mock_hummingbot_manager.get_all_bot_statuses.return_value = {"status": "success", "data": {}} # Bot is stopped, so it's not in active bots list
        self._active_trades_data = [trade_entry]

        with patch('asyncio.sleep', new=AsyncMock(side_effect=asyncio.CancelledError)):
            await self.bot_monitor.run()
            self.mock_hummingbot_manager.stop_and_archive_bot.assert_called_once_with('test_bot_4')
            self.trade_storage.save_trades.assert_called_once_with([])
            self.assertEqual(len(self._sent_messages), 1)
            self.assertEqual(self._sent_messages[0]['kwargs']['instance_name'], 'test_bot_4')
            self.assertEqual(self._sent_messages[0]['kwargs']['status'], 'stopped')
            self.assertEqual(self._sent_messages[0]['kwargs']['stop_reason'], 'Removed from active trades')
            self.assertEqual(len(self._active_trades_data), 0)

    async def test_bot_not_found(self):
        trade_entry = {
            'instance_name': 'test_bot_5',
            'chat_id': '12345',
            'trading_pair': 'ADA-USDT'
        }
        self._active_trades_data = [trade_entry]

        self.mock_hummingbot_manager.get_bot_status.return_value = (True, {
            'status': 'success',
            'data': {
                'status': 'not_found',
                'general_logs': [],
                'error_logs': []
            }
        })
        self.mock_hummingbot_manager.get_all_bot_statuses.return_value = {"status": "success", "data": {}} # Bot is not found, so it's not in active bots list

        with patch('asyncio.sleep', new=AsyncMock(side_effect=asyncio.CancelledError)):
            await self.bot_monitor.run()
            self.mock_hummingbot_manager.stop_and_archive_bot.assert_called_once_with('test_bot_5') # Should archive if not found in active bots
            self.trade_storage.save_trades.assert_called_once_with([])
            self.assertEqual(len(self._sent_messages), 1)
            self.assertEqual(self._sent_messages[0]['kwargs']['instance_name'], 'test_bot_5')
            self.assertEqual(self._sent_messages[0]['kwargs']['status'], 'stopped')
            self.assertEqual(self._sent_messages[0]['kwargs']['stop_reason'], 'Removed from active trades')
            self.assertEqual(len(self._active_trades_data), 0)

    async def test_error_during_status_check(self):
        trade_entry = {
            'instance_name': 'test_bot_6',
            'chat_id': '12345',
            'trading_pair': 'SOL-USDT'
        }
        self._active_trades_data = [trade_entry]

        self.mock_hummingbot_manager.get_bot_status.side_effect = Exception("API connection error")
        self.mock_hummingbot_manager.get_all_bot_statuses.return_value = {
            "status": "success",
            "data": {
                'test_bot_6': { # Changed to dictionary keyed by instance_name
                    'instance_name': 'test_bot_6',
                    'status': 'running', # Assume it's running for synchronization
                    'data': {
                        'status': 'running',
                        'trading_pair': 'SOL-USDT',
                        'order_amount_usd': 600,
                        'trailing_stop_loss_delta': 0.001,
                        'take_profit_delta': 0.002,
                        'fixed_stop_loss_delta': 0.0005
                    }
                }
            }
        }
        self._active_trades_data = [trade_entry]

        with patch('asyncio.sleep', new=AsyncMock(side_effect=asyncio.CancelledError)):
            await self.bot_monitor.run()
            self.mock_hummingbot_manager.get_bot_status.assert_called_once_with('test_bot_6')
            self.assertEqual(len(self._sent_messages), 1) # Expect 1 message for error
            self.assertEqual(self._sent_messages[0]['kwargs']['message'], "Error checking status for bot 'test_bot_6': API connection error")
            self.assertEqual(self._sent_messages[0]['kwargs']['message_type'], "error")
            self.assertEqual(len(self._active_trades_data), 1) # Trade should not be removed

    async def test_missing_instance_name_in_trade(self):
        trade_entry = {
            'chat_id': '12345',
            'trading_pair': 'DOGE-USDT'
        }
        self._active_trades_data = [trade_entry]

        with patch('asyncio.sleep', new=AsyncMock(side_effect=asyncio.CancelledError)):
            await self.bot_monitor.run()
            self.mock_hummingbot_manager.get_bot_status.assert_not_called()
            self.assertEqual(len(self._sent_messages), 0)
            self.assertEqual(len(self._active_trades_data), 1) # Trade should not be removed

    async def test_synchronize_with_provided_data(self):
        instance_name = "buy_sell_trailing_stop_bot_SOL_USDC_3iy1c2h6"
        trading_pair = "SOL-USDC"
        chat_id = "12345" # Assuming a chat ID for the test

        # Simulate an existing active trade that matches the provided data
        trade_entry = {
            'instance_name': instance_name,
            'chat_id': chat_id,
            'trading_pair': trading_pair
        }
        self._active_trades_data = [trade_entry]

        # Mock get_all_bot_statuses to return the exact data provided by the user
        self.mock_hummingbot_manager.get_all_bot_statuses.return_value = {
            "status": "success",
            "data": {
                instance_name: {
                    "status": "stopped",
                    "performance": {},
                    "error_logs": [],
                    "general_logs": [
                        {"level_name": "INFO", "msg": "Placing initial MARKET BUY order...", "timestamp": 1755610487.0020397},
                        {"level_name": "INFO", "msg": "The BUY order ... has been filled...", "timestamp": 1755610487.3215637},
                        {"level_name": "INFO", "msg": "BUY order ... completely filled.", "timestamp": 1755610487.3350017}
                    ],
                    "recently_active": True,
                    "source": "docker"
                }
            }
        }

        # Patch asyncio.sleep to raise CancelledError after one iteration
        with patch('asyncio.sleep', new=AsyncMock(side_effect=asyncio.CancelledError)):
            await self.bot_monitor.run()

            # Assertions
            # The bot should be removed from active trades and archived
            self.mock_hummingbot_manager.stop_and_archive_bot.assert_called_once_with(instance_name)
            self.trade_storage.save_trades.assert_called_once_with([])
            self.assertEqual(len(self._sent_messages), 1)
            self.assertEqual(self._sent_messages[0]['kwargs']['instance_name'], instance_name)
            self.assertEqual(self._sent_messages[0]['kwargs']['status'], 'stopped')
            self.assertEqual(self._sent_messages[0]['kwargs']['stop_reason'], 'Removed from active trades')
            self.assertEqual(len(self._active_trades_data), 0) # Should be removed

if __name__ == '__main__':
    unittest.main()