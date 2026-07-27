"""
Performance Tracker - Evaluates trade outcomes and updates database
"""
from datetime import datetime, timedelta, timezone
from .db_service import (
    get_pending_suggestions,
    update_outcome,
    init_db,
    get_pending_signal_trades,
    update_signal_trade_outcome,
)
from .market_data_service import fetch_klines, get_current_price


def calculate_pnl(entry_price, exit_price, trade_type):
    """
    Calculate profit/loss percentage.
    
    Args:
        entry_price: Entry price
        exit_price: Exit price (current or actual exit)
        trade_type: 'LONG' or 'SHORT'
    
    Returns:
        float: PnL percentage
    """
    if trade_type == 'LONG':
        pnl = ((exit_price - entry_price) / entry_price) * 100
    else:  # SHORT
        pnl = ((entry_price - exit_price) / entry_price) * 100
    
    return round(pnl, 2)


WAIT_MOVE_THRESHOLD_PERCENT = 2.0
WAIT_WINDOW_HOURS = 24


def evaluate_trade(suggestion, current_price):
    """
    Evaluate if a trade hit TP, SL, or expired.
    
    Args:
        suggestion: dict with trade details from DB
        current_price: Current market price
    
    Returns:
        tuple: (status, pnl_percent)
    """
    trade_type = suggestion['strategy_type']
    entry = suggestion['entry_price']
    tp = suggestion['take_profit']
    sl = suggestion['stop_loss']
    created_at = datetime.fromisoformat(suggestion['created_at'])
    
    if trade_type == 'WAIT':
        elapsed = datetime.now() - created_at
        if elapsed < timedelta(hours=WAIT_WINDOW_HOURS):
            return 'PENDING', None
        if not entry:
            return 'EXPIRED', 0
        pct_change = ((current_price - entry) / entry) * 100
        if pct_change >= WAIT_MOVE_THRESHOLD_PERCENT:
            return 'LOSS', round(-pct_change, 2)
        if pct_change <= -WAIT_MOVE_THRESHOLD_PERCENT:
            return 'WIN', round(-pct_change, 2)
        return 'WIN', 0

    is_expired = datetime.now() - created_at > timedelta(hours=24)
    
    if trade_type == 'LONG':
        # Check Take Profit
        if current_price >= tp:
            pnl = calculate_pnl(entry, tp, 'LONG')
            return 'WIN', pnl
        
        # Check Stop Loss
        if current_price <= sl:
            pnl = calculate_pnl(entry, sl, 'LONG')
            return 'LOSS', pnl
        
        # Check Expiry
        if is_expired:
            pnl = calculate_pnl(entry, current_price, 'LONG')
            return 'EXPIRED', pnl
    
    else:  # SHORT
        # Check Take Profit (price went down)
        if current_price <= tp:
            pnl = calculate_pnl(entry, tp, 'SHORT')
            return 'WIN', pnl
        
        # Check Stop Loss (price went up)
        if current_price >= sl:
            pnl = calculate_pnl(entry, sl, 'SHORT')
            return 'LOSS', pnl
        
        # Check Expiry
        if is_expired:
            pnl = calculate_pnl(entry, current_price, 'SHORT')
            return 'EXPIRED', pnl
    
    # Still pending
    return 'PENDING', None


def evaluate_signal_trade(signal, current_price):
    if current_price is None:
        return 'PENDING', None

    entry_ts = datetime.fromisoformat(signal['entry_ts']) if signal.get('entry_ts') else datetime.now()
    elapsed = datetime.now() - entry_ts

    if elapsed < timedelta(hours=WAIT_WINDOW_HOURS):
        return 'PENDING', None

    action = signal['action'].upper()
    entry = signal['entry_price']
    pnl = calculate_pnl(entry, current_price, action)

    threshold = WAIT_MOVE_THRESHOLD_PERCENT

    if pnl >= threshold:
        return 'WIN', pnl
    if pnl <= -threshold:
        return 'LOSS', pnl

    return 'EXPIRED', pnl


