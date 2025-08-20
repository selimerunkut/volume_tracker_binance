import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, call

# Add the parent directory to the sys.path to allow imports from the project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from bot_monitor import BotMonitor, TelegramNotifier
from telegram_messenger import TelegramMessenger
from trade_storage import TradeStorage # Import TradeStorage for mocking

async def simulate_premature_archiving_scenario():
    print("Starting premature archiving simulation...")

    # Mock TelegramMessenger and its methods
    mock_telegram_messenger = AsyncMock(spec=TelegramMessenger)
    mock_telegram_messenger.send_trade_update = AsyncMock()
    mock_telegram_messenger.send_bot_status_update = AsyncMock() # Also mock status updates
    mock_telegram_messenger.TELEGRAM_CHAT_ID = "12345"

    telegram_notifier = TelegramNotifier(mock_telegram_messenger)

    # Mock HummingbotManager
    mock_hummingbot_manager = AsyncMock()
    mock_hummingbot_manager.stop_and_archive_bot = AsyncMock() # Crucial for checking archiving
    mock_hummingbot_manager.get_bot_status = AsyncMock() # Mock get_bot_status for _process_active_trades

    # Mock TradeStorage
    trade_storage = MagicMock(spec=TradeStorage)
    trade_storage.load_trades.return_value = [] # Start with no active trades
    trade_storage.save_trades.return_value = None
    trade_storage.add_trade_entry = MagicMock()
    trade_storage.remove_trade_entry = MagicMock()

    # Initialize BotMonitor with mocks
    bot_monitor = BotMonitor(
        hummingbot_manager=mock_hummingbot_manager,
        trade_storage=trade_storage,
        notifier=telegram_notifier,
        check_interval_seconds=1,
        time_provider=None
    )

    instance_name_bought = "buy_sell_trailing_stop_bot_SOL_USDC_fh66bcqz"
    instance_name_no_buy = "buy_sell_trailing_stop_bot_BTC_USDC_ucha4sat"
    instance_name_completed = "buy_sell_trailing_stop_bot_XRP_USDC_completed"
    chat_id = "12345"

    # --- Scenario: Multiple bots running simultaneously ---
    print(f"\n--- Simulating Multiple Bots Scenario: All 3 bots running with different states ---")

    # Step 1: Simulate initial detection of multiple running bots
    mock_hummingbot_manager.get_all_bot_statuses.return_value = {
        "status": "success",
        "data": {
            instance_name_bought: {
                "status": "running",
                "performance": {},
                "error_logs": [],
                "general_logs": [
                    {"level_name": "INFO", "msg": "Starting Node <hbot.buy_sell_trailing_stop_bot_SOL_USDC_fh66bcqz>", "timestamp": 1755714510.1056917, "level_no": 20, "logger_name": "hummingbot.remote_iface.mqtt"},
                ],
                "recently_active": True,
                "source": "docker"
            },
            instance_name_no_buy: {
                "status": "running",
                "performance": {},
                "error_logs": [],
                "general_logs": [
                    {"level_name": "INFO", "msg": "Starting Node <hbot.buy_sell_trailing_stop_bot_BTC_USDC_ucha4sat>", "timestamp": 1755714961.2302234, "level_no": 20, "logger_name": "hummingbot.remote_iface.mqtt"},
                ],
                "recently_active": True,
                "source": "docker"
            },
            instance_name_completed: {
                "status": "running",
                "performance": {},
                "error_logs": [],
                "general_logs": [
                    {"level_name": "INFO", "msg": "Starting Node <hbot.buy_sell_trailing_stop_bot_XRP_USDC_completed>", "timestamp": 1755714510.1056917, "level_no": 20, "logger_name": "hummingbot.remote_iface.mqtt"},
                ],
                "recently_active": True,
                "source": "docker"
            }
        }
    }
    # Simulate active_trades.json being empty initially, then updated by synchronize
    trade_storage.load_trades.return_value = []
    active_trades_after_sync, bot_statuses_data = await bot_monitor._synchronize_active_trades()
    trade_storage.save_trades.assert_called_once_with(active_trades_after_sync)
    trade_storage.save_trades.reset_mock() # Reset save_trades mock

    print(f"  3 bots detected and added to active trades: {len(active_trades_after_sync)}")

    # Step 2: Simulate different final states for each bot
    # Update the bot statuses to show their final states
    bot_statuses_data_final = {
        instance_name_bought: {
            "status": "stopped",
            "performance": {},
            "error_logs": [],
            "general_logs": [
                {"level_name": "INFO", "msg": "Placing initial MARKET BUY order x-MG43PCSNBSLUC63cd023dfd6a99293 for 0.0328 SOL-USDC.", "timestamp": 1755714513.0009255, "level_no": 20, "logger_name": "hummingbot.strategy.script_strategy_base"},
                {"level_name": "INFO", "msg": "The BUY order x-MG43PCSNBSLUC63cd023dfd6a99293 amounting to 0.03200000/0.03200000 SOL has been filled at 183.05000000 USDC.", "timestamp": 1755714513.2909431, "level_no": 20, "logger_name": "hummingbot.connector.client_order_tracker"},
                {"level_name": "INFO", "msg": "Buy order x-MG43PCSNBSLUC63cd023dfd6a99293 filled. Entry price: 183.0500.", "timestamp": 1755714513.2916992, "level_no": 20, "logger_name": "hummingbot.strategy.script_strategy_base"},
                {"level_name": "INFO", "msg": "BUY order x-MG43PCSNBSLUC63cd023dfd6a99293 completely filled.", "timestamp": 1755714513.316238, "level_no": 20, "logger_name": "hummingbot.connector.client_order_tracker"}
            ],
            "recently_active": True,
            "source": "docker"
        },
        instance_name_no_buy: {
            "status": "stopped",
            "performance": {},
            "error_logs": [],
            "general_logs": [
                {"level_name": "WARNING", "msg": "binance is not ready. Please wait...", "timestamp": 1755714962.003179, "level_no": 30, "logger_name": "hummingbot.strategy.script_strategy_base"}
            ],
            "recently_active": True,
            "source": "docker"
        },
        instance_name_completed: {
            "status": "success",
            "performance": {},
            "error_logs": [],
            "general_logs": [
                {"level_name": "INFO", "msg": "The BUY order x-BUY123 amounting to 0.03200000/0.03200000 XRP has been filled at 0.60000000 USDC.", "timestamp": 1755617440.317745, "level_no": 20, "logger_name": "hummingbot.connector.client_order_tracker"},
                {"level_name": "INFO", "msg": "The SELL order x-COMPLETED amounting to 0.03200000/0.03200000 XRP has been filled at 0.65000000 USDC.", "timestamp": 1755617442.317745, "level_no": 20, "logger_name": "hummingbot.connector.client_order_tracker"},
                {"level_name": "INFO", "msg": "Sell order x-COMPLETED fully filled. Position closed for original buy order x-BUY123.", "timestamp": 1755617442.317745, "level_no": 20, "logger_name": "hummingbot.strategy.script_strategy_base"},
                {"level_name": "INFO", "msg": "All positions closed. Stopping the strategy.", "timestamp": 1755617442.318000, "level_no": 20, "logger_name": "hummingbot.strategy.script_strategy_base"}
            ],
            "recently_active": True,
            "source": "docker"
        }
    }

    # Simulate active_trades.json containing all bots from previous sync
    trade_storage.load_trades.return_value = active_trades_after_sync
    await bot_monitor._process_active_trades(active_trades_after_sync, bot_statuses_data_final)

    print(f"\n--- Results for Multiple Bots Scenario ---")
    print(f"  Total stop_and_archive_bot calls: {mock_hummingbot_manager.stop_and_archive_bot.call_count}")
    print(f"  Total remove_trade_entry calls: {trade_storage.remove_trade_entry.call_count}")
    print(f"  Total send_bot_status_update calls: {mock_telegram_messenger.send_bot_status_update.call_count}")
    print(f"  Total send_trade_update calls: {mock_telegram_messenger.send_trade_update.call_count}")

    # Expected results for multiple bots:
    # - Bot 1 (SOL, incomplete): NOT archived, status update sent, trade update sent (1 BUY)
    # - Bot 2 (BTC, no trades): NOT archived, status update sent, no trade update
    # - Bot 3 (XRP, completed): ARCHIVED, status update sent, trade updates sent (1 BUY + 1 SELL)
    
    # Verify correct handling:
    # Only 1 bot should be archived (the completed one)
    assert mock_hummingbot_manager.stop_and_archive_bot.call_count == 1, f"Expected 1 archive call, got {mock_hummingbot_manager.stop_and_archive_bot.call_count}"
    mock_hummingbot_manager.stop_and_archive_bot.assert_called_with(instance_name_completed)
    
    # Only 1 bot should be removed from storage (the completed one)
    assert trade_storage.remove_trade_entry.call_count == 1, f"Expected 1 remove call, got {trade_storage.remove_trade_entry.call_count}"
    trade_storage.remove_trade_entry.assert_called_with(instance_name_completed)
    
    # All 3 bots should send status updates
    assert mock_telegram_messenger.send_bot_status_update.call_count == 3, f"Expected 3 status updates, got {mock_telegram_messenger.send_bot_status_update.call_count}"
    
    # Total trade updates: 1 BUY (SOL) + 0 (BTC) + 1 BUY + 1 SELL (XRP) = 3
    assert mock_telegram_messenger.send_trade_update.call_count == 3, f"Expected 3 trade updates, got {mock_telegram_messenger.send_trade_update.call_count}"
    
    # Trades should be saved once (after processing)
    trade_storage.save_trades.assert_called_once()

    print(f"✅ Bot 1 ({instance_name_bought}): Incomplete trade - kept in monitoring")
    print(f"✅ Bot 2 ({instance_name_no_buy}): No trades - kept in monitoring")
    print(f"✅ Bot 3 ({instance_name_completed}): Completed trade - archived and removed")
    print(f"✅ All bot logs properly separated and processed individually")

    mock_hummingbot_manager.stop_and_archive_bot.reset_mock()
    trade_storage.remove_trade_entry.reset_mock()
    mock_telegram_messenger.send_bot_status_update.reset_mock()
    mock_telegram_messenger.send_trade_update.reset_mock()
    trade_storage.save_trades.reset_mock()

    print("\n--- Additional Test: Edge Case with Bot Not Found ---")
    
    # Test what happens when a bot suddenly disappears from API but is still in active_trades
    # This could happen if a bot crashes or is manually removed
    instance_name_missing = "buy_sell_trailing_stop_bot_ETH_USDC_missing"
    
    # Add a bot to active trades manually (simulating it was there before but now missing from API)
    missing_bot_trade = {
        "instance_name": instance_name_missing,
        "chat_id": chat_id,
        "trading_pair": "ETH-USDC",
        "order_amount_usd": 10,
        "trailing_stop_loss_delta": 0.001,
        "take_profit_delta": 0.001,
        "fixed_stop_loss_delta": 0.001
    }
    
    # Simulate API returning empty data (bot not found)
    empty_bot_statuses_data = {}
    active_trades_with_missing = [missing_bot_trade]
    trade_storage.load_trades.return_value = active_trades_with_missing
    
    await bot_monitor._process_active_trades(active_trades_with_missing, empty_bot_statuses_data)
    
    print(f"✅ Missing bot handled gracefully - no crashes with empty bot status data")

    print("\nMultiple bots simulation complete - all scenarios verified!")


if __name__ == "__main__":
    asyncio.run(simulate_premature_archiving_scenario())