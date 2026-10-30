#!/usr/bin/env bash
# HA cloud integrations and optional local Sonos callbacks; no USB/host network.
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
ha_config_dir="${OKABEBOT_HA_CONFIG_DIR:-$project_dir/.local/home-assistant}"
ha_bind="${OKABEBOT_HA_BIND:-127.0.0.1}"
sonos_bind="${OKABEBOT_HA_SONOS_BIND:-}"
ha_image="${OKABEBOT_HA_IMAGE:-ghcr.io/home-assistant/home-assistant:2026.10.4}"
mkdir -p "$ha_config_dir"
chmod 700 "$ha_config_dir"
ha_ports=(-p "127.0.0.1:8123:8123")
if [[ "$ha_bind" != "127.0.0.1" ]]; then
  ha_ports+=(-p "$ha_bind:8123:8123")
fi
if [[ -n "$sonos_bind" ]]; then
  python3 - "$sonos_bind" <<'PYIP'
import ipaddress, sys
address = ipaddress.ip_address(sys.argv[1])
if address.version != 4 or not address.is_private or address.is_unspecified or address.is_loopback:
    raise SystemExit("Choose a specific private LAN IPv4 address for Sonos callbacks")
PYIP
  ha_ports+=(-p "$sonos_bind:1400:1400/tcp")
fi
if docker container inspect okabebot-home-assistant >/dev/null 2>&1; then
  docker start okabebot-home-assistant
else
  docker run -d --name okabebot-home-assistant \
    --restart unless-stopped --stop-timeout 60 \
    -e TZ=America/Los_Angeles \
    -v "$ha_config_dir:/config" \
    "${ha_ports[@]}" \
    "$ha_image"
fi
printf 'Home Assistant: http://%s:8123\nConfiguration: %s\n' "$ha_bind" "$ha_config_dir"
