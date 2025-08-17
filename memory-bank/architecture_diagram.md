# Architecture Diagram and Flowchart for Hummingbot Telegram Integration

## 1. High-Level Architecture Diagram

```mermaid
graph TD
    A[Telegram User] -->|1. Clicks "Buy" button / Sends /buy command| B(Telegram Bot Handler)
    B -->|2. Initiates conversation, collects parameters| C(Hummingbot Integration Module)
    C -->|3. Creates config, deploys bot via API| D[Hummingbot API Server]
    D -->|4. Manages Hummingbot Instances| E[Hummingbot Docker Containers]
    C -->|5. Stores active trade info| F[Active Trades Persistent Storage (active_trades.json)]
    F -->|6. Periodically read by| G(Bot Status Monitor)
    G -->|7. Checks bot status via API| D
    D -->|8. Returns status| G
    G -->|9. If bot stopped, archives bot via API| D
    G -->|10. Updates active trades storage| F
    G -->|11. Sends completion notification| H(Telegram Alerts Module)
    H -->|12. Sends message to| A
    H -->|13. Sends volume alerts with "Buy" button| A
```

## 2. Detailed Flowchart: Initiating a Trade

```mermaid
graph TD
    A[Telegram User] --> B{Volume Alert with Buy Button?}
    B -- Yes --> C[User Clicks "Buy" Button]
    B -- No --> D[User Sends /buy Command]
    C --> E(Telegram Bot Handler: Callback Query)
    D --> E
    E --> F{Extract Trading Pair}
    F --> G[Initiate Conversation: Ask for order_amount_usd]
    G --> H[User Provides order_amount_usd]
    H --> I{Ask for Optional Parameters?}
    I -- Yes --> J[User Provides trailing_stop_loss_delta, take_profit_delta, fixed_stop_loss_delta]
    I -- No --> K[Proceed with default/no optional parameters]
    J --> L(Hummingbot Integration Module: create_and_deploy_bot)
    K --> L
    L --> M[Generate Unique config_name and instance_name]
    M --> N[Construct Hummingbot Configuration]
    N --> O[Check for existing Docker container with instance_name]
    O -- Exists & Active --> P[Stop and Remove existing container]
    O -- Exists & Exited --> Q[Remove existing container]
    P --> R[Deploy V2 Script via Hummingbot API]
    Q --> R
    R --> S[Store Trade Info in active_trades.json]
    S --> T[Send "Trade Initiated" Confirmation to Telegram User]
    T --> U[End Trade Initiation Flow]
```

## 3. Detailed Flowchart: Bot Status Monitoring and Archiving

```mermaid
graph TD
    A[Bot Status Monitor (bot_monitor.py)] --> B{Periodic Loop (e.g., every 5 minutes)}
    B --> C[Read active_trades.json]
    C --> D{For Each Active Trade Entry}
    D --> E[Call Hummingbot Integration Module: get_bot_status(instance_name)]
    E --> F{Bot Status == "stopped"?}
    F -- Yes --> G[Call Hummingbot Integration Module: stop_and_archive_bot(instance_name)]
    G --> H[Remove Trade Entry from active_trades.json]
    H --> I[Send "Trade Completed" Notification to Telegram User]
    I --> J[Continue to next active trade / End loop iteration]
    F -- No --> K[Bot still active, continue to next trade / End loop iteration]