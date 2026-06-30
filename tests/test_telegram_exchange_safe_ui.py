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
        return recorder

    async def edit_text(text, reply_markup=None, parse_mode=None):
        recorder.calls.append(
            {
                'text': text,
                'reply_markup': reply_markup,
                'parse_mode': parse_mode,
            }
        )

    recorder = SimpleNamespace(calls=[], reply_text=reply_text, edit_text=edit_text)
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


def test_menu_analyze_pair_button_defaults_to_all_exchanges_without_scope_picker(monkeypatch):
    analyzed = []

    monkeypatch.setattr(telegram_bot_handler, 'get_supported_exchange_names', lambda: ['binance', 'kraken'])
    monkeypatch.setattr(telegram_bot_handler, 'get_setting', lambda key, default=None: default)
    monkeypatch.setattr(telegram_bot_handler, 'validate_trading_pair', lambda symbol, exchange_name='binance': (True, None))

    async def fake_analyze_and_suggest(symbol, exchange_name='binance'):
        analyzed.append((symbol, exchange_name))
        return {
            'action': 'WAIT',
            'confidence': 77,
            'reasoning': f'ok on {exchange_name}',
        }

    monkeypatch.setattr(telegram_bot_handler, 'analyze_and_suggest', fake_analyze_and_suggest)

    update = _make_update(callback_data='menu_analyze_BABYDOGE-EUR')
    context = SimpleNamespace(user_data={}, args=[])

    asyncio.run(telegram_bot_handler.menu_callback(update, context))

    texts = [call.get('text', '') for call in update.effective_message.calls]
    assert all('Choose the exchange scope' not in text for text in texts)
    assert analyzed == [('BABYDOGE-EUR', 'binance'), ('BABYDOGE-EUR', 'kraken')]
    assert 'BINANCE strategy for BABYDOGE-EUR' in texts[-1]
    assert 'KRAKEN strategy for BABYDOGE-EUR' in texts[-1]


def test_menu_analyze_pair_button_keeps_original_alert_message_visible(monkeypatch):
    analyzed = []

    monkeypatch.setattr(telegram_bot_handler, 'get_supported_exchange_names', lambda: ['binance'])
    monkeypatch.setattr(telegram_bot_handler, 'get_setting', lambda key, default=None: default)
    monkeypatch.setattr(telegram_bot_handler, 'validate_trading_pair', lambda symbol, exchange_name='binance': (True, None))

    async def fake_analyze_and_suggest(symbol, exchange_name='binance'):
        analyzed.append((symbol, exchange_name))
        return {
            'action': 'WAIT',
            'confidence': 88,
            'reasoning': 'ok',
        }

    monkeypatch.setattr(telegram_bot_handler, 'analyze_and_suggest', fake_analyze_and_suggest)

    update = _make_update(callback_data='menu_analyze_STEEMUSDC')
    context = SimpleNamespace(user_data={}, args=[])

    asyncio.run(telegram_bot_handler.menu_callback(update, context))

    assert analyzed == [('STEEMUSDC', 'binance')]
    assert not any(call.get('action') == 'edit_message_text' for call in update.callback_query.calls)
    assert any('Analyzing STEEMUSDC on BINANCE' in call.get('text', '') for call in update.effective_message.calls)
    assert any('BINANCE strategy for STEEMUSDC' in call.get('text', '') for call in update.effective_message.calls)


def test_menu_analyze_pair_button_can_preserve_existing_scope_picker(monkeypatch):
    monkeypatch.setattr(telegram_bot_handler, 'get_setting', lambda key, default=None: 'ask')

    update = _make_update(callback_data='menu_analyze_BABYDOGE-EUR')
    context = SimpleNamespace(user_data={}, args=[])

    asyncio.run(telegram_bot_handler.menu_callback(update, context))

    assert context.user_data['pending_action'] == 'analyze'
    assert context.user_data['pending_symbol'] == 'BABYDOGE-EUR'
    assert 'Choose the exchange scope' in update.callback_query.calls[-1]['text']


def test_analyze_command_defaults_to_all_exchanges_without_scope_picker(monkeypatch):
    analyzed = []

    monkeypatch.setattr(telegram_bot_handler, 'get_supported_exchange_names', lambda: ['binance', 'kraken'])
    monkeypatch.setattr(telegram_bot_handler, 'validate_trading_pair', lambda symbol, exchange_name='binance': (True, None))

    async def fake_analyze_and_suggest(symbol, exchange_name='binance'):
        analyzed.append((symbol, exchange_name))
        return {
            'action': 'WAIT',
            'confidence': 90,
            'reasoning': 'ok',
        }

    monkeypatch.setattr(telegram_bot_handler, 'analyze_and_suggest', fake_analyze_and_suggest)

    update = _make_update()
    context = SimpleNamespace(user_data={}, args=['SUIUSD'])

    asyncio.run(telegram_bot_handler.analyze_symbol(update, context))

    texts = [call.get('text', '') for call in update.effective_message.calls]
    assert all('Choose the exchange scope' not in text for text in texts)
    assert analyzed == [('SUIUSD', 'binance'), ('SUIUSD', 'kraken')]
    assert any('Analyzing SUIUSD on BINANCE, KRAKEN' in text for text in texts)


