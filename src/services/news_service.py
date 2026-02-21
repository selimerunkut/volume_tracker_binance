"""
Crypto news service that fetches headlines from RSS feeds.
Supports multiple crypto and financial news sources.
"""
import feedparser
import os
import json
from datetime import datetime
from typing import List, Dict


CREDENTIALS_FILE = 'credentials_b.json'


def load_credentials():
    try:
        if os.path.exists(CREDENTIALS_FILE):
            with open(CREDENTIALS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"[{datetime.now()}] Error loading credentials: {e}")
    return {}


RSS_FEEDS = {
    "Crypto": {
        "CoinDesk": "https://feeds.feedburner.com/CoinDesk",
        "Cointelegraph": "https://cointelegraph.com/rss",
        "Bitcoinist": "https://bitcoinist.com/feed/",
        "Decrypt": "https://decrypt.co/feed",
    },
    "Markets": {
        "Yahoo Finance Crypto": "https://finance.yahoo.com/rss/symbol?sBTC-USD",
    },
    "Risk-On": {
        "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    },
}


def fetch_feed(source_name: str, feed_url: str, limit: int = 3) -> List[Dict]:
    news_items = []
    try:
        feed = feedparser.parse(feed_url)
        
        if feed.bozo:
            print(f"[{datetime.now()}] WARNING: Feed parsing issue for {source_name}")
        
        entries = feed.entries[:limit] if hasattr(feed, 'entries') else []
        
        for entry in entries:
            title = getattr(entry, 'title', 'No title') or 'No title'
            
            summary = getattr(entry, 'summary', None)
            if not summary:
                summary = getattr(entry, 'description', None)
            if not summary:
                content = getattr(entry, 'content', None)
                if content and isinstance(content, list) and len(content) > 0:
                    summary = content[0].get('value', 'No summary')
            
            if isinstance(summary, str) and len(summary) > 200:
                summary = summary[:200] + '...'
            elif not summary:
                summary = 'No summary available'
            
            published = getattr(entry, 'published', 'Unknown date') or 'Unknown date'
            
            news_items.append({
                'title': title.strip(),
                'summary': summary.strip() if isinstance(summary, str) else summary,
                'published': published,
                'source': source_name,
            })
        
    except Exception as e:
        print(f"[{datetime.now()}] ERROR fetching {source_name}: {e}")
    
    return news_items


def get_latest_news(limit: int = 5) -> List[Dict[str, str]]:
    all_news = []
    seen_titles = set()
    
    for category, feeds in RSS_FEEDS.items():
        for source_name, feed_url in feeds.items():
            news = fetch_feed(source_name, feed_url, limit=2)
            
            for item in news:
                title_key = item['title'][:50].lower()
                if title_key not in seen_titles:
                    seen_titles.add(title_key)
                    item['category'] = category
                    all_news.append(item)
    
    all_news = all_news[:limit]
    
    print(f"[{datetime.now()}] Total news items retrieved: {len(all_news)}")
    return all_news


def get_macro_news() -> List[Dict]:
    macro_feeds = {
        "CNBC Economy": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "Yahoo Finance Markets": "https://finance.yahoo.com/rss/markets",
    }
    
    news = []
    for source_name, feed_url in macro_feeds.items():
        news.extend(fetch_feed(source_name, feed_url, limit=2))
    
    return news[:5]


def format_news_for_llm(news_items: List[Dict], include_category: bool = True) -> str:
    if not news_items:
        return "No recent news available."
    
    formatted = []
    for item in news_items:
        if include_category and 'category' in item:
            formatted.append(f"- [{item['source']}] [{item['category']}] {item['title']}")
        else:
            formatted.append(f"- [{item['source']}] {item['title']}")
    
    return "\n".join(formatted)


if __name__ == "__main__":
    # Test the module
    print("Testing News Service...")
    
    news = get_latest_news(limit=5)
    print(f"\nFetched {len(news)} news items\n")
    
    for item in news:
        print(f"Source: {item['source']}")
        print(f"Title: {item['title']}")
        print(f"Published: {item['published']}")
        print(f"Summary: {item['summary']}")
        print("-" * 80)
