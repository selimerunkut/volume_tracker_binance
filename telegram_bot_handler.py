import os
import json
import re # Import for regex parsing
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from symbol_manager import SymbolManager
from hummingbot_integration import HummingbotManager
from trade_storage import TradeStorage
from telegram_messenger import TelegramMessenger # Import TelegramMessenger

# Load environment variables from .env file
load_dotenv()

# Determine if running in test mode
TELEGRAM_BOT_TEST_MODE = os.getenv("TELEGRAM_BOT_TEST_MODE", "False").lower() == "true"

# Load Telegram bot token and chat ID from credentials_b.json
def load_telegram_credentials():
    try:
        with open('credentials_b.json', 'r') as f:
            credentials = json.load(f)
            if TELEGRAM_BOT_TEST_MODE:
                print(f"[{datetime.now()}] Running in TEST MODE. Using test credentials.")
                return credentials.get('telegram_bot_token_test'), credentials.get('telegram_chat_id_test')
            else:
                print(f"[{datetime.now()}] Running in PRODUCTION MODE. Using production credentials.")
                return credentials.get('telegram_bot_token'), credentials.get('telegram_chat_id')
    except FileNotFoundError:
        print(f"[{datetime.now()}] credentials_b.json not found. Please create it with 'telegram_bot_token' and 'telegram_chat_id' (and test credentials if using TELEGRAM_BOT_TEST_MODE).")
        return None, None
    except json.JSONDecodeError as e:
        print(f"[{datetime.now()}] Error decoding credentials_b.json: {e}")
        return None, None

TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID = load_telegram_credentials()

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print(f"[{datetime.now()}] Telegram bot token or chat ID not found. Bot will not start.")
    exit()

symbol_manager = SymbolManager()
trade_storage = TradeStorage() # Instantiate TradeStorage
telegram_messenger = TelegramMessenger() # Instantiate TelegramMessenger

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the command /start is issued."""
    await update.effective_message.reply_text('Hi! I am your crypto volume alert bot. Use /help to see available commands.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /help is issued."""
    help_text = (
        "Available commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/list_restricted - List all restricted trading pairs\n"
        "/unrestrict <SYMBOL> - Unrestrict a specific trading pair (e.g., /unrestrict MATICBTC)\n"
        "/buy <trading_pair> <order_amount_usd> [trailing_stop_loss_delta] [take_profit_delta] [fixed_stop_loss_delta] - Deploy a new Hummingbot instance\n"
        "/status [instance_name] - Get status of a specific bot or all active bots\n"
    )
    await update.effective_message.reply_text(help_text)

