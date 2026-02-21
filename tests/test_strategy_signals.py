import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.services.strategy_signals import evaluate_hourly_strategy, evaluate_daily_strategy

def test_hourly_strategy():
    data = {
        'close': [100, 101, 102, 100, 90],
        'bb_lower': [98, 98, 98, 98, 98],
        'bb_middle': [100, 100, 100, 100, 100],
        'bb_upper': [102, 102, 102, 102, 102]
    }
    df = pd.DataFrame(data)
    
    signal = evaluate_hourly_strategy(df)
    assert signal == 'LONG'
    
    data_close = {
        'close': [90, 95, 101],
        'bb_lower': [98, 98, 98],
        'bb_middle': [100, 100, 100],
        'bb_upper': [102, 102, 102]
    }
    df_close = pd.DataFrame(data_close)
    signal_close = evaluate_hourly_strategy(df_close)
    assert signal_close == 'CLOSE'

def test_daily_strategy():
    data_long = {
        'close': [95, 98, 105],
        'sma_12': [100, 100, 100]
    }
    df_long = pd.DataFrame(data_long)
    signal_long = evaluate_daily_strategy(df_long)
    assert signal_long == 'LONG'
    
    data_short = {
        'close': [105, 102, 95],
        'sma_12': [100, 100, 100]
    }
    df_short = pd.DataFrame(data_short)
    signal_short = evaluate_daily_strategy(df_short)
    assert signal_short == 'SHORT'

if __name__ == "__main__":
    test_hourly_strategy()
    test_daily_strategy()
    print("All strategy tests passed!")
