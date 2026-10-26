# Alexa and OkabeBot

Start with Home Assistant's built-in **Alexa Devices** integration. It can provide Echo Speak/Announce entities, next timer/alarm/reminder sensors, and voice interaction events. Sensors normally poll every five minutes; voice history and media state use push updates. Voice events can include the spoken command, reply, intent, and recognized speaker. They are not a microphone stream or a general feed of other skills' notifications. See [Alexa Devices](https://www.home-assistant.io/integrations/alexa_devices/).

## Manual setup

1. In Amazon **Login & Security → 2-step verification**, configure an authenticator app and make it the preferred method. This integration requires app-based MFA.
2. In Home Assistant, open **Settings → Devices & services → Add integration → Alexa Devices**. Enter the Amazon login and authenticator code directly there.
3. Open one imported Echo device. Note its Speak notification entity and next-timer timestamp sensor. Actual entity IDs depend on your device names.
4. Use **Developer tools → Actions → notify.send_message** with that Speak entity and a short test message. Announce adds a chime. This test is audible.

## Optional display package

Install `examples/home-assistant/alexa.yaml` alongside the existing `okabebot.yaml` package. It reuses `rest_command.okabebot_notification` and the existing publish-only notification secret; no new controller credentials are required.

Replace `sensor.replace_with_echo_next_timer` with your actual timer sensor, check configuration, reload automations, then enable **OkabeBot - Alexa timer scheduled**. It is disabled by default. Start a timer long enough to allow discovery (try ten minutes), and wait for the sensor to change. The resulting card is silent and states the scheduled time. The automation ignores initial entity creation, recovery from unavailable, and old timestamps, and it does not claim the timer has finished. An idle timer may be unknown, so unknown-to-future transitions are accepted. The persistent event key prevents repeating the same scheduled timestamp. Because sensor updates may lag, do not use this package as an alarm or cancellation-sensitive countdown.

The included `script.okabebot_echo_say` is an optional manual action: select one Speak entity and enter text. Nothing calls it automatically. Keep Echo speech separate from notification priority to avoid two speakers announcing the same event.

## Voice commands and AWS

For the current first pass, account linking to Alexa Devices is enough; do not provision AWS resources yet. If we later want Alexa voice control of selected Home Assistant entities, the [self-hosted Alexa Smart Home guide](https://www.home-assistant.io/integrations/alexa.smart_home/) describes the separate AWS Lambda/skill and HTTPS/account-linking route.

A future voice-event bridge should allowlist a deliberate command and selected device, deduplicate the event, and send a structured action. Do not forward every household utterance into Codex or treat ambient speech as approval for arbitrary tools. Inspect the actual event attributes first; no voice-to-Codex automation is enabled by this package.

## Current upstream authentication issue

Home Assistant 2026.10.4 can stall on Amazon's newer `/ax/claim` login flow with
`InvalidUrlClientError`; retrying does not fix that server-side library failure.
See [upstream issue 187595](https://github.com/home-assistant/core/issues/187595).
Maintainers target the supported fix for 2026.11. No container-local credential
or authentication patch is bundled here. After updating to a release containing
the fix, cancel the old flow and retry with a fresh authenticator code.

For a deliberate local workaround on 2026.10.4, upstream's merged
[dependency update](https://github.com/home-assistant/core/pull/187985) uses
`aioamazondevices==16.9.1`. Replacing the installed library and matching the
integration manifest requirement is an unsupported local backport, not an app
installation step. Back up the original library and manifest, restart Home
Assistant, then retry setup with a fresh code. Container recreation removes this
change; a normal fixed Home Assistant release should replace it. To roll back,
restore the original manifest and library version, then restart.

The 16.9.1 backport also needs the matching upstream import in
`alexa_devices/binary_sensor.py`: `SENSOR_STATE_OFF` moved from
`aioamazondevices.const.metadata` to `aioamazondevices.const.sensors`. Without
this change authentication may succeed but entity setup fails. Verify every
integration module imports before restarting; retain the original integration
directory for rollback.

Local backport validation: authentication and entity import completed on the
2026.10.4 installation (8 devices, 94 entities). This verifies account import,
not timer-to-screen delivery, Echo speech, or long-term token refresh; test those
separately after choosing an Echo device.

## Optional context-aware speaking

Install `examples/home-assistant/context_speech.yaml` as a package and replace the
local ordered sensor-to-Speak routes. The helper starts off, and the script
defaults to dry-run. Calling it with `message` and `dry_run: true` returns the
selected speaker, enable state, and cooldown readiness without sound. For actual
speech, manually enable `input_boolean.okabebot_context_speech` and pass
`dry_run: false`. It selects the first active room sensor, rejects unavailable
speakers and inactive/unknown sensors, and enforces a five-minute cooldown.
No occupancy transition or notification automatically invokes this script.

Motion indicates activity, not identity or continuous occupancy. Map an indoor
room sensor only to a speaker in that same room. Connectivity is not presence;
Ring outdoor motion and a phone's home/away tracker should not select a room
speaker. The current installation exposes one Echo motion sensor; neither
imported Show exposes room occupancy through this integration.

The Show Speak action was tested successfully with soft-volume SSML. Speaker
routing remains an opt-in experiment; it is not attached to notification delivery.
