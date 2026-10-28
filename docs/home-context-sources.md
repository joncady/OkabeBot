# Home context sources and guided discovery

This is a capability plan, not a household inventory or trial report. Existing
Amadeus permissions do not automatically authorize additional source categories.
See [deployment](deployment.md) for installed roles and [Amadeus](amadeus.md) for
consent boundaries. Discovery, integration pairing, observation consent and action
permission are separate stages.

## Next source priorities

| Source | Useful output | Boundary / acceptance |
| --- | --- | --- |
| Weather | Morning brief: rain window, outdoor temperature, useful preparation | Reuse a configured weather entity/forecast; show forecast age. New installation: Met.no is free without an API key but uses cloud/location data. No inference from stale forecasts. |
| Room temperature | Sustained hot/cold overnight card | Room mapping, units, user-chosen range, dwell time, hysteresis and cooldown. Distinguish ambient air, device/battery/body temperature and appliance setpoints. Not a safety-critical alarm. |
| Battery/connectivity | One grouped maintenance card with reconnect/charge instructions | Provider-reported battery semantics; explicit expected-online policy and grace period. Sleeping device or missing update is not proof of battery failure. Do not automatically reboot or reconnect. |
| Appliance cycle/errors | Laundry finished, elapsed waiting time, actionable fault | Native LG ThinQ entities/events; internet/vendor cloud required. Start observation-only. Never start heating/cooking or change appliance settings from an observation. Deduplicate reconnect snapshots and require a real transition/event. |
| Media players | Room activity and selected context | Read HA media state/title only where reported; normalize with existing Cast/Spotify sources and deduplicate one physical endpoint. Do not infer personal watching or preferences. |
| Printer | Ink/toner, offline warning, job state where supported | Local IPP; capabilities vary. A saved OS queue is not discovery. Do not submit a print job as a reachability check. |
| Phone/router presence | Home/away/unknown household context | Link phone tracker to a Person; validate actual departure/return. Occupancy aggregation is separate from identity. Remote phone updates need a reachable HA endpoint or suitable VPN. |
| NFC/QR | Explicit check-in, focus start, call character here, recipe/workflow cue | User-initiated tag event mapped to an allowlisted shared action; tag IDs are identifiers, not credentials. No embedded owner tokens. |

Start with weather, device-health grouping and appliance-finished cards. Keep
speech optional and share quiet hours, attention budgets and deduplication with
other notifications. Expanded historical observation requires private onboarding
permissions and bounded schemas; adding a notification is not permission to retain
an appliance or room-activity history.

## Find my devices: proposed interface

A single action should offer a bounded, local discovery session and then a text
conversation to confirm the map. It is not continuous household surveillance.

1. Read HA's configured/discovered integrations, entity/device/area registries and
   existing OkabeBot destinations. Exclude credentials and precise location.
2. On the selected LAN interface, browse mDNS/SSDP. Use router/DHCP inventory when
   authorized; optionally perform bounded reachability checks on the confirmed local
   subnet. Do not assume `/24`, probe the internet or enroll everything automatically.
3. Read BLE advertisements through a supported scanner/proxy only when selected.
   BLE is not Bluetooth Classic. A Tuya Zigbee gateway is not a generic BLE scanner.
   Docker on macOS does not automatically inherit host multicast or Bluetooth.
4. Merge evidence using provider IDs/advertised service identities, retaining
   provenance and confidence. Names/IPs/RSSI alone are not stable identity or room.
5. Ask: “Which room?”, “Which is the same physical TV/speaker?”, “Who owns this
   phone?”, “Expected to stay online?”, “Observe, control, or ignore?” Only ask for
   capabilities relevant to the selected device.
6. Save the approved map privately, with ignored devices, observation permissions,
   action permissions and per-device health policy. Preview changes before saving.
   Surface permission does not imply speaker/control permission.
7. Report paired, discovered-unpaired, unavailable and unsupported separately.
   Rescan should propose a diff, not silently replace addresses or source bindings.

The dashboard scan action and persistent map schema are backlog work. The existing
setup skill now provides the conversational workflow; it should use available
protocol tools rather than claiming a universal scanner exists.

## NFC / QR first experiment

Use the official Companion app's Tags page to write an NFC sticker or scan a QR
containing `https://www.home-assistant.io/tag/<random-id>`. Both generate
`tag_scanned`. Map a tag plus an approved scanner to a named shared action, such as
calling the character to a configured location or starting a focus session.
Printed QR works before buying NFC hardware. Tags must never contain dashboard
keys; require normal authenticated app access. Remote use needs HA connectivity.
A tag scan identifies a scanner, not necessarily a person or completed habit.

## Official references

- [Weather / Met.no](https://www.home-assistant.io/integrations/met/)
- [LG ThinQ](https://www.home-assistant.io/integrations/lg_thinq/)
- [Local printer IPP](https://www.home-assistant.io/integrations/ipp/)
- [Person and tracker precedence](https://www.home-assistant.io/integrations/person/)
- [Tags](https://www.home-assistant.io/integrations/tag/) and [phone NFC/QR routing](https://companion.home-assistant.io/docs/integrations/universal-links/)
- [Zeroconf discovery](https://www.home-assistant.io/integrations/zeroconf/), [Nmap limitations](https://www.home-assistant.io/integrations/nmap_tracker/), [BLE/proxies](https://www.home-assistant.io/integrations/bluetooth/)
- [Cast](https://www.home-assistant.io/integrations/cast/) and [Sonos](https://www.home-assistant.io/integrations/sonos/) for richer native player state
