# Decision Log

This file records architectural and implementation decisions using a list format.
2025-08-03 17:41:46 - Log of updates made.

*

## Decision

*   **Project Structure**: Maintain a flat project structure instead of migrating to `src-layout`.

## Rationale

*   User preference for simplicity and to avoid unnecessary refactoring for a project of this size.

## Implementation Details

*   Explicitly defined `py-modules = ["b_volume_alerts", "telegram_alerts"]` in `pyproject.toml` under `[tool.setuptools]` to resolve `setuptools` "Multiple top-level modules discovered" error during `uv sync`.
*   **Scheduling Mechanism**: Utilize `systemd` for script scheduling and service management instead of `cron` or an internal `schedule` loop.
*   **Rationale**: `systemd` offers more robust process management, including automatic restarts (`Restart=always`) and centralized logging (`StandardOutput=journal`, `StandardError=journal`), which is superior for a long-running background service.
*   **Implementation Details**:
    *   A `binance-volume-tracker.service` file was created and configured in `setup_bot_server.sh` to be placed in `/etc/systemd/system/`.
    *   `ExecStart` path was set to `/root/CEX_volume_tracker_B/.venv/bin/python /root/CEX_volume_tracker_B/b_volume_alerts.py`.
    *   `Restart=always` was explicitly set to ensure continuous execution by restarting the script after each run.
    *   `README.md` was updated with detailed `systemd` setup instructions.
[2025-08-03 18:04:54] - Decision: Implement duplicate alert message prevention.
Rationale: User feedback indicates duplicate alerts for the same volume increase are being sent, leading to spam. A simple solution is preferred.
Implementation Details:
    - Use an in-memory dictionary to track recently sent alerts (symbol, alert level, timestamp).
    - Implement a cooldown period (e.g., 4 hours) to prevent re-sending the same alert within that timeframe.
    - This approach is simple and avoids new dependencies, though it will not persist across script restarts.
[2025-08-03 18:08:31] - Decision: Revise duplicate alert message prevention to use file-based persistence.
Rationale: The previous in-memory solution is not suitable for a script managed by `systemd` with `Restart=always`, as the in-memory state is lost upon script exit and restart, leading to duplicate alerts.
Implementation Details:
    - Store `last_alert_timestamps` in a JSON file to persist state across script restarts.
    - Load the state from the file at script startup.
    - Save the state to the file after each alert is sent.
    - Implement error handling for file operations (read/write).