import re
from typing import Dict, Any, List, Optional
from telegram_messenger import TelegramMessenger
from telegram_notifier import TelegramNotifier

class LogProcessor:
    """
    Handles parsing of Hummingbot logs for various information and trade events.
    Delegates trade notifications to TelegramNotifier.
    """
    def __init__(self, notifier: 'TelegramNotifier'):
        self._notifier = notifier
        self._last_processed_trade_logs: Dict[str, set] = {} # Stores a set of processed log hashes per instance

    async def parse_bot_logs_for_info(self, general_logs: List[Dict[str, Any]]) -> Dict[str, str]:
        """Parses general logs for PnL and Open Orders information."""
        pnl_info = "PnL: N/A"
        open_orders_info = "Open Orders: N/A"

        for log_entry in reversed(general_logs):
            msg = log_entry.get('msg', '')
            pnl_match = re.search(r"PnL: ([\d\.\-]+ [A-Z]+)", msg)
            open_orders_match = re.search(r"Open Orders: (\d+)", msg)

            if pnl_match:
                pnl_info = f"PnL: {pnl_match.group(1)}"
            if open_orders_match:
                open_orders_info = f"Open Orders: {open_orders_match.group(1)}"

            if pnl_match and open_orders_match:
                break
        return {"pnl_info": pnl_info, "open_orders_info": open_orders_info}

    async def determine_stop_reason(self, general_logs: List[Dict[str, Any]], error_logs: List[Dict[str, Any]]) -> str:
        """Determines the reason for a bot stopping based on logs."""
        stop_reason = "Unknown Reason"
        for log_entry in reversed(general_logs):
            msg = log_entry.get('msg', '').lower()
            if "fixed stop loss hit" in msg or "take profit hit" in msg or "all positions closed" in msg or "trade completed" in msg:
                stop_reason = "Trade Completed"
                break
            elif "stopping the strategy" in msg:
                stop_reason = "Manual Stop/Strategy Stopped"
                break

        if error_logs and stop_reason == "Unknown Reason":
            for log_entry in reversed(error_logs):
                msg = log_entry.get('msg', '').lower()
                if "error" in msg or "exception" in msg:
                    stop_reason = f"Error: {msg[:100]}..."
                    break
        return stop_reason

    async def parse_trade_logs_and_notify(self, chat_id: str, instance_name: str, general_logs: List[Dict[str, Any]]):
        """Parses general logs for trade events and sends notifications."""
        if instance_name not in self._last_processed_trade_logs:
            self._last_processed_trade_logs[instance_name] = set()

        print(f"DEBUG: parse_trade_logs_and_notify received general_logs for {instance_name}: {general_logs}")
        for log_entry in general_logs:
            log_msg = log_entry.get('msg', '')
            log_timestamp = log_entry.get('timestamp', '')
            print(f"DEBUG: Processing log entry: {log_msg}")

            trade_match = re.search(r"(BUY|SELL) order .*? amounting to ([\d\.]+)/[\d\.]+ ([A-Z]+) has been filled at ([\d\.]+) ([A-Z]+)\.", log_msg)
            
            if trade_match:
                trade_type, amount, base_asset, price, quote_asset = trade_match.groups()
                trading_pair = f"{base_asset}-{quote_asset}"
                trade_identifier = f"{instance_name}-{trading_pair}-{trade_type}-{amount}-{price}-{log_timestamp}"
                print(f"DEBUG: Trade match found for {instance_name}. Identifier: {trade_identifier}")

                if trade_identifier not in self._last_processed_trade_logs[instance_name]:
                    print(f"New trade detected for {instance_name}: {log_msg}")
                    await self._notifier.notify(
                        chat_id,
                        message_type="trade_update",
                        instance_name=instance_name,
                        trading_pair=trading_pair,
                        trade_type=trade_type,
                        price=float(price),
                        amount=float(amount),
                        timestamp=log_timestamp
                    )
                    self._last_processed_trade_logs[instance_name].add(trade_identifier)
                else:
                    print(f"DEBUG: Trade {trade_identifier} already processed for {instance_name}. Skipping notification.")
            else:
                print(f"DEBUG: No trade match found for log entry: {log_msg}")