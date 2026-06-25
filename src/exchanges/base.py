"""Minimal exchange adapter contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class ExchangeSymbol:
    symbol: str
    display_symbol: str
    base_asset: str
    quote_asset: str


class ExchangeAdapter(Protocol):
    name: str
    display_name: str

    def fetch_klines(self, symbol, interval='1h', limit=100) -> pd.DataFrame: ...

    def get_current_price(self, symbol): ...

    def validate_symbol(self, symbol): ...

    def list_symbols(self, quote_asset=None): ...

    def tradingview_url(self, symbol): ...

    def trade_url(self, symbol): ...
