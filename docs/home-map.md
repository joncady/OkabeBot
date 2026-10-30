# Home map and presence: proposed dashboard refresh

Status: broader design proposal. An owner-requested registry preview, entity
suggestions and private destination-to-area bindings are implemented. Continuous
registry subscriptions, home/room fusion and native Mac BLE positioning are not
implemented. The separately configurable HA portal link is
implemented. This specification contains no actual household layout or observations.

## One room model, two arrangements

Use Home Assistant floor and area registry IDs as room identities, with device and
entity assignments resolved from its registries. An explicit entity area overrides
its device's area; devices/entities belong to areas, and areas belong to floors.
Names and aliases are presentation and voice vocabulary, never primary keys.

HA owns room names, floors and device membership. OkabeBot owns a private overlay:
logical non-overlapping room rectangles, door/stair adjacency, screen membership,
relative screen positions, approved audio endpoints and character scene reservations.
HA Areas do not supply wall geometry or doorway adjacency; those require setup.
An optional uploaded plan can come later. Begin with a schematic, not coordinates
that pretend to be measured locations.

- **Home:** floor tabs and room tiles show fresh user/device estimates, character
  destination, room activity and attention icons. Unknown entities stay in an
  unplaced tray. Tapping a room shows evidence, age, permitted screens and speakers.
- **Screens:** existing cardinal display arrangement, scoped within rooms, controls
  character entrances/exits. A portable screen inherits the laptop/phone estimate
  without editing the house layout. A room change must not silently rewrite a
  calibrated screen orientation or duplicate the character's active scene.
- **Connections:** import/refresh HA metadata, preview changes, map orphaned
  endpoints, pair screens, select capability roles and run guided calibration.
- **Dev:** retain transcripts, timings and raw diagnostic evidence behind the
  existing small dev control. Daily views favor pixel portraits and status icons;
  setup controls disappear after completion and return under Edit home.

## Identity and evidence

Keep separate objects for Person, portable Device, fixed Sensor/Anchor, Room,
Character Surface and Audio Endpoint. A screen can use a different approved speaker;
a Bluetooth scanner is not automatically a speaker or a fixed room anchor.

A normalized location estimate contains:

- subject ID and kind: person, device or character;
- optional HA area/floor IDs and specific surface ID;
- certainty: confirmed, inferred, ambiguous, unknown or stale;
- method and source IDs, observation time, expiry and competing room candidates.

Do not display uncalibrated percentage confidence or RSSI-derived meters as truth.
Character position is acknowledged by the existing handoff protocol; in transit
show one traveling marker, and never invent arrival from a launch request. A user's
room is an inference unless explicitly checked in; a carried phone is a device
proxy, not proof of the user's body. Household occupancy does not identify people.

Door-open fallback means assumed home with room unknown. TV playback means activity
at a device, not that its owner is watching. Screen online is availability, not
presence. Phone near a known room anchor supports proximity; it does not establish
that every nearby device or person occupies that room.

## Fusion and output routing

Use explicit check-in first, then calibrated multi-anchor personal-device room
estimates, corroborated by occupancy where available. Router/phone trackers support
home/away, not room coordinates. BSSID may help only where access-point placement
is known and one access point does not cover several rooms. Calendar and DND gate
attention, not location. Contradictions yield ambiguity rather than a false precise
pin. Require dwell time and hysteresis for room changes, then expire stale sources.

A mobile Mac must never remain a fixed anchor when it is carried to another room.
A verified dock/manual stationary mode can temporarily make it a fixed scanner.
Sleep, lost permissions and disconnected sensors expire its estimates; they do not
move the laptop to the backend host's configured room or prove the person is away.

Provide high-level interfaces:

- `where_is(subject, max_age)` returns a typed estimate and evidence, not a guess.
- `list_room_capabilities(area)` returns approved screens, speakers and sensors.
- `resolve_recipient_output(person, purpose)` uses fresh room evidence, permission,
  focus/media/quiet policy, endpoint health and audience/privacy constraints.
- `move_companion(surface)` retains existing scene uniqueness and handoff ACK rules.

User-facing speech should use an approved output in the recipient's confidently
resolved room. Ambiguous location suppresses unsolicited speech unless the user
explicitly chose a fallback room. No broadcasting, TV wake, scene move or volume
change follows merely from importing a device or drawing it on the map. Initial
room fusion runs in shadow alongside the existing explicit-destination trial.

