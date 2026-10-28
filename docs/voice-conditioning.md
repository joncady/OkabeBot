# Local character voice conditioning

The Mac speech worker uses the existing Qwen3-TTS Base model through MLX-Audio.
References and manifests stay in private local state; no reference audio or
participant listening results belong in Git or public reports. This is reference
conditioning, not a newly trained model or supervised fine-tune.

## One manifest, two modes

Each character selects a private audio file and a conditioning mode:

- `speaker_only`: omit `text`. The worker passes `ref_text=None`, extracting speaker
  identity without supplying reference speech tokens. English output is explicit.
- `icl` (the backward-compatible default): provide `audio` and its exact `text`.
  This includes reference speech and transcript in conditioning.

```json
{
  "example_character": {
    "audio": "private-reference.wav",
    "mode": "speaker_only",
    "temperature": 0.3
  },
  "another_character": {
    "audio": "another-reference.wav",
    "text": "The exact reference transcript."
  }
}
```

Audio paths resolve against the manifest directory. Optional `temperature` is
bounded to 0–1; absent values preserve the model's default. A speaker-only entry
with a transcript is rejected rather than silently selecting ICL. Reference files
must exist before the worker loads. Generation uses the same streaming PCM path
for every character; no actor-specific branches or separate experimental worker
are required. The local status response identifies each character's loaded mode
without exposing audio paths or transcripts.

The installed deployment selects speaker-only Japanese references for Okabe and
Kurisu; Pip and Sonic retain their existing ICL references. Startup warms every
configured character. Changing the manifest requires restarting the supervised
voice worker, then checking readiness and loaded modes. It does not require
restarting the controller or changing any speaker volume. The supervisor also
respects the existing speech lock for direct tool callers, so a single-threaded
worker is not mistaken for unhealthy while it is producing audio.

## Quality and maintenance

Speaker-only conditioning does not guarantee accent removal or independent
control of pitch, phonemes or tone. Keep a private rollback manifest and evaluate
short and longer English speech before expanding a rollout. Audio received and
played by a browser is not proof of audible quality at its physical speaker.

Use `scripts/local-regression.py` and the isolated streaming/character-switching
regressions for maintenance. Superseded A/B helpers and generated comparison audio
are not part of the runtime. Keep reusable reference inputs separate from test
outputs, and remove private experiments when no longer needed. Do not promote a
reference merely because an experiment generated successfully.

References: [Qwen3-TTS cloning modes](https://github.com/QwenLM/Qwen3-TTS) and
[MLX-Audio Qwen implementation](https://github.com/Blaizzy/mlx-audio/tree/main/mlx_audio/tts/models/qwen3_tts).
