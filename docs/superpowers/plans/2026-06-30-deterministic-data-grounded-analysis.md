# Deterministic Data-Grounded Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `/analyze` LLM decisions with reproducible rule-based strategies, retain exchange isolation, and show informational news as safe clickable links in analysis details.

**Architecture:** A pure `deterministic_strategy` module converts a validated indicator snapshot into action, confidence, entry, TP, SL, rule IDs, and factual prose. A thin `strategy_advisor` service fetches exchange-specific data and news, invokes the pure engine, and persists structured evidence; Telegram only formats the result. News and historical outcomes never influence the signal.

**Tech Stack:** Python 3.12, pandas/pandas-ta, feedparser, SQLite, python-telegram-bot, pytest.

## Global Constraints

- KISS: use one transparent score, fixed thresholds, and fixed 2:1 reward/risk targets.
- YAGNI: no strategy DSL, plugin framework, prompt layer, NLP sentiment system, or database migration.
- DRY: one structured indicator snapshot and one stored `analysis_data` payload feed persistence and Telegram details.
- SOLID: keep pure decision policy, data orchestration, persistence, and presentation separate.
- Same symbol, exchange, OHLCV snapshot, and current price must produce byte-for-byte equivalent strategy fields.
- News is informational only and must never alter action, score, confidence, entry, TP, or SL.
- Each exchange is analyzed and later evaluated using that exchange's market price.
- Dynamic Telegram content and URLs must be escaped; only `http` and `https` news links are clickable.
- No new dependencies.

## File Structure

- Create `src/services/deterministic_strategy.py`: pure scoring, confidence, risk targets, rule IDs, and factual explanation.
- Create `src/services/strategy_advisor.py`: exchange-specific fetch/calculate/save orchestration under the existing `analyze_and_suggest` interface.
- Create `tests/test_deterministic_strategy.py`: policy boundary and repeatability tests.
- Create `tests/test_strategy_advisor.py`: orchestration, persistence, news-independence, and exchange-isolation tests.
- Create `tests/test_analysis_details.py`: RSS-link retention and Telegram HTML rendering tests.
- Create `tests/test_performance_tracker_exchange.py`: exchange-aware outcome lookup test.
- Modify `src/services/news_service.py`: retain RSS article URLs and remove LLM-only formatting.
- Modify `src/services/db_service.py`: deserialize `analysis_data` consistently for pending suggestions and detail/history reads.
- Modify `src/services/performance_tracker.py`: fetch each suggestion's price from its stored exchange.
- Modify `telegram_bot_handler.py`: import deterministic advisor, show one details button per exchange, and render structured indicators/rules/news links.
- Modify `pyproject.toml` and `uv.lock`: remove the unused `openai` package.
- Modify `README.md`, `AGENTS.md`, `credentials_b.json_example`, `setup_bot_server.sh`, and current memory-bank documentation: describe deterministic analysis and remove active LLM configuration instructions.
- Delete `src/services/llm_strategy.py`, `src/services/macro_data_service.py`, and `tests/test_llm_strategy_exchange.py` after their supported behavior is replaced.

---

### Task 1: Implement the Pure Deterministic Strategy Policy

**Files:**
- Create: `src/services/deterministic_strategy.py`
- Create: `tests/test_deterministic_strategy.py`

**Interfaces:**
- Consumes: `evaluate_strategy(indicators: dict[str, float], current_price: float) -> dict`
- Produces: a dictionary containing `action`, `confidence`, `entry`, `tp`, `sl`, `reasoning`, `score`, and `rule_ids`.
- Policy: RSI contributes `+2` at or below 30 and `-2` at or above 70; MACD-vs-signal and price-vs-EMA50 each contribute `+1` or `-1`; price at/outside a Bollinger band contributes `+1` or `-1`.
- Decision: score `>= 3` is LONG, score `<= -3` is SHORT, otherwise WAIT.
- Confidence: LONG/SHORT is `min(90, 50 + 10 * abs(score))`; WAIT is `max(50, 70 - 10 * abs(score))`.
- Risk: LONG TP `+4%`, SL `-2%`; SHORT TP `-4%`, SL `+2%`; WAIT uses current price for entry/TP/SL because the existing schema requires non-null values.

- [ ] **Step 1: Write failing policy and repeatability tests**

