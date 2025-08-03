import json
import os
from datetime import datetime

class SymbolManager:
    def __init__(self, file_path='restricted_pairs.json'):
        self.file_path = file_path
        self.excluded_symbols = self._load_symbols()

    def _load_symbols(self):
        """Loads the list of excluded symbols from a JSON file."""
        if not os.path.exists(self.file_path):
            self._save_symbols(set()) # Create an empty file if it doesn't exist
            return set()
        try:
            with open(self.file_path, 'r') as f:
                data = json.load(f)
                return set(data.get('excluded_symbols', []))
        except json.JSONDecodeError as e:
            print(f"[{datetime.now()}] Error decoding restricted pairs file: {e}. Starting with empty set.")
            return set()
        except Exception as e:
            print(f"[{datetime.now()}] An unexpected error occurred while loading restricted pairs: {e}. Starting with empty set.")
            return set()

    def _save_symbols(self):
        """Saves the current list of excluded symbols to the JSON file."""
        try:
            with open(self.file_path, 'w') as f:
                json.dump({'excluded_symbols': list(self.excluded_symbols)}, f, indent=4)
        except Exception as e:
            print(f"[{datetime.now()}] An error occurred while saving restricted pairs: {e}")

    def add_symbol(self, symbol):
        """Adds a symbol to the excluded list."""
        if symbol not in self.excluded_symbols:
            self.excluded_symbols.add(symbol)
            self._save_symbols()
            print(f"[{datetime.now()}] Added {symbol} to restricted pairs.")
            return True
        print(f"[{datetime.now()}] {symbol} is already in restricted pairs.")
        return False

    def remove_symbol(self, symbol):
        """Removes a symbol from the excluded list."""
        if symbol in self.excluded_symbols:
            self.excluded_symbols.remove(symbol)
            self._save_symbols()
            print(f"[{datetime.now()}] Removed {symbol} from restricted pairs.")
            return True
        print(f"[{datetime.now()}] {symbol} is not in restricted pairs.")
        return False

    def get_excluded_symbols(self):
        """Returns the current set of excluded symbols."""
        return self.excluded_symbols

    def is_symbol_excluded(self, symbol):
        """Checks if a symbol is in the excluded list."""
        return symbol in self.excluded_symbols
