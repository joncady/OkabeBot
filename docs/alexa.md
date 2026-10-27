# Alexa and OkabeBot

Start with Home Assistant's built-in **Alexa Devices** integration. It can provide Echo Speak/Announce entities, next timer/alarm/reminder sensors, and voice interaction events. Sensors normally poll every five minutes; voice history and media state use push updates. Voice events can include the spoken command, reply, intent, and recognized speaker. They are not a microphone stream or a general feed of other skills' notifications. See [Alexa Devices](https://www.home-assistant.io/integrations/alexa_devices/).

## Manual setup

1. In Amazon **Login & Security → 2-step verification**, configure an authenticator app and make it the preferred method. This integration requires app-based MFA.
2. In Home Assistant, open **Settings → Devices & services → Add integration → Alexa Devices**. Enter the Amazon login and authenticator code directly there.
3. Open one imported Echo device. Note its Speak notification entity and next-timer timestamp sensor. Actual entity IDs depend on your device names.
4. Use **Developer tools → Actions → notify.send_message** with that Speak entity and a short test message. Announce adds a chime. This test is audible.

## Timer and reminder cards

Install `examples/home-assistant/alexa.yaml` in Home Assistant's packages directory.
It uses the same `okabebot_notification_url` and publish-only
`okabebot_notification_token` secrets as the other notification packages. Check
configuration, then reload **RESTful Command** and **Automations**. The automation
is enabled on first installation and discovers imported Alexa Devices sensors
ending in `_next_timer` or `_next_reminder`; personal entity IDs are not shipped.
It does not act on alarm, presence or voice-history entities.

Cards are **silent**, normal priority, and explicitly say “timer scheduled” or
“reminder scheduled,” with the originating device and local due time. Alexa still
sounds the real alarm. Sensor polling uses a five-minute interval, with additional provider request
latency possible; manual refreshes are also debounced in the installed version.
Only the next
schedule per device/type is exposed. This is not a complete reminder list or a
reliable timer completion/cancellation feed. Household-linked reminders may be
missing from Amazon's response. Test with a ten-minute timer and a fifteen-minute
reminder on the chosen device.

Idle notification sensors can be `unavailable` in this integration version. The
bridge accepts a future timestamp from that state; it ignores initial creation,
attribute-only changes, past timestamps, removal and cancellation. Persistent
controller deduplication uses entity ID plus normalized due timestamp, so a known
schedule returning after reconnect does not generate another card. An unseen
schedule discovered on reconnect can correctly be shown as scheduled; it is not
claimed as newly created or finished. No countdown or due-time speech is inferred.

Use **Settings → Automations → OkabeBot - Alexa timer and reminder cards** to
disable the bridge. Notification source controls can separately disable `alexa`.
No speaker setting, new credential or public endpoint is required.

## Voice commands and AWS

For the current first pass, account linking to Alexa Devices is enough; do not provision AWS resources yet. If we later want Alexa voice control of selected Home Assistant entities, the [self-hosted Alexa Smart Home guide](https://www.home-assistant.io/integrations/alexa.smart_home/) describes the separate AWS Lambda/skill and HTTPS/account-linking route.

## Explicit voice-event bridge

`examples/home-assistant/alexa_voice.yaml` forwards only allowlisted phrases from
selected Echo voice-event entities to `/alexa/events`. Configure the controller's
`alexa_voice` section and select the same devices/phrases in the HA package.
Controller defaults are disabled with no devices. The HA enable helper starts off
on first installation and remembers subsequent user changes.

```json
{
  "alexa_voice": {
    "enabled": true,
    "devices": [{"entity_id": "event.your_echo_voice_event", "default_location": "your_location_id"}],
    "welcome_phrases": ["I'm home", "I am home"],
    "summon_phrases": ["call companion"],
    "move_prefixes": ["call companion to", "send companion to", "move the companion to"]
  }
}
```

`default_location` is a registered location ID for the bare summon phrase.
Qualified movement resolves an exact configured location name, ID or alias;
optional leading “the” is accepted. Pending/unapproved or ambiguous destinations
are rejected. No room name or Echo-to-surface association is inferred.

The controller generates a separate `alexa-voice-token` in private application
state. Put it in HA `secrets.yaml` as `okabebot_alexa_voice_token`, and configure
`okabebot_alexa_voice_url` to the controller's LAN `/alexa/events` endpoint.
Never substitute the full dashboard or publish-only notification credential.
Validate HA configuration, reload Input booleans, RESTful Command and Automations,
then enable **OkabeBot Alexa voice commands**. No public ingress is required.

Both sides require Amazon's original source timestamp (90 seconds), not the
Home Assistant receipt time. The controller independently checks the Echo
allowlist and phrase map, persistently claims the event before acting and keeps
a per-device source-time watermark. Older/out-of-order events, including after
restart, are rejected. Busy or uncertain actions are never retried. Unknown phrases are inert; utterances are never sent to an
LLM as tool instructions. Explicit welcome reuses the existing generated greeting,
important-update recap and quiet policy. These events are command history after
Alexa's own response, not a replacement Alexa conversation: Alexa may run its own
routine or say it does not understand. A custom skill is the cleaner future UX.

### History-format compatibility

The pinned HA 2026.10.4 integration does not expose Amazon's record timestamp.
Its event state is receipt time and can make restored history appear fresh.
Before enabling voice commands on that version, run the read-only check:

```sh
python scripts/patch-alexa-event-time.py
```

If needed, apply the version-guarded compatibility patch with `--apply`, then
restart the HA container so the Python module reloads. It backs up the original
`event.py` under private `/config/.local-compat-backups`, adds only
`source_timestamp_ms`, and refuses unknown source/version layouts. Restore the
backup and restart HA to undo it. Container recreation can remove this patch;
missing source time makes the voice automation fail closed. Do not substitute
HA `last_changed` or event state as a fallback.

Some Amazon history records use the generic title **Request** and put the user's
utterance in the subtitle. After verifying a device actually uses that format,
add its event ID to the HA package's `request_subtitle_entities` list. The adapter
uses the subtitle only for opted-in sources with that exact marker, then applies
the same command allowlist. It never generally treats Alexa replies as commands.
Other sources retain their normal `voice_command` interpretation.

Disable the HA helper or set `alexa_voice.enabled` false to stop the bridge.
No automatic room speech or arbitrary smart-home command forwarding is enabled.

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

## Explicit named speech from MCP and dashboard

Install `examples/home-assistant/echo_webhook.yaml` as a package, replace its
notify-entity allowlist, and define `okabebot_echo_webhook` in Home Assistant's
private secrets.yaml using a fresh random secret (at least 32 bytes). Validate HA
configuration and reload automations or restart HA. The webhook is local-only and
POST-only. Keep it on a trusted local network; it carries a bearer secret in its URL.

In the controller's private `.env`, set `OKABEBOT_ECHO_WEBHOOK` to
`http://your-ha-host:8123/api/webhook/YOUR_SECRET` and set
`OKABEBOT_ECHO_SPEAKERS` to a quoted JSON object mapping display names to the same
allowlisted `notify.*_speak` entity IDs. Never commit either credential. Rotate by
changing both the HA secret and controller URL, then reloading HA.

`list_echo_speakers` lists configured destinations, not proof they are online.
`speak_on_echo` requires an explicit name, escapes text and uses soft-volume SSML.
`dry_run=true` validates local configuration without sound. A successful webhook
submission is not proof of playback; no automatic retry is performed. No presence
routing or automatic notification-to-Echo announcement is enabled by these tools.

## Custom skill prototype (preferred next voice route)

The installed history-command bridge is disabled at the user's request. Alexa
still answers those commands itself, and retrospective history is an awkward
control path. Timer/reminder cards and named Echo speech remain separate.

Use the [custom skill prototype guide](alexa-skill.md) for the tested local
request/reply and generic Qwen audio path. A generic-audio AWS development endpoint and HTTPS media hosting are deployed.
Authenticated cloud-to-local tool transport and physical Echo acceptance are
not complete.
A Show renderer remains a separate session-limited APL adapter, not an always-on
browser surface.
