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
