import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from symbol_manager import SymbolManager
from datetime import datetime

# Load Telegram bot token and chat ID from credentials_b.json
def load_telegram_credentials():
    try:
        with open('credentials_b.json', 'r') as f:
            credentials = json.load(f)
            return credentials.get('telegram_bot_token'), credentials.get('telegram_chat_id')
    except FileNotFoundError:
        print(f"[{datetime.now()}] credentials_b.json not found. Please create it with 'telegram_bot_token' and 'telegram_chat_id'.")
        return None, None
    except json.JSONDecodeError as e:
        print(f"[{datetime.now()}] Error decoding credentials_b.json: {e}")
        return None, None

TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID = load_telegram_credentials()

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print(f"[{datetime.now()}] Telegram bot token or chat ID not found. Bot will not start.")
    exit()

symbol_manager = SymbolManager()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the command /start is issued."""
    await update.message.reply_text('Hi! I am your crypto volume alert bot. Use /help to see available commands.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /help is issued."""
    help_text = (
        "Available commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/list_restricted - List all restricted trading pairs\n"
        "/unrestrict <SYMBOL> - Unrestrict a specific trading pair (e.g., /unrestrict MATICBTC)\n"
    )
    await update.message.reply_text(help_text)

async def list_restricted(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all restricted trading pairs."""
    restricted = symbol_manager.get_excluded_symbols()
    if restricted:
        message = "Restricted pairs:\n" + "\n".join(sorted(list(restricted)))
    else:
        message = "No trading pairs are currently restricted."
    await update.message.reply_text(message)

async def unrestrict_pair(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unrestricts a specific trading pair."""
    if not context.args:
        await update.message.reply_text("Usage: /unrestrict <SYMBOL>")
        return

    symbol_to_unrestrict = context.args[0].upper()
    if symbol_manager.remove_symbol(symbol_to_unrestrict):
        await update.message.reply_text(f"Successfully unrestricted {symbol_to_unrestrict}.")
    else:
        await update.message.reply_text(f"{symbol_to_unrestrict} is not currently restricted.")

async def restrict_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles callback queries from inline buttons to restrict a pair."""
    query = update.callback_query
    await query.answer() # Acknowledge the callback query

    symbol_to_restrict = query.data.replace("restrict_", "")
    if symbol_manager.add_symbol(symbol_to_restrict):
        await query.edit_message_text(text=f"Successfully restricted {symbol_to_restrict}.")
    else:
        await query.edit_message_text(text=f"{symbol_to_restrict} is already restricted.")

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list_restricted", list_restricted))
    application.add_handler(CommandHandler("unrestrict", unrestrict_pair))
    application.add_handler(CallbackQueryHandler(restrict_callback, pattern="^restrict_"))

    # Run the bot until the user presses Ctrl-C
    print(f"[{datetime.now()}] Telegram bot started. Listening for updates...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()