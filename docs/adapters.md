# Integration contracts

The controller owns interaction state, notification priority, sound policy and
hardware presentation. Providers own transport/authentication and return data.
No external title or notification body is interpreted as a tool instruction.

## Media providers

`okabebot.adapters.media.MediaSource` defines `read`, `status`, `begin` and `close`.
`read()` returns a `MediaSnapshot` with independent `music`, `video` and `status`
dictionaries. Only the background worker calls it; page snapshots never trigger
provider network reads. `status()` is cached health plus capabilities, including
`can_authenticate`, display `label`, and an `auth_hosts` allowlist. `begin()` is used only when that capability is true; both server and browser validate its HTTPS destination against the provider allowlist.

Register a factory in `MEDIA_FACTORIES` and choose its key in `spotify.source`
(the config key is retained for compatibility). The factory receives the state
directory and settings. Configuration validation uses this same registry. Cast
and Spotify Web API are built-ins. A new provider doesn't require bridge branches,
new drawing code or changes to the browser's notification policy.

Video fields: `app`, `title`, `state` (`PLAYING`, `PAUSED`, `BUFFERING`, `IDLE`),
`content_id`, `position`, `duration`, `playback_rate`, `stream_type`, `updated_at`.
Use `None` for missing metadata; do not invent a title or fabricate a timeline.
Content IDs exposed to callers must not contain signed URLs or credentials.
Cast hashes URL IDs internally. Keep useful metadata between callbacks; clear it
on explicit stop/disconnect. `updated_at` anchors a reported position, not the
last time the coordinator happened to inspect it.

Cast snapshots are copied under its callback lock so app identity and media state
cannot race across a snapshot. Provider read exceptions are isolated and retried;
providers should report disconnection explicitly rather than retaining stale
playback forever. Close connections/workers when the controller shuts down.
`/media/connect` is the canonical auth route; `/spotify/connect` and the JSON
`spotify` status field remain aliases for existing clients. New clients use `media`.

## Notification providers

`okabebot.adapters.notifications.NotificationAdapter` has `name`, `enabled(context)`
and `poll(context)`. The context supplies `settings`, durable `state`, and `inbox`.
The GitHub and ICS implementations live in separate modules. Add an instance to
`BUILTIN_ADAPTERS`, or pass an adapter collection to `Sources` for another host.
Add its settings to the validated config defaults when exposing it through JSON.
`PollingAdapter(name, callback)` is a small convenience for simple providers.
Use its optional `setting` argument when separate monitors share one enable setting,
as GitHub inbox/deployment and workflow-check monitors do.

Providers call `context.inbox.publish(...)` with a stable dedupe key and optional
expiry. Source IDs are lowercase identifiers, at most 30 characters; unknown
sources get the generic icon. The coordinator persists checkpoints and isolates
one provider's failure from the others. Credentials belong in private environment
or state files. Return generic health errors without feed URLs or provider tokens.

Publish normalized events, not rendering instructions. Use `audio` (`default`,
`silent`, `chime`), priority and optional `group_key`/`group_title` when appropriate;
the queue and presenter own delivery. For incoming webhooks, use the existing
publish-only `/notifications` credential. A provider must validate the upstream
signature before converting an external webhook into a trusted event.

## Content enrichment and hardware

Title extraction returns the high-level contract in [content reactions](content-reactions.md).
League context is carried alongside format, sport and participants. The team
resolver validates identities and optional Wikidata league membership; network
failures leave literal title labels available. Rendering consumes the resulting
plan and local asset keys, never a provider API response.

Device transport is independent: each display/voice endpoint uses local loopback
or verified SSH with the same RPC operations. Failed physical actions are never
replayed automatically. The Pi services remain Python 3.7 compatible; controller
providers target Python 3.10+.

Before adding a provider, test normalized output, missing/partial metadata,
stop/disconnect, failure recovery, duplicate events, resource cleanup and an
unrelated provider continuing to work. Use fake providers for contract tests;
live tests should identify the exact app/device and what metadata it exposes.

## Media identity and logo assets

The Pi reads `pi/assets/media-apps.json` for normalized display-name aliases.
Override the complete aliases dictionary with ignored `pi/media-apps.local.json`;
restart the display service after editing. Unknown apps retain the generic TV icon.
This is a display fallback: provider app IDs should be preferred when available.

To use an actual Wikipedia logo, select its exact File: title from the app article
and run `python scripts/fetch-app-logo.py youtube 'File:Your chosen logo.svg'`.
The controller fetches through Wikipedia's image API, records file provenance and
rights, and caches a PNG in ignored `pi/assets/app-logos/`. Review the result and
copy that folder to the Pi. The renderer loads it locally and falls back to its
pixel icon if unavailable. No runtime network calls or downloaded logos ship in
this repository; check each file's usage terms before redistribution.

