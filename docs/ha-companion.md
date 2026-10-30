# Home Assistant companion facade

The optional `okabebot.ha_companion` process publishes a bounded projection of an
existing controller to MQTT Discovery. It does not move model inference onto the
satellite or Home Assistant. Install the `home-assistant` Python extra.

Private JSON passed with `--config` contains `id` (stable unique MQTT-safe ID),
`name`, `area` (suggested HA area), `location_id` (existing approved Pi destination),
`host`, optional `port`, `username`, `password`, and `control_file` (the existing
controller's private `ptt/control.json`). Keep it owner-readable and outside Git.
Run `python -m okabebot.ha_companion --config /private/bridge.json`, or use
`scripts/start-ha-companion.sh` with `OKABEBOT_HA_COMPANION_CONFIG` set.
Supervise it with launchd/systemd. The active Mac installation uses launchd.

Use an authenticated Mosquitto broker with persistent storage and retained discovery.
Bind the published broker port to loopback, not the LAN; connect HA and the broker
through a private Docker network. Add MQTT in HA with the broker's Docker DNS name.
Container installations do not have add-ons. Docker must start after login/reboot;
`unless-stopped` does not itself launch Docker. Use separate broker users/ACLs if
other clients are added. Do not expose the controller owner token to HA: the facade
reads it locally, and accepts only the two command types below.

The HA device suggests its configured area on first registration; subsequent room
changes belong to HA's device registry. Changing `area` does not override a user's
existing registry choice. The scene/location registry is still independent: automatic
HA-area synchronization is planned, not implemented.

## Exposed entities and semantics

- Character, bounded activity (`idle`, `busy`, `recording`), busy and recording.
- Voice/display service connectivity, based on controller RPC health probes.
- Speaker volume (0–100 integer) using the same physical mixer as the dashboard.
- Call companion button, moving to the configured approved Pi destination.
- Optional USB Uno room sensors: ultrasonic distance, nearby-object state, room temperature/humidity and tilt contact. Missing readings are unavailable. See [room sensors](room-sensors.md).

Broker availability describes the facade/controller connection, not proof that the
physical Pi is online. The separate service connectivity entities describe remote
RPC reachability. Recording is a state indicator, not a microphone power switch.
States publish every 15 seconds without retention. Discovery and availability are
retained; MQTT last-will marks an ungraceful facade disconnect offline. Retained
commands are ignored, and failed commands are not retried. Do not retain commands.
No notification bodies, transcripts, audio, preferences or calendar payloads are
published. No camera, arbitrary RPC, shell commands, or unrestricted tool execution
is exposed. Existing dashboard authentication stays unchanged.

## Responsibility audit

| Function | Current owner | HA role / next step |
|---|---|---|
| Rooms, floors, device assignment | HA | Canonical home metadata; automatic import remains planned |
| TV power/input | Native Samsung/Vizio integrations and wake workflow | Reuse HA controls; preserve verified Cast/CEC wake path |
| Cast content / receiver readiness | Direct Cast adapter | Add HA Google Cast for shared observations; do not replace handoff acknowledgments |
| Pi volume and call-home | Existing controller, now MQTT facade | HA automations can call bounded entities |
| Door, phone, appliances, weather | HA integrations and scoped publishers | Continue consented event delivery; avoid duplicate collectors |
| BLE phone proximity | Pi scanner | Not an HA Bluetooth proxy; publishing calibrated proximity is follow-up |
| Speech, transcription, local model | Controller/model workers | Keep outside HA; HA can request future bounded actions |
| Animation, scene reservations, screen movement | Controller | Keep single owner; HA must not independently duplicate actors |
| Quiet hours, focus, proactive conversation | Controller with HA context | Keep delivery policy centralized; expose status before moving policy |
| CPU temperature, power warnings, raw button events | Pi, not yet exported | Add explicit safe satellite telemetry rather than inventing values |

Neither native TV power nor a stale restored HA state proves active playback or
person presence. The external Chromecast and its physical TV are distinct devices
in the same area, representing one destination. Do not double-count them.

## Bounded two-screen presence trial

`python -m okabebot.presence_follow --config /private/follow.json` combines an
existing Pi BLE scanner with timestamped MQTT occupancy/on-body signals from
`examples/home-assistant/presence_follow.yaml`. The private configuration supplies
two approved destination IDs, broker credentials, `control_file`, `motion_topic`,
`body_topic`, scanner argv and a target-only `beacon` definition. Scanner argv must
use a bounded duration; the trial ends with the scanner. It is deliberately not
an always-on location service.

Only a positive on-body state accompanied by a fresh device heartbeat permits movement.
Bind `companion_watch_heartbeat` to a non-health Watch sensor such as battery level;
an unchanged event-driven on-body state is not itself an offline indication. A positive BLE near event
requests the Pi; a new sustained room-motion event requests the other screen.
Recent nearby samples take precedence over anonymous room motion. Missing BLE does
not itself select a room. Transitions, destinations outside the selected pair,
active conversations, focus, known playback and a two-minute cooldown block moves.
Failed/uncertain handoffs are not automatically retried. State recovery and retained
MQTT events do not trigger motion moves. On-body freshness is bounded separately
from the HA publisher heartbeat; a stale heartbeat disables following.

RSSI thresholds require local calibration. Motion can be another person; wearing
a watch does not prove that the person triggering motion is its owner. This proof
must not be described as reliable person tracking. The existing native Cast
handoff still owns TV preparation and scene arrival acknowledgment. Physical
near/far separation and bidirectional handoff require human validation.

## Two-anchor BLE follow proof

`python -m okabebot.ble_follow --config /private/two-anchor.json --seconds 900`
compares target-only samples from exactly two configured SSH scanners. Each private
`anchors` item supplies an approved `location_id` and `scanner_argv`; broker settings,
`body_topic`, `control_file`, and `beacon` follow the wearable trial above. The main
process accepts only a bounded 60–1800 second runtime and terminates its scanner
children on exit. It is not installed as a permanent service.

A winner needs three recent readings, a calibrated minimum signal, sustained dwell,
and a margin over any recent competing samples. Neither radio seeing the target
means unknown, not absence. Active handoffs, conversations, recording, focus and
known media playback block moves; a fresh worn/device-heartbeat feed is required.
Only the configured pair participates, and uncertain moves consume the cooldown
before physical delivery. Generic regressions cover ambiguous signals, insufficient
samples, stale windows and cooldowns. RSSI measurements, device identities and
physical calibration remain private; two successful samples do not establish
unattended localization reliability.

For a supervised device-follow calibration only, private `require_worn: false`
allows the bounded trial to follow the beacon without asserting that it is worn.
The default requires the wearable feed. This override is not evidence of person
presence and must not be carried into unattended home automations.

## Additional read-only satellite devices

Run `python -m okabebot.ha_satellite --config /private/satellite.json` under a
supervisor to register another SSH satellite. Configuration includes broker
`host`, optional `port`, `username`, `password`, stable `id`, device `name`,
suggested `area`, and trusted private `ssh_argv` (SSH binary/options/target only).
The process appends a fixed Python diagnostic program; it does not subscribe to
commands. It publishes connectivity, Wi-Fi dBm, CPU temperature and uptime every
30 seconds with non-retained telemetry and retained discovery/availability. Failed
SSH probes mark entities unavailable rather than maintaining stale measurements.
This telemetry agent does not start a BLE scanner or publish user proximity.


## Watch home estimate and return greeting

`python -m okabebot.home_presence --config /private/home-presence.json` runs a
supervised, opt-in observation bridge independent of character movement. It cycles
bounded target-only scans on two fixed satellites, requires powered/discovering
radio heartbeats, reconnects scanners/broker and exposes an expiring MQTT enum
sensor: home, probably_away or unknown. A healthy-scanner count is included as a
local HA attribute. It does not replace HA Person or override a stale GPS tracker.
Device presence is not proof that a watch is worn or identifies a room occupant.

Private configuration supplies broker settings, stable `id`/topic `prefix`,
`anchors` (unique IDs and verified SSH argv ending in a bounded scanner command),
`beacon`, `door_topic`, `state_file`, `control_file`, `arrival_token_file`, and the
optional owner-selected one-trip `departure_intent`. Use `ServerAliveInterval`
and `ServerAliveCountMax` on SSH sessions. State is owner-readable private metadata;
no transcripts or observations are committed. The bridge stores only the current
trip's arming/consumption state, not a location history.

The existing HA package `home_presence.yaml` sends only real off-to-on door events,
with timestamps and no retained messages. Bind its two secret references locally.
No sighting for five minutes can produce probably-away only with continuous healthy
scanners and recent door evidence or explicit departure intent. Scanner failure
produces unknown; stale door activity alone cannot turn a charging watch into a
new departure. A fresh door event plus repeated return sightings may consume one
armed greeting before HTTP submission. Uncertain outcomes are not retried.

The dedicated authenticated arrival endpoint accepts `ble_presence`, using the
same generated character introduction, bounded important-update recap, existing
announcement destination, quiet policy, volume and overlap deduplication as other
welcomes. It is separate from the optional door-armed Amadeus conversation trial;
that trial must not silently swallow an explicitly armed BLE welcome. A too-short
absence, missing door cue, radio outage, quiet policy or unavailable speaker can
prevent speech; do not promise a physical greeting until tested.


## Supervised following and Amadeus context

The installed home-presence bridge now reuses its two scanner streams for following;
it does not launch a second set of scanners. The older CLI proof stays bounded.
Owner dashboard controls call `/presence/follow` with a boolean `enabled`; current
state, freshness, health and pause reason appear beside the button. Disable remains
independent of read-only home estimation and return greetings.

Manual destination requests pause following for ten minutes. An unexpected settled
location change also creates that hold. Cooldowns are persisted before movement
submission, including rejected/uncertain requests, so a process restart does not
immediately replay a handoff. The controller revalidates the approved configured
pair, health, enabled state, manual hold, focus/media/busy state and destination
ownership before calling the existing surface movement API. A Cast target must be
on its active, idle Backdrop input; following does not wake an unknown/inactive
input or interrupt another Cast app. Morning wake remains a separately configured
workflow. These guards favor holding position when evidence is ambiguous.

Amadeus proactive delivery reads the expiring Watch runtime projection when the
bridge is configured: only fresh home evidence with two healthy scanners permits
delivery. Unknown and probably-away block it; stale phone state does not override
this gate. Other calendar/media/focus/quiet/guest/consent gates still apply. The
metadata observer can bind its presence source to the derived HA sensor instead
of phone/person entities. The store's existing confirmed-away schema maps the
probably-away estimate to unknown rather than silently upgrading it to certainty.
This is device evidence, not a wearer-identity guarantee.

## Buffered Pi announcements

Character announcements fully synthesize before uploading a bounded WAV to the
Voice service's `audio_prepare` operation. The expiring single-use capability is
then consumed by `play_prepared` over the same SSH tunnel, avoiding fresh SSH setup
between upload and playback. Scheduling uses the Pi's returned clock and a short
lead for animation. No synthesis or upload is needed while the audio is playing.
Interactive replies still use the existing streaming path; buffering adds time
before an announcement starts in exchange for continuous playback. Volume and
reference voices are unchanged. Upgrade `prepared_audio.py` with `voice_service.py`;
older satellites reject this operation rather than silently replaying or falling
back to a potentially choppy stream.

## Native Mac display state

The same supervised MQTT facade can publish a separate **Little Lab Mac** device
with a **Mac display awake** binary sensor. It projects only the controller's
fresh, paired native display signal. No app/window names or user activity history
are published. It becomes unavailable when the Mac surface stops reporting or the
controller/facade disconnects. Select the corresponding HA binary sensor explicitly
for any Amadeus observation; publishing MQTT state does not grant learning consent.
See [Mac display wake following](surfaces.md#mac-display-wake-following) for the
owner-editable automatic handoff rule and its distinct native event source.
