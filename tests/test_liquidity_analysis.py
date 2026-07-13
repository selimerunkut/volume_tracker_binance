from src.services.liquidity_analysis import analyze_entry_liquidity, estimate_market_buy


def test_market_buy_consumes_multiple_ask_levels():
    result = estimate_market_buy([(100, 10), (101, 10)], 1500)
    assert result['filled_notional'] == 1500
    assert result['consumed_levels'] == 2
    assert result['vwap'] > 100
    assert result['insufficient_depth'] is False


def test_market_buy_reports_insufficient_depth():
    result = estimate_market_buy([(100, 1)], 3000)
    assert result['filled_notional'] == 100
    assert result['insufficient_depth'] is True


def test_invalid_book_is_unavailable():
    result = analyze_entry_liquidity({'asks': [('bad', 1)]})
    assert result['unavailable'] is True


def test_insufficient_depth_is_labeled_severe():
    result = analyze_entry_liquidity({'asks': [(100, 10)]}, notionals=(3000, 5000, 10000))
    assert result['unavailable'] is False
    assert 'SEVERE' in result['summary']
