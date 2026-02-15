"""
LLM Strategy Service - Generates trading strategies using LLM with memory
"""
import os
import json
import logging
from datetime import datetime
from openai import OpenAI

# Import local services
from .market_data_service import fetch_klines, get_current_price
from .technical_analysis import calculate_indicators
from .news_service import get_latest_news
from .db_service import get_trade_history, get_recent_failures, save_suggestion, init_db

# Configure logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)

CREDENTIALS_FILE = 'credentials_b.json'

def load_credentials():
    """Load API keys from credentials file."""
    try:
        if os.path.exists(CREDENTIALS_FILE):
            with open(CREDENTIALS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading credentials: {e}")
    return {}

def get_llm_client():
    """Initialize LLM client (OpenRouter/OpenAI compatibility)."""
    creds = load_credentials()
    api_key = creds.get('llm_api_key') or os.getenv('LLM_API_KEY')
    base_url = creds.get('llm_base_url', 'https://openrouter.ai/api/v1')
    
    if not api_key:
        logger.warning("LLM_API_KEY not found in credentials.json or environment variables.")
        return None
        
    return OpenAI(
        base_url=base_url,
        api_key=api_key,
    )

def safe_format(value, fmt=".2f"):
    """Safely format a value that might be None/NaN."""
    if value is None:
        return "N/A"
    try:
        import math
        if isinstance(value, float) and math.isnan(value):
            return "N/A"
        return f"{value:{fmt}}"
    except (ValueError, TypeError):
        return str(value)

def get_llm_model():
    """Get the LLM model ID from credentials or default."""
    creds = load_credentials()
    # Default to a more stable model ID
    return creds.get('llm_model', 'google/gemini-2.0-flash-001')

def construct_context(ta_data, news, history, failures):
    ta_summary = "Technical Indicators:\n"
    if ta_data is not None and not ta_data.empty:
        latest = ta_data.iloc[-1]
        ta_summary += f"- RSI (14): {safe_format(latest.get('rsi'))}\n"
        ta_summary += f"- MACD: {safe_format(latest.get('macd'), '.4f')}\n"
        ta_summary += f"- MACD Signal: {safe_format(latest.get('macd_signal'), '.4f')}\n"
        ta_summary += f"- Bollinger Upper: {safe_format(latest.get('bb_upper'))}\n"
        ta_summary += f"- Bollinger Lower: {safe_format(latest.get('bb_lower'))}\n"
        ta_summary += f"- EMA (50): {safe_format(latest.get('ema_50'))}\n"
        ta_summary += f"- EMA (200): {safe_format(latest.get('ema_200'))}\n"
    else:
        ta_summary += "No technical data available.\n"

    news_summary = "Recent Crypto News:\n"
    for item in news[:5]:  # Top 5 headlines
        news_summary += f"- {item['title']} (Source: {item['source']})\n"
    
    memory_section = "Your Past Performance on this Symbol:\n"
    if history:
        for trade in history[:3]:
            outcome = trade['status']
            pnl = trade['pnl_percent']
            memory_section += f"- {trade['strategy_type']} @ {trade['entry_price']}: {outcome} ({pnl}%)\n"
    else:
        memory_section += "No past trades recorded for this symbol.\n"

    mistakes_section = "General Lessons from Past Failures:\n"
    if failures:
        for fail in failures[:3]:
            mistakes_section += f"- Failed {fail['strategy_type']} on {fail['symbol']}: {fail['reasoning'][:100]}...\n"
    else:
        mistakes_section += "No significant failures recorded yet.\n"
        
    return ta_summary, news_summary, memory_section, mistakes_section

def construct_prompt(symbol, price_data, ta_summary, news_summary, memory_section, mistakes_section):
    prompt = f"""
You are a professional crypto trading advisor. Analyze the following data for {symbol} and suggest a trading strategy.

CONTEXT:
Current Price: {price_data.get('current_price', 'N/A')}

{ta_summary}

{news_summary}

MEMORY (Learn from this):
{memory_section}
{mistakes_section}

INSTRUCTIONS:
1. Analyze the technicals and news sentiment.
2. Consider your past performance (wins/losses). If you lost recently, adjust your strategy to avoid the same mistake.
3. Determine if there is a Setup (LONG, SHORT, or WAIT).
4. If LONG or SHORT, provide Entry, Take Profit (TP), and Stop Loss (SL).
5. Provide a brief reasoning (max 2 sentences).

OUTPUT FORMAT (JSON ONLY):
{{
    "action": "LONG" | "SHORT" | "WAIT",
    "entry": float,
    "tp": float,
    "sl": float,
    "reasoning": "string",
    "confidence": float (0-100)
}}
"""
    return prompt


def analyze_and_suggest(symbol):
    """
    Main function to analyze a symbol and generate a strategy.
    """
    logger.info(f"Starting analysis for {symbol}...")
    
    # 1. Fetch Data
    try:
        current_price = get_current_price(symbol)
        klines = fetch_klines(symbol)
        
        if klines is None or klines.empty:
            logger.error(f"Failed to fetch market data for {symbol}")
            return None
            
        # 2. Calculate TA
        ta_df = calculate_indicators(klines)
        
        # 3. Fetch News
        news = get_latest_news()
        
        # 4. Fetch Memory
        history = get_trade_history(symbol, limit=5)
        failures = get_recent_failures(limit=5)
        
        price_data = {"current_price": current_price}
        ta_summary, news_summary, memory_section, mistakes_section = construct_context(
            ta_df, news, history, failures
        )
        prompt = construct_prompt(
            symbol, price_data, ta_summary, news_summary, memory_section, mistakes_section
        )
        
        client = get_llm_client()
        if not client:
            return {"error": "LLM client not configured"}

        logger.info("Sending prompt to LLM...")
        model_id = get_llm_model()
        completion = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "You are a disciplined crypto trader. You strictly follow technicals and risk management."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        response_text = completion.choices[0].message.content
        if response_text is None:
            return {"error": "LLM returned empty response"}
        strategy = json.loads(response_text)
        
        analysis_data = {
            'ta_summary': ta_summary,
            'news_summary': news_summary,
            'memory_section': memory_section,
            'mistakes_section': mistakes_section,
            'current_price': current_price
        }
        
        entry_price = strategy.get('entry') if strategy.get('entry') is not None else current_price
        take_profit = strategy.get('tp') if strategy.get('tp') is not None else current_price
        stop_loss = strategy.get('sl') if strategy.get('sl') is not None else current_price
        
        suggestion_id = save_suggestion(
            symbol=symbol,
            strategy_type=strategy['action'],
            entry_price=entry_price,
            take_profit=take_profit,
            stop_loss=stop_loss,
            reasoning=strategy.get('reasoning', ''),
            analysis_data=analysis_data
        )
        strategy['suggestion_id'] = suggestion_id
        logger.info(f"Saved {strategy['action']} strategy for {symbol} (ID: {suggestion_id})")
            
        return strategy

    except Exception as e:
        logger.error(f"Error in analysis: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    # Test block
    print("Testing LLM Strategy...")
    init_db()  # Initialize DB for testing
    result = analyze_and_suggest("BTCUSDC")
    print(json.dumps(result, indent=2))
