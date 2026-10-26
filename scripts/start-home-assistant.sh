#!/usr/bin/env bash
# Local cloud integrations: Tuya/Ring. No USB or host-network access required.
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
ha_config_dir="${OKABEBOT_HA_CONFIG_DIR:-$project_dir/.local/home-assistant}"
ha_bind="${OKABEBOT_HA_BIND:-127.0.0.1}"
ha_image="${OKABEBOT_HA_IMAGE:-ghcr.io/home-assistant/home-assistant:2026.10.4}"
mkdir -p "$ha_config_dir"
chmod 700 "$ha_config_dir"
ha_ports=(-p "127.0.0.1:8123:8123")
if [[ "$ha_bind" != "127.0.0.1" ]]; then
  ha_ports+=(-p "$ha_bind:8123:8123")
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