```python
from src.services.deterministic_strategy import evaluate_strategy


def snapshot(**overrides):
    values = {
        "rsi": 50.0,
        "macd": 0.0,
        "macd_signal": 0.0,
        "ema_50": 100.0,
        "bb_lower": 90.0,
        "bb_upper": 110.0,
    }
    values.update(overrides)
    return values


def test_bullish_votes_produce_long_with_fixed_risk():
    result = evaluate_strategy(
        snapshot(rsi=28.0, macd=1.0, macd_signal=0.5, ema_50=95.0),
        current_price=100.0,
    )
    assert result == {
        "action": "LONG",
        "confidence": 90,
        "entry": 100.0,
        "tp": 104.0,
        "sl": 98.0,
        "reasoning": (
            "RSI is 28.00, at or below the oversold threshold of 30 (+2). "
            "MACD 1.0000 is above its signal 0.5000 (+1). "
            "Price 100.00000000 is above EMA(50) 95.00000000 (+1). "
            "Price is inside the Bollinger Bands (0). Total score: +4; LONG requires at least +3."
        ),
        "score": 4,
        "rule_ids": ["rsi_oversold", "macd_bullish", "price_above_ema50", "price_inside_bands"],
    }


def test_bearish_votes_produce_short_with_fixed_risk():
    result = evaluate_strategy(
        snapshot(rsi=75.0, macd=-1.0, macd_signal=-0.5, ema_50=105.0, bb_lower=90.0, bb_upper=99.0),
        current_price=100.0,
    )
    assert result["action"] == "SHORT"
    assert result["confidence"] == 90
    assert result["tp"] == 96.0
    assert result["sl"] == 102.0
    assert result["score"] == -5


def test_mixed_votes_produce_wait():
    result = evaluate_strategy(
        snapshot(rsi=50.0, macd=1.0, macd_signal=0.5, ema_50=105.0),
        current_price=100.0,
    )
    assert result["action"] == "WAIT"
    assert result["confidence"] == 70
    assert result["entry"] == result["tp"] == result["sl"] == 100.0


def test_same_inputs_produce_identical_result():
    indicators = snapshot(rsi=61.35, macd=0.002, macd_signal=0.001, ema_50=99.0)
    first = evaluate_strategy(indicators, 100.0)
    second = evaluate_strategy(dict(indicators), 100.0)
    assert first == second


def test_missing_or_non_finite_values_are_rejected():
    import math
    import pytest

    with pytest.raises(ValueError, match="Missing indicator: rsi"):
        evaluate_strategy({key: value for key, value in snapshot().items() if key != "rsi"}, 100.0)
    with pytest.raises(ValueError, match="Non-finite indicator: macd"):
        evaluate_strategy(snapshot(macd=math.nan), 100.0)
```

- [ ] **Step 2: Run the tests and verify they fail because the module does not exist**

Run: `uv run --with pytest pytest tests/test_deterministic_strategy.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'src.services.deterministic_strategy'`.

- [ ] **Step 3: Implement the complete pure policy**

