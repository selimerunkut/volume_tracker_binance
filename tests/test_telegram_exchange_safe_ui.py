from __future__ import annotations

import asyncio
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import telegram_bot_handler
from src.services.watchlist_manager import WatchlistManager


def _make_reply_recorder():
    async def reply_text(text, reply_markup=None, parse_mode=None):
        recorder.calls.append(
            {
                'text': text,
                'reply_markup': reply_markup,
                'parse_mode': parse_mode,
            }
        )

    recorder = SimpleNamespace(calls=[], reply_text=reply_text)
    return recorder


def _make_update(chat_id=123, callback_data=None):
    message = _make_reply_recorder()
    chat = SimpleNamespace(id=chat_id)
    callback_query = None

    if callback_data is not None:
        async def answer():
            callback.calls.append({'action': 'answer'})

        async def edit_message_text(text, reply_markup=None, parse_mode=None):
            callback.calls.append(
                {
                    'action': 'edit_message_text',
                    'text': text,
                    'reply_markup': reply_markup,
                    'parse_mode': parse_mode,
                }
            )

        callback = SimpleNamespace(
            data=callback_data,
            message=SimpleNamespace(chat=chat),
            calls=[],
            answer=answer,
            edit_message_text=edit_message_text,
        )
        callback_query = callback

    return SimpleNamespace(
        effective_chat=chat,
        effective_message=message,
        callback_query=callback_query,
        message=message,
    )


def test_menu_watch_intro_opens_exchange_scope_picker():
    update = _make_update(callback_data='menu_watch_intro')
    context = SimpleNamespace(user_data={}, args=[])

    asyncio.run(telegram_bot_handler.menu_callback(update, context))

    assert context.user_data['pending_action'] == 'watch'
    assert 'Choose the exchange scope' in update.callback_query.calls[-1]['text']
    labels = [button.text for row in update.callback_query.calls[-1]['reply_markup'].inline_keyboard for button in row]
    assert '🌍 All exchanges' in labels
    assert '🎯 Single exchange' in labels
    assert '🗂 Multiple exchanges' in labels


def test_menu_list_watch_opens_exchange_scope_picker():
    update = _make_update(callback_data='menu_list_watch')
    context = SimpleNamespace(user_data={}, args=[])

    asyncio.run(telegram_bot_handler.menu_callback(update, context))

    assert context.user_data['pending_action'] == 'list'
    assert 'Choose which exchange watchlist' in update.callback_query.calls[-1]['text']


def test_scope_callback_analyze_uses_selected_exchange_and_symbol(monkeypatch):
    observed = {}

    async def fake_edit_message_text(text, reply_markup=None, parse_mode=None):
        observed['edit_text'] = text
        observed['reply_markup'] = reply_markup
        observed['parse_mode'] = parse_mode

    async def fake_analyze_and_suggest(symbol, exchange_name='binance'):
        observed['analysis_args'] = (symbol, exchange_name)
        return {
            'action': 'WAIT',
            'confidence': 77,
            'reasoning': 'ok',
        }

    monkeypatch.setattr(telegram_bot_handler, 'analyze_and_suggest', fake_analyze_and_suggest)

    update = _make_update(callback_data='scope|analyze|set|single|kraken')
    update.callback_query.edit_message_text = fake_edit_message_text
    context = SimpleNamespace(user_data={'pending_action': 'analyze', 'pending_symbol': 'BTCUSD'})

    asyncio.run(telegram_bot_handler.scope_callback(update, context))

    assert observed['analysis_args'] == ('BTCUSD', 'kraken')
    assert 'KRAKEN' in observed['edit_text']


def test_scope_callback_list_watch_groups_by_exchange(tmp_path):
    path = tmp_path / 'watchlist.json'
    path.write_text(json.dumps({'watchlist': {'binance': ['BTCUSDC'], 'kraken': ['BTCUSD']}}))
    manager = WatchlistManager(file_path=str(path))

    assert manager.get_watchlist('binance') == ['BTCUSDC']
    assert manager.get_watchlist('kraken') == ['BTCUSD']
    assert manager.get_watchlist() == ['BTCUSDC', 'BTCUSD']


def test_watchlist_manager_migrates_legacy_flat_data(tmp_path):
    path = tmp_path / 'watchlist.json'
    path.write_text(json.dumps({'watchlist': ['ETHUSDC', 'BTCUSDC']}))

    manager = WatchlistManager(file_path=str(path))

    assert manager.get_watchlist('binance') == ['BTCUSDC', 'ETHUSDC']
    assert manager.get_watchlist('kraken') == []
    persisted = json.loads(path.read_text())
    assert persisted['watchlist']['binance'] == ['BTCUSDC', 'ETHUSDC']

