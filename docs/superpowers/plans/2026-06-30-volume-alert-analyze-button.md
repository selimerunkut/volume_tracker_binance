# Volume Alert Analyze Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Telegram inline button under volume-alert messages that starts the existing `/analyze SYMBOL` flow for the alerted pair.

**Architecture:** Keep the volume alert service (`b_volume_alerts.py` → `telegram_alerts.py`) separate from the strategy bot. Reuse the existing `menu_analyze_<SYMBOL>` callback already handled by `telegram_bot_handler.py`, so no new command, settings screen, callback handler, or cross-service API is added.

**Tech Stack:** Python, `python-telegram-bot` inline keyboard types, Telegram Bot API `sendMessage`, existing pytest suite.

## Global Constraints

- No new dependencies.
- Keep the change small, DRY, KISS, and YAGNI.
- Reuse existing strategy-bot callback `menu_analyze_<SYMBOL>`.
- Preserve the existing `Restrict SYMBOL` button behavior.
- Do not change alert scanning, alert filtering, analysis logic, or systemd service definitions.
- Treat the already-modified local files as uncommitted work; do not include unrelated `signal_watchlist.json`.

---

## Current Code Facts

- `b_volume_alerts.py` sends alert messages by calling `send_telegram_message(alert_message, include_restrict_button=True, dry_run=dry_run)` around `b_volume_alerts.py:244`.
- `telegram_alerts.py:58-64` builds the inline keyboard for volume alerts when `include_restrict_button` is true.
- `telegram_bot_handler.py:1146-1152` already handles callback data starting with `menu_analyze_` and runs analysis for all exchanges by default.
- `telegram_bot_handler.py:1325-1331` already registers `CallbackQueryHandler(menu_callback, pattern="^menu_")`.

## Acceptance Criteria

1. A volume alert that currently displays `Restrict STEEMUSDC` also displays `🔍 Analyze STEEMUSDC`.
2. The analyze button uses `callback_data="menu_analyze_STEEMUSDC"` for the same symbol from the alert.
3. The existing restrict button remains unchanged: `callback_data="restrict_STEEMUSDC"`.
4. Clicking the analyze button is handled by existing strategy-bot menu callback logic; no new Telegram command or handler is invented.
5. Tests prove the generated Telegram `reply_markup` contains both buttons in the expected order.
6. Existing alert filtering tests and exchange-safe UI tests still pass.

## Implementation Steps

### Task 1: Lock the desired volume-alert keyboard behavior

**Files:**
- Modify/test: `tests/test_telegram_alert_exchange_filter.py`

**Interfaces:**
- Consumes: `telegram_alerts.send_telegram_message(alert_message, include_restrict_button=True, dry_run=False)`
- Produces: Regression coverage for `payload["reply_markup"]`

- [ ] **Step 1: Add the failing regression test**

Add a test that stubs `telegram_alerts.requests.post`, sends a sample BINANCE alert with `include_restrict_button=True`, parses `captured_payload["reply_markup"]`, and expects exactly:

```python
[
    [{'text': 'Restrict BTCUSDC', 'callback_data': 'restrict_BTCUSDC'}],
    [{'text': '🔍 Analyze BTCUSDC', 'callback_data': 'menu_analyze_BTCUSDC'}],
]
```

- [ ] **Step 2: Run the single test and confirm RED**

Run:

```bash
uv run --with pytest python -m pytest -q tests/test_telegram_alert_exchange_filter.py::test_volume_alert_restrict_keyboard_also_reuses_analyze_callback
```

Expected before implementation: FAIL because only the restrict button exists.

### Task 2: Add the analyze button with the smallest possible production change

**Files:**
- Modify: `telegram_alerts.py`
- Test: `tests/test_telegram_alert_exchange_filter.py`

**Interfaces:**
- Consumes: existing `symbol = alert_message["symbol"]`
- Produces: `InlineKeyboardMarkup` containing both restrict and analyze rows

- [ ] **Step 1: Update only the inline keyboard construction**

Change `telegram_alerts.py` inside `if include_restrict_button and symbol:` to build two rows:

```python
keyboard = [
    [InlineKeyboardButton(f"Restrict {symbol}", callback_data=f"restrict_{symbol}")],
    [InlineKeyboardButton(f"🔍 Analyze {symbol}", callback_data=f"menu_analyze_{symbol}")],
]
```

- [ ] **Step 2: Run the single test and confirm GREEN**

Run:

```bash
uv run --with pytest python -m pytest -q tests/test_telegram_alert_exchange_filter.py::test_volume_alert_restrict_keyboard_also_reuses_analyze_callback
```

Expected after implementation: PASS.

### Task 3: Verify no regressions in related behavior

**Files:**
- Read/verify only: `telegram_alerts.py`, `telegram_bot_handler.py`, `tests/test_telegram_alert_exchange_filter.py`, `tests/test_telegram_exchange_safe_ui.py`

**Interfaces:**
- Confirms restrict callback and menu callback continue to share the same bot callback routing.

- [ ] **Step 1: Run targeted related tests**

Run:

```bash
uv run --with pytest python -m pytest -q tests/test_telegram_alert_exchange_filter.py tests/test_telegram_exchange_safe_ui.py
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the full non-live test suite**

Run:

```bash
uv run --with pytest python -m pytest -q
```

Expected: all non-live tests pass; live API tests may remain skipped unless explicitly enabled.

### Task 4: Final review and optional commit/deploy handoff

**Files:**
- Review: `git diff -- telegram_alerts.py tests/test_telegram_alert_exchange_filter.py docs/superpowers/plans/2026-06-30-volume-alert-analyze-button.md`

**Interfaces:**
- Produces: clean summary and, only if requested, a commit/push/deploy step.

- [ ] **Step 1: Confirm the diff is scoped**

Run:

```bash
git status --short
git diff -- telegram_alerts.py tests/test_telegram_alert_exchange_filter.py
```

Expected: only the volume-alert button code and regression test are part of this task. `signal_watchlist.json` remains unrelated and must not be included in any commit for this task.

- [ ] **Step 2: If the user requests commit/push/deploy, use Lore commit protocol**

Commit only:

```bash
git add telegram_alerts.py tests/test_telegram_alert_exchange_filter.py docs/superpowers/plans/2026-06-30-volume-alert-analyze-button.md
```

Use a Lore-style commit message explaining why the button reuses the existing `menu_analyze_` callback.

## Risks and Mitigations

- **Risk:** Telegram callback data length limit is 64 bytes.  
  **Mitigation:** Existing symbol values are short exchange pair names; `menu_analyze_` plus a normal pair symbol stays under the limit.

- **Risk:** If the strategy bot is not running, the button will not be answered.  
  **Mitigation:** This matches existing callback behavior for other menu buttons; service health remains an operational concern, not a new code path.

- **Risk:** Volume tracker and strategy bot are separate services.  
  **Mitigation:** The volume tracker only sends markup; callback handling remains in `telegram_bot_handler.py`.

## Verification Checklist

- [ ] Regression test fails before production change.
- [ ] Regression test passes after production change.
- [ ] Targeted Telegram alert/UI tests pass.
- [ ] Full non-live pytest suite passes.
- [ ] No unrelated file is committed.

