#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
hook_dir="$repo_root/.git/hooks"

if [ ! -d "$hook_dir" ]; then
  echo "Hook directory not found: $hook_dir"
  exit 1
fi

cp "$repo_root/scripts/post-merge" "$hook_dir/post-merge"
chmod +x "$hook_dir/post-merge"
