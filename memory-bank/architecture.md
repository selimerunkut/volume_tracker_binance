# Architecture Design for Telegram Bot Integration and Refactoring

## 1. Overview

This document outlines the proposed architecture for integrating a Telegram bot to dynamically manage restricted trading pairs and refactoring the existing `CEX_volume_tracker_B` codebase for improved modularity and maintainability. The goal is to provide a more interactive and user-friendly experience for managing symbol exclusions.

## 2. Component Diagram

```mermaid
graph TD
    A[Binance API] --> B{b_volume_alerts.py};
    B --> C[Data Processing & Alert Logic];
    C --> D[Telegram Alerts (telegram_alerts.py)];
    D --> E[Telegram Bot API];
    E --> F[Telegram User];

    subgraph New Components
        G[Telegram Bot Handler (telegram_bot_handler.py)]
        H[Symbol Manager (symbol_manager.py)]
    end

    F -- Commands/Callbacks --> E;
    E --> G;
    G -- Read/Write --> I[restricted_pairs.json];
    G -- Interact --> H;
    H -- Read/Write --> I;
    B -- Use --> H;
    D -- Send Alerts with Buttons --> E;
```

## 3. Component Descriptions

*   **Binance API:** External service providing exchange information and kline data.
*   **`b_volume_alerts.py`:** The main script responsible for fetching data, calculating volume alerts, and orchestrating the process.
    *   **Refactoring:** This script will be refactored to delegate symbol management to `symbol_manager.py` and alert sending to `telegram_alerts.py`. Its primary role will be data fetching, volume calculation, and alert triggering.
*   **Data Processing & Alert Logic:** Core logic within `b_volume_alerts.py` for identifying significant volume changes.
*   **`telegram_alerts.py`:** Existing module for sending Telegram messages.
    *   **Modification:** Will be extended to support sending inline keyboard buttons with alert messages, allowing users to directly interact with alerts (e.g., "Restrict Pair").
*   **Telegram Bot API:** The interface through which the Telegram bot interacts with Telegram servers.
*   **Telegram User:** The end-user interacting with the bot.
*   **`telegram_bot_handler.py` (NEW):** A new module responsible for:
    *   Listening for incoming Telegram messages (commands like `/list_restricted`, `/unrestrict`) and callback queries (from inline buttons).
    *   Parsing commands and callbacks.
    *   Interacting with `symbol_manager.py` to perform actions (add, remove, list restricted symbols).
    *   Sending responses back to the Telegram user.
*   **`symbol_manager.py` (NEW):** A new module responsible for:
    *   Loading and saving the `restricted_pairs.json` file.
    *   Providing methods to add, remove, and list restricted symbols.
    *   Ensuring data consistency and handling file I/O errors.
    *   This module will be used by both `b_volume_alerts.py` (for filtering) and `telegram_bot_handler.py` (for management).
*   **`restricted_pairs.json`:** JSON file storing the list of symbols to be excluded from alerts. Its management will now be primarily through the Telegram bot.

## 4. Data Flow and Interactions

1.  **Alert Generation:**
    *   `b_volume_alerts.py` fetches data from Binance API.
    *   `b_volume_alerts.py` uses `symbol_manager.py` to get the current list of filtered symbols.
    *   `b_volume_alerts.py` calculates volume alerts.
    *   If an alert is triggered, `b_volume_alerts.py` calls `telegram_alerts.py` to send the message.
    *   `telegram_alerts.py` constructs the message, potentially including an inline keyboard button (e.g., "Restrict [SYMBOL]").
    *   The message is sent via Telegram Bot API to the Telegram User.

2.  **User Interaction (Restrict Pair):**
    *   Telegram User clicks "Restrict [SYMBOL]" button.
    *   Telegram Bot API sends a callback query to `telegram_bot_handler.py`.
    *   `telegram_bot_handler.py` parses the callback, extracts the symbol.
    *   `telegram_bot_handler.py` calls `symbol_manager.py` to add the symbol to `restricted_pairs.json`.
    *   `symbol_manager.py` updates the JSON file.
    *   `telegram_bot_handler.py` sends a confirmation message to the Telegram User.

3.  **User Interaction (List Restricted Pairs):**
    *   Telegram User sends `/list_restricted` command.
    *   Telegram Bot API sends the message to `telegram_bot_handler.py`.
    *   `telegram_bot_handler.py` parses the command.
    *   `telegram_bot_handler.py` calls `symbol_manager.py` to get the list of restricted symbols.
    *   `telegram_bot_handler.py` formats the list and sends it back to the Telegram User.

4.  **User Interaction (Unrestrict Pair):**
    *   Telegram User sends `/unrestrict [SYMBOL]` command.
    *   Telegram Bot API sends the message to `telegram_bot_handler.py`.
    *   `telegram_bot_handler.py` parses the command, extracts the symbol.
    *   `telegram_bot_handler.py` calls `symbol_manager.py` to remove the symbol from `restricted_pairs.json`.
    *   `symbol_manager.py` updates the JSON file.
    *   `telegram_bot_handler.py` sends a confirmation message to the Telegram User.

## 5. Refactoring Considerations

*   **Modularity:** Separate concerns into distinct modules (`b_volume_alerts.py`, `telegram_alerts.py`, `telegram_bot_handler.py`, `symbol_manager.py`).
*   **Dependency Injection (Implicit):** `b_volume_alerts.py` and `telegram_bot_handler.py` will depend on `symbol_manager.py`.
*   **Error Handling:** Robust error handling for file I/O, API calls, and Telegram interactions.
*   **Configuration:** Telegram bot token and chat ID will need to be securely configured (e.g., via environment variables or a separate `credentials.json` for the bot).

This architecture provides a clear separation of concerns and a scalable approach for adding more bot functionalities in the future.