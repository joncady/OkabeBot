# AI Hardware Lab — OkabeBot

A push-to-talk Codex companion with a talking pixel character and MCP tools for real hardware. Hold a button, speak, and release. Local speech recognition transcribes the recording; Codex can answer aloud, change expressions, show a picture, use a camera, or press a SwitchBot.

The default character is an original pixel-art interpretation of **Rintaro Okabe from Steins;Gate**: dark hair, lab coat, expressive eyes, and an audio-driven mouth. This is an unofficial fan project, with no affiliation or endorsement. The artwork is drawn in code; no anime frames or actor voice recordings are included. Pip, the original robot face, remains an option.

![Okabe character](docs/okabe.png)

## One controller, flexible hardware

| Setup | Controller | Display / camera / Bluetooth | Microphone / speaker / button |
| --- | --- | --- | --- |
| One Pi | Same capable Linux Pi | Local service | Local service |
| Multiple Pis | Mac or Linux computer | SSH to a Pi | SSH to another Pi |
| Hybrid | Mac, Linux computer, or capable Pi | Local or SSH | Local or SSH |

Each device endpoint independently selects `local` or `ssh`. Both use the same loopback HTTP protocol. SSH connections use your existing verified host keys; no hardware service needs an exposed network port.

The existing deployment uses a Mac controller and two legacy Pi Zero W/WH satellites. **The all-in-one ARM64 setup is an architectural option, not yet hardware-validated.** A Pi Zero cannot run this controller stack. Use a modern 64-bit Pi with sufficient RAM and supported dependencies for local Whisper and Codex CLI. Codex model inference still requires the OpenAI service; “local” refers to transcription, speech synthesis, and tool execution.

## Quick start

