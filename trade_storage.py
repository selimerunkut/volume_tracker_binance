import json
import os
from typing import Callable, List, Dict, Any, Optional

ACTIVE_TRADES_FILE = 'active_trades.json'

class TradeStorage:
    def __init__(self,
                 load_func: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 save_func: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
                 remove_func: Optional[Callable[[str], bool]] = None,
                 add_func: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Initializes the TradeStorage with optional custom functions for file operations.
        This allows for dependency injection and easier testing.
        """
        self._load_active_trades = load_func if load_func else self._default_load_active_trades
        self._save_active_trades = save_func if save_func else self._default_save_active_trades
        self._remove_trade_entry = remove_func if remove_func else self._default_remove_trade_entry
        self._add_trade_entry = add_func if add_func else self._default_add_trade_entry

    def _get_file_path(self) -> str:
        """Returns the absolute path to the active trades JSON file."""
        return os.path.join(os.getcwd(), ACTIVE_TRADES_FILE)

    def _default_load_active_trades(self) -> List[Dict[str, Any]]:
        """Loads active trades from the JSON file (default implementation)."""
        file_path = self._get_file_path()
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

    def _default_save_active_trades(self, trades: List[Dict[str, Any]]):
        """Saves active trades to the JSON file (default implementation)."""
        file_path = self._get_file_path()
        try:
            with open(file_path, 'w') as f:
                json.dump(trades, f, indent=4)
        except Exception as e:
            print(f"Error saving trades to {file_path}: {e}")

    def _default_add_trade_entry(self, trade_data: Dict[str, Any]):
        """Adds a new trade entry to the active trades (default implementation)."""
        trades = self._load_active_trades()
        trades.append(trade_data)
        self._save_active_trades(trades)

    def _default_remove_trade_entry(self, instance_name: str) -> bool:
        """Removes a trade entry by instance name (default implementation)."""
        trades = self._load_active_trades()
        initial_count = len(trades)
        trades = [trade for trade in trades if trade.get('instance_name') != instance_name]
        if len(trades) < initial_count:
            self._save_active_trades(trades)
            return True
        return False

    # Public methods to be used by other modules
    def load_trades(self) -> List[Dict[str, Any]]:
        return self._load_active_trades()

    def save_trades(self, trades: List[Dict[str, Any]]):
        self._save_active_trades(trades)

    def add_trade_entry(self, trade_data: Dict[str, Any]):
        self._add_trade_entry(trade_data)

    def remove_trade_entry(self, instance_name: str) -> bool:
        return self._remove_trade_entry(instance_name)

if __name__ == '__main__':
    # Example Usage:
    # Instantiate with default file operations
    trade_storage = TradeStorage()

    print("Loading initial trades:")
    current_trades = trade_storage.load_trades()
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
    trade_storage.add_trade_entry(new_trade)
    print("Trades after adding:")
    print(trade_storage.load_trades())

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
    trade_storage.add_trade_entry(another_trade)
    print("Trades after adding another:")
    print(trade_storage.load_trades())

    print("\nRemoving 'test_bot_1':")
    removed = trade_storage.remove_trade_entry("test_bot_1")
    print(f"Removed: {removed}")
    print("Trades after removal:")
    print(trade_storage.load_trades())

    print("\nAttempting to remove non-existent trade:")
    removed = trade_storage.remove_trade_entry("non_existent_bot")
    print(f"Removed: {removed}")
    print("Trades after non-existent removal attempt:")
    print(trade_storage.load_trades())

    # Clean up for example
    trade_storage.save_trades([])
    print("\nTrades after cleanup:")
    print(trade_storage.load_trades())