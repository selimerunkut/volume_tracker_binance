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
