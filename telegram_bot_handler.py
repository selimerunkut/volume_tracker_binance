import os
import json
import asyncio
import html
import logging
import inspect
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import BadRequest, TelegramError
from symbol_manager import SymbolManager
from src.services.watchlist_manager import WatchlistManager

# pyright: reportOptionalMemberAccess=false,reportAttributeAccessIssue=false,reportArgumentType=false

# Import services
from src.services.llm_strategy import analyze_and_suggest
from src.services.performance_tracker import track_performance
from src.services.db_service import get_performance_stats, init_db, get_suggestion_details, get_setting, set_setting
from src.services.db_service import get_suggestions_between_dates, get_last_analyzed_symbols
from src.services.alert_preferences import (
    get_alert_exchange_selection,
    normalize_alert_exchange_selection,
    set_alert_exchange_selection,
)
from src.services.binance_permissions_service import permissions_service
from src.services.market_data_service import get_top_volume_pairs, validate_trading_pair
from src.services.signal_service import SignalService
from src.exchanges.registry import get_exchange, get_supported_exchange_names

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


def set_pending_flow(context, action: str, symbol: str | None = None) -> None:
    user_data = context.user_data
    if user_data is None:
        user_data = {}
        context.user_data = user_data
    user_data['pending_action'] = action
    if symbol:
        user_data['pending_symbol'] = symbol.upper()
    else:
        user_data.pop('pending_symbol', None)
    user_data.pop('pending_prompt', None)
    user_data.pop('pending_scope', None)


def clear_pending_flow(context) -> None:
    user_data = context.user_data
    if not user_data:
        return
    for key in ('pending_action', 'pending_symbol', 'pending_prompt', 'pending_scope'):
        user_data.pop(key, None)


def get_pending_action(context):
    user_data = context.user_data or {}
    return user_data.get('pending_action')


def get_pending_symbol(context):
    user_data = context.user_data or {}
    symbol = user_data.get('pending_symbol')
    if symbol:
        return str(symbol).upper()
    return None


def get_pending_scope(context):
    user_data = context.user_data or {}
    return normalize_alert_exchange_selection(user_data.get('pending_scope'))


def get_pending_scope_raw(context):
    user_data = context.user_data or {}
    return user_data.get('pending_scope')


def has_pending_scope(context) -> bool:
    user_data = context.user_data or {}
    return 'pending_scope' in user_data


def set_pending_scope(context, scope):
    user_data = context.user_data
    if user_data is None:
        user_data = {}
        context.user_data = user_data
    user_data['pending_scope'] = normalize_alert_exchange_selection(scope)


def get_scope_summary(selection):
    normalized = normalize_alert_exchange_selection(selection)
    if normalized['mode'] == 'all':
        return "🌍 Current scope: all exchanges"
    if len(normalized['exchanges']) == 1:
        return f"🎯 Current scope: single exchange ({normalized['exchanges'][0].upper()})"
    return f"🗂 Current scope: multiple exchanges ({format_exchange_names(normalized['exchanges'])})"


def _flow_prompt_copy(action: str):
    return {
        'analyze': {
            'root': "Choose the exchange scope for this analysis.",
            'single': "Choose one exchange for this analysis.",
            'multiple': "Select one or more exchanges for this analysis.",
            'symbol': "Send the trading pair symbol to analyze, for example BTCUSDC or BTCUSD.",
        },
        'watch': {
            'root': "Choose the exchange scope for the symbol you want to watch.",
            'single': "Choose one exchange for this watchlist entry.",
            'multiple': "Select one or more exchanges for this watchlist entry.",
            'symbol': "Send the trading pair symbol to watch.",
        },
        'unwatch': {
            'root': "Choose the exchange scope for the symbol you want to remove.",
            'single': "Choose one exchange for this removal.",
            'multiple': "Select one or more exchanges for this removal.",
            'symbol': "Send the trading pair symbol to remove from watchlist.",
        },
        'list': {
            'root': "Choose which exchange watchlist you want to view.",
            'single': "Choose one exchange to view.",
            'multiple': "Select one or more exchanges to view.",
            'symbol': None,
        },
    }[action]


