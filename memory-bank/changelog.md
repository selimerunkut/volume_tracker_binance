# Changelog

## 2025-08-02

-   Added Binance trade URL to Telegram alerts.
-   Formatted `curr_volume` and `prev_volume_mean` as integers in Telegram alerts.
-   Updated `README.md` with new features and setup instructions.
-   Created `memory-bank` directory and `changelog.md`.

## 2026-02-21

-   Implemented **AI Strategy Advisor** in `telegram_bot_handler.py`.
-   Added **dynamic menu buttons** for last 5 analyzed pairs.
-   Implemented **robust symbol detection** in message handler.
-   Added **typo correction** logic for `/anlayze`.
-   Improved **error handling** for invalid symbols in `market_data_service.py` and `llm_strategy.py`.
-   Fixed **NoneType crashes** and improved HTML/parsing stability.
-   Updated **Documentation** (`AGENTS.md`) and **Memory Bank** files.

## 2026-06-25

-   Added a shared exchange registry with Binance and Kraken adapters.
-   Added chat-scoped alert exchange selection with single, multiple, and all-exchange modes.
-   Updated documentation to describe the modular multi-exchange alert flow and universal Telegram menu.
