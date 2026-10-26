# Codex completion cards

Codex's `notify` hook passes one JSON argument on `agent-turn-complete`.
OkabeBot forwards a durable notification to the running controller: the session
name, “Codex finished. Ready to review on your laptop.” and a short two-tone
chime on the Voice-kit speaker. No TTS, prompt, response text or tool output is
sent. Notifications expire after five minutes and duplicate thread/turn IDs are
ignored. A card remains visible for 15 seconds; notification history retains it.

Create a private settings file, outside Git, with absolute paths:

```json
{
  "url": "http://YOUR_CONTROLLER:8768/notifications",
  "token_file": "/absolute/path/to/state/notification-token",
  "codex_home": "/absolute/path/to/.codex",
  "previous_notify": [],
  "exclude_clients": ["hardware_lab_ptt"],
  "exclude_threads": []
}
```

Use the controller's configured state directory for `notification-token`; this
publish-only token survives controller restarts. Keep the file private. The
adapter reads only the matching thread title from Codex's local state database;
if unavailable, it falls back to the project directory name. The database is a
best-effort local lookup, not a public stable API. You can also supply a
`session-name` in a manually emitted event.

In the **top level** of `~/.codex/config.toml`:

```toml
notify = ["/path/to/python3", "/path/to/OkabeBot/scripts/notify-codex.py", "--settings", "/path/to/private/settings.json"]
```

If `notify` already exists, move its command array into `previous_notify` before
replacing it: the adapter invokes that command with the original event even if
the controller is unavailable. It never logs the event contents. Restart the
Codex client to load configuration. Client support must be checked with a real
completed turn; a direct script test proves delivery only. The voice bridge's
own `hardware_lab_ptt` turns are excluded because they already speak responses.

Test the complete notification path without running a model:

```sh
python3 scripts/notify-codex.py --settings /path/to/private/settings.json \
  '{"type":"agent-turn-complete","thread-id":"test","turn-id":"unique-test-id","session-name":"Completion test"}'
```

Notification publishers may use `audio: "chime"`, `"silent"` or `"default"`.
`chime` and `silent` explicitly suppress TTS regardless of priority;
`default` preserves the configured important-notification speech policy.
There is no arbitrary sound-file or remote-audio input.

Official reference: [Codex advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced#notifications).

Completion chimes use the same **Dev → Speaker volume** mixer as speech.
`notifications.chime_gain` (0–1, default 0.25) additionally scales the generated
chime waveform; 0 silences the chime while preserving the visual card. This is
independent of TTS priority and applies after restarting the controller.
