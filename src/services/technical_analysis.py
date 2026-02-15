"""
Technical Analysis Service - Calculates indicators using pandas-ta
"""
import pandas as pd
import pandas_ta as ta


def calculate_indicators(df):
    """
    Calculate technical indicators for a DataFrame.
    
    Args:
        df: DataFrame with OHLCV data
    
    Returns:
        DataFrame with added indicator columns
    """
    # Make a copy to avoid modifying original
    df = df.copy()
    
    # RSI (14)
    df['rsi'] = ta.rsi(df['close'], length=14)
    
    # MACD (12, 26, 9)
    macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
    df['macd'] = macd['MACD_12_26_9']
    df['macd_signal'] = macd['MACDs_12_26_9']
    df['macd_histogram'] = macd['MACDh_12_26_9']
    
    # EMA (50 and 200)
    df['ema_50'] = ta.ema(df['close'], length=50)
    df['ema_200'] = ta.ema(df['close'], length=200)
    
    # Bollinger Bands (20, 2)
    bbands = ta.bbands(df['close'], length=20, std=2)
    # pandas-ta returns columns with format: BBL_20_2.0_2.0, BBM_20_2.0_2.0, BBU_20_2.0_2.0
    cols = bbands.columns.tolist()
    df['bb_lower'] = bbands[cols[0]]
    df['bb_middle'] = bbands[cols[1]]
    df['bb_upper'] = bbands[cols[2]]
    
    return df


def get_latest_indicators(df):
    """
    Get the most recent indicator values.
    
    Args:
        df: DataFrame with indicators
    
    Returns:
        dict: Latest indicator values
    """
    latest = df.iloc[-1]
    
    return {
        'rsi': latest.get('rsi'),
        'macd': latest.get('macd'),
        'macd_signal': latest.get('macd_signal'),
        'macd_histogram': latest.get('macd_histogram'),
        'ema_50': latest.get('ema_50'),
        'ema_200': latest.get('ema_200'),
        'bb_upper': latest.get('bb_upper'),
        'bb_middle': latest.get('bb_middle'),
        'bb_lower': latest.get('bb_lower'),
        'close': latest.get('close'),
        'volume': latest.get('volume')
    }


def format_indicators_for_llm(indicators):
    """
    Format indicators for LLM prompt.
    
    Args:
        indicators: dict of indicator values
    
    Returns:
        str: Formatted indicators string
    """
    def safe_format(val, decimals=2):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "N/A"
        return f"{val:.{decimals}f}"
    
    lines = [
        f"Current Price: {safe_format(indicators['close'])}",
        f"RSI(14): {safe_format(indicators['rsi'])}",
        f"MACD: {safe_format(indicators['macd'], 4)} (Signal: {safe_format(indicators['macd_signal'], 4)})",
        f"EMA(50): {safe_format(indicators['ema_50'])}",
        f"EMA(200): {safe_format(indicators['ema_200'])}",
        f"Bollinger Bands: Lower={safe_format(indicators['bb_lower'])}, Upper={safe_format(indicators['bb_upper'])}",
        f"Volume: {safe_format(indicators['volume'])}"
    ]
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Test the module
    print("Testing Technical Analysis Service...")
    
    # Import market data service to get test data
    import sys
    sys.path.insert(0, '/Users/semacair/dev/CEX_volume_tracker_B')
    from market_data_service import fetch_klines
    
    # Get data
    df = fetch_klines("BTCUSDC", interval="1h", limit=100)
    
    # Calculate indicators
    df = calculate_indicators(df)
    
    # Get latest
    indicators = get_latest_indicators(df)
    
    print("\nLatest Indicators:")
    print(format_indicators_for_llm(indicators))
