"""
Database Service - SQLite storage for trade suggestions and outcomes
"""
import sqlite3
from datetime import datetime
import json

DB_PATH = 'trading_memory.db'


def get_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database with tables."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            strategy_type TEXT NOT NULL,  -- LONG or SHORT
            entry_price REAL NOT NULL,
            take_profit REAL NOT NULL,
            stop_loss REAL NOT NULL,
            reasoning TEXT,
            status TEXT DEFAULT 'PENDING',  -- PENDING, WIN, LOSS, EXPIRED
            pnl_percent REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            analysis_data TEXT
        )
    ''')

    try:
        cursor.execute("ALTER TABLE suggestions ADD COLUMN analysis_data TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    print(f"[{datetime.now()}] Database initialized at {DB_PATH}")


def save_suggestion(symbol, strategy_type, entry_price, take_profit, stop_loss, reasoning, analysis_data=None):
    """
    Save a new trade suggestion.
    
    Returns:
        int: ID of the inserted suggestion
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    analysis_json = json.dumps(analysis_data) if analysis_data is not None else None

    cursor.execute('''
        INSERT INTO suggestions 
        (timestamp, symbol, strategy_type, entry_price, take_profit, stop_loss, reasoning, analysis_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        datetime.now().isoformat(),
        symbol.upper(),
        strategy_type.upper(),
        entry_price,
        take_profit,
        stop_loss,
        reasoning,
        analysis_json
    ))
    
    suggestion_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    print(f"[{datetime.now()}] Saved suggestion #{suggestion_id} for {symbol}")
    return suggestion_id


def get_pending_suggestions():
    """Get all pending suggestions."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM suggestions 
        WHERE status = 'PENDING'
        ORDER BY created_at DESC
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def update_outcome(suggestion_id, status, pnl_percent=None):
    """
    Update the outcome of a suggestion.
    
    Args:
        suggestion_id: ID of the suggestion
        status: WIN, LOSS, or EXPIRED
        pnl_percent: Profit/Loss percentage
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE suggestions 
        SET status = ?, pnl_percent = ?
        WHERE id = ?
    ''', (status, pnl_percent, suggestion_id))
    
    conn.commit()
    conn.close()
    
    print(f"[{datetime.now()}] Updated suggestion #{suggestion_id} to {status} (PnL: {pnl_percent}%)")


def get_trade_history(symbol=None, limit=10):
    """
    Get trade history.
    
    Args:
        symbol: Filter by symbol (optional)
        limit: Maximum number of records
    
    Returns:
        list: Trade records
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    if symbol:
        cursor.execute('''
            SELECT * FROM suggestions 
            WHERE symbol = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (symbol.upper(), limit))
    else:
        cursor.execute('''
            SELECT * FROM suggestions 
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_recent_failures(limit=5):
    """Get recent losing trades for learning."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM suggestions 
        WHERE status = 'LOSS'
        ORDER BY created_at DESC
        LIMIT ?
    ''', (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_performance_stats(symbol=None):
    """
    Get win/loss statistics.
    
    Returns:
        dict: Statistics including win_rate, total_trades, etc.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    if symbol:
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN status = 'LOSS' THEN 1 ELSE 0 END) as losses,
                AVG(CASE WHEN pnl_percent IS NOT NULL THEN pnl_percent END) as avg_pnl
            FROM suggestions 
            WHERE symbol = ? AND status IN ('WIN', 'LOSS')
        ''', (symbol.upper(),))
    else:
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN status = 'LOSS' THEN 1 ELSE 0 END) as losses,
                AVG(CASE WHEN pnl_percent IS NOT NULL THEN pnl_percent END) as avg_pnl
            FROM suggestions 
            WHERE status IN ('WIN', 'LOSS')
        ''')
    
    row = cursor.fetchone()
    conn.close()
    
    total = row['total'] or 0
    wins = row['wins'] or 0
    losses = row['losses'] or 0
    avg_pnl = row['avg_pnl'] or 0
    
    win_rate = (wins / total * 100) if total > 0 else 0
    
    return {
        'total_trades': total,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'avg_pnl': avg_pnl
    }


def get_suggestion_details(suggestion_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM suggestions WHERE id = ?', (suggestion_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        data = dict(row)
        if data.get('analysis_data'):
            try:
                data['analysis_data'] = json.loads(data['analysis_data'])
            except json.JSONDecodeError:
                data['analysis_data'] = {}
        return data
    return None


if __name__ == "__main__":
    # Test the module
    print("Testing Database Service...")
    
    # Initialize DB
    init_db()
    
    # Test save
    suggestion_id = save_suggestion(
        symbol="BTCUSDC",
        strategy_type="LONG",
        entry_price=65000.0,
        take_profit=70000.0,
        stop_loss=62000.0,
        reasoning="Strong RSI momentum with positive MACD crossover"
    )
    
    # Test get pending
    pending = get_pending_suggestions()
    print(f"\nPending suggestions: {len(pending)}")
    
    # Test update outcome
    update_outcome(suggestion_id, "WIN", pnl_percent=7.69)
    
    # Test get history
    history = get_trade_history(limit=5)
    print(f"\nTrade history (last 5): {len(history)}")
    for trade in history:
        print(f"  - {trade['symbol']}: {trade['status']} (PnL: {trade['pnl_percent']}%)")
    
    # Test stats
    stats = get_performance_stats()
    print(f"\nPerformance Stats:")
    print(f"  Total: {stats['total_trades']}, Wins: {stats['wins']}, Losses: {stats['losses']}")
    print(f"  Win Rate: {stats['win_rate']:.1f}%, Avg PnL: {stats['avg_pnl']:.2f}%")