async def list_restricted(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all restricted trading pairs."""
    restricted = symbol_manager.get_excluded_symbols()
    if restricted:
        message = "Restricted pairs:\n" + "\n".join(sorted(list(restricted)))
    else:
        message = "No trading pairs are currently restricted."
    await update.effective_message.reply_text(message)

async def unrestrict_pair(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unrestricts a specific trading pair."""
    if not context.args:
        await update.effective_message.reply_text("Usage: /unrestrict <SYMBOL>")
        return

    symbol_to_unrestrict = context.args[0].upper()
    if symbol_manager.remove_symbol(symbol_to_unrestrict):
        await telegram_messenger.send_simple_message(chat_id, f"Successfully unrestricted {symbol_to_unrestrict}.")
    else:
        await telegram_messenger.send_simple_message(chat_id, f"{symbol_to_unrestrict} is not currently restricted.")

async def restrict_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles callback queries from inline buttons to restrict a pair."""
    query = update.callback_query
    await query.answer() # Acknowledge the callback query

    symbol_to_restrict = query.data.replace("restrict_", "")
    if symbol_manager.add_symbol(symbol_to_restrict):
        await telegram_messenger.send_simple_message(chat_id, f"Successfully restricted {symbol_to_restrict}.")
    else:
        await telegram_messenger.send_simple_message(chat_id, f"{symbol_to_restrict} is already restricted.")

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deploys a new Hummingbot instance based on user input."""
    chat_id = str(update.effective_chat.id)
    
    if not context.args or len(context.args) < 2:
        await update.effective_message.reply_text(
            "Usage: /buy <trading_pair> <order_amount_usd> [trailing_stop_loss_delta] [take_profit_delta] [fixed_stop_loss_delta]\n"
            "Example: /buy ETH-USDT 100 0.005 0.01 0.002"
        )
        return

    try:
        trading_pair = context.args[0].upper()
        order_amount_usd = float(context.args[1])
        
        # Optional parameters with default values
        trailing_stop_loss_delta = float(context.args[2]) if len(context.args) > 2 else 0.0005
        take_profit_delta = float(context.args[3]) if len(context.args) > 3 else 0.0009
        fixed_stop_loss_delta = float(context.args[4]) if len(context.args) > 4 else 0.0003

        hummingbot_manager: HummingbotManager = context.bot_data['hummingbot_manager']

        await update.effective_message.reply_text(f"Attempting to deploy bot for {trading_pair} with order amount ${order_amount_usd}...")

        success, instance_name, result = await hummingbot_manager.create_and_deploy_bot(
            trading_pair=trading_pair,
            order_amount_usd=order_amount_usd,
            trailing_stop_loss_delta=trailing_stop_loss_delta,
            take_profit_delta=take_profit_delta,
            fixed_stop_loss_delta=fixed_stop_loss_delta
        )

        if success:
            trade_data = {
                "instance_name": instance_name,
                "chat_id": chat_id,
                "trading_pair": trading_pair,
                "order_amount_usd": order_amount_usd,
                "trailing_stop_loss_delta": trailing_stop_loss_delta,
                "take_profit_delta": take_profit_delta,
                "fixed_stop_loss_delta": fixed_stop_loss_delta
            }
            trade_storage.add_trade_entry(trade_data)
            
            confirmation_message = (
                f"✅ Bot Deployed Successfully! ✅\n"
                f"Instance: `{instance_name}`\n"
                f"Pair: `{trading_pair}`\n"
                f"Amount: `${order_amount_usd}`\n"
                f"TrailingStopLoss: `{trailing_stop_loss_delta}`\n"
                f"TakeProfit: `{take_profit_delta}`\n"
                f"FixedStopLoss: `{fixed_stop_loss_delta}`\n"
                f"Monitoring will begin shortly."
            )
            await telegram_messenger.send_bot_deployed_confirmation(
                chat_id,
                instance_name,
                trading_pair,
                order_amount_usd,
                trailing_stop_loss_delta,
                take_profit_delta,
                fixed_stop_loss_delta,
                dry_run=False
            )
            await update.effective_message.reply_text(confirmation_message) # Also reply in the chat
        else:
            error_message = f"Failed to deploy bot for {trading_pair}. Error: {result.get('error', 'Unknown error')}"
            await telegram_messenger.send_error_message(chat_id, error_message, dry_run=False)
            await update.effective_message.reply_text(error_message)

    except ValueError:
        await update.effective_message.reply_text("Invalid number format for order amount or deltas. Please provide valid numbers.")
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        await telegram_messenger.send_error_message(chat_id, error_message, dry_run=False)
        await update.effective_message.reply_text(error_message)

async def get_bot_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gets the status of a specific bot or all active bots."""
    chat_id = str(update.effective_chat.id)
    hummingbot_manager: HummingbotManager = context.bot_data.get('hummingbot_manager')

    if not hummingbot_manager:
        await update.effective_message.reply_text("Hummingbot manager is not initialized. Please try again later.")
        return

    instance_name = context.args[0] if context.args else None
    status_messages = []

    try:
        if instance_name:
            # Get status for a specific bot
            success, response = await hummingbot_manager.get_bot_status(instance_name)
            if success:
                bot_actual_status = response.get('data', {}).get('status')
                general_logs = response.get('data', {}).get('general_logs', [])
                error_logs = response.get('data', {}).get('error_logs', [])

                status_text = f"Bot: `{instance_name}`\nStatus: `{bot_actual_status}`\n"
                
                # PnL and Open Orders are not available in structured JSON, parse from logs
                pnl_info = "PnL: N/A"
                open_orders_info = "Open Orders: N/A"
                
                # Iterate through logs to find PnL and Open Orders
                for log_entry in reversed(general_logs):
                    msg = log_entry.get('msg', '')
                    # Example log for PnL: "Current PnL: 0.001 ETH"
                    pnl_match = re.search(r"PnL: ([\d\.\-]+ [A-Z]+)", msg)
                    # Example log for Open Orders: "Open orders: 2"
                    open_orders_match = re.search(r"Open orders: (\d+)", msg)
                    
                    if pnl_match:
                        pnl_info = f"PnL: {pnl_match.group(1)}"
                    if open_orders_match:
                        open_orders_info = f"Open Orders: {open_orders_match.group(1)}"
                    
                    # If both are found, no need to search further in older logs
                    if pnl_match and open_orders_match:
                        break
                
                status_text += f"{pnl_info}\n{open_orders_info}\n"

                if bot_actual_status == "stopped":
                    stop_reason = "Unknown Reason"
                    for log_entry in reversed(general_logs):
                        msg = log_entry.get('msg', '').lower()
                        if "fixed stop loss hit" in msg or "take profit hit" in msg or "all positions closed" in msg:
                            stop_reason = "Trade Completed"
                            break
                        elif "stopping the strategy" in msg:
                            stop_reason = "Manual Stop/Strategy Stopped"
                            break
                    if error_logs:
                        for log_entry in reversed(error_logs):
                            msg = log_entry.get('msg', '').lower()
                            if "error" in msg or "exception" in msg:
                                stop_reason = f"Error: {msg[:100]}..."
                                break
                    status_text += f"Stop Reason: {stop_reason}\n"
                
                status_messages.append(status_text)
            else:
                status_messages.append(f"Failed to get status for `{instance_name}`. Error: {response.get('error', 'Unknown error')}")
        else:
            # Get status for all active bots for this chat_id
            active_trades = trade_storage.load_trades()
            user_bots = [trade for trade in active_trades if trade.get('chat_id') == chat_id]

            if not user_bots:
                status_messages.append("No active bots found for your chat ID.")
            else:
                status_messages.append("--- Your Active Bots ---\n")
                for trade in user_bots:
                    bot_instance_name = trade.get('instance_name')
                    trading_pair = trade.get('trading_pair')
                    
                    success, response = await hummingbot_manager.get_bot_status(bot_instance_name)
                    if success:
                        bot_actual_status = response.get('data', {}).get('status')
                        general_logs = response.get('data', {}).get('general_logs', [])
                        error_logs = response.get('data', {}).get('error_logs', [])

                        status_text = f"Bot: `{bot_instance_name}` (Pair: `{trading_pair}`)\nStatus: `{bot_actual_status}`\n"
                        
                        # PnL and Open Orders are not available in structured JSON, parse from logs
                        pnl_info = "PnL: N/A"
                        open_orders_info = "Open Orders: N/A"
                        
                        # Iterate through logs to find PnL and Open Orders
                        for log_entry in reversed(general_logs):
                            msg = log_entry.get('msg', '')
                            pnl_match = re.search(r"PnL: ([\d\.\-]+ [A-Z]+)", msg)
                            open_orders_match = re.search(r"Open orders: (\d+)", msg)
                            
                            if pnl_match:
                                pnl_info = f"PnL: {pnl_match.group(1)}"
                            if open_orders_match:
                                open_orders_info = f"Open Orders: {open_orders_match.group(1)}"
                            
                            if pnl_match and open_orders_match:
                                break
                        
                        status_text += f"{pnl_info}\n{open_orders_info}\n"

                        if bot_actual_status == "stopped":
                            stop_reason = "Unknown Reason"
                            for log_entry in reversed(general_logs):
                                msg = log_entry.get('msg', '').lower()
                                if "fixed stop loss hit" in msg or "take profit hit" in msg or "all positions closed" in msg:
                                    stop_reason = "Trade Completed"
                                    break
                                elif "stopping the strategy" in msg:
                                    stop_reason = "Manual Stop/Strategy Stopped"
                                    break
                            if error_logs:
                                for log_entry in reversed(error_logs):
                                    msg = log_entry.get('msg', '').lower()
                                    if "error" in msg or "exception" in msg:
                                        stop_reason = f"Error: {msg[:100]}..."
                                        break
                            status_text += f"Stop Reason: {stop_reason}\n"
                        
                        status_messages.append(status_text)
                    else:
                        status_messages.append(f"Failed to get status for `{bot_instance_name}`. Error: {response.get('error', 'Unknown error')}")
                    status_messages.append("-" * 20) # Separator for multiple bots
    except Exception as e:
        status_messages.append(f"An unexpected error occurred while fetching bot status: {e}")

    final_message = "\n".join(status_messages)
    await update.effective_message.reply_text(final_message)

async def post_init_callback(application: Application) -> None:
    """Initializes HummingbotManager after the event loop has started."""
    hummingbot_api_url = os.getenv("HUMMINGBOT_API_URL", "http://localhost:8000")
    hummingbot_api_username = os.getenv("USERNAME")
    hummingbot_api_password = os.getenv("PASSWORD")

    if not all([hummingbot_api_url, hummingbot_api_username, hummingbot_api_password]):
        print("Error: Missing Hummingbot API credentials in .env file. Telegram bot cannot deploy bots.")
        # Do not add hummingbot_manager to bot_data if credentials are missing
    else:
        hummingbot_manager = HummingbotManager(
            api_base_url=hummingbot_api_url,
            api_username=hummingbot_api_username,
            api_password=hummingbot_api_password
        )
        await hummingbot_manager.initialize_client()
        application.bot_data['hummingbot_manager'] = hummingbot_manager
        print("HummingbotManager initialized and logged in.")

async def post_shutdown_callback(application: Application) -> None:
    """Closes HummingbotManager client session on shutdown."""
    hummingbot_manager: Optional[HummingbotManager] = application.bot_data.get('hummingbot_manager')
    if hummingbot_manager:
        print("Closing Hummingbot API client session...")
        await hummingbot_manager.close_client()
        print("Hummingbot API client session closed.")

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Set post_init and post_shutdown callbacks
    application.post_init = post_init_callback
    application.post_shutdown = post_shutdown_callback

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list_restricted", list_restricted))
    application.add_handler(CommandHandler("unrestrict", unrestrict_pair))
    application.add_handler(CallbackQueryHandler(restrict_callback, pattern="^restrict_"))
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list_restricted", list_restricted))
    application.add_handler(CommandHandler("unrestrict", unrestrict_pair))
    application.add_handler(CallbackQueryHandler(restrict_callback, pattern="^restrict_"))
    
    # The /buy command handler will be added dynamically in post_init_callback
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CommandHandler("status", get_bot_status_command)) # Register new status command

    # Run the bot until the user presses Ctrl-C
    print(f"[{datetime.now()}] Telegram bot started. Listening for updates...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()