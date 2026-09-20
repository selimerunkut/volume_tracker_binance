"""
Performance Tracker - Evaluates trade outcomes and updates database
"""
from datetime import datetime, timedelta, timezone
import pandas as pd
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


UNEVALUABLE = 'UNEVALUABLE'


def _utc_datetime(value):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _prepare_candles(klines):
    if klines is None or klines.empty or 'timestamp' not in klines:
        return pd.DataFrame()
    frame = klines.copy()
    frame['timestamp'] = pd.to_datetime(frame['timestamp'], utc=True, errors='coerce')
    for column in ('high', 'low', 'close'):
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    return frame.dropna(subset=['timestamp', 'high', 'low', 'close']).sort_values('timestamp')


def _candle_interval(frame):
    seconds = frame['timestamp'].diff().dt.total_seconds().dropna()
    seconds = seconds[seconds > 0]
    return timedelta(seconds=float(seconds.median())) if not seconds.empty else timedelta(hours=1)


def _missing_interior_candles(frame, expected_interval, start=None):
    if frame.empty:
        return 0
    expected_seconds = expected_interval.total_seconds()
    missing = 0
    if start is not None:
        first_gap = (frame.iloc[0]['timestamp'] - pd.Timestamp(start)).total_seconds()
        if first_gap > expected_seconds * 1.5:
            missing += max(1, round(first_gap / expected_seconds) - 1)
    for previous, current in zip(frame['timestamp'], frame['timestamp'].iloc[1:]):
        gap = (current - previous).total_seconds()
        if gap > expected_seconds * 1.5:
            missing += max(1, round(gap / expected_seconds) - 1)
    return missing


