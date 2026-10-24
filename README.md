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

Set `style` to `pip`, `name` to `Pip`, and `persona` to a friendly robot description for the original robot. The `character.persona` text controls the conversational character independently of its drawing; current preferences are included with every voice turn, including resumed chats. The `shell` color applies to Pip's body. The character supports neutral, happy, curious, concerned, and excited emotions, with idle, listening, thinking, and speaking activities. Mouth movement follows the synthesized audio amplitude rather than phoneme-level lip sync.

Voice presets are `warm`, `calm`, and `robotic`. Map them to installed voices in `speech.mac_voices` or `speech.linux_voices`. `speech.engine: auto` selects macOS `say` or Linux eSpeak. These are generic system voices, not the character's actor. A voice selected through `set_character_voice` is saved in `state/character.json` and takes precedence over `default_voice`; remove that saved preference to use the config default again. Tool argument `voice: default` uses the selected voice (`pip` remains a compatibility alias).

The Codex instruction interprets “wave” as a happy face plus **one SwitchBot press**. A durable request ID prevents a retry from pressing again. Different physical gestures can be implemented by changing the instruction and tool adapter together.

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
