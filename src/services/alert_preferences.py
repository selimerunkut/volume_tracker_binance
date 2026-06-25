"""Chat-scoped alert exchange preferences."""

from __future__ import annotations

import json

from src.exchanges.registry import get_supported_exchange_names

from .db_service import get_chat_setting as db_get_chat_setting
from .db_service import set_chat_setting as db_set_chat_setting


DEFAULT_ALERT_EXCHANGE_SELECTION = {'mode': 'all', 'exchanges': []}
ALERT_EXCHANGE_SELECTION_KEY = 'alert_exchange_selection'


def get_chat_setting(chat_id, key, default=None):
    raw_value = db_get_chat_setting(chat_id, key, None)
    if raw_value is None:
        return default

    try:
        return json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return raw_value


def set_chat_setting(chat_id, key, value):
    original_value = value
    if isinstance(value, (dict, list, tuple, set)):
        value = json.dumps(value)
    db_set_chat_setting(chat_id, key, value)
    return original_value


def normalize_alert_exchange_selection(selection):
    supported = get_supported_exchange_names()

    if selection is None:
        return DEFAULT_ALERT_EXCHANGE_SELECTION.copy()

    if isinstance(selection, str):
        normalized = selection.strip().lower()
        if normalized == 'all':
            return {'mode': 'all', 'exchanges': []}
        if normalized in supported:
            return {'mode': 'selected', 'exchanges': [normalized]}
        return DEFAULT_ALERT_EXCHANGE_SELECTION.copy()

    if isinstance(selection, dict):
        mode = str(selection.get('mode', 'all')).strip().lower()
        if mode == 'all':
            return {'mode': 'all', 'exchanges': []}
        if mode == 'selected':
            return normalize_alert_exchange_selection(selection.get('exchanges', []))
        return DEFAULT_ALERT_EXCHANGE_SELECTION.copy()

    if isinstance(selection, (list, tuple, set)):
        normalized = []
        for exchange_name in selection:
            candidate = str(exchange_name).strip().lower()
            if candidate in supported and candidate not in normalized:
                normalized.append(candidate)
        if not normalized:
            return DEFAULT_ALERT_EXCHANGE_SELECTION.copy()
        if len(normalized) == len(supported):
            return {'mode': 'all', 'exchanges': []}
        return {'mode': 'selected', 'exchanges': normalized}

    return DEFAULT_ALERT_EXCHANGE_SELECTION.copy()


def get_alert_exchange_selection(chat_id):
    raw_selection = get_chat_setting(chat_id, ALERT_EXCHANGE_SELECTION_KEY, DEFAULT_ALERT_EXCHANGE_SELECTION)
    return normalize_alert_exchange_selection(raw_selection)


def set_alert_exchange_selection(chat_id, selection):
    normalized = normalize_alert_exchange_selection(selection)
    set_chat_setting(chat_id, ALERT_EXCHANGE_SELECTION_KEY, normalized)
    return normalized


def should_send_alert_for_scope(alert_exchange, selected_scope):
    exchange = (alert_exchange or '').strip().lower()

    if isinstance(selected_scope, dict):
        if selected_scope.get('mode') == 'all':
            return True
        return exchange in selected_scope.get('exchanges', [])

    scope = (selected_scope or 'all').strip().lower()
    return scope == 'all' or scope == exchange


def should_deliver_exchange_alert(chat_id, exchange_name):
    selection = get_alert_exchange_selection(chat_id)
    return should_send_alert_for_scope(exchange_name, selection)
