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