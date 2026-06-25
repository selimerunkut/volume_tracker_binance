# Telegram Exchange-Safe UI Design

Date: 2026-06-25

## Purpose

Define the exact Telegram button layout and callback flow for the bot’s four user-facing flows:

1. Analyze
2. Watch Symbol
3. Unwatch Symbol
4. List Watchlist

The design must be exchange-safe across Binance and Kraken. It must not silently assume Binance when the user may intend Kraken, and it must support:

- single exchange
- multiple selected exchanges
- all supported exchanges

This spec is intentionally separate from the older multi-exchange alert plan so the Telegram UI contract has one dedicated source of truth.

## Design Principles

1. **Scope first, symbol second** for any action that can vary by exchange.
2. **No hidden Binance fallback** when the user explicitly chose exchange-specific behavior.
3. **Reuse one shared exchange-scope picker** across Analyze, Watch, Unwatch, and List Watch.
4. **Label every result with its exchange**.
5. **Treat legacy watchlist data as Binance-only** during migration.

## Supported Exchanges

The UI assumes the supported exchange set is:

- BINANCE
- KRAKEN

If the supported set changes later, the picker should expand automatically from the registry; the callback design below should remain the same.

## Main Menu Layout

The main menu should present these buttons in this order:

1. 🔍 Analyze
2. ➕ Watch Symbol
3. ➖ Unwatch Symbol
4. 📚 List Watchlist
5. 🎛 Alert Exchanges
6. 📜 List Restricted Pairs
7. 🪄 Run Signals
8. 📊 High Volume Pairs

The existing shortcut buttons for recently analyzed symbols may remain, but they must not run analysis immediately.

### Recent Analyze Shortcut Behavior

If the bot shows a button such as:

- 🔍 Analyze BTCUSDC
- 🔍 Analyze ETHUSDC

then clicking that button must:

1. open the exchange-scope picker for Analyze
2. preload the clicked symbol
3. wait for exchange selection before running analysis

It must **not** skip the scope step.

## Shared Exchange-Scope Picker

All four flows use the same three-mode model:

- 🌍 All exchanges
- 🎯 Single exchange
- 🗂 Multiple exchanges

### Root screen

Text:

> Choose the exchange scope for this action.

Buttons:

- 🌍 All exchanges
- 🎯 Single exchange
- 🗂 Multiple exchanges
- ⬅️ Back to main menu

### Single screen

Text:

> Choose one exchange.

Buttons:

- BINANCE
- KRAKEN
- 🌍 All exchanges
- 🗂 Multiple exchanges
- ⬅️ Back

### Multiple screen

Text:

> Select one or more exchanges.

Buttons:

- ☑ BINANCE / ☐ BINANCE
- ☑ KRAKEN / ☐ KRAKEN
- 🌍 All exchanges
- ✅ Done
- ⬅️ Back

If every supported exchange becomes selected in Multiple mode, the picker should normalize to All exchanges.

## Flow 1: Analyze

### Entry points

- Main menu button: 🔍 Analyze
- Recent symbol shortcut: 🔍 Analyze <SYMBOL>
- Command: `/analyze <SYMBOL>`
- Shortcut command: `/a <SYMBOL>`

### Step 1: scope selection

When Analyze is triggered, the bot must ask which exchange scope should be used before analysis runs.

If the user entered a symbol directly, the bot should still require scope selection before analysis proceeds.

### Step 2: symbol input

After scope selection, prompt:

> Send the trading pair symbol to analyze, for example BTCUSDC or BTCUSD.

If the symbol was already preloaded from a shortcut button, skip this prompt.

### Step 3: execution behavior

- **Single exchange**: run analysis only for that exchange.
- **Multiple exchanges**: run analysis once per selected exchange and return grouped results.
- **All exchanges**: run analysis on every supported exchange and return grouped results.

### Result formatting

Every result line must include the exchange name.

Example:

- BINANCE: BTCUSDC → LONG
- KRAKEN: BTCUSD → WAIT

If a symbol is unavailable on one exchange, show that explicitly:

- KRAKEN: BTCUSDC unavailable on Kraken

### Safety rule

Do not silently fall back to Binance when the user selected exchange-specific analysis.

## Flow 2: Watch Symbol

### Entry points

- Main menu button: ➕ Watch Symbol
- Command: `/watch <SYMBOL>`

### Step 1: scope selection

When Watch is triggered, the bot must ask which exchange scope should receive the watch entry before asking for the symbol.

Prompt:

> Choose the exchange scope for the symbol you want to watch.

### Step 2: symbol input

Prompt:

> Send the trading pair symbol to watch.

### Step 3: storage behavior

The watchlist must be exchange-aware.

Recommended storage shape:

```json
{
  "watchlist": {
    "binance": ["BTCUSDC", "ETHUSDC"],
    "kraken": ["BTCUSD"]
  }
}
```

Legacy flat watchlist entries should migrate into the Binance bucket on first load, because the old behavior was Binance-centric.

### Add behavior

- **Single exchange**: add only to that exchange.
- **Multiple exchanges**: add to each selected exchange where the symbol is valid.
- **All exchanges**: add to every supported exchange where the symbol is valid.

