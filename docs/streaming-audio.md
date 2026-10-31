# Shared incremental speech delivery

This design separates generation, delivery and playback. Receiving the last audio
byte is not proof that a person heard the reply. Model/tool generation and speech
output have separate timing boundaries; no generic filler is played to hide work.

## Research and design choice

A streaming pipeline overlaps work rather than waiting for a finished file at each
stage. Sentence-sized text segments preserve useful prosody when a provider does
not produce reliable incremental codec output. LiveKit documents a sentence
adapter for non-streaming TTS and segment-aware interruption handling:
[voice pipeline nodes](https://docs.livekit.io/agents/logic/nodes/).

[MLX Audio](https://github.com/Blaizzy/mlx-audio) and
[Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) expose streaming generation. That
capability does not prove equivalent sound for every reference-conditioning mode.
The installed speaker-identity path deliberately decodes complete clauses to
avoid previously observed incremental-codec artifacts. Deliver those clauses as
soon as they are ready; do not change voice references, model, sampling settings
or the codec decoder as part of a transport optimization.

Android's [AudioTrack](https://developer.android.com/reference/android/media/AudioTrack)
provides MODE_STREAM, blocking writes, playback-head position and underrun counts.
Use a bounded writer off the UI thread and confirm drain with the playback clock.
Do not report completion when write() merely accepts bytes. Low-latency flags are
not a substitute for enough buffering and supported output sample rates.

The shared browser sink schedules decoded PCM on the AudioContext clock using
[AudioBufferSourceNode](https://developer.mozilla.org/en-US/docs/Web/API/AudioBufferSourceNode).
It uses a short initial jitter buffer and schedules consecutive buffers without
restarting playback for every sentence. An AudioWorklet/ring buffer can be added
if measured main-thread stalls justify its additional lifecycle complexity.

## Common contract

- Format: mono, signed 16-bit little-endian PCM, 24,000 samples/second.
- Lifecycle: start → ordered chunk events → end → playback completion; abort is
  terminal at any point. Each stream has a unique ID and binds to one receiver
  session and destination. A changed session cannot resume an old stream.
- The relay adds cursor ordering and chunk sequence. Legacy consumers can use
  cursors; new consumers also validate sequence and format when present.
- Queue sizes, audio duration and lifetime are bounded. Backpressure pauses the
  producer rather than dropping unconsumed speech. Expired, revoked or aborted
  streams cannot be replayed by reconnecting with the same device credential.
- Startup buffering is sink policy, not a voice-model setting. A short first PCM
  packet can be released before the normal packet size fills. Buffer enough for
  smooth output; report underruns instead of silently claiming low latency.
- Gain uses the existing destination setting. Do not change hardware volume or
  reroute a failed reply to a different room.
- Mouth animation follows actual local playback timing, including buffering,
  interruption and drain. Server generation status is not a speaking clock.
- Never retry a partly heard reply automatically. A failed or uncertain action/tool
  is also never replayed as an audio recovery mechanism.

## Platform capability matrix

| Destination | Delivery path | Policy / remaining acceptance |
| --- | --- | --- |
| Android native | Same paired AudioHub events, native AudioTrack | Incremental opt-in for capable APK; existing native WAV fallback remains for old APKs. Physical listening check required. |
| Mac app | Shared companion page and Web Audio PCM sink | Short startup buffering, explicit cancellation and actual-drain acknowledgment; OS sleep/wake remains a physical check. |
| Mobile browser | Same Web Audio sink over trusted HTTPS | Gesture/audio permission remains front-loaded. Browser background scheduling is best-effort; no background mic capture. |
| Cast/TV | Same Web Audio sink | Existing complete-buffer mode remains the conservative fallback. An explicit startup-buffer event can request incremental playback; TV quality needs a dedicated test. |
| Pi reply speaker | Existing PCM RPC → aplay | Generate ahead, short initial packet, bounded later packets and acknowledged drain. Preserve volume and announcement fallback. |
| Pi prepared announcements | Existing uploaded WAV path | Keep the reliable prepared-file mode; streaming replies do not silently change announcement timing. |
| Sonos Beam overlay | Existing short-lived WAV URL / audioClip | Buffered capability; no claim of arbitrary PCM streaming or matching latency. Preserve ducking/overlay behavior. |
| Alexa custom skill | Existing signed media assets / skill response | Buffered conversational capability; separate protocol investigation required. |

[Sonos audioClip](https://docs.sonos.com/reference/audioclip-loadaudioclip-playerid)
loads audio through a URL. Its behavior is not the native PCM queue contract.
Alexa distinguishes [short response audio from long-form AudioPlayer streaming](https://developer.amazon.com/en-GB/docs/alexa/custom-skills/add-audio.html).
[AudioPlayer](https://developer.amazon.com/en-US/docs/alexa/custom-skills/audioplayer-interface-reference.html)
is not a drop-in replacement for a conversational custom-voice response. These
adapters should declare their limitations rather than pretending to stream PCM.

## Initial implementation boundary

The first increment removes mobile whole-WAV waiting and hardens shared sinks.
It does not yet stream the language model's tokens, transcribe during capture,
change tool authority, or claim subsecond first speech. Read-only mobile tools,
private preference consent and destination/session checks remain in force.

Old mobile clients keep the WAV request/response. A capable native client opts in
with `playback_mode: "stream"`; the response identifies the accepted stream. First
PCM can race the response, so completion/failure tracking must handle either
ordering. Async errors travel as abort/failure, never as a replayed HTTP request.

Operational timings contain durations and stream state only. They exclude speech
content and health/preferences. Private trials and reference audio stay out of
commits, issues and review descriptions.

## Validation and follow-up

Use invented PCM for deterministic ordering, early-delivery, jitter, bounds,
backpressure, revocation, destination changes and cancellation tests. Android
emulator completion checks use silent PCM and do not prove physical audibility.

The silent local probe never records or plays sound:

```sh
PYTHONPATH=. python scripts/benchmark-streaming.py --config /path/to/private-config.json
```

It reports first PCM and complete PCM for the same generation. The difference is
only the whole-file wait potentially avoided; it excludes network, model routing,
transcription, device buffering and the actual first audible sample. Keep trial
outputs in ignored private state.

Next checkpoints: phone streaming/switch-app listening, Mac playback/sleep, Pi
smoothness, then TV incremental-preview quality. Preserve buffered fallbacks until
those checks pass. Subsequent work can overlap model text and TTS at sentence
boundaries, evaluate a true streaming codec against the quality baseline, add
capability-specific Beam/Alexa experiments, and adapt buffers using real underrun
measurements. Do not promise a hardware-independent latency target.


The current MLX speaker-only path also reloads reference audio and recomputes
speaker embeddings for each clause. Upstream Qwen documents reusable clone prompts,
but the installed MLX API does not expose the same prepared-prompt interface.
Conditioning-cache work therefore needs a versioned adapter or upstream support,
not arbitrary generation-KV reuse. Track further work and physical acceptance in
[voice synthesis issue #64](https://github.com/joncady/OkabeBot/issues/64).
