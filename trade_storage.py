import json
import os

ACTIVE_TRADES_FILE = 'active_trades.json'

def _get_file_path():
    """Returns the absolute path to the active trades JSON file."""
    return os.path.join(os.getcwd(), ACTIVE_TRADES_FILE)

def load_active_trades():
    """Loads active trades from the JSON file."""
    file_path = _get_file_path()
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {file_path}: {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred while loading trades: {e}")
        return []

def save_active_trades(trades):
    """Saves active trades to the JSON file."""
    file_path = _get_file_path()
    try:
        with open(file_path, 'w') as f:
            json.dump(trades, f, indent=4)
    except Exception as e:
        print(f"Error saving trades to {file_path}: {e}")

def add_trade_entry(trade_data):
    """Adds a new trade entry to the active trades."""
    trades = load_active_trades()
    trades.append(trade_data)
    save_active_trades(trades)

def remove_trade_entry(instance_name):
    """Removes a trade entry by instance name."""
    trades = load_active_trades()
    initial_count = len(trades)
    trades = [trade for trade in trades if trade.get('instance_name') != instance_name]
    if len(trades) < initial_count:
        save_active_trades(trades)
        return True
    return False

if __name__ == '__main__':
    # Example Usage:
    print("Loading initial trades:")
    current_trades = load_active_trades()
    print(current_trades)

    print("\nAdding a new trade:")
    new_trade = {
        "instance_name": "test_bot_1",
        "chat_id": "12345",
        "trading_pair": "ETH-USDT",
        "order_amount_usd": 100,
        "trailing_stop_loss_delta": 0.01,
        "take_profit_delta": 0.02,
        "fixed_stop_loss_delta": 0.005
    }
    add_trade_entry(new_trade)
    print("Trades after adding:")
    print(load_active_trades())

    print("\nAdding another trade:")
    another_trade = {
        "instance_name": "test_bot_2",
        "chat_id": "67890",
        "trading_pair": "BTC-USDT",
        "order_amount_usd": 200,
        "trailing_stop_loss_delta": 0.015,
        "take_profit_delta": 0.03,
        "fixed_stop_loss_delta": 0.007
    }
    add_trade_entry(another_trade)
    print("Trades after adding another:")
    print(load_active_trades())

    print("\nRemoving 'test_bot_1':")
    removed = remove_trade_entry("test_bot_1")
    print(f"Removed: {removed}")
    print("Trades after removal:")
    print(load_active_trades())

    print("\nAttempting to remove non-existent trade:")
    removed = remove_trade_entry("non_existent_bot")
    print(f"Removed: {removed}")
    print("Trades after non-existent removal attempt:")
    print(load_active_trades())

    # Clean up for example
    save_active_trades([])
    print("\nTrades after cleanup:")
    print(load_active_trades())