def evaluate_candle_path(suggestion, klines, now=None):
    """Evaluate TP/SL using candle highs/lows with a deterministic SL-first tie break."""
    now = now or datetime.now()
    created_at = datetime.fromisoformat(suggestion['created_at'])
    if created_at.tzinfo is not None:
        created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
    window_end = created_at + timedelta(hours=24)
    action = suggestion['strategy_type']
    frame = klines.copy() if klines is not None else None
    if frame is None or frame.empty:
        return 'PENDING', None
    def normalize_timestamp(value):
        value = value.to_pydatetime() if hasattr(value, 'to_pydatetime') else value
        if getattr(value, 'tzinfo', None) is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    frame['timestamp'] = frame['timestamp'].apply(normalize_timestamp)
    frame = frame.sort_values('timestamp')
    frame = frame[(frame['timestamp'] > created_at) & (frame['timestamp'] <= min(now, window_end))]
    if action == 'WAIT':
        if now < window_end:
            return 'PENDING', None
        close = float(frame.iloc[-1]['close']) if not frame.empty else float(suggestion['entry_price'])
        pct_change = ((close - float(suggestion['entry_price'])) / float(suggestion['entry_price'])) * 100
        if pct_change >= WAIT_MOVE_THRESHOLD_PERCENT:
            return 'LOSS', round(-pct_change, 2)
        if pct_change <= -WAIT_MOVE_THRESHOLD_PERCENT:
            return 'WIN', round(-pct_change, 2)
        return 'WIN', 0
    for _, candle in frame.iterrows():
        high = float(candle['high'])
        low = float(candle['low'])
        tp = float(suggestion['take_profit'])
        sl = float(suggestion['stop_loss'])
        if action == 'LONG':
            if low <= sl:
                return 'LOSS', calculate_pnl(float(suggestion['entry_price']), sl, 'LONG')
            if high >= tp:
                return 'WIN', calculate_pnl(float(suggestion['entry_price']), tp, 'LONG')
        else:
            if high >= sl:
                return 'LOSS', calculate_pnl(float(suggestion['entry_price']), sl, 'SHORT')
            if low <= tp:
                return 'WIN', calculate_pnl(float(suggestion['entry_price']), tp, 'SHORT')
    if now >= window_end and not frame.empty:
        close = float(frame.iloc[-1]['close'])
        return 'EXPIRED', calculate_pnl(float(suggestion['entry_price']), close, action)
    return 'PENDING', None


def track_performance():
    """
    Main function to track and update all pending trades.
    """
    print(f"[{datetime.now()}] Starting performance tracking...")

    # Get pending suggestions
    pending = get_pending_suggestions()
    
    if not pending:
        print(f"[{datetime.now()}] No pending trades to evaluate")
        return
    
    print(f"[{datetime.now()}] Found {len(pending)} pending trades")
    
    updated_count = 0
    
    for suggestion in pending:
        symbol = suggestion['symbol']
        suggestion_id = suggestion['id']
        analysis_data = suggestion.get('analysis_data') or {}
        exchange_name = analysis_data.get('exchange_name', 'binance')
        
        try:
            # Use candle highs/lows so intra-hour TP/SL touches are not missed.
            current_price = get_current_price(symbol, exchange_name=exchange_name)
            klines = fetch_klines(symbol, interval='1h', limit=72, exchange_name=exchange_name)
            if klines is None or klines.empty:
                status, pnl = evaluate_trade(suggestion, current_price)
            else:
                status, pnl = evaluate_candle_path(suggestion, klines)
            
            if status != 'PENDING':
                # Update database
                update_outcome(suggestion_id, status, pnl)
                updated_count += 1
                print(f"[{datetime.now()}] Trade #{suggestion_id} ({symbol}): {status} (PnL: {pnl}%)")
            else:
                print(f"[{datetime.now()}] Trade #{suggestion_id} ({symbol}): Still pending")
        
        except Exception as e:
            print(f"[{datetime.now()}] Error evaluating trade #{suggestion_id} ({symbol} on {exchange_name}): {e}")
            continue
    
    print(f"[{datetime.now()}] Performance tracking complete. Updated {updated_count} trades")

    pending_signals = get_pending_signal_trades()
    if not pending_signals:
        print(f"[{datetime.now()}] No pending signal trades to evaluate")
        return

    print(f"[{datetime.now()}] Found {len(pending_signals)} pending signal trades")
    signal_updates = 0

    for signal in pending_signals:
        symbol = signal['symbol']
        signal_id = signal['id']
        exchange_name = signal.get('exchange_name', 'binance')
        try:
            current_price = get_current_price(symbol, exchange_name=exchange_name)
            status, pnl = evaluate_signal_trade(signal, current_price)
            if status != 'PENDING':
                update_signal_trade_outcome(signal_id, status, pnl)
                signal_updates += 1
                print(f"[{datetime.now()}] Signal #{signal_id} ({symbol} on {exchange_name}): {status} (PnL: {pnl}%)")
            else:
                print(f"[{datetime.now()}] Signal #{signal_id} ({symbol} on {exchange_name}): Still pending")
        except Exception as e:
            print(f"[{datetime.now()}] Error evaluating signal #{signal_id} ({symbol} on {exchange_name}): {e}")
            continue

    print(f"[{datetime.now()}] Signal tracking complete. Updated {signal_updates} signal trades")


if __name__ == "__main__":
    # Test the module
    print("Testing Performance Tracker...")
    
    # Initialize DB for testing
    init_db()
    
    # Run tracking
    track_performance()