```python
import math


REQUIRED_INDICATORS = ("rsi", "macd", "macd_signal", "ema_50", "bb_lower", "bb_upper")


def _number(values, key):
    if key not in values:
        raise ValueError(f"Missing indicator: {key}")
    value = float(values[key])
    if not math.isfinite(value):
        raise ValueError(f"Non-finite indicator: {key}")
    return value


def evaluate_strategy(indicators, current_price):
    price = float(current_price)
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Current price must be a positive finite number")

    values = {key: _number(indicators, key) for key in REQUIRED_INDICATORS}
    score = 0
    rule_ids = []
    reasons = []

    if values["rsi"] <= 30:
        score += 2
        rule_ids.append("rsi_oversold")
        reasons.append(f'RSI is {values["rsi"]:.2f}, at or below the oversold threshold of 30 (+2).')
    elif values["rsi"] >= 70:
        score -= 2
        rule_ids.append("rsi_overbought")
        reasons.append(f'RSI is {values["rsi"]:.2f}, at or above the overbought threshold of 70 (-2).')
    else:
        rule_ids.append("rsi_neutral")
        reasons.append(f'RSI is {values["rsi"]:.2f}, between 30 and 70 (0).')

    if values["macd"] > values["macd_signal"]:
        score += 1
        rule_ids.append("macd_bullish")
        reasons.append(f'MACD {values["macd"]:.4f} is above its signal {values["macd_signal"]:.4f} (+1).')
    elif values["macd"] < values["macd_signal"]:
        score -= 1
        rule_ids.append("macd_bearish")
        reasons.append(f'MACD {values["macd"]:.4f} is below its signal {values["macd_signal"]:.4f} (-1).')
    else:
        rule_ids.append("macd_neutral")
        reasons.append(f'MACD equals its signal at {values["macd"]:.4f} (0).')

    if price > values["ema_50"]:
        score += 1
        rule_ids.append("price_above_ema50")
        reasons.append(f'Price {price:.8f} is above EMA(50) {values["ema_50"]:.8f} (+1).')
    elif price < values["ema_50"]:
        score -= 1
        rule_ids.append("price_below_ema50")
        reasons.append(f'Price {price:.8f} is below EMA(50) {values["ema_50"]:.8f} (-1).')
    else:
        rule_ids.append("price_at_ema50")
        reasons.append(f'Price equals EMA(50) at {price:.8f} (0).')

    if price <= values["bb_lower"]:
        score += 1
        rule_ids.append("price_at_or_below_lower_band")
        reasons.append(f'Price is at or below the lower Bollinger Band {values["bb_lower"]:.8f} (+1).')
    elif price >= values["bb_upper"]:
        score -= 1
        rule_ids.append("price_at_or_above_upper_band")
        reasons.append(f'Price is at or above the upper Bollinger Band {values["bb_upper"]:.8f} (-1).')
    else:
        rule_ids.append("price_inside_bands")
        reasons.append("Price is inside the Bollinger Bands (0).")

    if score >= 3:
        action = "LONG"
        confidence = min(90, 50 + 10 * abs(score))
        tp, sl = price * 1.04, price * 0.98
        conclusion = f"Total score: {score:+d}; LONG requires at least +3."
    elif score <= -3:
        action = "SHORT"
        confidence = min(90, 50 + 10 * abs(score))
        tp, sl = price * 0.96, price * 1.02
        conclusion = f"Total score: {score:+d}; SHORT requires at most -3."
    else:
        action = "WAIT"
        confidence = max(50, 70 - 10 * abs(score))
        tp = sl = price
        conclusion = f"Total score: {score:+d}; LONG needs +3 and SHORT needs -3."

    return {
        "action": action,
        "confidence": confidence,
        "entry": round(price, 12),
        "tp": round(tp, 12),
        "sl": round(sl, 12),
        "reasoning": " ".join([*reasons, conclusion]),
        "score": score,
        "rule_ids": rule_ids,
    }
```

- [ ] **Step 4: Run the policy tests**

Run: `uv run --with pytest pytest tests/test_deterministic_strategy.py -q`

Expected: `5 passed`.

- [ ] **Step 5: Commit the policy**

```bash
git add src/services/deterministic_strategy.py tests/test_deterministic_strategy.py
git commit -m "feat: add deterministic strategy policy"
```

---

### Task 2: Replace LLM Orchestration with a Thin Deterministic Advisor

**Files:**
- Create: `src/services/strategy_advisor.py`
- Create: `tests/test_strategy_advisor.py`
- Delete after replacement: `tests/test_llm_strategy_exchange.py`

**Interfaces:**
- Consumes: `get_current_price`, `fetch_klines`, `calculate_indicators`, `get_latest_indicators`, `get_latest_news`, `evaluate_strategy`, `save_suggestion`.
- Produces: `analyze_and_suggest(symbol: str, exchange_name: str = "binance") -> dict`, preserving the Telegram-facing interface.
- Stored `analysis_data`: `exchange_name`, `current_price`, `indicators`, `score`, `rule_ids`, and `news_items`.

- [ ] **Step 1: Write failing orchestration and news-independence tests**

