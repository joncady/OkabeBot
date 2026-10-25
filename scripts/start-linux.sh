#!/usr/bin/env bash
# Bootstrap/start the app; accounts, OS persistence and device pairing stay explicit.
set -euo pipefail
app_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
app_config="$app_root/okabebot.local.json"
app_python=${OKABEBOT_PYTHON:-"$app_root/.venv/bin/python"}
app_mode=start
app_args=()
while (( $# )); do
  case "$1" in
    --help|-h)
      cat <<'HELP'
Usage: scripts/start-linux.sh [CONFIG] [--bootstrap|--check] [-- BRIDGE_ARGS]
  --bootstrap  Create the venv, install voice/Cast/calendar extras, cache the model, then start.
  --check      Check local prerequisites and read-only device health, then exit.
Requires OS packages, a configured Codex CLI/sign-in and authorized hardware SSH.
Does not modify disks, configure Wi-Fi, install OS packages or enable boot services.
HELP
      exit 0 ;;
    --bootstrap) app_mode=bootstrap ;;
    --check) app_mode=check ;;
    --) shift; app_args=("$@"); break ;;
    --*) app_args=("$@"); break ;;
    *) app_config=$1 ;;
  esac
  shift
done
if [[ $(uname -s) != Linux ]]; then
  echo 'This launcher is for Linux; use python -m okabebot.bridge on macOS.' >&2; exit 1
fi
if [[ ! -f "$app_config" ]]; then
  echo 'Create okabebot.local.json from an example and configure devices first.' >&2; exit 1
fi
app_config=$(cd -- "$(dirname -- "$app_config")" && pwd)/$(basename -- "$app_config")
cd -- "$app_root"
if [[ $app_mode == bootstrap ]]; then
  python3 -c 'import sys,struct; assert sys.version_info >= (3,10) and struct.calcsize("P")==8, "64-bit Python 3.10+ required"'
  if [[ ! -x "$app_python" ]]; then python3 -m venv "$(dirname -- "$(dirname -- "$app_python")")"; fi
  "$app_python" -m pip install -e '.[voice,cast,notifications]'
  "$app_python" -m okabebot.doctor --config "$app_config"
  "$app_python" -m okabebot.setup --config "$app_config"
fi
if [[ ! -x "$app_python" ]]; then
  echo 'Python environment missing. Use --bootstrap after OS prerequisites are installed.' >&2; exit 1
fi
if [[ $app_mode == check ]]; then
  exec "$app_python" -m okabebot.doctor --config "$app_config" --devices
fi
exec "$app_python" -m okabebot.bridge --config "$app_config" "${app_args[@]}"