def build_scope_markup(action, selection=None, view='root'):
    normalized = normalize_alert_exchange_selection(selection)
    supported = get_supported_exchange_names()
    keyboard = []

    if view == 'root':
        keyboard.append([InlineKeyboardButton("🌍 All exchanges", callback_data=f"scope|{action}|mode|all")])
        keyboard.append([InlineKeyboardButton("🎯 Single exchange", callback_data=f"scope|{action}|view|single")])
        keyboard.append([InlineKeyboardButton("🗂 Multiple exchanges", callback_data=f"scope|{action}|view|multiple")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to main menu", callback_data=f"scope|{action}|main")])
        return InlineKeyboardMarkup(keyboard)

    if view == 'single':
        for exchange_name in supported:
            label = f"☑ {exchange_name.upper()}" if normalized['mode'] == 'selected' and normalized['exchanges'] == [exchange_name] else exchange_name.upper()
            keyboard.append([InlineKeyboardButton(label, callback_data=f"scope|{action}|set|single|{exchange_name}")])
        keyboard.append([
            InlineKeyboardButton("🌍 All exchanges", callback_data=f"scope|{action}|mode|all"),
            InlineKeyboardButton("🗂 Multiple exchanges", callback_data=f"scope|{action}|view|multiple"),
        ])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"scope|{action}|view|root")])
        return InlineKeyboardMarkup(keyboard)

    if view == 'multiple':
        for exchange_name in supported:
            checked = normalized['mode'] == 'all' or exchange_name in normalized['exchanges']
            label = f"{'☑' if checked else '☐'} {exchange_name.upper()}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"scope|{action}|toggle|{exchange_name}")])
        keyboard.append([InlineKeyboardButton("🌍 All exchanges", callback_data=f"scope|{action}|mode|all")])
        keyboard.append([
            InlineKeyboardButton("✅ Done", callback_data=f"scope|{action}|done"),
            InlineKeyboardButton("⬅️ Back", callback_data=f"scope|{action}|view|root"),
        ])
        return InlineKeyboardMarkup(keyboard)

    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"scope|{action}|view|root")]])


def render_scope_message(action, selection=None, view='root'):
    prompt_copy = _flow_prompt_copy(action)
    summary = get_scope_summary(selection)
    if view == 'root':
        return f"{summary}\n\n{prompt_copy['root']}"
    if view == 'single':
        return f"{summary}\n\n{prompt_copy['single']}"
    if view == 'multiple':
        return f"{summary}\n\n{prompt_copy['multiple']}"
    return f"{summary}\n\n{prompt_copy['root']}"


async def safe_edit_message_text(query, text, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except BadRequest as err:
        if "Message is not modified" not in str(err):
            raise


async def prompt_scoped_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, symbol: str | None = None) -> None:
    set_pending_flow(context, action, symbol=symbol)
    selection = get_pending_scope(context)
    markup = build_scope_markup(action, selection, view='root')
    message = render_scope_message(action, selection, view='root')
    if update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=markup)
    else:
        await update.effective_message.reply_text(message, reply_markup=markup)


def get_flow_exchanges(scope):
    normalized = normalize_alert_exchange_selection(scope)
    if normalized['mode'] == 'all':
        return get_supported_exchange_names()
    return normalized['exchanges']


async def complete_scoped_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    scope = get_pending_scope_raw(context)
    symbol = get_pending_symbol(context)

    if scope is None:
        await prompt_scoped_flow(update, context, action, symbol=symbol)
        return

    if action == 'list':
        await list_watch(update, context, scope=scope)
        return

    if not symbol:
        set_pending_prompt(context, action)
        prompt_text = _flow_prompt_copy(action)['symbol']
        if update.callback_query:
            await safe_edit_message_text(update.callback_query, prompt_text)
        else:
            await update.effective_message.reply_text(prompt_text)
        return

    if action == 'analyze':
        await analyze_symbol(update, context, symbol=symbol, exchange_scope=scope)
    elif action == 'watch':
        await watch_pair(update, context, symbol=symbol, exchange_scope=scope)
    elif action == 'unwatch':
        await unwatch_pair(update, context, symbol=symbol, exchange_scope=scope)

def format_exchange_names(exchange_names):
    return ", ".join(name.upper() for name in exchange_names)


