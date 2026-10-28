# Local conversation backend

The controller can use a warm local MLX model instead of Codex for button-held
conversation and explicit tool commands. The Pi remains a microphone/button,
speaker/display and Bluetooth satellite; model inference runs on the Apple Silicon
controller. This backend is optional and defaults to Codex for existing installs.

Create a separate Python environment on the Mac and install `mlx-lm`. Keep it
outside protected Documents/Desktop folders for unattended startup, beside the
installed controller. In private configuration set:

```json
{
  "conversation": {
    "backend": "local",
    "model": "mlx-community/Qwen3-4B-Instruct-2507-4bit",
    "command": ["/absolute/path/to/chat-venv/bin/python", "-m", "okabebot.local_worker"]
  }
}
```

The worker loads once, warms inference at controller startup, and caches fixed
persona/tool prefixes. Persona changes rebuild that cache; recent casual chat
context is bounded. MLX dependencies do not replace the controller or voice-worker
environments. Linux/Dell needs a different inference worker; this implementation
is specifically MLX on Apple Silicon, not a claim of Pi inference support.

The local adapter reads existing MCP tool schemas and calls the same server
functions and application operations as Codex. Tool results use short deterministic
acknowledgements, so execution does not wait for a second generation. Read-only
queries are available directly; mutations require existing approval allowlisting,
an explicit target in the current utterance, and schema validation. It does not
resolve ambiguous pronouns from chat history. Volume requires an exact percentage.
Reminder/SwitchBot request IDs are assigned by the application rather than model.
No shell, filesystem, camera capture, ambient recording, arbitrary Home Assistant
service, or automatic Codex fallback is exposed to the local model. Unsupported
requests ask for clarification. These conservative guards are not a general NLU
accuracy guarantee; test new intents before expanding the allowlist.

The existing durable clip ledger prevents replay after an uncertain turn. Actions
are not retried on timeout. Stop cancels pending generation results before dispatch;
it cannot undo an action already sent. Worker failure disables button processing
until controller restart rather than falling back and possibly repeating an action.

To return to Codex, set `conversation.backend` to `codex` and restart the controller.
Existing Codex sign-in/history remains separate. The dashboard identifies the active
backend; its legacy `codex_alive` state key covers either backend's worker process.

## Synthetic full-path validation

An authenticated controller-only POST to `/conversation/test-clip` accepts a
`clip_id` beginning `test-` (8–95 subsequent letters/digits/-/_) and base64 PCM WAV
up to 700 KB. It rejects busy/recording turns and requires the full dashboard token;
notification/arrival credentials cannot submit commands. It invokes the real clip
ledger, Whisper, configured backend and speaker path. Reuse the same clip ID after
an uncertain response. This route intentionally performs actual tools and speech;
do not use it for a physical-action test unless those effects are authorized.
It bypasses the physical button, recording and Pi-to-controller audio upload.

## Isolated regression suite

Run the portable suite with `python -m unittest discover -s tests`. Its full-path
test uses deterministic ASR/model/PCM doubles, real clip handling, validation and
application state. It verifies one dispatch per clip and byte-preserving speech
buffering; it is not a model-quality or acoustic-quality test.

With a configured local worker and model cache, run real inference separately:

```sh
python scripts/local-regression.py \
  --fixtures tests/fixtures/local_commands.json \
  --output .local/regression.json
```

Set `OKABEBOT_CONFIG` to the private configuration if necessary. Add `--speech` to
generate real voice-worker PCM and inspect nonzero signal, duration and buffering;
the PCM is discarded. Add `--audio` on macOS to synthesize input with `say` and
exercise real Whisper/clip handling. This bypasses button capture/upload and does
not play audio or measure perceived pronunciation. All tool dispatch uses isolated
temporary application state and simulated external devices, never production
SwitchBot, Spotify, Echo or speaker calls. Reports contain synthetic test text.

`--case ID` selects cases. `--max-action-seconds N` adds an explicit latency budget.
`--worker-command 'python -m okabebot.http_worker'` and `--model NAME` permit
isolated comparisons without changing private configuration. The HTTP worker
requires a separately running loopback inference server and never retries calls.
Its structured responses still pass the same application-owned validation and
request-ID rules. It is optional and does not replace the deployed worker.


## Per-character speech routing

A local Qwen worker reports the characters for which it has private reference
material. Choosing another character no longer makes the entire voice interface
unavailable. `speech.local_fallback` defaults to `system`: missing references use
macOS `say` or Linux eSpeak locally. Linux also needs the existing ffmpeg
normalization dependency. Set it to `none` to require a dedicated worker reference
for every character. No fallback calls a cloud service or changes the saved
speech-engine selection.

The current installed worker has references for Okabe, Kurisu, Sonic and Pip.
Sonic uses private isolated English dialogue; Pip uses an original synthetic
reference. Both passed generated-sample transcription checks. System fallback
remains available for future characters without references. Switching between
configured characters does not restart the worker. The
speaker route, volume, character appearance and personality remain independent
of synthesis-backend choice. The dev panel reports the effective fallback;
the engine selector continues to show the user's configured backend.

System speech can produce the same bounded 24 kHz mono PCM stream used by browser,
Pi and Beam sinks; it synthesizes a local file before streaming chunks. Existing
Pi system output retains its WAV path. Missing references are distinct from a
worker outage: a disconnected worker is still reported as unavailable, rather
than silently changing a supported character's voice. Worker capability caching
is invalidated when its socket identity changes on restart.
