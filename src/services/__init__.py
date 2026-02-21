# Services package for Smart Strategy Advisor
from .market_data_service import fetch_klines, get_current_price
from .news_service import get_latest_news, format_news_for_llm
from .technical_analysis import calculate_indicators, get_latest_indicators, format_indicators_for_llm
from .macro_data_service import get_macro_summary, format_macro_for_llm, get_fred_data, get_nasdaq_data
from .db_service import (
    init_db, save_suggestion, get_pending_suggestions, 
    update_outcome, get_trade_history, get_recent_failures, get_performance_stats, get_suggestion_details
)

__all__ = [
    'fetch_klines', 'get_current_price',
    'get_latest_news', 'format_news_for_llm',
    'calculate_indicators', 'get_latest_indicators', 'format_indicators_for_llm',
    'get_macro_summary', 'format_macro_for_llm', 'get_fred_data', 'get_nasdaq_data',
    'init_db', 'save_suggestion', 'get_pending_suggestions', 
    'update_outcome', 'get_trade_history', 'get_recent_failures', 'get_performance_stats', 'get_suggestion_details'
]
