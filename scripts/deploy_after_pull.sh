#!/usr/bin/env bash
set -euo pipefail

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl not found"
  exit 1
fi

if command -v uv >/dev/null 2>&1; then
  uv sync
elif [ -x .venv/bin/uv ]; then
  .venv/bin/uv sync
elif [ -x .venv/bin/python ]; then
  echo "uv is not installed; skipping dependency sync and using the existing .venv"
else
  echo "No uv command or .venv found"
  exit 1
fi

systemctl restart binance-strategy-bot.service
systemctl restart binance-volume-tracker.service
systemctl status binance-strategy-bot.service
systemctl status binance-volume-tracker.service
