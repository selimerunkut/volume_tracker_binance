from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import telegram_bot_handler
from telegram.error import BadRequest


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
    effective_message = message
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
        effective_message=effective_message,
        callback_query=callback_query,
        message=effective_message,
    )


def test_alerts_scope_command_supports_all_single_and_multiple(monkeypatch):
    state = {'selection': {'mode': 'selected', 'exchanges': ['binance']}}

    def fake_get_alert_exchange_selection(chat_id):
        return state['selection']

    def fake_set_alert_exchange_selection(chat_id, selection):
        if selection == 'all':
            state['selection'] = {'mode': 'all', 'exchanges': []}
        elif isinstance(selection, str):
            state['selection'] = {'mode': 'selected', 'exchanges': [selection]}
        else:
            state['selection'] = telegram_bot_handler.normalize_alert_exchange_selection(selection)
        return state['selection']

    monkeypatch.setattr(telegram_bot_handler, 'get_alert_exchange_selection', fake_get_alert_exchange_selection)
    monkeypatch.setattr(telegram_bot_handler, 'set_alert_exchange_selection', fake_set_alert_exchange_selection)
    monkeypatch.setattr(telegram_bot_handler, 'get_supported_exchange_names', lambda: ['binance', 'kraken'])

    update = _make_update()
    context = SimpleNamespace(args=['multiple', 'binance', 'kraken'])

    asyncio.run(telegram_bot_handler.alerts_scope_command(update, context))

    assert state['selection'] == {'mode': 'selected', 'exchanges': ['binance', 'kraken']}
    assert update.effective_message.calls[-1]['text'].startswith('🗂 Current alert scope:')
    keyboard = update.effective_message.calls[-1]['reply_markup'].inline_keyboard
    assert any('All exchanges' in button.text for row in keyboard for button in row)

    update = _make_update()
    context = SimpleNamespace(args=['single', 'kraken'])
    asyncio.run(telegram_bot_handler.alerts_scope_command(update, context))
    assert state['selection'] == {'mode': 'selected', 'exchanges': ['kraken']}

    update = _make_update()
    context = SimpleNamespace(args=['all'])
    asyncio.run(telegram_bot_handler.alerts_scope_command(update, context))
    assert state['selection'] == {'mode': 'all', 'exchanges': []}


def test_alert_scope_callback_toggles_into_all_selection(monkeypatch):
    state = {'selection': {'mode': 'selected', 'exchanges': ['binance']}}

    def fake_get_alert_exchange_selection(chat_id):
        return state['selection']

    def fake_set_alert_exchange_selection(chat_id, selection):
        state['selection'] = telegram_bot_handler.normalize_alert_exchange_selection(selection)
        return state['selection']

    monkeypatch.setattr(telegram_bot_handler, 'get_alert_exchange_selection', fake_get_alert_exchange_selection)
    monkeypatch.setattr(telegram_bot_handler, 'set_alert_exchange_selection', fake_set_alert_exchange_selection)
    monkeypatch.setattr(telegram_bot_handler, 'get_supported_exchange_names', lambda: ['binance', 'kraken'])

    update = _make_update(callback_data='alertscope_toggle|kraken')
    context = SimpleNamespace()

    asyncio.run(telegram_bot_handler.alert_scope_callback(update, context))

    assert state['selection'] == {'mode': 'all', 'exchanges': []}
    assert update.callback_query.calls[0]['action'] == 'answer'
    assert update.callback_query.calls[-1]['action'] == 'edit_message_text'
    assert 'toggle any subset' in update.callback_query.calls[-1]['text'].lower()


def test_alert_scope_callback_ignores_noop_all_selection_edit(monkeypatch):
    state = {'selection': {'mode': 'all', 'exchanges': []}}

    def fake_get_alert_exchange_selection(chat_id):
        return state['selection']

    def fake_set_alert_exchange_selection(chat_id, selection):
        state['selection'] = telegram_bot_handler.normalize_alert_exchange_selection(selection)
        return state['selection']

    async def edit_message_text(text, reply_markup=None, parse_mode=None):
        raise BadRequest('Message is not modified: specified new message content and reply markup are exactly the same as a current content and reply markup of the message')

    monkeypatch.setattr(telegram_bot_handler, 'get_alert_exchange_selection', fake_get_alert_exchange_selection)
    monkeypatch.setattr(telegram_bot_handler, 'set_alert_exchange_selection', fake_set_alert_exchange_selection)
    monkeypatch.setattr(telegram_bot_handler, 'get_supported_exchange_names', lambda: ['binance', 'kraken'])

    update = _make_update(callback_data='alertscope_mode|all')
    update.callback_query.edit_message_text = edit_message_text
    context = SimpleNamespace()

    asyncio.run(telegram_bot_handler.alert_scope_callback(update, context))

    assert state['selection'] == {'mode': 'all', 'exchanges': []}
    assert update.callback_query.calls == [{'action': 'answer'}]


def test_alert_scope_menu_markup_includes_scope_buttons():
    markup = telegram_bot_handler.build_alert_scope_markup({'mode': 'selected', 'exchanges': ['kraken']}, view='root')
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert '🌍 All exchanges' in labels
    assert '🎯 Single exchange' in labels
    assert '🗂 Multiple exchanges' in labels