## Home Assistant self-service

Connect locally through a backend-owned authenticated HA connection. Bootstrap
floors, areas, devices, entities and selected current states, then subscribe to
registry/state events and reconcile after reconnects. The existing write-only
publisher cannot perform that import. Do not read `.storage` files as the production
sync interface. No HA token belongs in browser markup, map data, QR codes or URLs.

HA authentication is not assumed to provide a bespoke read-only token scope. Keep
connector code observation-only, protect its credential and verify registry access
permissions during implementation; configuration writes need a deliberate separate
workflow. Prefer deep links to HA for room/device editing before adding write access.

The setup wizard should:

1. Connect HA and preview imported rooms/floors; keep absent metadata unresolved.
2. Reconcile physical endpoints across Cast, HA and paired screens using stable
   provider identities, not friendly names/IP guesses. Confirm unresolved duplicates.
3. Assign screens, speakers and fixed scanners to areas, with explicit capability
   and observation choices. Link a Person to its approved personal device proxy.
4. Arrange non-overlapping room blocks and door/stair links; then orient screens.
5. Offer guided near/far and room-to-room calibration with visible evidence quality.
6. Show a private readiness summary and allow correction, forgetting or disabling
   tracking. New discoveries enter a review tray; they do not gain control permission.

## BLE choices

For room presence, evaluate Bermuda, a community HA integration using HA Bluetooth
sources such as ESPHome proxies. It produces area estimates and benefits from fixed
scanners assigned to actual areas. Do not assume it consumes the existing custom Pi
near/far scanner; an explicit HA-compatible adapter or separate proxy is needed.
The Docker-on-Mac HA deployment does not automatically expose the host Bluetooth
adapter. Fixed supported network BLE proxies avoid that dependency.

For the native Mac app, CoreBluetooth can observe permitted known advertisements
and RSSI. Room location requires fixed identifiable anchors mapped to rooms, smoothing,
calibration, competing-candidate handling and freshness limits. Cross-platform beacon
payload compatibility must be tested; do not assume every phone beacon is exposed
identically on macOS. A small explicit BLE beacon service is an option. Scanning a
phone alone only says laptop-near-phone, without an absolute room anchor.

Mac implementation is optional and requires front-loaded Bluetooth permission and
usage description. Preserve the stable app identity and existing microphone grants.
Initial support should be foreground/awake only; background/sleep behavior needs
separate validation. Default off; do not scan unknown household devices continuously.

A Bluetooth-advertising tag attached to a laptop is another option for fixed room
scanners to observe, without relying on the laptop app staying awake. This tracks
the tag/device, not necessarily the user. No purchase is required for the first
HA import/map iteration.

## Delivery checkpoints

1. Read-only HA registry sync, room/device review tray and editable schematic.
2. Character's acknowledged surface on the map; manual Person check-in and clear
   unknown state. Existing screen arrangement becomes a per-room editor.
3. One calibrated room-presence source in shadow, compared with explicit check-ins.
4. Optional native Mac beacon scanning and portable-screen room inheritance.
5. Opt-in room-aware speech/following after wrong-room and stale-source tests pass.

Private map/sensor data stays local and out of public commits. Default to current
estimates with short expiry; historical location retention needs a separate choice.
Tests use invented plans and sources. Include shared occupancy, phone-left-behind,
room-boundary oscillation, sleep/reconnect, floors, duplicate endpoints, HA renames,
unknown state, character handoff failure and forbidden audio routing.

## References

- [Home Assistant Areas](https://www.home-assistant.io/docs/organizing/areas/)
- [Home Assistant Floors](https://www.home-assistant.io/docs/organizing/floors/)
- [HA WebSocket API](https://developers.home-assistant.io/docs/api/websocket/)
- [Bermuda](https://github.com/agittins/bermuda)
- [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy/)
- [Apple CoreBluetooth scanning](https://developer.apple.com/documentation/corebluetooth/cbcentralmanager)

## Portal link

Set `web.home_assistant_url` to a stable, client-reachable HTTP(S) HA portal URL.
The dashboard exposes it after normal owner authentication. Defaults are empty;
there is no universal HA hostname, automatic credential transfer or iframe login.
URLs containing credentials, query parameters or fragments are rejected. HA owns
its own sign-in and permissions. This link is navigation, not an authenticated
registry-sync connection or proof of device reachability.
