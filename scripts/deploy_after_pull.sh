#!/usr/bin/env bash
set -euo pipefail

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl not found"
  exit 1
fi

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  if command -v curl >/dev/null 2>&1; then
    echo "uv is not installed; bootstrapping it"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  else
    echo "uv is not installed and curl is unavailable"
    exit 1
  fi
fi

uv sync
systemctl restart binance-strategy-bot.service
systemctl restart binance-volume-tracker.service
systemctl status binance-strategy-bot.service
systemctl status binance-volume-tracker.service
