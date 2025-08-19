import asyncio
import os
import json
from datetime import datetime
from dotenv import load_dotenv

# Assuming telegram_alerts.py is in the same directory or accessible via PYTHONPATH
from telegram_alerts import send_telegram_message
from hummingbot_integration import HummingbotManager
from trade_storage import load_active_trades, save_active_trades, remove_trade_entry

# Load environment variables from .env file
load_dotenv()

async def main():
    hummingbot_manager = None # Initialize to None for finally block
    """
    Main function for the bot monitor service.
    Periodically checks the status of active Hummingbot instances
    and takes action if a bot has stopped.
    """
    # Load Hummingbot API credentials
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

    # Initialize Hummingbot API client
    await hummingbot_manager.initialize_client()
    # The client handles its own login/authentication during initialization

    print("Hummingbot Bot Monitor started...")

    try:
        while True:
            print(f"[{datetime.now()}] Checking active bots...")
            active_trades = load_active_trades()

            if not active_trades:
                print("No active trades found.")
            else:
                trades_to_remove = []
                for trade in active_trades:
                    instance_name = trade.get('instance_name')
                    chat_id = trade.get('chat_id')
                    trading_pair = trade.get('trading_pair')

                    if not instance_name:
                        print(f"Skipping trade entry due to missing 'instance_name': {trade}")
                        continue

                    try:
                        status_response = await hummingbot_manager.get_bot_status(instance_name)
                        bot_status = status_response.get('status')
                        print(f"Bot '{instance_name}' status: {bot_status}")

                        if bot_status == "stopped":
                            print(f"Bot '{instance_name}' has stopped. Archiving and notifying...")
                            await hummingbot_manager.stop_and_archive_bot(instance_name)
                            trades_to_remove.append(instance_name)

                            message = (
                                f"🔔 Trade Completed! 🔔\n"
                                f"Bot: `{instance_name}`\n"
                                f"Pair: `{trading_pair}`\n"
                                f"Status: Stopped and Archived."
                            )
                            await send_telegram_message(chat_id, message, dry_run=False) # For testing without Telegram
                        elif bot_status == "not_found":
                            print(f"Bot '{instance_name}' not found on Hummingbot instance. Removing from active trades.")
                            trades_to_remove.append(instance_name)
                            message = (
                                f"⚠️ Bot Not Found! ⚠️\n"
                                f"Bot: `{instance_name}`\n"
                                f"Pair: `{trading_pair}`\n"
                                f"Status: Not found on Hummingbot instance. Removed from active trades."
                            )
                            await send_telegram_message(chat_id, message, dry_run=False) # For testing without Telegram

                    except Exception as e:
                        print(f"Error checking status for bot '{instance_name}': {e}")
                        # Optionally, send an error alert to the chat_id
                        # await send_telegram_message(chat_id, f"Error checking bot '{instance_name}': {e}")

                for instance_name in trades_to_remove:
                    remove_trade_entry(instance_name)
                    print(f"Removed '{instance_name}' from active_trades.json")

            await asyncio.sleep(60)  # Check every 60 seconds
    except asyncio.CancelledError:
        print("Bot Monitor task cancelled.")
    except Exception as e:
        print(f"An error occurred in the bot monitor: {e}")
    finally:
        if hummingbot_manager:
            print("Closing Hummingbot API client session...")
            await hummingbot_manager.close_client()
        print("Bot Monitor stopped.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot Monitor stopped by user via KeyboardInterrupt.")
    except Exception as e:
        print(f"An unexpected error occurred during main execution: {e}")