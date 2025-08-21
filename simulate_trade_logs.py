import asyncio
import sys
import os
from datetime import datetime # Correct import for datetime.now()
from dotenv import load_dotenv
from unittest.mock import AsyncMock, MagicMock, call

# Add the parent directory to the sys.path to allow imports from the project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from bot_monitor import BotMonitor
from hummingbot_integration import HummingbotManager
from telegram_messenger import TelegramMessenger
from trade_storage import TradeStorage
from bot_status_handler import BotStatusHandler
from log_processor import LogProcessor
from telegram_notifier import TelegramNotifier

async def simulate_bot_monitor_cycles():
    print("Starting Bot Monitor multi-cycle simulation...")

    # Mock TelegramMessenger and its methods
    mock_telegram_messenger = AsyncMock(spec=TelegramMessenger)
    mock_telegram_messenger.send_trade_update = AsyncMock()
    mock_telegram_messenger.send_bot_status_update = AsyncMock()
    mock_telegram_messenger.TELEGRAM_CHAT_ID = "12345"

    telegram_notifier = TelegramNotifier(mock_telegram_messenger)

    # Initialize HummingbotManager (not mocked for PnL retrieval)
    # NOTE: For this simulation to work correctly for PnL retrieval,
    # a Hummingbot instance with its API server must be running,
    # and HUMMINGBOT_API_URL, USERNAME, and PASSWORD environment variables
    # must be set in your .env file.
    load_dotenv()
    api_base_url = os.getenv("HUMMINGBOT_API_URL", "http://localhost:8000")
    api_username = os.getenv("USERNAME")
    api_password = os.getenv("PASSWORD")

    if not all([api_base_url, api_username, api_password]):
        print("ERROR: Please set HUMMINGBOT_API_URL, USERNAME, and PASSWORD environment variables in your .env file for PnL simulation.")
        print("Skipping PnL retrieval simulation due to missing credentials.")
        # Create a mocked manager if credentials are not set, to allow other parts of the simulation to run
        # Always create a mock for the manager that will be passed to BotMonitor
        mock_hummingbot_manager = AsyncMock(spec=HummingbotManager)
        mock_hummingbot_manager.stop_and_archive_bot = AsyncMock(return_value=(True, {"message": "Bot archived successfully (simulated)"}))
        mock_hummingbot_manager.get_bot_pnl_after_completion = AsyncMock(return_value=(True, {
            "total_pnl": 0.001,
            "total_pnl_quote": 0.001,
            "total_volume_quote": 100.0,
            "total_fees_quote": 0.0001,
            "pnl_daily_usd": 0.0005,
            "pnl_daily_percent": 0.00001
        }))
    else:
        # Create a real HummingbotManager instance for actual API calls
        hummingbot_manager_to_use = HummingbotManager(api_base_url, api_username, api_password)
        await hummingbot_manager_to_use.initialize_client()
        
        # We will use the real manager, but still mock get_all_bot_statuses and get_bot_status
        # to control the simulation's bot status responses.
        mock_hummingbot_manager = AsyncMock(wraps=hummingbot_manager_to_use)
        mock_hummingbot_manager._real_manager = hummingbot_manager_to_use # Store for cleanup

    # Mock get_bot_status to return full details for new bots (this part can still be mocked for consistent simulation behavior)
    mock_hummingbot_manager.get_bot_status = AsyncMock(side_effect=[
        # First call for SOL bot (newly detected)
        (True, {
            "status": "running",
            "trading_pair": "SOL-USDC",
            "order_amount_usd": 100,
            "trailing_stop_loss_delta": 0.001,
            "take_profit_delta": 0.001,
            "fixed_stop_loss_delta": 0.001,
            "general_logs": [
                {"level_name": "INFO", "msg": "Starting Node <hbot.buy_sell_trailing_stop_bot_SOL_USDC_fh66bcqz>", "timestamp": 1755714510.1056917, "level_no": 20, "logger_name": "hummingbot.remote_iface.mqtt"},
            ],
        }),
        # Second call for BTC bot (newly detected)
        (True, {
            "status": "running",
            "trading_pair": "BTC-USDC",
            "order_amount_usd": 1000,
            "trailing_stop_loss_delta": 0.001,
            "take_profit_delta": 0.001,
            "fixed_stop_loss_delta": 0.001,
            "general_logs": [
                {"level_name": "INFO", "msg": "Starting Node <hbot.buy_sell_trailing_stop_bot_BTC_USDC_ucha4sat>", "timestamp": 1755714961.2302234, "level_no": 20, "logger_name": "hummingbot.remote_iface.mqtt"},
            ],
        }),
        # Third call for XRP bot (newly detected)
        (True, {
            "status": "running",
            "trading_pair": "XRP-USDC",
            "order_amount_usd": 50,
            "trailing_stop_loss_delta": 0.001,
            "take_profit_delta": 0.001,
            "fixed_stop_loss_delta": 0.001,
            "general_logs": [
                {"level_name": "INFO", "msg": "Starting Node <hbot.buy_sell_trailing_stop_bot_XRP_USDC_completed>", "timestamp": 1755714510.1056917, "level_no": 20, "logger_name": "hummingbot.remote_iface.mqtt"},
            ],
        }),
        # Subsequent calls for existing bots (can return minimal data as full logs are in all_bot_statuses)
        # This is a simplified mock, in reality, get_bot_status might return more.
        # For the purpose of _synchronize_active_trades, we only need the status.
        (True, {"status": "running"}), # For SOL in cycle 2
        (True, {"status": "running"}), # For BTC in cycle 2
        (True, {"status": "success"}), # For XRP in cycle 2 (after completion)
        (True, {"status": "stopped"}), # For SOL in cycle 3 (after it stops)
        (True, {"status": "stopped"}), # For BTC in cycle 3 (after it stops)
        (True, {"status": "not_found"}), # For XRP in cycle 3 (after archiving)
        (True, {"status": "not_found"}), # For missing bot in edge case
    ])

    # Mock TradeStorage
    trade_storage = MagicMock(spec=TradeStorage)
    trade_storage.load_trades.return_value = []
    trade_storage.save_trades.return_value = None
    trade_storage.remove_trade_entry = MagicMock()

    # Initialize BotMonitor with mocks
    log_processor = LogProcessor(notifier=telegram_notifier)
    bot_status_handler = BotStatusHandler(
        notifier=telegram_notifier,
        hummingbot_manager=mock_hummingbot_manager,
        log_processor=log_processor,
        time_provider=datetime.now
    )

    bot_monitor = BotMonitor(
        hummingbot_manager=mock_hummingbot_manager,
        trade_storage=trade_storage,
        notifier=telegram_notifier,
        bot_status_handler=bot_status_handler,
        log_processor=log_processor,
        check_interval_seconds=1,
        time_provider=datetime.now
    )

    instance_name_bought = "buy_sell_trailing_stop_bot_SOL_USDC_fh66bcqz"
    instance_name_no_buy = "buy_sell_trailing_stop_bot_BTC_USDC_ucha4sat"
    instance_name_completed = "buy_sell_trailing_stop_bot_SOL_USDC_dfkkwzqe"
    instance_name_missing = "buy_sell_trailing_stop_bot_ETH_USDC_missing"
    chat_id = "12345"

    # Redefine the BotMonitor's run method for simulation purposes to execute a single cycle
    # This avoids the infinite loop and sleep
    async def run_single_cycle():
        active_trades, bot_statuses_data = await bot_monitor._synchronize_active_trades()
        if active_trades:
            processed_trades = await bot_monitor._process_active_trades(active_trades, bot_statuses_data)
            bot_monitor._trade_storage.save_trades(processed_trades)

    # --- Cycle 1: Initial detection of all bots ---
    print("\n--- Cycle 1: Initial detection and processing ---")
    mock_hummingbot_manager.get_all_bot_statuses.return_value = {
        "status": "success",
        "data": {
            instance_name_bought: {"status": "running", "general_logs": [{"level_name": "INFO", "msg": "Starting Node...", "timestamp": 1}], "recently_active": True, "source": "docker"},
            instance_name_no_buy: {"status": "running", "general_logs": [{"level_name": "INFO", "msg": "Starting Node...", "timestamp": 1}], "recently_active": True, "source": "docker"},
            instance_name_completed: {"status": "running", "general_logs": [{"level_name": "INFO", "msg": "Starting Node...", "timestamp": 1}], "recently_active": True, "source": "docker"}
        }
    }
    trade_storage.load_trades.return_value = []
    await run_single_cycle()

    # Assertions for Cycle 1
    assert trade_storage.save_trades.call_count == 2
    final_trades_c1 = trade_storage.save_trades.call_args[0][0]
    assert len(final_trades_c1) == 3
    mock_hummingbot_manager.stop_and_archive_bot.assert_not_called()
    trade_storage.remove_trade_entry.assert_not_called()
    assert mock_telegram_messenger.send_bot_status_update.call_count == 3
    mock_telegram_messenger.send_trade_update.assert_not_called()
    
    # Reset mocks for next cycle
    trade_storage.save_trades.reset_mock()
    mock_telegram_messenger.reset_mock()

    # --- Cycle 2: One bot completes trade, others stop ---
    print("\n--- Cycle 2: One bot completes trade, others stop/run ---")
    mock_hummingbot_manager.get_all_bot_statuses.return_value = {
        "status": "success",
        "data": {
            instance_name_bought: {
                "status": "stopped", "general_logs": [{"level_name": "INFO", "msg": "The BUY order..."}, {"level_name": "INFO", "msg": "All positions closed."}], "recently_active": True, "source": "docker"
            },
            instance_name_no_buy: {
                "status": "stopped", "general_logs": [{"level_name": "WARNING", "msg": "binance is not ready."}], "recently_active": True, "source": "docker"
            },
            instance_name_completed: {
                "status": "success", "general_logs": [{"level_name": "INFO", "msg": "The SELL order..."}, {"level_name": "INFO", "msg": "All positions closed. Stopping the strategy."}], "recently_active": True, "source": "docker"
            }
        }
    }
    trade_storage.load_trades.return_value = final_trades_c1  # Use state from previous cycle
    await run_single_cycle()

    # Assertions for Cycle 2
    assert trade_storage.save_trades.call_count == 2
    final_trades_c2 = trade_storage.save_trades.call_args[0][0]
    assert len(final_trades_c2) == 1  # Two bots should be removed (SOL and XRP), leaving BTC
    instance_names_c2 = {t['instance_name'] for t in final_trades_c2}
    assert instance_name_completed not in instance_names_c2
    assert mock_hummingbot_manager.stop_and_archive_bot.call_count == 2
    mock_hummingbot_manager.stop_and_archive_bot.assert_has_calls([
        call(instance_name_bought), # SOL bot stopped with "All positions closed."
        call(instance_name_completed) # XRP bot status 'success' with "All positions closed."
    ], any_order=True)
    
    # Verify PnL retrieval is called for completed trades
    assert mock_hummingbot_manager.get_bot_pnl_after_completion.call_count == 2
    mock_hummingbot_manager.get_bot_pnl_after_completion.assert_has_calls([
        call(instance_name_bought),
        call(instance_name_completed)
    ], any_order=True)
    
    assert trade_storage.remove_trade_entry.call_count == 2
    trade_storage.remove_trade_entry.assert_has_calls([
        call(instance_name_bought),
        call(instance_name_completed)
    ], any_order=True)
    
    # Reset mocks (only for the ones that are still mocked)
    trade_storage.reset_mock()
    mock_telegram_messenger.reset_mock()
    
    # If a real HummingbotManager was used, close its client
    if hasattr(mock_hummingbot_manager, '_real_manager'):
        await mock_hummingbot_manager._real_manager.close_client()

    # --- Cycle 3: Verify no re-adding of archived bot ---
    print("\n--- Cycle 3: Verify no re-adding of archived bot ---")
    mock_hummingbot_manager.get_all_bot_statuses.return_value = {
        "status": "success",
        "data": {
            instance_name_bought: {"status": "stopped", "general_logs": [], "recently_active": True, "source": "docker"},
            instance_name_no_buy: {"status": "stopped", "general_logs": [], "recently_active": True, "source": "docker"},
            instance_name_completed: {"status": "success", "general_logs": [], "recently_active": False}
        }
    }
    trade_storage.load_trades.return_value = final_trades_c2
    
    # Reset mocks for Cycle 3
    mock_hummingbot_manager.stop_and_archive_bot.reset_mock()
    trade_storage.remove_trade_entry.reset_mock()
    
    await run_single_cycle()

    # Assertions for Cycle 3
    assert trade_storage.save_trades.call_count == 2
    final_trades_c3 = trade_storage.save_trades.call_args[0][0]
    assert len(final_trades_c3) == 1 # BTC bot should remain in active trades
    mock_hummingbot_manager.stop_and_archive_bot.assert_not_called() # BTC bot is not archived
    trade_storage.remove_trade_entry.assert_not_called() # BTC bot is not removed

    print(f"✅ Bot 1 ({instance_name_bought}): Stopped with 'All positions closed.' - correctly archived in Cycle 2")
    print(f"✅ Bot 2 ({instance_name_no_buy}): Stopped with no specific reason - correctly kept in monitoring")
    print(f"✅ Bot 3 ({instance_name_completed}): Completed trade - correctly archived in Cycle 2 and NOT re-added")
    
    print("\nAll simulation scenarios complete and verified!")

if __name__ == "__main__":
    asyncio.run(simulate_bot_monitor_cycles())

