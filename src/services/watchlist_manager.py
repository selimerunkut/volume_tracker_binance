import json
import os
from datetime import datetime

class WatchlistManager:
    def __init__(self, file_path='signal_watchlist.json'):
        self.file_path = file_path
        self.symbols = self._load_symbols()

    def _load_symbols(self):
        if not os.path.exists(self.file_path):
            self._save_to_file(set())
            return set()
        try:
            with open(self.file_path, 'r') as f:
                data = json.load(f)
                return set(data.get('watchlist', []))
        except Exception as e:
            print(f"[{datetime.now()}] Error loading watchlist: {e}")
            return set()

    def _save_to_file(self, symbols_to_save=None):
        if symbols_to_save is None:
            symbols_to_save = self.symbols
        try:
            with open(self.file_path, 'w') as f:
                json.dump({'watchlist': list(symbols_to_save)}, f, indent=4)
        except Exception as e:
            print(f"[{datetime.now()}] Error saving watchlist: {e}")

    def add_symbol(self, symbol):
        symbol = symbol.upper()
        if symbol not in self.symbols:
            self.symbols.add(symbol)
            self._save_to_file()
            return True
        return False

    def remove_symbol(self, symbol):
        symbol = symbol.upper()
        if symbol in self.symbols:
            self.symbols.remove(symbol)
            self._save_to_file()
            return True
        return False

    def get_watchlist(self):
        return sorted(list(self.symbols))

    def refresh(self):
        self.symbols = self._load_symbols()
