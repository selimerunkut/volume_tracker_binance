# AGENTS.md - Agentic Coding Guidelines

## Project Overview
Python-based cryptocurrency volume tracker for Binance that sends Telegram alerts for significant volume changes.

## Build Commands

```bash
# Install dependencies
uv sync

# Run main scripts
python b_volume_alerts.py          # Volume tracking and alerts
python telegram_bot_handler.py      # Telegram bot service
python telegram_alerts.py           # Test Telegram messaging

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

### File Organization
- Root-level scripts for main functionality
- `memory-bank/` for project documentation
- `helper_test_scripts/` for utility scripts
- JSON files for configuration and state

### Key Dependencies
- `requests` - HTTP requests
- `pandas` - Data manipulation
- `python-binance` - Binance API client
- `python-telegram-bot` - Telegram bot framework

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
- See README.md for service file template
