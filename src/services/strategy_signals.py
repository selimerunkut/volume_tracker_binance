import pandas as pd

def evaluate_hourly_strategy(df):
    if df is None or df.empty or len(df) < 2:
        return 'WAIT'
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    current_close = latest['close']
    prev_close = prev['close']
    bb_lower = latest['bb_lower']
    bb_middle = latest['bb_middle']
    
    if current_close < bb_lower and prev_close >= bb_lower:
        return 'LONG'
    
    if current_close > bb_middle and prev_close <= bb_middle:
        return 'CLOSE'
        
    return 'WAIT'

def evaluate_daily_strategy(df):
    if df is None or df.empty or len(df) < 2:
        return 'WAIT'
        
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    current_close = latest['close']
    prev_close = prev['close']
    sma_12 = latest['sma_12']
    prev_sma_12 = prev['sma_12']
    
    if current_close > sma_12 and prev_close <= prev_sma_12:
        return 'LONG'
        
    if current_close < sma_12 and prev_close >= prev_sma_12:
        return 'SHORT'
        
    return 'WAIT'


def _format_value(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    return f"{value:.2f}"


def describe_hourly_signal(df, signal):
    if signal not in {'LONG', 'CLOSE'} or df is None or len(df) < 2:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    current_close = latest['close']
    prev_close = prev['close']
    bb_lower = latest['bb_lower']
    bb_middle = latest['bb_middle']

    if signal == 'LONG':
        return (
            "Rule: 1h price dipped below the lower Bollinger Band after previously sitting at or above it, "
            "suggesting a mean-reversion LONG entry.\n"
            f"Current Close: {_format_value(current_close)}\n"
            f"Previous Close: {_format_value(prev_close)}\n"
            f"BB Lower: {_format_value(bb_lower)}\n"
            f"BB Middle: {_format_value(bb_middle)}"
        )

    if signal == 'CLOSE':
        return (
            "Rule: 1h price crossed back above the middle Bollinger Band after being below it, "
            "indicating a momentum shift and opportunity to close.\n"
            f"Current Close: {_format_value(current_close)}\n"
            f"Previous Close: {_format_value(prev_close)}\n"
            f"BB Middle: {_format_value(bb_middle)}\n"
            f"BB Upper: {_format_value(latest['bb_upper'])}"
        )

    return None


def describe_daily_signal(df, signal):
    if signal not in {'LONG', 'SHORT'} or df is None or len(df) < 2:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    current_close = latest['close']
    prev_close = prev['close']
    sma_12 = latest['sma_12']
    prev_sma_12 = prev['sma_12']

    if signal == 'LONG':
        return (
            "Rule: Daily close crossed above SMA(12), signaling the start of an upward trend.\n"
            f"Current Close: {_format_value(current_close)}\n"
            f"Previous Close: {_format_value(prev_close)}\n"
            f"SMA(12): {_format_value(sma_12)}\n"
            f"Prev SMA(12): {_format_value(prev_sma_12)}"
        )

    if signal == 'SHORT':
        return (
            "Rule: Daily close crossed below SMA(12), suggesting momentum is turning bearish.\n"
            f"Current Close: {_format_value(current_close)}\n"
            f"Previous Close: {_format_value(prev_close)}\n"
            f"SMA(12): {_format_value(sma_12)}\n"
            f"Prev SMA(12): {_format_value(prev_sma_12)}"
        )

    return None
