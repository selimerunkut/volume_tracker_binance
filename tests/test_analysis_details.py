from __future__ import annotations

import telegram_bot_handler as tb


def test_news_links_are_clickable_only_for_http_urls():
    rendered = tb.format_news_items_html(
        [
            {'title': 'Safe <headline>', 'source': 'Feed', 'url': 'https://example.test/story'},
            {'title': 'Ignore javascript', 'source': 'Feed', 'url': 'javascript:alert(1)'},
            {'title': 'No link', 'source': 'Feed', 'url': None},
        ]
    )

    assert '<a href="https://example.test/story">Safe &lt;headline&gt;</a>' in rendered
    assert 'javascript:alert(1)' not in rendered
    assert 'No link' in rendered
    assert rendered.count('<a href=') == 1


def test_analysis_details_message_is_structured_and_escaped():
    message = tb.format_analysis_details_message(
        {
            'symbol': 'SAFEUSD',
            'strategy_type': 'WAIT',
            'reasoning': 'Neutral <stable> state.',
            'analysis_data': {
                'exchange_name': 'kraken',
                'action': 'WAIT',
                'confidence': 72,
                'entry': 1.23,
                'tp': 1.23,
                'sl': 1.23,
                'score': 1,
                'rule_ids': ['macd_bullish'],
                'indicators': {
                    'rsi': 61.35,
                    'macd': 0.12,
                    'macd_signal': 0.10,
                    'ema_50': 0.11,
                    'bb_lower': 0.09,
                    'bb_upper': 0.14,
                },
                'news_items': [
                    {'title': 'SAFE <update>', 'source': 'Feed', 'url': 'https://example.test/news'},
                ],
            },
        }
    )

    assert '<b>KRAKEN analysis details for SAFEUSD</b>' in message
    assert '<b>Informational news — not used in the signal</b>' in message
    assert '<a href="https://example.test/news">SAFE &lt;update&gt;</a>' in message
    assert 'Neutral &lt;stable&gt; state.' in message
    assert 'Entry / TP / SL' in message
