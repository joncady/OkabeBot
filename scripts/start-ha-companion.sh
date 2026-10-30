#!/usr/bin/env bash
# Keep this foreground service under launchd/systemd in an unattended installation.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
config="${OKABEBOT_HA_COMPANION_CONFIG:?Set OKABEBOT_HA_COMPANION_CONFIG to private bridge JSON}"
cd "$root"
exec "${OKABEBOT_PYTHON:-$root/.venv/bin/python}" -m okabebot.ha_companion --config "$config"
