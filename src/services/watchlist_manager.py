import json
import os
from datetime import datetime

from src.exchanges.registry import get_supported_exchange_names


class WatchlistManager:
    def __init__(self, file_path='signal_watchlist.json'):
        self.file_path = file_path
        self.supported_exchanges = get_supported_exchange_names()
        self.watchlist_by_exchange = self._load_watchlists()

    def _empty_watchlist(self):
        return {exchange_name: set() for exchange_name in self.supported_exchanges}

    def _normalize_exchange_name(self, exchange_name):
        candidate = (exchange_name or 'binance').strip().lower()
        if candidate not in self.supported_exchanges:
            return 'binance'
        return candidate

    def _load_watchlists(self):
        if not os.path.exists(self.file_path):
            self._save_to_file(self._empty_watchlist())
            return self._empty_watchlist()
        try:
            with open(self.file_path, 'r') as f:
                data = json.load(f)
                raw_watchlist = data.get('watchlist', [])
                if isinstance(raw_watchlist, dict):
                    loaded = self._empty_watchlist()
                    for exchange_name, symbols in raw_watchlist.items():
                        normalized_exchange = self._normalize_exchange_name(exchange_name)
                        if not isinstance(symbols, list):
                            continue
                        loaded[normalized_exchange].update(str(symbol).upper() for symbol in symbols if symbol)
                    self._save_to_file(loaded)
                    return loaded

                legacy_symbols = {str(symbol).upper() for symbol in raw_watchlist if symbol}
                loaded = self._empty_watchlist()
                loaded['binance'].update(legacy_symbols)
                self._save_to_file(loaded)
                return loaded
        except Exception as e:
            print(f"[{datetime.now()}] Error loading watchlist: {e}")
            return self._empty_watchlist()

    def _save_to_file(self, symbols_to_save=None):
        if symbols_to_save is None:
            symbols_to_save = self.watchlist_by_exchange
        try:
            with open(self.file_path, 'w') as f:
                json.dump(
                    {
                        'watchlist': {
                            exchange_name: sorted(list(symbols))
                            for exchange_name, symbols in symbols_to_save.items()
                        }
                    },
                    f,
                    indent=4,
                )
        except Exception as e:
            print(f"[{datetime.now()}] Error saving watchlist: {e}")

    def add_symbol(self, symbol, exchange_name='binance'):
        symbol = symbol.upper()
        exchange_name = self._normalize_exchange_name(exchange_name)
        if symbol not in self.watchlist_by_exchange[exchange_name]:
            self.watchlist_by_exchange[exchange_name].add(symbol)
            self._save_to_file()
            return True
        return False

    def remove_symbol(self, symbol, exchange_name='binance'):
        symbol = symbol.upper()
        exchange_name = self._normalize_exchange_name(exchange_name)
        if symbol in self.watchlist_by_exchange[exchange_name]:
            self.watchlist_by_exchange[exchange_name].remove(symbol)
            self._save_to_file()
            return True
        return False

    def get_watchlist(self, exchange_name=None):
        if exchange_name is None:
            flattened = []
            for supported_exchange in self.supported_exchanges:
                flattened.extend(sorted(self.watchlist_by_exchange.get(supported_exchange, set())))
            return flattened

        exchange_name = self._normalize_exchange_name(exchange_name)
        return sorted(list(self.watchlist_by_exchange.get(exchange_name, set())))

    def get_watchlists(self):
        return {
            exchange_name: sorted(list(symbols))
            for exchange_name, symbols in self.watchlist_by_exchange.items()
        }

    def refresh(self):
        self.watchlist_by_exchange = self._load_watchlists()
