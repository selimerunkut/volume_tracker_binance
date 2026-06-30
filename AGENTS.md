# AGENTS.md - Agentic Coding Guidelines

## Project Overview
Python-based cryptocurrency volume tracker for Binance that sends Telegram alerts for significant volume changes. Now includes a **deterministic Strategy Advisor** with exchange-specific data grounding and structured analysis details.

### Components
1. **Volume Tracker** (`b_volume_alerts.py`) - Monitors volume changes and sends alerts
2. **Strategy Advisor** (`telegram_bot_handler.py`) - Deterministic trading strategy suggestions with structured evidence
3. **Service Layer** (`src/services/`) - Modular business logic for market data, technical analysis, and persistence

## Build Commands

```bash
# Install dependencies
uv sync

# Run main scripts
python b_volume_alerts.py          # Volume tracking and alerts (legacy)
python telegram_bot_handler.py      # Telegram bot with Deterministic Strategy Advisor
python telegram_alerts.py           # Test Telegram messaging

# Run Strategy Advisor services individually
python -m src.services.strategy_advisor     # Test strategy generation
python -m src.services.performance_tracker  # Test performance tracking
python -m src.services.db_service       # Test database operations

# Dry run mode (no actual Telegram messages sent)
python b_volume_alerts.py --dry-run

# Single test execution (scripts have built-in test blocks)
python telegram_alerts.py          # Runs test message in __main__ block
python alert_levels_tg.py          # Module with testable functions
```

## Code Style Guidelines

### Imports
- Order: stdlib → third-party → local modules
- Example:
```python
import json
import os
from datetime import datetime

import requests
import pandas as pd
from telegram import Update

from symbol_manager import SymbolManager
```

### Naming Conventions
- Functions/variables: `snake_case` (e.g., `load_alert_state`, `curr_volume`)
- Classes: `CamelCase` (e.g., `SymbolManager`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `STATE_FILE`, `COOLDOWN_PERIOD_HOURS`)
- Private methods: `_leading_underscore` (e.g., `_load_symbols`)

### Formatting
- 4-space indentation
- No strict line length limit observed
- Use f-strings for string formatting
- Include thousand separators for large numbers: `f"{volume:,}"`

### Error Handling
- Use specific exceptions before generic ones
- Always include timestamp in error messages
- Pattern:
```python
try:
    # operation
except FileNotFoundError:
    print(f"[{datetime.now()}] File not found: {e}")
except json.JSONDecodeError as e:
    print(f"[{datetime.now()}] JSON error: {e}")
except Exception as e:
    print(f"[{datetime.now()}] Unexpected error: {e}")
```

### Logging
- Use timestamped print statements: `f"[{datetime.now()}] Message"`
- Include context (symbol, operation) in log messages
- Use DEBUG prefix for debug logs

### Type Hints
- Not currently used in codebase
- Optional for new code

### Testing
- No formal test framework configured
- Use `if __name__ == "__main__":` blocks for standalone testing
- Tests directory exists but is empty
- In this repo, "e2e tests" means tests that hit real live APIs/endpoints; mocked network tests are regression or integration tests, not e2e.

/Users/semacair/dev/agent_system/roo_task_feb-20-2026_9-50-58-pm.md

This keeps the interactions explicit, removes guesswork, and lets both you and the agents know exactly what success looks like.

### File Organization
- Root-level scripts for main functionality
- `memory-bank/` for project documentation
- `helper_test_scripts/` for utility scripts
- JSON files for configuration and state

### Key Dependencies
- `requests` - HTTP requests
- `pandas` - Data manipulation
- `python-binance` - Binance API client
- `numpy` - Added numpy as it's often a dependency for pandas operations, and the user mentioned np.float64
- `pandas-ta` - Technical analysis indicators (RSI, MACD, Bollinger Bands)
- `APScheduler` - Task scheduling for performance tracking

### Credentials Management
- Store in `credentials_b.json` (gitignored)
- Format: `{"Binance_api_key": "...", "Binance_secret_key": "...", "telegram_bot_token": "...", "telegram_chat_id": "..."}`

## Project-Specific Patterns

### Alert State Management
- Persist alert timestamps to `alert_state.json`
- Use compound keys: `(symbol, level)`
- Implement cooldown logic to prevent duplicate alerts

### Symbol Management
- Use `SymbolManager` class for restricted pairs
- Persist to `restricted_pairs.json`

### Service Deployment
- Use `systemd` for Linux service management
- Two services available:
  1. `binance-strategy-bot.service` - Telegram bot with Deterministic Strategy Advisor (recommended)
  2. `binance-volume-tracker.service` - Volume alerts only (legacy)
- See README.md for detailed service file templates

#### Suggestion Lifecycle
1. **Generation** (`strategy_advisor.py`): Analyze symbol → Generate strategy (LONG/SHORT/WAIT) → Save to DB with structured evidence
2. **Storage** (`db_service.py`): Persist suggestion with `analysis_data` (TA, news, score, rules) as JSON. Use `get_last_analyzed_symbols` for dynamic UI menus.
3. **Tracking** (`performance_tracker.py`): Background job evaluates outcomes every 30 minutes using the stored exchange
4. **Learning**: Historical outcomes are visible in the DB/UI, but they do not influence the deterministic signal

#### Telegram Interaction Patterns
- **Robust Message Parsing**: Use `update.effective_message` instead of `update.message` to handle both direct commands and `callback_query` updates.
- **HTML Parse Mode**: Preferred over Markdown for resilience against special characters in AI-generated text. Always escape dynamic content with `html.escape()`.
- **Shorthand Commands**: Provide single-character shorthands (e.g., `/a`) for high-frequency actions.
- **Dynamic Menus**: Update inline keyboards frequently with recent context (e.g., last 5 symbols analyzed).
- **Flexible Symbol Detection**: In `MessageHandler`, detect uppercase strings (3-12 chars) as symbols to trigger analysis without requiring formal commands.
- **Explicit Feedback**: When API calls fail (e.g., Binance 400), check for "invalid symbol" errors and suggest common alternatives (e.g., "Try SOLBTC instead of BTCSOL").

#### WAIT Strategy Scoring
- Window: 24 hours after suggestion
- Threshold: ±2% price movement
- Scoring:
  - Price moves up ≥2% → LOSS (missed opportunity)
  - Price moves down ≥2% or stays flat → WIN (avoided loss)

#### Database Schema (suggestions table)
```sql
id, timestamp, symbol, strategy_type, entry_price, take_profit, stop_loss,
reasoning, status (PENDING/WIN/LOSS/EXPIRED), pnl_percent, created_at, analysis_data
```