1. Install Python 3.10+, a signed-in [Codex CLI](https://github.com/openai/codex), and the platform speech dependencies: macOS `say`/`afconvert` are built in; Linux needs `espeak-ng` and `ffmpeg`.
2. Install the controller from this checkout:

   ```sh
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -e '.[voice]'
   cp examples/single-pi.json okabebot.local.json
   # Or copy examples/multi-pi.json for SSH-connected devices.
   ```

3. Configure and start the Pi services using [device setup](docs/devices.md). Edit `okabebot.local.json` with the matching ports and local/SSH endpoints. Relative paths resolve from the config file, so copy the example to the project root before editing.
4. Download the configured transcription model once, then start:

   ```sh
   okabebot-model
   okabebot
   # Alternative: okabebot --config /absolute/path/my-config.json
   ```

5. Open the loopback control URL printed in the terminal. It contains a private access token. Hold the hardware button while speaking, release to submit (20-second maximum). The page shows transcripts, tool activity, and any remaining approval prompts. Stop the controller with Ctrl-C.

The controller resumes its saved Codex chat. The button disarms while Codex works or speaks. A renewable lease disarms it if the controller disconnects. Recordings are deduplicated before submission; uncertain actions are not automatically replayed.

## Auto-approval

Hardware MCP tool calls are **automatically approved by default** in this voice controller. This includes physical button presses, camera capture, and audio recording when requested by Codex. The policy is limited to the `hardware-lab` server and the named `approvals.allowed_tools` list. It does not approve shell commands, file edits, other MCP servers, arbitrary forms, or explicit review denials.

To require manual confirmation, set:

```json
{
  "approvals": { "auto_approve_hardware": false }
}
```

Or keep auto-approval enabled and remove individual tools from `allowed_tools`. Restart the controller after editing configuration. Automatic decisions are shown in the control page. Unknown request formats fall back to manual approval. This setting belongs to this controller, not to every Codex chat or the desktop app.

## Make the character yours

Configuration is merged with defaults, so a small override is sufficient:

```json
{
  "character": {
    "name": "Okabe",
    "style": "okabe",
    "default_voice": "calm",
    "intensity": 0.6,
    "palette": {
      "background": "#101e25",
      "shell": "#accdc1",
      "accent": "#a5f4ce"
    }
  }
}
```

The control page’s **Character** selector switches between Okabe, Makise Kurisu, Pip, and your configuration default. It saves the selection in `state/profile.json`; both the controller and MCP process read it for subsequent turns. Changing characters starts a fresh chat on the next turn so the previous persona cannot override the new one; previous chats remain in Codex history. Switching is disabled during recording or a Codex turn. A saved voice override stays selected; otherwise Kurisu and Pip use the warm preset. Update the display Pi’s service and renderer files together when upgrading: older services do not recognize `kurisu`.

Set `style` to `pip`, `name` to `Pip`, and `persona` to a friendly robot description for the original robot. The `character.persona` text controls the conversational character independently of its drawing; current preferences are included with every voice turn, including resumed chats. The `shell` color applies to Pip's body. The character supports neutral, happy, curious, concerned, and excited emotions, with idle, listening, thinking, and speaking activities. Mouth movement follows the synthesized audio amplitude rather than phoneme-level lip sync.

Voice presets are `warm`, `calm`, and `robotic`. Map them to installed voices in `speech.mac_voices` or `speech.linux_voices`. `speech.engine: auto` selects macOS `say` or Linux eSpeak. These are generic system voices, not the character's actor. A voice selected through `set_character_voice` is saved in `state/character.json` and takes precedence over `default_voice`; remove that saved preference to use the config default again. Tool argument `voice: default` uses the selected voice (`pip` remains a compatibility alias).

The Codex instruction interprets “wave” as a happy face plus **one SwitchBot press**. A durable request ID prevents a retry from pressing again. Different physical gestures can be implemented by changing the instruction and tool adapter together.

## Response timing and voice engines

The control page reports transcription, first model message, total Codex turn,
and speech synthesis/stream timing. These overlap: total turn time includes
hardware calls and playback. Playback launch is a device-clock estimate, not an
acoustic measurement. Hardware RPC calls reuse per-process SSH tunnels and never
automatically replay failed actions. Restart the controller after a tunnel fails.

`speech.sync_lead_seconds` defaults to 0.5 seconds; increase it if audio and the
face drift. `transcription.beam_size` (1–5, default 5) and `codex.effort`
(`low`, `medium`, `high`; default `low`) allow latency/quality comparisons.

Local speech remains the default. Optional `openai` speech streams 24 kHz PCM to
the voice Pi while updating the mouth envelope. Update both Pi services and
include `pi/stream_audio.py` when upgrading. Streams are capped at 30 seconds;
an abandoned stream releases the speaker after a timeout. No automatic fallback
or replay occurs after partial playback.

To enable cloud voices, configure `OPENAI_API_KEY` in the controller service's
private environment and restart it. The web engine selector stays disabled until
a key is configured. Codex ChatGPT sign-in does not provide speech API access.
For the `okabebot` systemd user service, run
`python3 scripts/configure-cloud-voice.py` in a private terminal on the controller.
It prompts without echoing, saves the key in ignored `state/openai.env` with
permissions 600, configures the service, and restarts it. Keep that state
directory and service configuration on persistent storage for a live USB.
Do not put the key in configuration JSON, a command argument, or Git.

Cloud reply text is sent to OpenAI and billed through the API. Configure
`speech.cloud_model` and `speech.cloud_voices` (warm/calm/robotic) to choose the
model and voices. The default is `gpt-4o-mini-tts`, with coral/onyx/alloy voices.
These are synthetic voices, not the characters' actors. Cloud speech requires a
live API test before its sound quality and latency can be compared; local tests
only verify the streaming transport and error handling.

## MCP tools

Run `okabebot-mcp` as a stdio MCP server. The voice controller registers it automatically for its App Server connection. Other MCP clients can launch it with `OKABEBOT_CONFIG` pointing at an absolute config file.

| Area | Tools |
| --- | --- |
| SwitchBot | `get_bot_status`, `press_bot` |
| Screen | `display_message`, `display_image`, `clear_display`, `get_display_status`, `preview_display` |
| Camera | `capture_camera`, `record_camera` |
| Audio and button | `get_voice_status`, `get_button_events`, `record_audio`, `play_audio`, `speak` |
| Character | `character_speak`, `character_expression`, `list_character_voices`, `set_character_voice` |

Hardware is optional per operation: an unavailable camera or Bot makes that tool fail, not a substitute device act. The voice workflow needs both running services. The display service currently needs a graphical desktop session even if you only use its camera/Bluetooth tools.

For a Linux PC controller, remote control-page access, and live-USB persistence
limitations, see [Linux controller setup](docs/linux-controller.md).

## Development

```sh
pip install -e '.[dev]'
ruff check .
ruff format --check .
OKABEBOT_CONFIG=examples/single-pi.json python -m unittest discover -s tests -v
python -m build
```

Unit tests use mocks and do not actuate hardware. The separate `tests/*_smoke.py` scripts are opt-in live checks: some change the screen, capture media, or play speech. `mcp_smoke.py` only presses the Bot when explicitly passed `--press`.

- `okabebot/`: controller, MCP tools, configuration, speech, transport, approvals, and control page.
- `pi/`: Python 3.7-compatible hardware services and character renderers.
- `examples/`: public, credential-free topology/configuration examples.
- `tests/`: offline tests and explicitly invoked live checks.

Local configs (`*.local.json`), state, SSH keys, recordings, and transcripts are ignored. Keep private material outside source control. Hardware services bind only to loopback and trust local processes; they are not intended for untrusted multi-user hosts. The control page is loopback-only and token protected. For a remote controller, forward its port through SSH rather than exposing it publicly.

Code is MIT licensed. Bundled DejaVu fonts retain their own license in `okabebot/assets/LICENSE-DejaVu.txt`. Steins;Gate and its characters belong to their respective rights holders; the code license does not grant rights to those characters.