```python
import pandas as pd

from src.services import strategy_advisor


INDICATORS = {
    "rsi": 50.0,
    "macd": 0.2,
    "macd_signal": 0.1,
    "ema_50": 99.0,
    "ema_200": 95.0,
    "bb_lower": 90.0,
    "bb_middle": 100.0,
    "bb_upper": 110.0,
    "close": 100.0,
    "volume": 1234.0,
}


def wire(monkeypatch, news):
    observed = {}

    def fake_price(symbol, exchange_name="binance"):
        observed["price_exchange"] = exchange_name
        return 100.0

    def fake_klines(symbol, interval="1h", limit=250, exchange_name="binance"):
        observed["kline_exchange"] = exchange_name
        return pd.DataFrame([{"close": 100.0}])

    monkeypatch.setattr(strategy_advisor, "get_current_price", fake_price)
    monkeypatch.setattr(strategy_advisor, "fetch_klines", fake_klines)
    monkeypatch.setattr(strategy_advisor, "calculate_indicators", lambda frame: frame)
    monkeypatch.setattr(strategy_advisor, "get_latest_indicators", lambda frame: dict(INDICATORS))
    monkeypatch.setattr(strategy_advisor, "get_latest_news", lambda limit=5: news)
    saved = {}
    monkeypatch.setattr(strategy_advisor, "save_suggestion", lambda **kwargs: saved.update(kwargs) or 42)
    return observed, saved


def test_requested_exchange_is_used_and_persisted(monkeypatch):
    observed, saved = wire(monkeypatch, [{"title": "Market update", "url": "https://example.test/a", "source": "Example", "published": "Today"}])
    result = strategy_advisor.analyze_and_suggest("SAFEUSD", exchange_name="kraken")
    assert observed == {"price_exchange": "kraken", "kline_exchange": "kraken"}
    assert result["suggestion_id"] == 42
    assert saved["analysis_data"]["exchange_name"] == "kraken"
    assert saved["analysis_data"]["news_items"][0]["url"] == "https://example.test/a"


def test_news_content_cannot_change_strategy(monkeypatch):
    _, saved_a = wire(monkeypatch, [{"title": "Bullish", "url": "https://example.test/up", "source": "A", "published": "Today"}])
    first = strategy_advisor.analyze_and_suggest("SAFEUSD", "okx")
    _, saved_b = wire(monkeypatch, [{"title": "Bearish", "url": "https://example.test/down", "source": "B", "published": "Today"}])
    second = strategy_advisor.analyze_and_suggest("SAFEUSD", "okx")
    for key in ("action", "confidence", "entry", "tp", "sl", "reasoning", "score", "rule_ids"):
        assert first[key] == second[key]
    assert saved_a["analysis_data"]["news_items"] != saved_b["analysis_data"]["news_items"]


def test_missing_market_data_returns_exchange_specific_error(monkeypatch):
    monkeypatch.setattr(strategy_advisor, "get_current_price", lambda *args, **kwargs: 100.0)
    monkeypatch.setattr(strategy_advisor, "fetch_klines", lambda *args, **kwargs: pd.DataFrame())
    assert strategy_advisor.analyze_and_suggest("SAFEUSD", "kraken") == {
        "error": "Failed to fetch market data for SAFEUSD on kraken. Is it a valid symbol for that exchange?"
    }
```

- [ ] **Step 2: Run the tests and verify the new service is missing**

Run: `uv run --with pytest pytest tests/test_strategy_advisor.py -q`

Expected: collection fails because `src.services.strategy_advisor` does not exist.

- [ ] **Step 3: Implement the deterministic orchestration service**

```python
import logging

from .db_service import save_suggestion
from .deterministic_strategy import evaluate_strategy
from .market_data_service import fetch_klines, get_current_price
from .news_service import get_latest_news
from .technical_analysis import calculate_indicators, get_latest_indicators


logger = logging.getLogger(__name__)


def normalize_exchange_name(exchange_name):
    normalized = str(exchange_name or "binance").strip().lower()
    return normalized or "binance"


def analyze_and_suggest(symbol, exchange_name="binance"):
    exchange_name = normalize_exchange_name(exchange_name)
    symbol = symbol.upper()
    try:
        current_price = get_current_price(symbol, exchange_name=exchange_name)
        klines = fetch_klines(symbol, interval="1h", limit=250, exchange_name=exchange_name)
        if klines is None or klines.empty:
            return {"error": f"Failed to fetch market data for {symbol} on {exchange_name}. Is it a valid symbol for that exchange?"}

        raw_indicators = get_latest_indicators(calculate_indicators(klines))
        indicators = {
            key: float(value)
            for key, value in raw_indicators.items()
            if value is not None
        }
        strategy = evaluate_strategy(indicators, current_price)
        news_items = get_latest_news(limit=5)
        analysis_data = {
            "exchange_name": exchange_name,
            "current_price": current_price,
            "indicators": indicators,
            "score": strategy["score"],
            "rule_ids": strategy["rule_ids"],
            "news_items": news_items,
        }
        suggestion_id = save_suggestion(
            symbol=symbol,
            strategy_type=strategy["action"],
            entry_price=strategy["entry"],
            take_profit=strategy["tp"],
            stop_loss=strategy["sl"],
            reasoning=strategy["reasoning"],
            analysis_data=analysis_data,
        )
        return {**strategy, "suggestion_id": suggestion_id}
    except Exception as exc:
        logger.error("Deterministic analysis failed for %s on %s: %s", symbol, exchange_name, exc)
        return {"error": str(exc)}
```

