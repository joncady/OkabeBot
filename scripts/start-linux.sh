#!/usr/bin/env bash
# Start an installed controller; does not install packages or modify disks.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CONFIG=${1:-"$ROOT/okabebot.local.json"}
if (( $# > 0 )); then shift; fi
PYTHON=${OKABEBOT_PYTHON:-"$ROOT/.venv/bin/python"}
if [[ $(uname -s) != Linux ]]; then
  echo 'This launcher is for Linux.' >&2; exit 1
fi
if [[ ! -f "$CONFIG" ]]; then
  echo "Configuration not found: $CONFIG" >&2; exit 1
fi
if [[ ! -x "$PYTHON" ]]; then
  echo "Python environment not found: $PYTHON" >&2
  echo 'Follow docs/linux-controller.md or set OKABEBOT_PYTHON.' >&2; exit 1
fi
exec "$PYTHON" -m okabebot.bridge --config "$CONFIG" "$@"
