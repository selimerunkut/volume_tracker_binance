#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed"
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl not found"
  exit 1
fi

uv sync
systemctl restart binance-strategy-bot.service
systemctl restart binance-volume-tracker.service
systemctl status binance-strategy-bot.service
systemctl status binance-volume-tracker.service