- [ ] **Step 4: Run the orchestration and policy tests**

Run: `uv run --with pytest pytest tests/test_strategy_advisor.py tests/test_deterministic_strategy.py -q`

Expected: `8 passed`.

- [ ] **Step 5: Remove the superseded LLM orchestration test and commit**

```bash
git rm tests/test_llm_strategy_exchange.py
git add src/services/strategy_advisor.py tests/test_strategy_advisor.py
git commit -m "feat: orchestrate deterministic exchange analysis"
```

---

### Task 3: Preserve RSS Links and Render Exchange-Specific Analysis Details

**Files:**
- Modify: `src/services/news_service.py:41-127`
- Modify: `telegram_bot_handler.py:16-20,698-867`
- Create: `tests/test_analysis_details.py`
- Modify: `tests/test_telegram_exchange_safe_ui.py`

**Interfaces:**
- `fetch_feed(...)` adds `url` to each news dictionary from `entry.link`.
- `format_news_items_html(news_items: list[dict]) -> str` returns Telegram-safe HTML.
- `format_indicator_details(indicators: dict) -> str` returns escaped plain factual lines.
- `/analyze` creates one details button for every successful exchange suggestion.

- [ ] **Step 1: Write failing RSS URL and safe HTML tests**

```python
from types import SimpleNamespace

from src.services import news_service
import telegram_bot_handler


def test_fetch_feed_retains_entry_link(monkeypatch):
    entry = SimpleNamespace(
        title="SAFE rises <fast>",
        summary="Summary",
        published="2026-06-30",
        link="https://example.test/news?a=1&b=2",
    )
    monkeypatch.setattr(news_service.feedparser, "parse", lambda url: SimpleNamespace(bozo=False, entries=[entry]))
    assert news_service.fetch_feed("Example", "https://example.test/feed", limit=1)[0]["url"] == "https://example.test/news?a=1&b=2"


def test_news_formatter_escapes_text_and_builds_safe_links():
    rendered = telegram_bot_handler.format_news_items_html([
        {"title": "SAFE <rises>", "source": "A&B", "published": "Today", "url": "https://example.test/a?x=1&y=2"},
        {"title": "Unsafe", "source": "X", "published": "Today", "url": "javascript:alert(1)"},
    ])
    assert '<a href="https://example.test/a?x=1&amp;y=2">SAFE &lt;rises&gt;</a>' in rendered
    assert "A&amp;B — Today" in rendered
    assert "javascript:" not in rendered
    assert "Unsafe" in rendered


def test_indicator_formatter_uses_structured_values():
    rendered = telegram_bot_handler.format_indicator_details({
        "rsi": 61.35,
        "macd": 0.0012,
        "macd_signal": 0.0009,
        "ema_50": 0.083,
        "ema_200": 0.079,
        "bb_lower": 0.078,
        "bb_middle": 0.083,
        "bb_upper": 0.088,
    })
    assert "RSI(14): 61.35" in rendered
    assert "MACD: 0.0012" in rendered
    assert "Bollinger Bands" in rendered
```

- [ ] **Step 2: Add a failing multi-exchange details-button assertion**

In `tests/test_telegram_exchange_safe_ui.py`, extend the successful all-exchange test fake so each result has an exchange-specific ID and assert:

```python
reply_markup = update.effective_message.calls[-1]["reply_markup"]
buttons = [row[0] for row in reply_markup.inline_keyboard]
assert [button.text for button in buttons] == ["📜 BINANCE details", "📜 KRAKEN details"]
assert [button.callback_data for button in buttons] == ["details_101", "details_102"]
```

- [ ] **Step 3: Run the focused tests and verify failures**

Run: `uv run --with pytest pytest tests/test_analysis_details.py tests/test_telegram_exchange_safe_ui.py -q`

Expected: failures show missing RSS `url`, missing formatter functions, and only one details button.

- [ ] **Step 4: Retain RSS links and add small presentation helpers**

Add `url` in `fetch_feed`:

```python
news_items.append({
    "title": title.strip(),
    "summary": summary.strip() if isinstance(summary, str) else summary,
    "published": published,
    "source": source_name,
    "url": str(getattr(entry, "link", "") or "").strip(),
})
```

Add these helpers near the other Telegram formatting helpers:

