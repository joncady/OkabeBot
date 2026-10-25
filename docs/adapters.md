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
