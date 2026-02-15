"""
Performance Tracker - Evaluates trade outcomes and updates database
"""
from datetime import datetime, timedelta
from .db_service import get_pending_suggestions, update_outcome, init_db
from .market_data_service import get_current_price


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
        
        try:
            # Get current price
            current_price = get_current_price(symbol)
            
            # Evaluate trade
            status, pnl = evaluate_trade(suggestion, current_price)
            
            if status != 'PENDING':
                # Update database
                update_outcome(suggestion_id, status, pnl)
                updated_count += 1
                print(f"[{datetime.now()}] Trade #{suggestion_id} ({symbol}): {status} (PnL: {pnl}%)")
            else:
                print(f"[{datetime.now()}] Trade #{suggestion_id} ({symbol}): Still pending")
        
        except Exception as e:
            print(f"[{datetime.now()}] Error evaluating trade #{suggestion_id} ({symbol}): {e}")
            continue
    
    print(f"[{datetime.now()}] Performance tracking complete. Updated {updated_count} trades")


if __name__ == "__main__":
    # Test the module
    print("Testing Performance Tracker...")
    
    # Initialize DB for testing
    init_db()
    
    # Run tracking
    track_performance()
