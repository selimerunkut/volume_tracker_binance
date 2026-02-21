import os
import json
import asyncio
import html
import logging
from datetime import datetime, time
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import TelegramError
from symbol_manager import SymbolManager
from src.services.watchlist_manager import WatchlistManager

# pyright: reportOptionalMemberAccess=false,reportAttributeAccessIssue=false,reportArgumentType=false

# Import services
from src.services.llm_strategy import analyze_and_suggest
from src.services.performance_tracker import track_performance
from src.services.db_service import get_performance_stats, init_db, get_suggestion_details, get_setting, set_setting
from src.services.db_service import get_suggestions_between_dates, get_last_analyzed_symbols
from src.services.binance_permissions_service import permissions_service
from src.services.market_data_service import get_top_volume_pairs, validate_trading_pair
from src.services.signal_service import SignalService

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
watchlist_manager = WatchlistManager()
signal_service = SignalService(chat_id=TELEGRAM_CHAT_ID, watchlist_manager=watchlist_manager)

# Initialize DB
init_db()


def set_pending_prompt(context, prompt_type: str) -> None:
    user_data = context.user_data
    if user_data is None:
        user_data = {}
        context.user_data = user_data
    user_data['pending_prompt'] = prompt_type


def pop_pending_prompt(context):
    user_data = context.user_data
    if not user_data:
        return None
    return user_data.pop('pending_prompt', None)

async def get_main_menu_markup():
    """Returns the main menu keyboard markup dynamic with last 5 used symbols."""
    last_symbols = await asyncio.to_thread(get_last_analyzed_symbols, 5)
    
    alerts_enabled = await asyncio.to_thread(get_setting, "volume_alerts_enabled", "True") == "True"
    alerts_text = "🔔 Alerts: ON" if alerts_enabled else "🔕 Alerts: OFF"
    
    keyboard = []
    # Add buttons for last analyzed symbols
    for symbol in last_symbols:
        keyboard.append([InlineKeyboardButton(f"🔍 Analyze {symbol}", callback_data=f"menu_analyze_{symbol}")])

    # Add utility buttons
    keyboard.append([InlineKeyboardButton("✍️ Analyze, enter pair symbol", callback_data="menu_new_analyze")])
    keyboard.append([
        InlineKeyboardButton("📊 History", callback_data="menu_history"),
        InlineKeyboardButton(alerts_text, callback_data="menu_toggle_alerts")
    ])
    keyboard.append([InlineKeyboardButton("📜 List Restricted Pairs", callback_data="menu_list_restricted")])
    keyboard.append([
        InlineKeyboardButton("➕ Watch Symbol", callback_data="menu_watch_intro"),
        InlineKeyboardButton("➖ Unwatch Symbol", callback_data="menu_unwatch_intro")
    ])
    keyboard.append([
        InlineKeyboardButton("🪄 Run Signals", callback_data="menu_run_signals"),
        InlineKeyboardButton("📚 List Watchlist", callback_data="menu_list_watch")
    ])
    keyboard.append([InlineKeyboardButton("📊 High Volume Pairs", callback_data="menu_high_volume")])

    return InlineKeyboardMarkup(keyboard)