```python
from urllib.parse import urlparse


def _format_number(value, decimals=2):
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "N/A"


def format_indicator_details(indicators):
    lines = [
        f'RSI(14): {_format_number(indicators.get("rsi"))}',
        f'MACD: {_format_number(indicators.get("macd"), 4)} (Signal: {_format_number(indicators.get("macd_signal"), 4)})',
        f'EMA(50): {_format_number(indicators.get("ema_50"), 8)}',
        f'EMA(200): {_format_number(indicators.get("ema_200"), 8)}',
        "Bollinger Bands: "
        f'Lower={_format_number(indicators.get("bb_lower"), 8)}, '
        f'Middle={_format_number(indicators.get("bb_middle"), 8)}, '
        f'Upper={_format_number(indicators.get("bb_upper"), 8)}',
    ]
    return html.escape("\n".join(lines))


def format_news_items_html(news_items):
    if not news_items:
        return "No recent news available."
    lines = []
    for item in news_items:
        title = html.escape(str(item.get("title") or "Untitled"))
        source = html.escape(str(item.get("source") or "Unknown source"))
        published = html.escape(str(item.get("published") or "Unknown date"))
        url = str(item.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            title = f'<a href="{html.escape(url, quote=True)}">{title}</a>'
        lines.append(f"• {title}\n  {source} — {published}")
    return "\n".join(lines)
```

- [ ] **Step 5: Switch Telegram to the deterministic advisor and structured details**

Replace the import:

```python
from src.services.strategy_advisor import analyze_and_suggest
```

Inside `analyze_symbol`, initialize `detail_buttons = []` before the exchange loop, append after each successful saved suggestion, and create the keyboard after the loop:

```python
detail_buttons = []

# inside the successful exchange branch
if strategy.get("suggestion_id"):
    detail_buttons.append([
        InlineKeyboardButton(
            f"📜 {exchange_name.upper()} details",
            callback_data=f'details_{strategy["suggestion_id"]}',
        )
    ])

# after the loop
reply_markup = InlineKeyboardMarkup(detail_buttons) if detail_buttons else None
```

Replace `details_callback` message construction with:

```python
data = details["analysis_data"]
exchange_name = html.escape(str(data.get("exchange_name", "binance")).upper())
symbol = html.escape(str(details["symbol"]))
rule_ids = ", ".join(html.escape(str(rule_id)) for rule_id in data.get("rule_ids", [])) or "N/A"
message = (
    f"📜 <b>{exchange_name} analysis details for {symbol}</b>\n\n"
    f"<b>Technical indicators</b>:\n{format_indicator_details(data.get('indicators', {}))}\n\n"
    f"<b>Deterministic score</b>: {html.escape(str(data.get('score', 'N/A')))}\n"
    f"<b>Triggered rules</b>: {rule_ids}\n\n"
    f"<b>Informational news — not used in the signal</b>:\n"
    f"{format_news_items_html(data.get('news_items', []))}"
)
```

- [ ] **Step 6: Run Telegram and news tests**

Run: `uv run --with pytest pytest tests/test_analysis_details.py tests/test_telegram_exchange_safe_ui.py tests/test_strategy_advisor.py -q`

Expected: all selected tests pass; the exact count may increase when the existing UI test is extended.

- [ ] **Step 7: Commit linked informational news and exchange detail buttons**

```bash
git add src/services/news_service.py telegram_bot_handler.py tests/test_analysis_details.py tests/test_telegram_exchange_safe_ui.py
git commit -m "feat: show linked news in deterministic analysis details"
```

---

### Task 4: Make Persisted Analysis and Performance Tracking Exchange-Safe

**Files:**
- Modify: `src/services/db_service.py:252-266,405-463`
- Modify: `src/services/performance_tracker.py:131-169`
- Create: `tests/test_performance_tracker_exchange.py`

**Interfaces:**
- `_deserialize_analysis_data(row) -> dict` converts a SQLite row and parses `analysis_data` once.
- `get_pending_suggestions()` returns dictionaries with `analysis_data` as a dictionary.
- `track_performance()` calls `get_current_price(symbol, exchange_name=stored_exchange)` for suggestions; existing signal-trade tracking remains unchanged because its schema has no exchange field and is outside `/analyze`.

- [ ] **Step 1: Write a failing exchange-aware tracker test**

