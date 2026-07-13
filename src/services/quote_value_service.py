"""Small helpers for comparing exchange quote values in USD terms."""

import math


STABLE_QUOTES = {'USD', 'USDC', 'USDT'}


def to_usd_quote_value(native_quote_value, quote_asset, usd_rate=1.0):
    try:
        value = float(native_quote_value)
        rate = 1.0 if str(quote_asset).upper() in STABLE_QUOTES else float(usd_rate)
    except (TypeError, ValueError) as exc:
        raise ValueError('quote value and conversion rate must be numeric') from exc
    if not math.isfinite(value) or value < 0 or not math.isfinite(rate) or rate <= 0:
        raise ValueError('quote value must be finite and non-negative; rate must be finite and positive')
    return value * rate


def rate_from_bid_ask(bid, ask, *, inverse=False):
    """Return a conservative USD rate from a market bid/ask quote.

    Direct markets use the bid (the amount received when selling the quote
    asset); inverse markets use one divided by the ask.
    """
    try:
        bid = float(bid)
        ask = float(ask)
    except (TypeError, ValueError) as exc:
        raise ValueError('bid and ask must be numeric') from exc
    if not math.isfinite(bid) or not math.isfinite(ask) or bid <= 0 or ask <= 0:
        raise ValueError('bid and ask must be finite and positive')
    return 1.0 / ask if inverse else bid