async def prompt_new_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts the user to type a new symbol using ForceReply."""
    set_pending_prompt(context, 'analyze')
    await update.effective_message.reply_text(
        "Please type the symbol you want to analyze (e.g., SOLUSDC):",
        reply_markup=ForceReply(selective=True)
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the command /start is issued."""
    markup = await get_main_menu_markup()
    await update.effective_message.reply_text(
        'Hi! I am your crypto volume alert bot. Use the buttons below or see /help for commands.',
        reply_markup=markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /help is issued."""
    help_text = (
        "Available commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/watch <SYMBOL> - Add a pair to the signal watchlist\n"
        "/unwatch <SYMBOL> - Remove a pair from the watchlist\n"
        "/list_watch - Show current watchlist\n"
        "/list_restricted - List all restricted trading pairs\n"
        "/unrestrict <SYMBOL> - Unrestrict a specific trading pair\n"
        "/analyze <SYMBOL> - Get AI strategy (alias: /a)\n"
        "/history - Show trading performance stats\n"
        "/alerts - Toggle volume alerts on/off\n"
    )
    markup = await get_main_menu_markup()
    await update.effective_message.reply_text(help_text, reply_markup=markup)

async def list_restricted(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all restricted trading pairs."""
    restricted = symbol_manager.get_excluded_symbols()
    if restricted:
        message = "Restricted pairs:\n" + "\n".join(sorted(list(restricted)))
    else:
        message = "No trading pairs are currently restricted."
    
    # Use effective_message which works for both message and callback_query
    await update.effective_message.reply_text(message)

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

async def high_volume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_msg = await update.effective_message.reply_text("🔍 Fetching top volume pairs from Binance...")
    
    pairs = await asyncio.to_thread(get_top_volume_pairs, limit=20)
    
    if not pairs:
        await status_msg.edit_text("❌ Failed to fetch top volume pairs.")
        return
        
    lines = ["📊 <b>Top 20 Binance Pairs (24h Volume)</b>\n"]
    for i, p in enumerate(pairs, 1):
        lines.append(f"{i}. <code>{p['symbol']}</code>: ${p['volume']:,.0f}")
        
    await status_msg.edit_text("\n".join(lines), parse_mode='HTML')

async def watch_pair(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Usage: /watch <SYMBOL>")
        return
    symbol = context.args[0].upper()
    is_valid, reason = await asyncio.to_thread(validate_trading_pair, symbol)
    if not is_valid:
        if reason == "invalid_symbol":
            await update.effective_message.reply_text(
                "❌ Invalid trading pair. Please provide a Binance pair symbol like BTCUSDC."
            )
        elif reason == "not_permitted":
            trading_group = permissions_service.trading_group or "your trading group"
            await update.effective_message.reply_text(
                f"❌ {symbol} is not enabled for {trading_group}. Binance only allows pairs returned by /api/v3/exchangeInfo?permissions={trading_group}."
            )
        else:
            await update.effective_message.reply_text(
                "⚠️ Unable to verify the symbol right now. Please try again later."
            )
        return
    if watchlist_manager.add_symbol(symbol):
        await update.effective_message.reply_text(f"✅ Added {symbol} to signal watchlist.")
    else:
        await update.effective_message.reply_text(f"ℹ️ {symbol} is already in watchlist.")

async def unwatch_pair(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Usage: /unwatch <SYMBOL>")
        return
    symbol = context.args[0].upper()
    if watchlist_manager.remove_symbol(symbol):
        await update.effective_message.reply_text(f"✅ Removed {symbol} from signal watchlist.")
    else:
        await update.effective_message.reply_text(f"ℹ️ {symbol} not in watchlist.")

async def list_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    watchlist = watchlist_manager.get_watchlist()
    if not watchlist:
        await update.effective_message.reply_text("Signal watchlist is empty.")
    else:
        await update.effective_message.reply_text("🔭 <b>Signal Watchlist:</b>\n" + "\n".join(watchlist), parse_mode='HTML')


async def run_signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = [arg.lower() for arg in context.args] if context.args else []
    timeframes = []
    if not args or 'hourly' in args:
        timeframes.append('1h')
    if not args or 'daily' in args:
        timeframes.append('1d')

    notifications = []
    for tf in timeframes:
        await update.effective_message.reply_text(f"Running {tf} signal check...")
        await signal_service.check_signals(timeframe=tf)
        notifications.append(f"{tf} done")

    await update.effective_message.reply_text("Signal checks completed: " + ", ".join(notifications))


async def prompt_watch_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    set_pending_prompt(context, 'watch')
    await update.effective_message.reply_text(
        "Please reply with the trading pair symbol (e.g., BTCUSDC) to add it to the watchlist.",
        reply_markup=ForceReply(selective=True)
    )


async def prompt_unwatch_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    set_pending_prompt(context, 'unwatch')
    await update.effective_message.reply_text(
        "Please reply with the trading pair symbol (e.g., BTCUSDC) to remove it from the watchlist.",
        reply_markup=ForceReply(selective=True)
    )

async def restrict_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles callback queries from inline buttons to restrict a pair."""
    query = update.callback_query
    await query.answer() # Acknowledge the callback query

    symbol_to_restrict = query.data.replace("restrict_", "")
    if symbol_manager.add_symbol(symbol_to_restrict):
        await query.edit_message_text(text=f"Successfully restricted {symbol_to_restrict}.")
    else:
        await query.edit_message_text(text=f"{symbol_to_restrict} is already restricted.")

async def debug_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs every incoming message and handles ForceReply inputs."""
    if not update.message:
        return

    if update.message.text:
        user_text = update.message.text.strip()
        logger.info(f"DEBUG: Received message from {update.effective_user.username}: {user_text}")
        
        pending_prompt = pop_pending_prompt(context)
        reply = update.message.reply_to_message
        if reply:
            logger.info(f"DEBUG: Message is a reply to: '{reply.text}'")

        if pending_prompt:
            symbol = user_text.upper()
            if pending_prompt == 'analyze':
                logger.info(f"DEBUG: Recognized symbol from prompt reply: {symbol}")
                context.args = [symbol]
                await analyze_symbol(update, context)
                return
            if pending_prompt == 'watch':
                context.args = [symbol]
                await watch_pair(update, context)
                return
            if pending_prompt == 'unwatch':
                context.args = [symbol]
                await unwatch_pair(update, context)
                return

    elif update.callback_query:
        logger.info(f"DEBUG: Received callback query from {update.effective_user.username}: {update.callback_query.data}")

async def analyze_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Analyzes a symbol using AI strategy."""
    logger.info(f"DEBUG: analyze_symbol reached with args: {context.args}")
    if not context.args:
        await update.effective_message.reply_text("Usage: /analyze <SYMBOL> (e.g., /analyze BTCUSDC)")
        return

    symbol = context.args[0].upper()
    logger.info(f"DEBUG: Processing analysis for symbol: {symbol}")
    
    status_msg = await update.effective_message.reply_text(f"🔍 Analyzing {symbol}... This may take a moment.")

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


async def signal_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    parts = query.data.split("|")
    if len(parts) != 3:
        await query.edit_message_text(text="❌ Unable to parse signal details payload.")
        return

    _, symbol, timeframe = parts
    details = signal_service.get_signal_context(symbol, timeframe)

    if not details:
        await query.edit_message_text(text="❌ Signal explanation not available for this pair/timeframe.")
        return

    explanation = details.get('explanation', 'No additional context available.')
    generated_at = details.get('generated_at')
    generated_str = generated_at.strftime('%Y-%m-%d %H:%M:%S') if generated_at else 'Unknown time'

    message = (
        f"🧾 <b>{symbol} {timeframe} Signal Breakdown</b>\n\n"
        f"<b>Action</b>: {details.get('signal', 'N/A')}\n"
        f"{html.escape(explanation)}\n\n"
        f"<i>Generated: {generated_str}</i>"
    )

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
        f"Simulated Trades: {stats['total_trades']}\n"
        f"Wins: {stats['wins']}\n"
        f"Losses: {stats['losses']}\n"
        f"Win Rate: {stats['win_rate']:.1f}%\n"
        f"Avg PnL: {stats['avg_pnl']:.2f}%"
    )

    keyboard = [
        [InlineKeyboardButton("📜 View Simulated Trade Details", callback_data=f"history_details|{start_iso}|{end_iso}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.effective_message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)


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
        end_date=end_token or None,
        completed_only=True
    )

    if not results:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="No analysis records found for the selected range."
        )
        return

    lines = ["📜 **Last 10 Completed Simulated Trades**"]
    for row in results:
        ts = row['created_at'][:19]
        status = row['status']
        pnl = row['pnl_percent']
        symbol = row['symbol']
        act = row['strategy_type']
        pnl_str = f"+{pnl:.2f}%" if pnl and pnl > 0 else f"{pnl:.2f}%" if pnl else "N/A"
        lines.append(f"{ts} — {symbol} ({act}) {status} [{pnl_str}]")

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="\n".join(lines),
        parse_mode='Markdown'
    )

async def toggle_alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    alerts_enabled = await asyncio.to_thread(get_setting, "volume_alerts_enabled", "True") == "True"
    new_state = "False" if alerts_enabled else "True"
    await asyncio.to_thread(set_setting, "volume_alerts_enabled", new_state)
    
    state_text = "ENABLED" if new_state == "True" else "DISABLED"
    markup = await get_main_menu_markup()
    await update.effective_message.reply_text(f"Volume alerts are now {state_text}.", reply_markup=markup)

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles callback queries from the main menu buttons."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("menu_analyze_"):
        symbol = data.replace("menu_analyze_", "")
        context.args = [symbol]
        await analyze_symbol(update, context)
    elif data == "menu_history":
        context.args = [] # Clear args for show_history
        await show_history(update, context)
    elif data == "menu_list_restricted":
        await list_restricted(update, context)
    elif data == "menu_toggle_alerts":
        alerts_enabled = await asyncio.to_thread(get_setting, "volume_alerts_enabled", "True") == "True"
        new_state = "False" if alerts_enabled else "True"
        await asyncio.to_thread(set_setting, "volume_alerts_enabled", new_state)

        markup = await get_main_menu_markup()
        state_text = "ON" if new_state == "True" else "OFF"
        await query.edit_message_reply_markup(reply_markup=markup)
        await query.answer(f"Volume alerts turned {state_text}")
    elif data == "menu_new_analyze":
        await prompt_new_analysis(update, context)
    elif data == "menu_watch_intro":
        await prompt_watch_symbol(update, context)
    elif data == "menu_unwatch_intro":
        await prompt_unwatch_symbol(update, context)
    elif data == "menu_run_signals":
        await run_signals_command(update, context)
    elif data == "menu_list_watch":
        await list_watch(update, context)
    elif data == "menu_high_volume":
        await high_volume(update, context)

async def run_tracker(context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"[{datetime.now()}] Running background performance tracker...")
    await asyncio.to_thread(track_performance)

async def run_hourly_signals(context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"[{datetime.now()}] Running background hourly signal check...")
    signal_service.bot_context = context
    await signal_service.check_signals(timeframe='1h')

async def run_daily_signals(context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"[{datetime.now()}] Running background daily signal check...")
    signal_service.bot_context = context
    await signal_service.check_signals(timeframe='1d')

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
    application.add_handler(CommandHandler("a", analyze_symbol)) # Shorthand
    application.add_handler(CommandHandler("history", show_history))
    application.add_handler(CommandHandler("alerts", toggle_alerts_command))
    application.add_handler(CommandHandler("high_volume", high_volume))
    application.add_handler(CommandHandler("watch", watch_pair))
    application.add_handler(CommandHandler("unwatch", unwatch_pair))
    application.add_handler(CommandHandler("list_watch", list_watch))
    application.add_handler(CommandHandler("run_signals", run_signals_command))
    
    application.add_handler(CallbackQueryHandler(restrict_callback, pattern="^restrict_"))
    application.add_handler(CallbackQueryHandler(details_callback, pattern="^details_"))
    application.add_handler(CallbackQueryHandler(signal_details_callback, pattern="^signal_details"))
    application.add_handler(CallbackQueryHandler(history_details_callback, pattern="^history_details"))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))

    # Register debug message handler (filters out commands to avoid double logging if desired, 
    # but here we want to see EVERYTHING)
    application.add_handler(MessageHandler(filters.ALL, debug_message_handler), group=-1)

    # Register error handler
    application.add_error_handler(error_handler)

    job_queue = application.job_queue
    job_queue.run_repeating(run_tracker, interval=1800, first=10)
    test_mode = os.getenv('SIGNAL_TEST_MODE', 'False').lower() == 'true'
    hourly_interval = 60 if test_mode else 3600
    daily_interval = 180 if test_mode else 86400
    job_queue.run_repeating(run_hourly_signals, interval=hourly_interval, first=20)
    job_queue.run_repeating(run_daily_signals, interval=daily_interval, first=30)

    # Run the bot until the user presses Ctrl-C
    print(f"[{datetime.now()}] Telegram bot started with AI Strategy Advisor. Listening for updates...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