def get_alert_scope_summary(selection):
    normalized = normalize_alert_exchange_selection(selection)
    if normalized['mode'] == 'all':
        return "🌍 Current alert scope: all exchanges"
    if len(normalized['exchanges']) == 1:
        return f"🎯 Current alert scope: single exchange ({normalized['exchanges'][0].upper()})"
    return f"🗂 Current alert scope: multiple exchanges ({format_exchange_names(normalized['exchanges'])})"


def build_alert_scope_markup(selection=None, view='root'):
    normalized = normalize_alert_exchange_selection(selection)
    supported = get_supported_exchange_names()
    keyboard = []

    if view == 'root':
        keyboard.append([InlineKeyboardButton("🌍 All exchanges", callback_data="alertscope_mode|all")])
        keyboard.append([InlineKeyboardButton("🎯 Single exchange", callback_data="alertscope_view|single")])
        keyboard.append([InlineKeyboardButton("🗂 Multiple exchanges", callback_data="alertscope_view|multiple")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to main menu", callback_data="alertscope_view|main")])
        return InlineKeyboardMarkup(keyboard)

    if view == 'single':
        for exchange_name in supported:
            label = f"☑ {exchange_name.upper()}" if normalized['mode'] == 'selected' and normalized['exchanges'] == [exchange_name] else exchange_name.upper()
            keyboard.append([InlineKeyboardButton(label, callback_data=f"alertscope_set|single|{exchange_name}")])
        keyboard.append([
            InlineKeyboardButton("🌍 All exchanges", callback_data="alertscope_mode|all"),
            InlineKeyboardButton("🗂 Multiple exchanges", callback_data="alertscope_view|multiple"),
        ])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="alertscope_view|root")])
        return InlineKeyboardMarkup(keyboard)

    if view == 'multiple':
        for exchange_name in supported:
            checked = normalized['mode'] == 'all' or exchange_name in normalized['exchanges']
            label = f"{'☑' if checked else '☐'} {exchange_name.upper()}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"alertscope_toggle|{exchange_name}")])
        keyboard.append([InlineKeyboardButton("🌍 All exchanges", callback_data="alertscope_mode|all")])
        keyboard.append([
            InlineKeyboardButton("✅ Done", callback_data="alertscope_view|root"),
            InlineKeyboardButton("⬅️ Back", callback_data="alertscope_view|root"),
        ])
        return InlineKeyboardMarkup(keyboard)

    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="alertscope_view|root")]])


def render_alert_scope_message(selection, view='root'):
    normalized = normalize_alert_exchange_selection(selection)
    summary = get_alert_scope_summary(normalized)

    if view == 'single':
        return (
            f"{summary}\n\n"
            "Choose one exchange. This keeps alerts limited to a single venue."
        )

    if view == 'multiple':
        exchange_list = format_exchange_names(get_supported_exchange_names())
        return (
            f"{summary}\n\n"
            f"Toggle any subset of these exchanges: {exchange_list}.\n"
            "If you select every exchange, the scope will collapse to all exchanges."
        )

    return (
        f"{summary}\n\n"
        "Choose how Telegram alerts should be routed. You can keep one exchange selected, add more supported exchanges, or select all supported exchanges."
    )


def parse_alert_scope_args(args):
    supported = set(get_supported_exchange_names())
    if not args:
        return None

    lowered = [arg.lower() for arg in args]
    if lowered[0] in {'all', 'every', 'everything'}:
        return 'all'

    if lowered[0] in {'single', 'one'}:
        if len(args) < 2:
            raise ValueError("Usage: /alerts_scope single <exchange>")
        candidate = args[1].lower()
        if candidate not in supported:
            raise ValueError(f"Unsupported exchange: {args[1]}. Supported exchanges: {format_exchange_names(get_supported_exchange_names())}")
        return candidate

    if lowered[0] in {'multiple', 'multi'}:
        candidates = args[1:]
    else:
        candidates = args

    normalized = []
    for candidate in candidates:
        lowered_candidate = candidate.lower()
        if lowered_candidate in supported and lowered_candidate not in normalized:
            normalized.append(lowered_candidate)

    if not normalized:
        raise ValueError(f"Supported exchanges: {format_exchange_names(get_supported_exchange_names())}")

    return normalized

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
    keyboard.append([InlineKeyboardButton("🎛 Alert Exchanges", callback_data="menu_alert_scope")])
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
        "/alerts_scope [all|single <exchange>|multiple <exchanges...>] - Set alert exchanges\n"
        "\nNote: /analyze, /watch, /unwatch, and /list_watch will ask you to choose a supported exchange or all exchanges before proceeding.\n"
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

