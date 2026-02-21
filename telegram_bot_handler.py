import os
import json
import asyncio
import html
import logging
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import TelegramError
from symbol_manager import SymbolManager

# Import services
from src.services.llm_strategy import analyze_and_suggest
from src.services.performance_tracker import track_performance
from src.services.db_service import get_performance_stats, init_db, get_suggestion_details
from src.services.db_service import get_suggestions_between_dates

logger = logging.getLogger(__name__)

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
        await update.message.reply_text("Usage: /analyze &lt;SYMBOL&gt; (e.g., /analyze BTCUSDC)")
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
            await status_msg.edit_text(f"❌ Error: {html.escape(str(strategy['error']))}")
            return

        # Format the response using HTML (safer than Markdown v1 for LLM-generated text)
        action = html.escape(str(strategy.get('action', 'N/A')))
        confidence = strategy.get('confidence', 0)
        reasoning = html.escape(str(strategy.get('reasoning', 'N/A')))

        response = (
            f"🤖 <b>Strategy for {symbol}</b>\n\n"
            f"<b>Action</b>: {action} "
            f"(Confidence: {confidence}%)\n"
        )
        
        if strategy.get('action') in ['LONG', 'SHORT']:
            response += (
                f"<b>Entry</b>: {strategy.get('entry')}\n"
                f"<b>TP</b>: {strategy.get('tp')}\n"
                f"<b>SL</b>: {strategy.get('sl')}\n\n"
            )
        
        response += f"<b>Reasoning</b>: {reasoning}"
        
        reply_markup = None
        if strategy.get('suggestion_id'):
            keyboard = [
                [InlineKeyboardButton("📜 View Analysis Details", callback_data=f"details_{strategy['suggestion_id']}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_msg.edit_text(response, parse_mode='HTML', reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Unexpected error in analyze_symbol: {e}")
        try:
            await status_msg.edit_text(f"❌ An unexpected error occurred: {html.escape(str(e))}")
        except TelegramError:
            pass

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
    
    message = f"📜 <b>Analysis Details for {details['symbol']}</b>\n\n"
    message += f"<b>Technical Indicators</b>:\n{html.escape(data.get('ta_summary', 'N/A'))}\n"
    message += f"<b>News Context</b>:\n{html.escape(data.get('news_summary', 'N/A'))}\n"
    
    if data.get('memory_section') and "No past trades" not in data['memory_section']:
        message += f"<b>Past Performance Context</b>:\n{html.escape(data['memory_section'])}\n"
        
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=message,
        parse_mode='HTML'
    )

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows performance statistics."""
    start_range = None
    end_range = None
    range_text = "All time"
    args = context.args

    if args:
        try:
            start_range = parse_date_arg(args[0])
            if len(args) > 1:
                end_range = parse_date_arg(args[1])
            else:
                end_range = start_range
        except ValueError as err:
            await update.message.reply_text(str(err))
            return

        range_text = f"{start_range.strftime('%Y-%m-%d')} to {end_range.strftime('%Y-%m-%d')}"

    start_iso = get_day_start_iso(start_range) if start_range else ''
    end_iso = get_day_end_iso(end_range) if end_range else ''

    stats = await asyncio.to_thread(
        get_performance_stats,
        start_date=start_iso or None,
        end_date=end_iso or None
    )

    msg = (
        f"📊 **Performance History ({range_text})**\n\n"
        f"Total Analysis: {stats['total_trades']}\n"
        f"Wins: {stats['wins']}\n"
        f"Losses: {stats['losses']}\n"
        f"Win Rate: {stats['win_rate']:.1f}%\n"
        f"Avg PnL: {stats['avg_pnl']:.2f}%"
    )

    keyboard = [
        [InlineKeyboardButton("📜 View History Details", callback_data=f"history_details|{start_iso}|{end_iso}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)


def parse_date_arg(date_text: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_text, fmt)
        except ValueError:
            continue
    raise ValueError("Please provide dates in YYYY-MM-DD or YYYY/MM/DD format.")


def get_day_start_iso(dt: datetime) -> str:
    return datetime.combine(dt.date(), time.min).isoformat()


def get_day_end_iso(dt: datetime) -> str:
    return datetime.combine(dt.date(), time.max).isoformat()


async def history_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    payload = query.data.split("|")
    _, start_token, end_token = payload if len(payload) == 3 else (payload[0], '', '')
    start_dt = datetime.fromisoformat(start_token) if start_token else None
    end_dt = datetime.fromisoformat(end_token) if end_token else None

    results = await asyncio.to_thread(
        get_suggestions_between_dates,
        limit=10,
        start_date=start_token or None,
        end_date=end_token or None
    )

    if not results:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="No analysis records found for the selected range."
        )
        return

    lines = ["📜 **Last 10 Analyses**"]
    for row in results:
        ts = row['created_at'][:19]
        act = row['strategy_type']
        symbol = row['symbol']
        lines.append(f"{ts} — {symbol} ({act})")

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="\n".join(lines),
        parse_mode='Markdown'
    )

async def run_tracker(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Background job to track trade performance."""
    print(f"[{datetime.now()}] Running background performance tracker...")
    await asyncio.to_thread(track_performance)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and Telegram API conflicts."""
    logger.error(f"Bot error: {context.error}", exc_info=context.error)

def main() -> None:
    """Start the bot."""
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
    )

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
    application.add_handler(CallbackQueryHandler(history_details_callback, pattern="^history_details"))

    # Register error handler
    application.add_error_handler(error_handler)

    # Add background job (run every 30 minutes)
    job_queue = application.job_queue
    job_queue.run_repeating(run_tracker, interval=1800, first=10)

    # Run the bot until the user presses Ctrl-C
    print(f"[{datetime.now()}] Telegram bot started with AI Strategy Advisor. Listening for updates...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