```python
from src.services import performance_tracker


def test_pending_suggestion_uses_stored_exchange(monkeypatch):
    observed = []
    suggestion = {
        "id": 7,
        "symbol": "SAFEUSD",
        "strategy_type": "WAIT",
        "entry_price": 1.0,
        "take_profit": 1.0,
        "stop_loss": 1.0,
        "created_at": "2020-01-01T00:00:00",
        "analysis_data": {"exchange_name": "kraken"},
    }
    monkeypatch.setattr(performance_tracker, "get_pending_suggestions", lambda: [suggestion])
    monkeypatch.setattr(performance_tracker, "get_pending_signal_trades", lambda: [])
    monkeypatch.setattr(performance_tracker, "get_current_price", lambda symbol, exchange_name="binance": observed.append((symbol, exchange_name)) or 1.0)
    monkeypatch.setattr(performance_tracker, "update_outcome", lambda *args: None)
    performance_tracker.track_performance()
    assert observed == [("SAFEUSD", "kraken")]
```

- [ ] **Step 2: Add a failing database deserialization regression test**

Add to the same test file using a temporary database path:

```python
import json

from src.services import db_service


def test_pending_suggestions_deserialize_analysis_data(monkeypatch, tmp_path):
    monkeypatch.setattr(db_service, "DB_PATH", str(tmp_path / "memory.db"))
    db_service.init_db()
    db_service.save_suggestion(
        symbol="SAFEUSD",
        strategy_type="WAIT",
        entry_price=1.0,
        take_profit=1.0,
        stop_loss=1.0,
        reasoning="score 0",
        analysis_data={"exchange_name": "okx"},
    )
    rows = db_service.get_pending_suggestions()
    assert rows[0]["analysis_data"] == {"exchange_name": "okx"}
```

- [ ] **Step 3: Run the focused tests and verify the current failures**

Run: `uv run --with pytest pytest tests/test_performance_tracker_exchange.py -q`

Expected: tracker records `binance`, and pending `analysis_data` is still a JSON string.

- [ ] **Step 4: Centralize row deserialization in the database service**

```python
def _deserialize_analysis_data(row):
    data = dict(row)
    raw_analysis = data.get("analysis_data")
    if isinstance(raw_analysis, str):
        try:
            data["analysis_data"] = json.loads(raw_analysis)
        except json.JSONDecodeError:
            data["analysis_data"] = {}
    elif not isinstance(raw_analysis, dict):
        data["analysis_data"] = {}
    return data
```

Use it in all three readers:

```python
return [_deserialize_analysis_data(row) for row in rows]
```

For `get_suggestion_details`:

```python
return _deserialize_analysis_data(row) if row else None
```

- [ ] **Step 5: Use the stored exchange in suggestion performance tracking**

```python
analysis_data = suggestion.get("analysis_data") or {}
exchange_name = analysis_data.get("exchange_name", "binance")
current_price = get_current_price(symbol, exchange_name=exchange_name)
```

- [ ] **Step 6: Run database, tracker, and advisor tests**

Run: `uv run --with pytest pytest tests/test_performance_tracker_exchange.py tests/test_strategy_advisor.py tests/test_signal_persistence.py -q`

Expected: all selected tests pass.

- [ ] **Step 7: Commit exchange-safe persistence and tracking**

```bash
git add src/services/db_service.py src/services/performance_tracker.py tests/test_performance_tracker_exchange.py
git commit -m "fix: track analysis outcomes on their source exchange"
```

---

### Task 5: Remove the LLM Surface, Update Documentation, and Verify the System

**Files:**
- Delete: `src/services/llm_strategy.py`
- Delete: `src/services/macro_data_service.py`
- Modify: `src/services/news_service.py:103-127`
- Modify: `pyproject.toml:5-14`
- Modify generated lock: `uv.lock`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `credentials_b.json_example`
- Modify: `setup_bot_server.sh`
- Modify: `memory-bank/activeContext.md`
- Modify: `memory-bank/progress.md`
- Modify: `memory-bank/changelog.md`

**Interfaces:**
- No production import, credential, dependency, command, or documentation requires OpenAI/OpenRouter.
- Historical changelog entries remain intact; add a new dated entry instead of rewriting history.
- `get_latest_news()` remains the only news API needed by `/analyze`.

- [ ] **Step 1: Add a dependency-boundary regression test**

Append to `tests/test_strategy_advisor.py`:

```python
def test_strategy_advisor_has_no_llm_dependency():
    source = open(strategy_advisor.__file__, encoding="utf-8").read()
    forbidden = ("openai", "OpenRouter", "construct_prompt", "get_llm_client")
    assert all(name not in source for name in forbidden)
```