async def watch_pair(update: Update, context: ContextTypes.DEFAULT_TYPE, symbol: str | None = None, exchange_scope=None) -> None:
    if symbol is None and context.args:
        symbol = context.args[0].upper()
    elif symbol is not None:
        symbol = symbol.upper()
    else:
        symbol = get_pending_symbol(context)

    scope = exchange_scope if exchange_scope is not None else get_pending_scope_raw(context)
    if scope is None:
        await prompt_scoped_flow(update, context, 'watch', symbol=symbol)
        return

    if not symbol:
        set_pending_prompt(context, 'watch')
        await update.effective_message.reply_text(
            _flow_prompt_copy('watch')['symbol'],
            reply_markup=ForceReply(selective=True)
        )
        return

    exchanges = get_flow_exchanges(scope)
    if not exchanges:
        exchanges = get_supported_exchange_names()

    results = []
    for exchange_name in exchanges:
        is_valid, reason = await asyncio.to_thread(validate_trading_pair, symbol, exchange_name=exchange_name)
        if not is_valid:
            if reason == "invalid_symbol":
                results.append(f"{exchange_name.upper()}: invalid trading pair")
            elif reason == "not_permitted":
                trading_group = permissions_service.trading_group or "your trading group"
                results.append(
                    f"{exchange_name.upper()}: not enabled for {trading_group}"
                )
            else:
                results.append(f"{exchange_name.upper()}: unable to verify symbol")
            continue

        added = watchlist_manager.add_symbol(symbol, exchange_name=exchange_name)
        if added:
            results.append(f"{exchange_name.upper()}: added {symbol}")
        else:
            results.append(f"{exchange_name.upper()}: already watching {symbol}")

    clear_pending_flow(context)
    await update.effective_message.reply_text("✅ Watchlist update:\n" + "\n".join(results))

async def unwatch_pair(update: Update, context: ContextTypes.DEFAULT_TYPE, symbol: str | None = None, exchange_scope=None) -> None:
    if symbol is None and context.args:
        symbol = context.args[0].upper()
    elif symbol is not None:
        symbol = symbol.upper()
    else:
        symbol = get_pending_symbol(context)

    scope = exchange_scope if exchange_scope is not None else get_pending_scope_raw(context)
    if scope is None:
        await prompt_scoped_flow(update, context, 'unwatch', symbol=symbol)
        return

    if not symbol:
        set_pending_prompt(context, 'unwatch')
        await update.effective_message.reply_text(
            _flow_prompt_copy('unwatch')['symbol'],
            reply_markup=ForceReply(selective=True)
        )
        return

    exchanges = get_flow_exchanges(scope)
    if not exchanges:
        exchanges = get_supported_exchange_names()

    results = []
    for exchange_name in exchanges:
        removed = watchlist_manager.remove_symbol(symbol, exchange_name=exchange_name)
        if removed:
            results.append(f"{exchange_name.upper()}: removed {symbol}")
        else:
            results.append(f"{exchange_name.upper()}: not in watchlist")

    clear_pending_flow(context)
    await update.effective_message.reply_text("✅ Watchlist removal:\n" + "\n".join(results))

async def list_watch(update: Update, context: ContextTypes.DEFAULT_TYPE, scope=None) -> None:
    selection = normalize_alert_exchange_selection(scope or get_pending_scope_raw(context))
    if scope is None and not has_pending_scope(context):
        await prompt_scoped_flow(update, context, 'list')
        return

    watchlists = watchlist_manager.get_watchlists()
    exchanges = get_flow_exchanges(selection)
    if not exchanges:
        exchanges = get_supported_exchange_names()

    lines = ["🔭 <b>Signal Watchlist:</b>"]
    has_any = False
    for exchange_name in exchanges:
        symbols = watchlists.get(exchange_name, [])
        if not symbols:
            continue
        has_any = True
        lines.append(f"\n<b>{exchange_name.upper()}</b>")
        for symbol in symbols:
            lines.append(symbol)

    clear_pending_flow(context)

    if not has_any:
        await update.effective_message.reply_text("No watched pairs found for the selected exchange scope.")
        return

    await update.effective_message.reply_text("\n".join(lines), parse_mode='HTML')


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
                await analyze_symbol(update, context, symbol=symbol)
                return
            if pending_prompt == 'watch':
                context.args = [symbol]
                await watch_pair(update, context, symbol=symbol)
                return
            if pending_prompt == 'unwatch':
                context.args = [symbol]
                await unwatch_pair(update, context, symbol=symbol)
                return

    elif update.callback_query:
        logger.info(f"DEBUG: Received callback query from {update.effective_user.username}: {update.callback_query.data}")

