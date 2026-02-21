import pandas as pd
import numpy as np
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.services.technical_analysis import calculate_indicators

def test_indicators_calculation():
    data = {
        'close': [100 + i for i in range(100)],
        'open': [100 + i for i in range(100)],
        'high': [101 + i for i in range(100)],
        'low': [99 + i for i in range(100)],
        'volume': [1000 for i in range(100)]
    }
    df = pd.DataFrame(data)
    
    df_result = calculate_indicators(df)
    
    assert 'bb_lower' in df_result.columns
    assert 'bb_middle' in df_result.columns
    assert 'bb_upper' in df_result.columns
    
    if 'sma_12' not in df_result.columns:
        print("Test failed: 'sma_12' not in columns")
    else:
        print("Test passed: 'sma_12' in columns")

if __name__ == "__main__":
    test_indicators_calculation()