def evaluate_candle_path_detailed(suggestion, klines, now=None):
    """Evaluate a 24-hour window and report coverage separately from its outcome.

    Interior candle gaps do not invalidate the fixed return calculation, but they
    make an exact TP/SL path unknowable unless the target was hit before the gap.
    """
    created_at = _utc_datetime(suggestion['created_at'])
    window_end = created_at + timedelta(hours=24)
    now = _utc_datetime(now or datetime.now(timezone.utc))
    action = str(suggestion['strategy_type']).upper()
    entry = float(suggestion['entry_price'])
    frame = _prepare_candles(klines)
    result = {
        'status': 'PENDING',
        'pnl_percent': None,
        'raw_return_percent': None,
        'coverage_status': 'IN_PROGRESS' if now < window_end else 'UNEVALUABLE',
        'missing_candles': 0,
    }
    if frame.empty:
        if now >= window_end:
            result.update(status=UNEVALUABLE, coverage_status='UNEVALUABLE')
        return result

    expected_interval = _candle_interval(frame)
    path_window = frame[(frame['timestamp'] > pd.Timestamp(created_at)) &
                        (frame['timestamp'] + pd.Timedelta(seconds=expected_interval.total_seconds()) <= pd.Timestamp(min(now, window_end)))].copy()
    observation_limit = pd.Timestamp(window_end) + pd.Timedelta(seconds=expected_interval.total_seconds())
    observation_window = frame[(frame['timestamp'] > pd.Timestamp(created_at)) &
                               (frame['timestamp'] <= observation_limit)].copy()
    coverage_window = path_window if not path_window.empty else observation_window
    missing = _missing_interior_candles(coverage_window, expected_interval, start=created_at)
    result['missing_candles'] = missing

    exact = observation_window[observation_window['timestamp'] == pd.Timestamp(window_end)]
    before = observation_window[observation_window['timestamp'] < pd.Timestamp(window_end)]
    after = observation_window[observation_window['timestamp'] > pd.Timestamp(window_end)]
    if not exact.empty:
        endpoint = exact.tail(1)
    elif not before.empty and (pd.Timestamp(window_end) - before.iloc[-1]['timestamp']) <= expected_interval * 1.5:
        # Candle timestamps are opens; prefer the last observation not after the cutoff.
        endpoint = before.tail(1)
    elif not after.empty and (after.iloc[0]['timestamp'] - pd.Timestamp(window_end)) <= expected_interval * 1.5:
        endpoint = after.head(1)
    else:
        endpoint = observation_window.iloc[0:0]
    boundary_offset_minutes = None
    if not endpoint.empty:
        endpoint_timestamp = endpoint.iloc[-1]['timestamp']
        boundary_offset_minutes = round(abs((endpoint_timestamp - pd.Timestamp(window_end)).total_seconds()) / 60, 2)
        close = float(endpoint.iloc[-1]['close'])
        raw_return = ((close - entry) / entry) * 100
        result['raw_return_percent'] = round(raw_return, 8)
        result['boundary_offset_minutes'] = boundary_offset_minutes
    result['coverage_status'] = 'PARTIAL_COVERAGE' if missing or boundary_offset_minutes else 'EVALUABLE'

    if action == 'WAIT':
        if now < window_end:
            return result
        if endpoint.empty:
            result.update(status=UNEVALUABLE, coverage_status='UNEVALUABLE')
            return result
        if raw_return >= WAIT_MOVE_THRESHOLD_PERCENT:
            result.update(status='LOSS', pnl_percent=round(-raw_return, 2))
        elif raw_return <= -WAIT_MOVE_THRESHOLD_PERCENT:
            result.update(status='WIN', pnl_percent=round(-raw_return, 2))
        else:
            result.update(status='WIN', pnl_percent=0.0)
        return result

    tp = float(suggestion['take_profit'])
    sl = float(suggestion['stop_loss'])
    valid_targets = ((action == 'LONG' and sl < entry < tp) or
                     (action == 'SHORT' and tp < entry < sl))
    if not valid_targets:
        result.update(status=UNEVALUABLE, coverage_status='INVALID_TARGETS')
        return result

    coverage_start = path_window if not path_window.empty else observation_window
    initial_gap = (coverage_start.iloc[0]['timestamp'] - pd.Timestamp(created_at)).total_seconds() if not coverage_start.empty else 0
    if initial_gap > expected_interval.total_seconds() * 1.5:
        result.update(status=UNEVALUABLE, coverage_status='PARTIAL_COVERAGE')
        return result

    previous = None
    for _, candle in path_window.iterrows():
        if previous is not None:
            gap = candle['timestamp'] - previous['timestamp']
            if gap > expected_interval * 1.5:
                result.update(status=UNEVALUABLE, pnl_percent=None, coverage_status='PARTIAL_COVERAGE')
                return result
        high = float(candle['high'])
        low = float(candle['low'])
        if action == 'LONG':
            if low <= sl:
                result.update(status='LOSS', pnl_percent=calculate_pnl(entry, sl, 'LONG'))
                return result
            if high >= tp:
                result.update(status='WIN', pnl_percent=calculate_pnl(entry, tp, 'LONG'))
                return result
        else:
            if high >= sl:
                result.update(status='LOSS', pnl_percent=calculate_pnl(entry, sl, 'SHORT'))
                return result
            if low <= tp:
                result.update(status='WIN', pnl_percent=calculate_pnl(entry, tp, 'SHORT'))
                return result
        previous = candle

    if now < window_end:
        return result
    if endpoint.empty:
        result.update(status=UNEVALUABLE, coverage_status='UNEVALUABLE')
        return result
    result.update(status='EXPIRED', pnl_percent=calculate_pnl(entry, close, action))
    return result


def evaluate_candle_path(suggestion, klines, now=None):
    """Backward-compatible ``(status, pnl)`` wrapper around detailed evaluation."""
    result = evaluate_candle_path_detailed(suggestion, klines, now=now)
    return result['status'], result['pnl_percent']


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
            # Keep the ticker fetch for diagnostics; candle data is the source of truth.
            get_current_price(symbol, exchange_name=exchange_name)
            klines = fetch_klines(symbol, interval='1h', limit=72, exchange_name=exchange_name)
            detail = evaluate_candle_path_detailed(suggestion, klines)
            status = detail['status']
            pnl = detail['pnl_percent']

            if status != 'PENDING':
                try:
                    update_outcome(
                        suggestion_id,
                        status,
                        pnl,
                        raw_return_percent=detail['raw_return_percent'],
                        coverage_status=detail['coverage_status'],
                        missing_candles=detail['missing_candles'],
                    )
                except TypeError as exc:
                    if 'unexpected keyword argument' not in str(exc):
                        raise
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
