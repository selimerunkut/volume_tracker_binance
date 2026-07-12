"""
Macro data service for fetching Nasdaq and Fed rate information.
Uses FRED API for Fed data and Alpha Vantage for Nasdaq.
"""
import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional


CREDENTIALS_FILE = 'credentials_b.json'
CACHE_FILE = 'macro_cache.json'
CACHE_DURATION_HOURS = 4


def load_credentials():
    try:
        if os.path.exists(CREDENTIALS_FILE):
            with open(CREDENTIALS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"[{datetime.now()}] Error loading credentials: {e}")
    return {}


def load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_cache(data):
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[{datetime.now()}] Error saving cache: {e}")


def get_cached(key: str) -> Optional[Dict]:
    cache = load_cache()
    if key in cache:
        cached = cache[key]
        cached_time = datetime.fromisoformat(cached['timestamp'])
        if datetime.now() - cached_time < timedelta(hours=CACHE_DURATION_HOURS):
            return cached['data']
    return None


def set_cached(key: str, data: Dict):
    cache = load_cache()
    cache[key] = {
        'timestamp': datetime.now().isoformat(),
        'data': data
    }
    save_cache(cache)


def get_fred_data() -> Dict:
    cached = get_cached('fred')
    if cached:
        print(f"[{datetime.now()}] Using cached FRED data")
        return cached
    
    creds = load_credentials()
    fred_api_key = creds.get('fred_api_key')
    
    if not fred_api_key:
        return {'error': 'FRED API key not configured'}
    
    result = {
        'current_rate': None,
        'rate_direction': 'neutral',
        'last_change': None,
        'narrative': 'No recent Fed data available',
    }
    
    try:
        url = f"https://api.stlouisfed.org/fred/series/observations"
        params = {
            'series_id': 'DFEDTARU',
            'api_key': fred_api_key,
            'file_type': 'json',
            'limit': 5,
            'sort_order': 'desc'
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            observations = data.get('observations', [])
            
            if observations:
                latest = observations[0]
                result['current_rate'] = float(latest['value'])
                result['last_updated'] = latest['date']
                
                if len(observations) >= 2:
                    prev = observations[1]
                    prev_rate = float(prev['value'])
                    
                    if result['current_rate'] > prev_rate:
                        result['rate_direction'] = 'hiking'
                        result['narrative'] = f"Fed is HIKING rates (currently {result['current_rate']}%)"
                    elif result['current_rate'] < prev_rate:
                        result['rate_direction'] = 'cutting'
                        result['narrative'] = f"Fed is CUTTING rates (currently {result['current_rate']}%)"
                    else:
                        result['narrative'] = f"Fed holding rates at {result['current_rate']}%"
                else:
                    result['narrative'] = f"Fed rate at {result['current_rate']}%"
        
        print(f"[{datetime.now()}] FRED data fetched: {result['narrative']}")
        
    except Exception as e:
        result['error'] = str(e)
        print(f"[{datetime.now()}] Error fetching FRED data: {e}")
    
    set_cached('fred', result)
    return result


def get_nasdaq_data() -> Dict:
    cached = get_cached('nasdaq')
    if cached:
        print(f"[{datetime.now()}] Using cached Nasdaq data")
        return cached
    
    creds = load_credentials()
    alpha_vantage_key = creds.get('alpha_vantage_api_key')
    
    result = {
        'price': None,
        'change_percent': None,
        'direction': 'neutral',
        'narrative': 'No Nasdaq data available',
    }
    
    if not alpha_vantage_key:
        result['narrative'] = 'Alpha Vantage API key not configured for Nasdaq'
        result['error'] = 'Alpha Vantage API key missing'
        return result
    
    try:
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'GLOBAL_QUOTE',
            'symbol': 'QQQ',
            'apikey': alpha_vantage_key
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            quote = data.get('Global Quote', {})
            
            if quote and '05. price' in quote:
                result['price'] = float(quote['05. price'])
                change_pct = quote['10. change percent'].rstrip('%')
                result['change_percent'] = float(change_pct)
                
                if result['change_percent'] > 0.5:
                    result['direction'] = 'up'
                    result['narrative'] = f"NASDAQ up {result['change_percent']:.2f}% (risk-on sentiment)"
                elif result['change_percent'] < -0.5:
                    result['direction'] = 'down'
                    result['narrative'] = f"NASDAQ down {abs(result['change_percent']):.2f}% (risk-off sentiment)"
                else:
                    result['direction'] = 'flat'
                    result['narrative'] = f"NASDAQ flat {result['change_percent']:.2f}%"
        
        print(f"[{datetime.now()}] Nasdaq data fetched: {result['narrative']}")
        
    except Exception as e:
        result['error'] = str(e)
        print(f"[{datetime.now()}] Error fetching Nasdaq data: {e}")
    
    set_cached('nasdaq', result)
    return result


def get_macro_summary() -> Dict:
    fred = get_fred_data()
    nasdaq = get_nasdaq_data()
    
    return {
        'fed': fred,
        'nasdaq': nasdaq,
        'timestamp': datetime.now().isoformat()
    }


def format_macro_for_llm() -> str:
    macro = get_macro_summary()
    
    lines = ["Macro Market Context:"]
    
    if 'error' not in macro.get('nasdaq', {}):
        nasdaq = macro['nasdaq']
        lines.append(f"- {nasdaq.get('narrative', 'N/A')}")
    else:
        lines.append(f"- Nasdaq: {macro['nasdaq'].get('error', 'Unavailable')}")
    
    if 'error' not in macro.get('fed', {}):
        fed = macro['fed']
        lines.append(f"- {fed.get('narrative', 'N/A')}")
    else:
        lines.append(f"- Fed: {macro['fed'].get('error', 'Unavailable')}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print("Testing Macro Data Service...")
    
    print("\n=== FRED Data ===")
    fred = get_fred_data()
    print(fred)
    
    print("\n=== Nasdaq Data ===")
    nasdaq = get_nasdaq_data()
    print(nasdaq)
    
    print("\n=== Combined Summary ===")
    print(format_macro_for_llm())
