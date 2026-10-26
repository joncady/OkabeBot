#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
current_hooks="$(git config --get core.hooksPath || true)"
if [[ -n "$current_hooks" && "$current_hooks" != '.githooks' ]]; then
  echo "Existing hooksPath is configured; add this commit-msg hook to that workflow manually." >&2
  exit 1
fi
git config --local core.hooksPath .githooks
echo 'README review hook installed for this checkout.'
