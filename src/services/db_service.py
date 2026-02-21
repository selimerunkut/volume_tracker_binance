"""
Database Service - SQLite storage for trade suggestions and outcomes
"""
import json
import os
import sqlite3
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, 'trading_memory.db')


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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    conn.commit()
    conn.close()
    print(f"[{datetime.now()}] Database initialized at {DB_PATH}")


def get_setting(key, default=None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()
    except sqlite3.OperationalError:
        conn.close()
        return default
    conn.close()
    if row:
        return row['value']
    return default


def set_setting(key, value):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value)
            VALUES (?, ?)
        ''', (key, str(value)))
        conn.commit()
        conn.close()
    except sqlite3.OperationalError:
        conn.close()
        init_db()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value)
            VALUES (?, ?)
        ''', (key, str(value)))
        conn.commit()
        conn.close()


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


def get_last_analyzed_symbols(limit=5):
    """Get the most recently analyzed unique symbols."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT symbol FROM (
            SELECT symbol, MAX(created_at) as last_created 
            FROM suggestions 
            GROUP BY symbol 
            ORDER BY last_created DESC 
            LIMIT ?
        )
    ''', (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [row['symbol'] for row in rows]


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


def get_performance_stats(symbol=None, start_date=None, end_date=None):
    conn = get_connection()
    cursor = conn.cursor()
    
    filters = ["status IN ('WIN', 'LOSS')"]
    params = []

    if symbol:
        filters.append('symbol = ?')
        params.append(symbol.upper())

    if start_date:
        filters.append('datetime(created_at) >= datetime(?)')
        params.append(start_date)
    if end_date:
        filters.append('datetime(created_at) <= datetime(?)')
        params.append(end_date)

    where_clause = ' AND '.join(filters)
    query = f'''
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'WIN' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN status = 'LOSS' THEN 1 ELSE 0 END) as losses,
            AVG(CASE WHEN pnl_percent IS NOT NULL THEN pnl_percent END) as avg_pnl
        FROM suggestions
        WHERE {where_clause}
    '''

    cursor.execute(query, tuple(params))
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


def get_suggestions_between_dates(limit=10, start_date=None, end_date=None, completed_only=False):
    conn = get_connection()
    cursor = conn.cursor()

    filters = ['1=1']
    params = []

    if completed_only:
        filters.append("status IN ('WIN', 'LOSS')")

    if start_date:
        filters.append('datetime(created_at) >= datetime(?)')
        params.append(start_date)
    if end_date:
        filters.append('datetime(created_at) <= datetime(?)')
        params.append(end_date)

    where_clause = ' AND '.join(filters)
    query = f'''
        SELECT * FROM suggestions
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ?
    '''

    params.append(limit)
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        data = dict(row)
        if data.get('analysis_data'):
            try:
                data['analysis_data'] = json.loads(data['analysis_data'])
            except json.JSONDecodeError:
                data['analysis_data'] = {}
        result.append(data)
    return result


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
