"""Deterministic market-entry impact estimates from a visible ask book."""

import math


def estimate_market_buy(asks, quote_notional):
    requested = float(quote_notional)
    if not math.isfinite(requested) or requested <= 0:
        raise ValueError('quote_notional must be positive')
    levels = []
    for level in asks or []:
        try:
            price, quantity = float(level[0]), float(level[1])
        except (TypeError, ValueError, IndexError):
            continue
        if math.isfinite(price) and math.isfinite(quantity) and price > 0 and quantity > 0:
            levels.append((price, quantity))
    levels.sort(key=lambda item: item[0])
    best_price = levels[0][0] if levels else None
    remaining = requested
    filled = 0.0
    base_filled = 0.0
    consumed = 0
    for price, quantity in levels:
        notional = min(remaining, price * quantity)
        filled += notional
        base_filled += notional / price
        remaining -= notional
        consumed += 1
        if remaining <= 1e-9:
            break
    vwap = filled / base_filled if base_filled else None
    slippage_pct = ((vwap / best_price) - 1.0) * 100 if vwap and best_price else None
    return {
        'vwap': vwap,
        'slippage_pct': slippage_pct,
        'filled_notional': filled,
        'consumed_levels': consumed,
        'insufficient_depth': remaining > 1e-9,
    }


def analyze_entry_liquidity(order_book, notionals=(3000, 5000, 10000)):
    sizes = {int(size): estimate_market_buy(order_book.get('asks', []), size) for size in notionals}
    unavailable = not order_book or not order_book.get('asks') or all(item['vwap'] is None for item in sizes.values())
    if unavailable:
        return {'unavailable': True, 'sizes': {int(size): estimate_market_buy([], size) for size in notionals}}
    worst = max(
        (item['slippage_pct'] if item['slippage_pct'] is not None else float('inf'))
        for item in sizes.values()
    )
    if worst < 0.25:
        label = '✅ Liquidity: GOOD'
    elif worst < 0.75:
        label = '⚠️ Liquidity: MODERATE — larger entries may move the price materially'
    elif worst < 1.50:
        label = '⚠️ Liquidity: HIGH — entries may move the price materially'
    else:
        label = '🚨 Liquidity: SEVERE — entry depth is thin'
    return {'unavailable': False, 'sizes': sizes, 'summary': label}