- [ ] **Step 2: Run the boundary test**

Run: `uv run --with pytest pytest tests/test_strategy_advisor.py::test_strategy_advisor_has_no_llm_dependency -q`

Expected: pass for the new service; the repository-wide search in Step 6 will remain red until cleanup is complete.

- [ ] **Step 3: Remove dead LLM and macro modules plus LLM-only news helpers**

```bash
git rm src/services/llm_strategy.py src/services/macro_data_service.py
```

Delete `get_macro_news()` and `format_news_for_llm()` from `src/services/news_service.py`; neither has a remaining caller after `strategy_advisor.py` becomes the `/analyze` service.

- [ ] **Step 4: Remove the OpenAI dependency and regenerate the lockfile**

Run: `uv remove openai`

Expected: `openai` is removed from `pyproject.toml`, and `uv.lock` is regenerated without the package unless another dependency requires it.

- [ ] **Step 5: Update active documentation and configuration examples**

Apply these exact content changes:

```text
README.md
- Rename "AI Strategy Advisor" to "Deterministic Strategy Advisor".
- Describe the fixed RSI/MACD/EMA/Bollinger score and fixed 2:1 reward/risk levels.
- State explicitly that news is informational and does not affect the signal.
- Show linked headlines in the "View Analysis Details" description.
- Remove llm_api_key, llm_base_url, llm_model, OpenRouter setup, and AI-generated claims.

AGENTS.md
- Replace LLM-powered architecture references with strategy_advisor.py and deterministic_strategy.py.
- Remove the openai dependency entry and prompt/memory generation lifecycle.
- Keep HTML escaping guidance and describe structured analysis_data.

credentials_b.json_example
- Remove llm_api_key, llm_base_url, and llm_model.

setup_bot_server.sh
- Rename user-visible "AI Strategy Advisor" service descriptions to "Deterministic Strategy Advisor" without changing service filenames.

memory-bank/activeContext.md and memory-bank/progress.md
- Record the current deterministic architecture.

memory-bank/changelog.md
- Add a 2026-06-30 entry documenting the migration; do not alter the historical entry that records when the LLM feature was introduced.
```

- [ ] **Step 6: Prove the active code and configuration contain no LLM integration**

Run:

```bash
rg -n "from openai|import openai|OpenRouter|llm_api_key|llm_base_url|llm_model|src\.services\.llm_strategy" \
  src telegram_bot_handler.py pyproject.toml credentials_b.json_example README.md AGENTS.md setup_bot_server.sh
```

Expected: no matches.

- [ ] **Step 7: Run targeted regression tests**

Run:

```bash
uv run --with pytest pytest \
  tests/test_deterministic_strategy.py \
  tests/test_strategy_advisor.py \
  tests/test_analysis_details.py \
  tests/test_performance_tracker_exchange.py \
  tests/test_telegram_exchange_safe_ui.py \
  tests/test_signal_persistence.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Run broad static and regression verification**

Run:

```bash
uv run python -m compileall -q src telegram_bot_handler.py
uv run --with pytest pytest -q
git diff --check
```

Expected: compileall exits `0`, the full non-live suite passes, and `git diff --check` prints nothing.

- [ ] **Step 9: Run live exchange smoke tests separately**

Run:

```bash
uv run --with pytest pytest -m e2e tests/test_live_exchange_e2e.py -q
```

Expected: live public endpoints return usable market data and exchange-specific URLs. If network access is unavailable, record this as an explicit validation gap rather than treating mocked tests as e2e evidence.

- [ ] **Step 10: Commit cleanup and documentation**

```bash
git add pyproject.toml uv.lock README.md AGENTS.md credentials_b.json_example setup_bot_server.sh memory-bank src/services/news_service.py tests/test_strategy_advisor.py
git commit -m "refactor: remove LLM from strategy analysis"
```

## Completion Criteria

- Repeating `/analyze` against an identical captured exchange snapshot returns identical action, confidence, entry, TP, SL, reasoning, score, and rule IDs.
- Kraken, OKX, and Binance analyses use only their own current price and candles.
- News headline changes do not change any strategy field.
- Every successful exchange has its own details button.
- Analysis details show clickable safe article links and explicitly label news as informational.
- Performance tracking fetches prices from the suggestion's stored exchange.
- No OpenAI/OpenRouter production dependency, credential, prompt, or runtime call remains.
- Targeted tests, full regression tests, compilation, and diff validation pass; live e2e status is reported separately.
