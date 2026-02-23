# Plan: Persist Strategy Signals to Learning DB

## Context
- Signals currently only send Telegram alerts; the learning database only records `/analyze` suggestions.
- Requirements: persist both hourly and daily signals immediately at the signal candle with the current ticker entry price, use a new table, reuse scoring logic when possible, and suppress duplicate inserts/cooldown.

## Steps
1. **Design the schema**
   - Extend the DB schema (via `db_service`) with a new table (e.g., `signal_trades`) capturing symbol, timeframe, action, explanation, entry_price, entry_ts, signal_type, status, entry_reason, and dedup key (symbol+timeframe+action+cooldown window).
   - Add indexes/constraints for deduplication and querying by timeframe.
2. **Persistence helpers**
   - Add functions in `db_service` to insert a signal record, fetch the last signal for a given symbol/timeframe/action, and update signal status/outcomes.
   - Provide helpers for scoring (reuse the existing `/analyze` logic via shared utilities or new wrappers).
3. **SignalService integration**
   - After `evaluate_hourly_strategy`/`evaluate_daily_strategy`, call the new persistence helper with the computed signal, explanation, entry_price (current ticker), and type.
   - Respect the dedup cooldown (e.g., no new signal of the same symbol/timeframe/action until `COOLDOWN_PERIOD_HOURS` passes) and log when suppression occurs.
   - Continue sending Telegram alerts and details as before.
4. **Scoring pipeline**
   - Ensure the new signals are consumed by `performance_tracker` (either extend it or reuse existing scoring routes) so signal trades contribute to the learning DB.
   - If needed, add new scheduled job or hook in the existing tracker to evaluate these persisted records.
5. **Testing (Tests-after approach)**
   - Add unit tests for the new `db_service` helpers and dedup logic.
   - Add tests verifying `SignalService` calls the persistence helpers and respects deduplication.
6. **QA/runbook**
   - Document steps to trigger/hourly run and confirm records appear in the DB.
   - Include dedup and scoring verification scenarios.

## Notes
- Use existing constants (cooldown) for dedup to keep behavior aligned with alerts.
- Keep the new table normalized so it can be expanded (signal metadata, scoring fields).