Sports identity and crest discovery use the existing on-demand Wikidata/Wikipedia
resolver. Team registries and downloaded crests are local data, not required
install assets. An optional legacy `okabebot/assets/teams.local.json` can supply
aliases, but new installations do not need one.

## Local speech workers

The controller accepts any private Unix-socket worker through `speech.engine: local`
and `speech.local_socket`. Configure its argv in `speech.worker_command` for the
supervisor to launch and restart it. The command runs from the configuration
directory; no shell interpolation occurs. Keep model packages in that worker's
environment. The controller and device protocol do not depend on MLX or Qwen.

Each connection carries one newline-terminated JSON request. A speech request has
`text`, `character`, `emotion`, and `voice`. Reply with big-endian unsigned 32-bit
length-prefixed frames of mono PCM16 little-endian audio at 24 kHz. Frames must be
even, at most 48,000 bytes; total audio is limited to 30 seconds. A zero-length
frame marks successful completion. Close an incomplete stream on failure; clients
abort rather than replay it. Preserve audio boundaries across frames and bound
requests to 600 text characters. The Qwen example currently uses character
references and does not implement emotion/preset changes.

For `{"op":"status"}`, return one length-prefixed UTF-8 JSON frame (at most
8192 bytes), then the zero frame, with `ready`, `characters`, and `sample_rate`.
Do not report readiness before model/reference warm-up finishes. Create the socket
with mode 0600 and never replace an endpoint owned by a live worker. Workers should
exit if their supervisor dies; the example watches `OKABEBOT_PARENT_PID`.
This makes controller and model failure recovery independent. Speech references,
model caches, credentials and generated recordings are private installation data.

### Voice tools and controller state

MCP read tools project only relevant fields from the authenticated local controller
API (`controller_tools.py`); they do not return transcripts or credentials. Focus
mutations call the same endpoints as the dashboard. Notifications use the existing
Inbox store. Calendar range reads reuse `calendar_feed.load_calendar` and expand
recurrences without scheduling reminders or mutating the inbox. Date ranges have
an exclusive end and a 366-day expansion bound; results indicate truncation.
Provider text remains untrusted data. Read failures must not be reported as an
empty successful schedule. Physical actions are never automatically replayed.

`Application.execute(path, data)` is the shared mutation boundary for existing
HTTP controls and MCP wrappers: volume, focus, notification policy/dismissal,
reminders, agenda cards, device discovery, and explicit Echo speech. Add validation
here or in its provider/domain objects, not separately in an MCP wrapper and UI.
MCP calls the controller API through the private control file. A controller timeout
is an uncertain result, not permission to repeat a physical/audio action. Reminders
are the exception with explicit durable request-ID deduplication. No new pollers
are created by these tools.


## Companion destinations

`surface_registry.Registry` owns persistent browser discovery, approval, name and
layout state. `Surfaces` owns the single character and acknowledged transfer.
Callers use `get_companion_locations` / `move_companion(location_id)` or the shared
HTTP application operation; they do not decide credentials, pixel offsets or
speaker policy. `pi` and `cast` are configured adapters; `browser` and `mac` are
registered device instances. Names and positions come from the registry, not
user text interpreted as an executable URL. Worker tool schemas refresh location
IDs/labels each turn and prefix caches include the schema to avoid stale IDs.

A new surface must implement render-ready, entered/departed acknowledgements,
identity-scoped heartbeat and close behavior. Prepare failures keep the origin
visible. Only an approved active screen may submit bounded user-held WAV capture;
this uses the ordinary clip ledger, busy gate and tool policy, without controller
credentials. Add adapters through that contract, and verify background visibility
semantics instead of assuming every browser behaves like a TV receiver.


Reply audio is a separate location capability (`audio_target`), resolved once at
speech start. `AudioHub` relays bounded PCM to an enabled paired device session;
`BrowserStream` implements the existing stream start/chunk/end/abort contract.
The browser cannot submit relay PCM or gain full controller authority. A future
speaker adapter should preserve acknowledged completion and no automatic replay
on uncertain playback. OS Bluetooth routing is not a new server-side adapter.

Alexa voice history uses the narrow `/alexa/events` adapter: entity ID, event
timestamp and an allowlisted command string. It maps only to welcome or the
shared location move interface; provider text is never an arbitrary tool prompt.
The separate integration token, allowlist, 90-second freshness check and durable
event claim are enforced again at the controller boundary. See [Alexa setup](alexa.md#explicit-voice-event-bridge).