def test_analyze_command_accepts_ask_parameter_for_scope_picker(monkeypatch):
    monkeypatch.setattr(telegram_bot_handler, 'get_supported_exchange_names', lambda: ['binance', 'kraken'])
    monkeypatch.setattr(telegram_bot_handler, 'validate_trading_pair', lambda symbol, exchange_name='binance': (True, None))

    update = _make_update()
    context = SimpleNamespace(user_data={}, args=['ask', 'SUIUSD'])

    asyncio.run(telegram_bot_handler.analyze_symbol(update, context))

    assert 'Choose the exchange scope' in update.effective_message.calls[-1]['text']


def test_pair_button_analysis_mode_defaults_invalid_settings_to_all(monkeypatch):
    monkeypatch.setattr(telegram_bot_handler, 'get_setting', lambda key, default=None: 'surprise')

    assert telegram_bot_handler.get_pair_button_analysis_mode() == 'all'


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
    monkeypatch.setattr(telegram_bot_handler, 'validate_trading_pair', lambda symbol, exchange_name='binance': (True, None))

    update = _make_update(callback_data='scope|analyze|set|single|kraken')
    update.callback_query.edit_message_text = fake_edit_message_text
    context = SimpleNamespace(user_data={'pending_action': 'analyze', 'pending_symbol': 'BTCUSD'})

    asyncio.run(telegram_bot_handler.scope_callback(update, context))

    assert observed['analysis_args'] == ('BTCUSD', 'kraken')
    assert 'KRAKEN' in observed['edit_text']


def test_analyze_symbol_skips_unavailable_exchange_with_clean_message(monkeypatch):
    analyzed = []

    monkeypatch.setattr(telegram_bot_handler, 'get_supported_exchange_names', lambda: ['binance', 'kraken', 'okx'])

    def fake_validate(symbol, exchange_name='binance'):
        if exchange_name == 'kraken':
            return False, 'invalid_symbol'
        return True, None

    async def fake_analyze_and_suggest(symbol, exchange_name='binance'):
        analyzed.append((symbol, exchange_name))
        return {
            'action': 'WAIT',
            'confidence': 81,
            'reasoning': f'valid on {exchange_name}',
        }

    monkeypatch.setattr(telegram_bot_handler, 'validate_trading_pair', fake_validate)
    monkeypatch.setattr(telegram_bot_handler, 'analyze_and_suggest', fake_analyze_and_suggest)

    update = _make_update(callback_data='scope|unused')
    context = SimpleNamespace(user_data={}, args=[])

    asyncio.run(telegram_bot_handler.analyze_symbol(update, context, symbol='BABYDOGE-EUR', exchange_scope='all'))

    final_text = update.callback_query.calls[-1]['text']
    assert analyzed == [('BABYDOGE-EUR', 'binance'), ('BABYDOGE-EUR', 'okx')]
    assert 'BINANCE strategy for BABYDOGE-EUR' in final_text
    assert 'OKX strategy for BABYDOGE-EUR' in final_text
    assert 'KRAKEN: BABYDOGE-EUR is not listed on this exchange.' in final_text
    assert 'error -' not in final_text
    assert 'Failed to fetch market data' not in final_text
    assert 'Is it a valid symbol' not in final_text


def test_analysis_error_fallback_hides_raw_market_data_error(monkeypatch):
    monkeypatch.setattr(telegram_bot_handler, 'validate_trading_pair', lambda symbol, exchange_name='binance': (True, None))

    async def fake_analyze_and_suggest(symbol, exchange_name='binance'):
        return {
            'error': f'Failed to fetch market data for {symbol} on {exchange_name}. Is it a valid symbol for that exchange?'
        }

    monkeypatch.setattr(telegram_bot_handler, 'analyze_and_suggest', fake_analyze_and_suggest)

    update = _make_update(callback_data='scope|unused')
    context = SimpleNamespace(user_data={}, args=[])

    asyncio.run(telegram_bot_handler.analyze_symbol(update, context, symbol='BABYDOGE-EUR', exchange_scope='kraken'))

    final_text = update.callback_query.calls[-1]['text']
    assert final_text == 'KRAKEN: BABYDOGE-EUR is not listed on this exchange.'
    assert 'error -' not in final_text
    assert 'Failed to fetch market data' not in final_text
    assert 'Is it a valid symbol' not in final_text


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
