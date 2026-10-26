#!/usr/bin/env bash
set -euo pipefail
app_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
app_python=${OKABEBOT_PYTHON:-"$app_root/.venv/bin/python"}
cd -- "$app_root"
if [[ ! -x "$app_python" ]]; then
  echo 'Create the controller environment from README.md first.' >&2; exit 1
fi
exec "$app_python" -m okabebot.runtime "$@"
