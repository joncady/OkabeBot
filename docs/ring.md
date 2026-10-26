# Ring doorbell cards

Ring connects directly to Home Assistant; Alexa and an AWS skill are not needed for this path. This setup sends a silent character card when the doorbell is pressed. Motion, video, and speech remain separate opt-ins.

## Manual account setup

1. Open Home Assistant → **Settings → Devices & services → Add integration → Ring**.
2. Enter your Ring username/password directly in Home Assistant, then the verification code from the method configured in Ring. Do not put these in the repository or chat.
3. Open the imported doorbell device and find its **event** entity for doorbell presses. Copy that entity ID; do not select its motion entity. Current Ring uses event entities rather than the old binary sensors.
4. Press the doorbell once and confirm that entity's timestamp changes. Share the entity ID and whether this test succeeded; no credentials are needed to finish wiring the card.

## Enable the card

The prepared `examples/home-assistant/ring.yaml` package depends on the reusable `rest_command.okabebot_notification` in `examples/home-assistant/okabebot.yaml`. Add both packages to Home Assistant and configure the notification URL/token as described in [the home integration guide](home-assistant.md#door-card-package).

Replace `event.replace_with_ring_doorbell_event` with the verified entity. Validate Home Assistant configuration before reloading/restarting. The automation is intentionally disabled initially: enable **OkabeBot - Ring doorbell card** after selecting and testing the entity. `initial_state: false` also disables it at each HA startup; remove that line after the end-to-end test to retain the enabled state across restarts.

A recent event timestamp triggers the card; old restored timestamps and attribute-only changes do not. A 20-second cooldown handles duplicate Ring alerts. The shared REST action gives cards a 60-second expiry. `priority: normal` is silent; changing it to `important` opts into the existing spoken notification behavior. No camera feed or recording is downloaded.

## Verify

With the controller and display running, enable the automation and press the doorbell. Confirm one silent card appears. Check the automation trace if it does not. After a restart, check that no stale card appears. To test a second real alert, wait at least 20 seconds.

Ring uses its cloud service. Real-time events require outbound TCP port 5228 from the Home Assistant host; no inbound internet port or public OkabeBot endpoint is needed. Last-recording playback requires a Ring subscription, but this card only consumes doorbell events. The integration also exposes live-view entities; camera presentation is a later feature.

Source: [Home Assistant Ring integration](https://www.home-assistant.io/integrations/ring/).
