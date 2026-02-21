import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests

CREDENTIALS_FILE = 'credentials_b.json'
API_BASE_URL = 'https://api.binance.com'


def _load_credentials():
    if not os.path.exists(CREDENTIALS_FILE):
        logging.getLogger(__name__).debug(f"Binance credentials file {CREDENTIALS_FILE} is missing.")
        return None, None

    try:
        with open(CREDENTIALS_FILE, 'r') as f:
            data = json.load(f)
        return data.get('Binance_api_key'), data.get('Binance_secret_key')
    except json.JSONDecodeError as exc:
        logging.getLogger(__name__).error(f"Failed to parse {CREDENTIALS_FILE}: {exc}")
        return None, None
    except Exception as exc:
        logging.getLogger(__name__).error(f"Unexpected error loading Binance credentials: {exc}")
        return None, None


class BinancePermissionsService:
    def __init__(self, cache_ttl: int = 300):
        self.logger = logging.getLogger(__name__)
        self.api_key, self.api_secret = _load_credentials()
        self.cache_ttl = cache_ttl
        self._allowed_symbols = set()
        self._last_refresh = 0
        self._trading_group = None
        self._last_error = None

    def _has_credentials(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def _sign(self, params: Dict[str, Any]) -> str:
        secret = self.api_secret
        if not secret:
            raise RuntimeError("Missing Binance API secret for signing requests.")
        query = urlencode(params)
        return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False):
        url = f"{API_BASE_URL}{path}"
        headers = {'X-MBX-APIKEY': self.api_key} if self.api_key else None

        request_params: Dict[str, Any] = {}
        if params:
            request_params.update(params)

        if signed:
            if not self._has_credentials():
                self.logger.debug("Cannot sign request without API credentials.")
                return None
            request_params.setdefault('timestamp', int(time.time() * 1000))
            request_params.setdefault('recvWindow', 60000)
            request_params['signature'] = self._sign(request_params)

        try:
            params_for_request = request_params if request_params else None
            response = requests.get(url, headers=headers, params=params_for_request)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            self.logger.error(f"Binance API request failed ({path}): {exc}")
            self._last_error = str(exc)
            return None

    def get_account_info(self):
        if not self._has_credentials():
            return None
        return self._request('/api/v3/account', signed=True)

    def get_trading_group(self):
        if self._trading_group:
            return self._trading_group

        info = self.get_account_info()
        if not info:
            self._last_error = 'failed_account_info'
            return None

        permissions = info.get('permissions', [])
        for entry in permissions:
            if isinstance(entry, str) and entry.upper().startswith('TRD_GRP'):
                self._trading_group = entry.upper()
                return self._trading_group

        for key in ('trdGrp', 'trd_group', 'tradingGroup', 'trading_group'):
            value = info.get(key)
            if isinstance(value, str) and value.upper().startswith('TRD_GRP'):
                self._trading_group = value.upper()
                return self._trading_group

        self.logger.debug('No TRD_GRP value found in account info permissions.')
        self._last_error = 'missing_trading_group'
        return None

    def _fetch_exchange_info(self, trading_group: str):
        params = {'permissions': trading_group}
        return self._request('/api/v3/exchangeInfo', params=params)

    def _refresh_allowed_symbols(self) -> bool:
        trading_group = self.get_trading_group()
        if not trading_group:
            return False

        info = self._fetch_exchange_info(trading_group)
        if not info:
            self._last_error = 'failed_exchange_info'
            return False

        symbols = info.get('symbols', [])
        allowed = set()
        for entry in symbols:
            if entry.get('status') != 'TRADING':
                continue
            symbol = entry.get('symbol')
            if symbol:
                allowed.add(symbol)

        if allowed:
            self._allowed_symbols = allowed
            self._last_refresh = time.time()
            self.logger.info(f"Loaded {len(allowed)} tradable symbols for {trading_group}.")
            return True

        self._last_error = 'empty_symbol_list'
        return False

    def get_allowed_symbols(self):
        now = time.time()
        if (now - self._last_refresh) > self.cache_ttl or not self._allowed_symbols:
            refreshed = self._refresh_allowed_symbols()
            if not refreshed:
                return None
        return self._allowed_symbols

    def can_trade_symbol(self, symbol: str):
        if not self._has_credentials():
            return None
        allowed = self.get_allowed_symbols()
        if allowed is None:
            return None
        if symbol in allowed:
            return True, None
        return False, 'not_permitted'

    @property
    def trading_group(self) -> Optional[str]:
        if not self._trading_group:
            self.get_trading_group()
        return self._trading_group

    def last_error(self) -> Optional[str]:
        return self._last_error


permissions_service = BinancePermissionsService()