### Output behavior

If the symbol is valid on some exchanges and invalid on others, report both:

- ✅ Added BTCUSDC to Binance watchlist
- ⚠️ BTCUSDC is not valid on Kraken

Do not hide partial success.

## Flow 3: Unwatch Symbol

### Entry points

- Main menu button: ➖ Unwatch Symbol
- Command: `/unwatch <SYMBOL>`

### Step 1: scope selection

Prompt:

> Choose the exchange scope for the symbol you want to remove.

### Step 2: symbol input

Prompt:

> Send the trading pair symbol to remove from watchlist.

### Step 3: removal behavior

- **Single exchange**: remove only from that exchange.
- **Multiple exchanges**: remove from each selected exchange.
- **All exchanges**: remove from all supported exchanges.

If the symbol is not present in a selected exchange, say so plainly.

Example:

- ✅ Removed BTCUSDC from Binance watchlist
- ℹ️ BTCUSDC was not present in Kraken watchlist

## Flow 4: List Watchlist

### Entry points

- Main menu button: 📚 List Watchlist
- Command: `/list_watch`

### Step 1: scope selection

Prompt:

> Choose which exchange watchlist you want to view.

### Step 2: output

No symbol prompt is needed.

- **All exchanges**: show grouped sections for Binance and Kraken.
- **Single exchange**: show only the selected exchange section.
- **Multiple exchanges**: show only the chosen exchange sections.

Example output:

```text
📚 Signal Watchlist

BINANCE
- BTCUSDC
- ETHUSDC

KRAKEN
- BTCUSD
```

If no watched pairs exist for the selected scope:

> No watched pairs found for the selected exchange scope.

## Callback Flow

The callback grammar should be action-scoped so one picker can serve all four flows.

### Recommended callback prefix

Use one namespace:

- `scope`

### Exact callback shapes

#### Root screen

- `scope|analyze|view|root`
- `scope|watch|view|root`
- `scope|unwatch|view|root`
- `scope|list|view|root`

#### All exchanges

- `scope|analyze|mode|all`
- `scope|watch|mode|all`
- `scope|unwatch|mode|all`
- `scope|list|mode|all`

#### Single screen

- `scope|analyze|view|single`
- `scope|watch|view|single`
- `scope|unwatch|view|single`
- `scope|list|view|single`

#### Pick single exchange

- `scope|analyze|set|single|binance`
- `scope|analyze|set|single|kraken`
- same pattern for `watch`, `unwatch`, and `list`

#### Multiple screen

- `scope|analyze|view|multiple`
- `scope|watch|view|multiple`
- `scope|unwatch|view|multiple`
- `scope|list|view|multiple`

#### Toggle exchange in multiple mode

- `scope|analyze|toggle|binance`
- `scope|analyze|toggle|kraken`
- same pattern for `watch`, `unwatch`, and `list`

#### Finish multiple mode

- `scope|analyze|done`
- `scope|watch|done`
- `scope|unwatch|done`
- `scope|list|done`

#### Back navigation

- `scope|analyze|back`
- `scope|watch|back`
- `scope|unwatch|back`
- `scope|list|back`

## State Model

The bot should use `context.user_data` to hold the active flow state.

Recommended fields:

```python
context.user_data = {
    "pending_action": "analyze" | "watch" | "unwatch" | "list",
    "pending_scope": {"mode": "all" | "selected", "exchanges": [...]},
    "pending_symbol": "BTCUSDC" | None
}
```

### State rules

- `pending_action` tells the bot which flow is active.
- `pending_scope` stores the selected exchange scope.
- `pending_symbol` is used for Analyze / Watch / Unwatch when the symbol has not yet been entered.

## Error Handling

### Analyze

If a symbol is valid on one exchange but not another, show the per-exchange failure explicitly.

### Watch / Unwatch

If a selected exchange cannot accept the symbol, skip that exchange and report the skip.

### Invalid scope state

If scope state becomes invalid, reset to All exchanges and show a clear error message.

### Telegram no-op edits

If a callback would re-render the same message and Telegram raises `Message is not modified`, ignore that as a harmless no-op rather than surfacing a bot error.

## Acceptance Criteria

This spec is satisfied when all of the following are true:

1. Clicking Analyze asks for exchange scope before analysis runs.
2. Clicking Watch Symbol asks for exchange scope before symbol entry.
3. Clicking Unwatch Symbol asks for exchange scope before symbol entry.
4. Clicking List Watchlist asks for exchange scope before showing results.
5. Recent Analyze shortcut buttons also route through exchange scope selection.
6. The bot never silently assumes Binance for exchange-sensitive analysis.
7. Results are grouped or labeled by exchange.
8. Watchlist storage is exchange-aware.
9. Legacy flat watchlist data still loads safely.
10. `Message is not modified` callback redraws are handled cleanly.

## Notes for Implementation

This spec is designed to sit on top of the existing alert-scope interaction pattern already present in the bot. The safest implementation path is to generalize that picker into a reusable exchange-scope component rather than creating separate UI systems for each action.