async def analyze_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE, symbol: str | None = None, exchange_scope=None) -> None:
    """Analyzes a symbol using AI strategy."""
    logger.info(f"DEBUG: analyze_symbol reached with args: {getattr(context, 'args', [])}")
    if symbol is None and context.args:
        symbol = context.args[0].upper()
    elif symbol is not None:
        symbol = symbol.upper()
    else:
        symbol = get_pending_symbol(context)

    pending_scope = exchange_scope if exchange_scope is not None else get_pending_scope_raw(context)
    if pending_scope is None:
        await prompt_scoped_flow(update, context, 'analyze', symbol=symbol)
        return
    if not symbol:
        set_pending_prompt(context, 'analyze')
        await update.effective_message.reply_text(
            _flow_prompt_copy('analyze')['symbol'],
            reply_markup=ForceReply(selective=True)
        )
        return

    exchanges = get_flow_exchanges(pending_scope)
    if not exchanges:
        exchanges = get_supported_exchange_names()

    logger.info(f"DEBUG: Processing analysis for symbol: {symbol} on {exchanges}")
    progress_text = f"🔍 Analyzing {symbol} on {format_exchange_names(exchanges)}... This may take a moment."
    if update.callback_query:
        status_editor = update.callback_query
        await safe_edit_message_text(status_editor, progress_text)
    else:
        status_editor = await update.effective_message.reply_text(progress_text)

    try:
        responses = []
        reply_markup = None
        for exchange_name in exchanges:
            strategy_candidate = await asyncio.to_thread(analyze_and_suggest, symbol, exchange_name=exchange_name)
            if inspect.isawaitable(strategy_candidate):
                strategy = await strategy_candidate
            else:
                strategy = strategy_candidate
            if not strategy:
                responses.append(f"{exchange_name.upper()}: failed to analyze")
                continue

            if "error" in strategy:
                responses.append(f"{exchange_name.upper()}: error - {html.escape(str(strategy['error']))}")
                continue

            action = html.escape(str(strategy.get('action', 'N/A')))
            confidence = strategy.get('confidence', 0)
            reasoning = html.escape(str(strategy.get('reasoning', 'N/A')))

            response = (
                f"🤖 <b>{exchange_name.upper()} strategy for {symbol}</b>\n\n"
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
            responses.append(response)

            if strategy.get('suggestion_id') and reply_markup is None:
                keyboard = [
                    [InlineKeyboardButton("📜 View Analysis Details", callback_data=f"details_{strategy['suggestion_id']}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

        if not responses:
            if update.callback_query:
                await safe_edit_message_text(status_editor, f"❌ Failed to analyze {symbol}. Check logs or try again.")
            else:
                await status_editor.edit_text(f"❌ Failed to analyze {symbol}. Check logs or try again.")
            clear_pending_flow(context)
            return

        if update.callback_query:
            await safe_edit_message_text(status_editor, "\n\n".join(responses), parse_mode='HTML', reply_markup=reply_markup)
        else:
            await status_editor.edit_text("\n\n".join(responses), parse_mode='HTML', reply_markup=reply_markup)
        clear_pending_flow(context)

    except Exception as e:
        logger.error(f"Unexpected error in analyze_symbol: {e}")
        try:
            error_text = f"❌ An unexpected error occurred: {html.escape(str(e))}"
            if update.callback_query:
                await safe_edit_message_text(status_editor, error_text)
            else:
                await status_editor.edit_text(error_text)
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


async def alerts_scope_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        await update.effective_message.reply_text("Unable to determine the chat scope for alert preferences.")
        return

    try:
        selection = parse_alert_scope_args(context.args or [])
    except ValueError as err:
        await update.effective_message.reply_text(str(err))
        return

    if selection is not None:
        selection = set_alert_exchange_selection(chat.id, selection)

    current_selection = await asyncio.to_thread(get_alert_exchange_selection, chat.id)
    markup = build_alert_scope_markup(current_selection, view='root')
    await update.effective_message.reply_text(
        render_alert_scope_message(current_selection, view='root'),
        reply_markup=markup,
    )


async def alert_scope_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    chat = query.message.chat if query.message else None
    if not chat:
        await query.edit_message_text("Unable to determine the chat scope for alert preferences.")
        return

    data = query.data.split("|")
    action = data[0]
    selection = await asyncio.to_thread(get_alert_exchange_selection, chat.id)

    if action == 'alertscope_mode':
        mode = data[1] if len(data) > 1 else 'all'
        if mode == 'all':
            selection = await asyncio.to_thread(set_alert_exchange_selection, chat.id, 'all')
            try:
                await query.edit_message_text(
                    render_alert_scope_message(selection, view='root'),
                    reply_markup=build_alert_scope_markup(selection, view='root'),
                )
            except BadRequest as err:
                if "Message is not modified" not in str(err):
                    raise
            return

    if action == 'alertscope_set':
        mode = data[1] if len(data) > 1 else 'single'
        exchange_name = data[2] if len(data) > 2 else ''
        if mode == 'single' and exchange_name:
            selection = await asyncio.to_thread(set_alert_exchange_selection, chat.id, exchange_name)
            try:
                await query.edit_message_text(
                    render_alert_scope_message(selection, view='root'),
                    reply_markup=build_alert_scope_markup(selection, view='root'),
                )
            except BadRequest as err:
                if "Message is not modified" not in str(err):
                    raise
            return

    if action == 'alertscope_toggle':
        exchange_name = data[1] if len(data) > 1 else ''
        if not exchange_name:
            await query.edit_message_text("❌ Unable to parse exchange selection.")
            return

        normalized = normalize_alert_exchange_selection(selection)
        supported = get_supported_exchange_names()
        if normalized['mode'] == 'all':
            selected = [name for name in supported if name != exchange_name]
        else:
            selected = list(normalized['exchanges'])
            if exchange_name in selected:
                selected.remove(exchange_name)
            else:
                selected.append(exchange_name)

        if not selected:
            selected = 'all'
        elif len(selected) == 1:
            selected = selected[0]
        elif set(selected) == set(supported):
            selected = 'all'

        selection = await asyncio.to_thread(set_alert_exchange_selection, chat.id, selected)
        try:
            await query.edit_message_text(
                render_alert_scope_message(selection, view='multiple'),
                reply_markup=build_alert_scope_markup(selection, view='multiple'),
            )
        except BadRequest as err:
            if "Message is not modified" not in str(err):
                raise
        return

    if action == 'alertscope_view':
        view = data[1] if len(data) > 1 else 'root'
        if view == 'main':
            markup = await get_main_menu_markup()
            try:
                await query.edit_message_text(
                    "Back to the main menu.",
                    reply_markup=markup,
                )
            except BadRequest as err:
                if "Message is not modified" not in str(err):
                    raise
            return

        try:
            await query.edit_message_text(
                render_alert_scope_message(selection, view=view),
                reply_markup=build_alert_scope_markup(selection, view=view),
            )
        except BadRequest as err:
            if "Message is not modified" not in str(err):
                raise
        return

    try:
        await query.edit_message_text(
            render_alert_scope_message(selection, view='root'),
            reply_markup=build_alert_scope_markup(selection, view='root'),
        )
    except BadRequest as err:
        if "Message is not modified" not in str(err):
            raise

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles callback queries from the main menu buttons."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("menu_analyze_"):
        symbol = data.replace("menu_analyze_", "")
        await prompt_scoped_flow(update, context, 'analyze', symbol=symbol)
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
        await prompt_scoped_flow(update, context, 'analyze')
    elif data == "menu_alert_scope":
        current_selection = await asyncio.to_thread(get_alert_exchange_selection, update.effective_chat.id)
        await query.edit_message_text(
            render_alert_scope_message(current_selection, view='root'),
            reply_markup=build_alert_scope_markup(current_selection, view='root'),
        )
    elif data == "menu_watch_intro":
        await prompt_scoped_flow(update, context, 'watch')
    elif data == "menu_unwatch_intro":
        await prompt_scoped_flow(update, context, 'unwatch')
    elif data == "menu_run_signals":
        await run_signals_command(update, context)
    elif data == "menu_list_watch":
        await prompt_scoped_flow(update, context, 'list')
    elif data == "menu_high_volume":
        await high_volume(update, context)


async def scope_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    parts = query.data.split("|")
    if len(parts) < 3:
        await safe_edit_message_text(query, "❌ Unable to parse the exchange scope selection.")
        return

    _, action, verb, *rest = parts
    current_scope = get_pending_scope(context)

    if verb == "main":
        clear_pending_flow(context)
        markup = await get_main_menu_markup()
        await safe_edit_message_text(query, "Back to the main menu.", reply_markup=markup)
        return

    if verb == "view":
        view = rest[0] if rest else "root"
        await safe_edit_message_text(
            query,
            render_scope_message(action, current_scope, view=view),
            reply_markup=build_scope_markup(action, current_scope, view=view),
        )
        return

    if verb == "toggle":
        exchange_name = rest[0] if rest else ""
        if not exchange_name:
            await safe_edit_message_text(query, "❌ Unable to parse exchange selection.")
            return

        normalized = normalize_alert_exchange_selection(current_scope)
        supported = get_supported_exchange_names()
        if normalized['mode'] == 'all':
            selected = [name for name in supported if name != exchange_name]
        else:
            selected = list(normalized['exchanges'])
            if exchange_name in selected:
                selected.remove(exchange_name)
            else:
                selected.append(exchange_name)

        if not selected:
            selected = 'all'
        elif len(selected) == 1:
            selected = selected[0]
        elif set(selected) == set(supported):
            selected = 'all'

        set_pending_scope(context, selected)
        updated_scope = get_pending_scope(context)
        await safe_edit_message_text(
            query,
            render_scope_message(action, updated_scope, view='multiple'),
            reply_markup=build_scope_markup(action, updated_scope, view='multiple'),
        )
        return

    if verb == "mode":
        mode = rest[0] if rest else "all"
        if mode != "all":
            await safe_edit_message_text(query, "❌ Unsupported scope mode.")
            return
        set_pending_scope(context, 'all')
        await complete_scoped_flow(update, context, action)
        return

    if verb == "set":
        scope_kind = rest[0] if rest else "single"
        exchange_name = rest[1] if len(rest) > 1 else ""
        if scope_kind != "single" or not exchange_name:
            await safe_edit_message_text(query, "❌ Unable to parse exchange selection.")
            return
        set_pending_scope(context, exchange_name)
        await complete_scoped_flow(update, context, action)
        return

    if verb == "done":
        if not get_pending_scope(context):
            set_pending_scope(context, 'all')
        await complete_scoped_flow(update, context, action)
        return

    await safe_edit_message_text(
        query,
        render_scope_message(action, current_scope, view='root'),
        reply_markup=build_scope_markup(action, current_scope, view='root'),
    )

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

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Telegram bot token or chat ID not found. Bot startup aborted.")
        return

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
    application.add_handler(CommandHandler("alerts_scope", alerts_scope_command))
    application.add_handler(CommandHandler("high_volume", high_volume))
    application.add_handler(CommandHandler("watch", watch_pair))
    application.add_handler(CommandHandler("unwatch", unwatch_pair))
    application.add_handler(CommandHandler("list_watch", list_watch))
    application.add_handler(CommandHandler("run_signals", run_signals_command))
    
    application.add_handler(CallbackQueryHandler(restrict_callback, pattern="^restrict_"))
    application.add_handler(CallbackQueryHandler(details_callback, pattern="^details_"))
    application.add_handler(CallbackQueryHandler(signal_details_callback, pattern="^signal_details"))
    application.add_handler(CallbackQueryHandler(history_details_callback, pattern="^history_details"))
    application.add_handler(CallbackQueryHandler(scope_callback, pattern="^scope\\|"))
    application.add_handler(CallbackQueryHandler(alert_scope_callback, pattern="^alertscope_"))
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
