"""Small helpers for comparing exchange quote values in USD terms."""

import math


STABLE_QUOTES = {'USD', 'USDC', 'USDT'}


def to_usd_quote_value(native_quote_value, quote_asset, usd_rate=1.0):
    value = float(native_quote_value)
    rate = 1.0 if str(quote_asset).upper() in STABLE_QUOTES else float(usd_rate)
    if not math.isfinite(value) or value < 0 or not math.isfinite(rate) or rate <= 0:
        raise ValueError('quote value and conversion rate must be finite and non-negative')
    return value * rate
