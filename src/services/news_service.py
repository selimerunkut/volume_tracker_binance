"""
Crypto news service that fetches headlines from RSS feeds.
Supports CoinDesk and Cointelegraph feeds.
"""
import feedparser
from datetime import datetime
from typing import List, Dict


# RSS Feed URLs
FEEDS = {
    "CoinDesk": "https://feeds.feedburner.com/CoinDesk",
    "Cointelegraph": "https://cointelegraph.com/rss",
}


def get_latest_news(limit: int = 5) -> List[Dict[str, str]]:
    """
    Fetch latest crypto news from configured RSS feeds.
    
    Args:
        limit: Maximum number of news items to return per feed
        
    Returns:
        List of news items with structure: {title, summary, published, source}
    """
    all_news = []
    
    for source_name, feed_url in FEEDS.items():
        try:
            print(f"[{datetime.now()}] Fetching news from {source_name}...")
            feed = feedparser.parse(feed_url)
            
            if feed.bozo:
                print(f"[{datetime.now()}] WARNING: Feed parsing issue for {source_name}: {feed.bozo_exception}")
            
            entries = feed.entries[:limit] if hasattr(feed, "entries") else []
            
            for entry in entries:
                title = getattr(entry, "title", "No title") or "No title"
                
                summary = getattr(entry, "summary", None)
                if not summary:
                    summary = getattr(entry, "description", None)
                if not summary:
                    summary = getattr(entry, "content", None)
                    if summary and isinstance(summary, list) and len(summary) > 0:
                        summary = summary[0].get("value", "No summary available")
                
                if isinstance(summary, str):
                    if len(summary) > 200:
                        summary = summary[:200] + "..."
                else:
                    summary = "No summary available"
                
                published = getattr(entry, "published", "Unknown date") or "Unknown date"
                
                news_item = {
                    "title": title,
                    "summary": summary,
                    "published": published,
                    "source": source_name,
                }
                all_news.append(news_item)
                
            print(f"[{datetime.now()}] Successfully fetched {len(entries)} items from {source_name}")
            
        except Exception as e:
            print(f"[{datetime.now()}] ERROR fetching news from {source_name}: {e}")
            continue
    
    # Return limited total news items
    all_news = all_news[:limit]
    
    print(f"[{datetime.now()}] Total news items retrieved: {len(all_news)}")
    return all_news


def format_news_for_llm(news_items):
    """
    Format news items for LLM prompt.
    
    Args:
        news_items: List of news item dicts
    
    Returns:
        str: Formatted news string
    """
    if not news_items:
        return "No recent news available."
    
    formatted = []
    for item in news_items:
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
