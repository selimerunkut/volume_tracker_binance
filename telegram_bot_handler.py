import os
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from symbol_manager import SymbolManager
from datetime import datetime

# Import services
from src.services.llm_strategy import analyze_and_suggest
from src.services.performance_tracker import track_performance
from src.services.db_service import get_performance_stats, init_db, get_suggestion_details

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

# Initialize DB
init_db()

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
        "/analyze <SYMBOL> - Get AI strategy for a symbol\n"
        "/history - Show trading performance stats\n"
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

async def analyze_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Analyzes a symbol using AI strategy."""
    if not context.args:
        await update.message.reply_text("Usage: /analyze <SYMBOL> (e.g., /analyze BTCUSDC)")
        return

    symbol = context.args[0].upper()
    status_msg = await update.message.reply_text(f"🔍 Analyzing {symbol}... This may take a moment.")

    try:
        # Run analysis in a separate thread to not block the bot
        strategy = await asyncio.to_thread(analyze_and_suggest, symbol)
        
        if not strategy:
            await status_msg.edit_text(f"❌ Failed to analyze {symbol}. Check logs or try again.")
            return

        if "error" in strategy:
            await status_msg.edit_text(f"❌ Error: {strategy['error']}")
            return

        # Format the response
        response = (
            f"🤖 **Strategy for {symbol}**\n\n"
            f"**Action**: {strategy.get('action', 'N/A')} "
            f"(Confidence: {strategy.get('confidence', 0)}%)\n"
        )
        
        if strategy.get('action') in ['LONG', 'SHORT']:
            response += (
                f"**Entry**: {strategy.get('entry')}\n"
                f"**TP**: {strategy.get('tp')}\n"
                f"**SL**: {strategy.get('sl')}\n\n"
            )
        
        response += f"**Reasoning**: {strategy.get('reasoning')}"
        
        reply_markup = None
        if strategy.get('suggestion_id'):
            keyboard = [
                [InlineKeyboardButton("📜 View Analysis Details", callback_data=f"details_{strategy['suggestion_id']}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_msg.edit_text(response, parse_mode='Markdown', reply_markup=reply_markup)

    except Exception as e:
        await status_msg.edit_text(f"❌ An unexpected error occurred: {str(e)}")

async def details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles callback queries to show analysis details."""
    query = update.callback_query
    await query.answer()

    suggestion_id = int(query.data.replace("details_", ""))
    details = get_suggestion_details(suggestion_id)

    if not details or not details.get('analysis_data'):
        await query.edit_message_text(text="❌ Details not available for this analysis.")
        return

    data = details['analysis_data']
    
    message = f"📜 **Analysis Details for {details['symbol']}**\n\n"
    message += f"**Technical Indicators**:\n{data.get('ta_summary', 'N/A')}\n"
    message += f"**News Context**:\n{data.get('news_summary', 'N/A')}\n"
    
    if data.get('memory_section') and "No past trades" not in data['memory_section']:
        message += f"**Past Performance Context**:\n{data['memory_section']}\n"
        
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=message,
        parse_mode='Markdown'
    )

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows performance statistics."""
    stats = await asyncio.to_thread(get_performance_stats)
    
    msg = (
        "📊 **Performance History**\n\n"
        f"Total Trades: {stats['total_trades']}\n"
        f"Wins: {stats['wins']}\n"
        f"Losses: {stats['losses']}\n"
        f"Win Rate: {stats['win_rate']:.1f}%\n"
        f"Avg PnL: {stats['avg_pnl']:.2f}%"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def run_tracker(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Background job to track trade performance."""
    print(f"[{datetime.now()}] Running background performance tracker...")
    await asyncio.to_thread(track_performance)

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list_restricted", list_restricted))
    application.add_handler(CommandHandler("unrestrict", unrestrict_pair))
    application.add_handler(CommandHandler("analyze", analyze_symbol))
    application.add_handler(CommandHandler("history", show_history))
    
    application.add_handler(CallbackQueryHandler(restrict_callback, pattern="^restrict_"))
    application.add_handler(CallbackQueryHandler(details_callback, pattern="^details_"))

    # Add background job (run every 30 minutes)
    job_queue = application.job_queue
    job_queue.run_repeating(run_tracker, interval=1800, first=10)

    # Run the bot until the user presses Ctrl-C
    print(f"[{datetime.now()}] Telegram bot started with AI Strategy Advisor. Listening for updates...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
