# Linux controller

The controller can run on an x86-64 Linux computer while the display/camera and
voice/button services remain on separate Pis. Transcription, speech synthesis,
and MCP execution run on the controller; Codex inference requires Internet access.

## Install and start

On Ubuntu, install the system dependencies:

```sh
sudo apt-get update
sudo apt-get install -y python3-venv espeak-ng ffmpeg git openssh-client
python3 -m venv .venv
.venv/bin/pip install -e '.[voice,cast,notifications]'
```

Install and sign into the [Codex CLI](https://developers.openai.com/codex/cli/).
For a remote machine, `codex login --device-auth` provides a browser sign-in flow.
Run `codex login status` to confirm completion on the controller itself.

Create `okabebot.local.json` using the README's device configuration. Set
`codex.binary` to an installed Linux executable and `codex.cwd` to the project.
Authorize the controller's SSH public key on each Pi and verify their host keys.
Do not copy a macOS executable path or assume the Mac's SSH setup exists on Linux.

After OS prerequisites, private configuration and account/SSH setup, bootstrap
and start from the checkout with one command:

```sh
./scripts/start-linux.sh --bootstrap
```

This creates `.venv` if needed, installs the voice/Cast/calendar extras, downloads
the configured model once, and starts the controller. It does not install OS
packages, authorize devices, sign in, or change disk/boot configuration. Downloads
need Internet access. Existing private config and state are preserved.

For subsequent starts and read-only diagnosis:

```sh
./scripts/start-linux.sh
./scripts/start-linux.sh --check
# Alternate config and bridge arguments:
./scripts/start-linux.sh /path/controller.local.json -- --port 8768
```

Set `OKABEBOT_PYTHON` for an existing virtual environment. The launcher runs in
the foreground; Ctrl+C stops it. `okabebot-doctor` checks dependencies and writable
state, with `--devices` adding read-only device status probes. It doesn't prove
account sign-in, speech-model readiness or a successful physical interaction.

Linux speech uses eSpeak NG rather than the Mac's voices. Configure
`speech.linux_voices` to change the available presets.

Only one controller should handle the hardware button at a time. Stop the old
controller before starting its replacement. Test device status, speech/display,
and finally a button-held recording before treating a migration as complete.

## Remote control page

The web page binds to loopback. From another computer, forward its port:

```sh
ssh -N -L 8768:127.0.0.1:8768 USER@CONTROLLER
```

Port 8768 must be free on that computer. Open the complete URL printed by the
controller, including its private token. A restarted controller generates a new
URL. The hardware controller keeps running without this browser tunnel.

## Live USB versus an installed system

Ubuntu's **Try Ubuntu** session normally discards installed packages, SSH server
configuration, home-directory changes, and service definitions on reboot.
Saving an application bundle on a writable USB partition does not make the whole
operating system persistent. A launcher stored there must be run locally after
boot to restore the temporary environment; SSH cannot perform that initial step
until the SSH server and authorization have been restored.

A custom live-USB bundle must preserve the app, Python environment, model,
configuration, hardware keys, trusted host keys, Codex executable and login/state.
Python environments can contain absolute paths and depend on system libraries;
such a bundle is tied to its original OS, architecture, username, and paths.
Keep bundles containing credentials private and outside Git. Reconnect Wi-Fi
before starting. Shut down normally before removing the USB.

A cache of `.deb` files is not proof that every dependency is available offline.
If restoring packages fails, reconnect to the Internet and run on the controller:

```sh
sudo apt-get update
sudo apt-get install -y openssh-server python3-venv espeak-ng ffmpeg git
```

Then rerun the bundle's own restore/start script. Inspect actual errors if this
fails; do not assume every download error is a missing dependency. A newly
restored SSH server can have a different host key: verify it before replacing an
existing trusted entry.

The repository launcher above is not a live-session restoration script. The
machine-specific USB bundle must provide that behavior separately. A normal
Linux installation preserves packages and SSH configuration and can run the
controller as a service; it does not require erasing Windows if installed on a
separate drive or alongside Windows.

## Validation so far

An i7-6700HQ Dell with 8 GB RAM running Ubuntu from a live USB passed the 37
unit tests, exposed all 18 MCP tools, and completed a button-to-Codex-to-hardware
interaction. CPU `base.en` int8 transcription took about 1.3 seconds for a
10-second synthetic speech clip. This is one smoke test, not a general accuracy
or latency benchmark. Slow USB storage noticeably increased startup time.

## Moving the current Mac setup to a Dell

Recreate the environment on Linux; do not copy the Mac virtual environment.
Preserve the private configuration, inbox/profile/model cache and chosen provider
state separately from Git. Replace Mac executable paths with Linux paths, verify
Codex and GitHub sign-in on the Dell, and verify its SSH key/known hosts for each
Pi. The startup script cannot infer these accounts or grant access.

Home Assistant and the laptop Codex notify adapter must publish to the new
controller address after cutover. If keeping Home Assistant on the Mac, its
notification URL still needs updating; don't start a second competing HA instance.
Keep the notification token stable when moving its state. Spotify API OAuth may
need a local browser tunnel/sign-in on the new host; Cast mode uses the configured
TV address. Choose a LAN bind explicitly for tablet access.

Stop the Mac controller before the Dell takes over the button/display. Validate
read-only health, quiet audio, display, PTT and an incoming notification, then check
restart behavior on the actual Dell. The launcher has automated shell/dispatch coverage, and CI is configured for
Ubuntu. The current full feature set has not yet been live-validated on the Dell. The prior live-USB persistence limitation still applies.
