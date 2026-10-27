# Device setup

Run `service.py` for the display/camera/Bluetooth role and `voice_service.py` for the audio/button role. They can share one Pi or run separately. Device scripts are intentionally independent of the Python 3.10+ controller package so legacy Python 3.7 satellites remain usable.

For what is actually deployed, see the [current deployment inventory](deployment.md)
and [README topology diagram](../README.md#current-deployment-map). The active
satellite is a single Pi Zero W running both services; the commands below are
generic installation examples, not a second live deployment.

## Dependencies and hardware

On a compatible Raspberry Pi OS installation, the baseline packages are:

```sh
sudo apt install python3-tk python3-pil python3-pil.imagetk python3-pexpect python3-gpiozero bluez alsa-utils ffmpeg
```

The display uses Tk on an **X11 desktop session**, normally `DISPLAY=:0`; a native Wayland-only session needs an X11/XWayland setup. An LCD must already work as an OS display: this project does not install HDMI or GPIO LCD drivers. Configure its orientation/resolution in the OS first.

Camera support selects `rpicam-still`/`rpicam-vid`, then `libcamera-still`/`libcamera-vid`, then legacy `raspistill`/`raspivid`. Install the camera tools appropriate to your OS and enable the camera as required. Legacy cameras were tested; modern camera commands still need hardware validation. Infrared illumination and an IR-sensitive camera are hardware requirements for night vision, not something software alone can add.

The current SwitchBot adapter uses **`gatttool`**, supplied by older BlueZ distributions. Check `command -v gatttool`; some modern distributions omit it. Until a modern BLE adapter is added, use a compatible Bluetooth satellite for the Bot if your all-in-one OS lacks it. The Bot must be in press mode and within Bluetooth range. A hub is not required.

For the Google AIY Voice Bonnet, working ALSA and AIY drivers are prerequisites; this repository does not install or port them to newer kernels. Set `button_backend` to `aiy` on an existing AIY installation. For a standard GPIO button use `gpiozero`, or `none` to run audio tools without a physical button. GPIO numbering is BCM. The defaults are button GPIO23 (to ground, pull-up) and LED GPIO25; check for pin conflicts with LCDs/HATs and use suitable LED current limiting. Inspect ALSA devices with `arecord -L` and `aplay -L`.

## Install the services

Copy `pi/` to `/opt/okabebot/pi` on each participating Pi. The service user needs write access there for recordings and the Bot's deduplication database. A simple deployment from the checkout is:

```sh
ssh pi@display-pi.local 'sudo mkdir -p /opt/okabebot && sudo chown pi:pi /opt/okabebot'
scp -r pi pi@display-pi.local:/opt/okabebot/
scp examples/device.json pi@display-pi.local:/opt/okabebot/pi/device.local.json
```

Replace the host and username with your own. For one Pi, copy locally instead of using SSH. Edit `device.local.json` on each device:

```json
{
  "display_port": 8765,
  "voice_port": 8766,
  "switchbot_address": "",
  "audio_device": "default",
  "button_backend": "gpiozero",
  "button_pin": 23,
  "led_pin": 25,
  "camera_backend": "auto"
}
```

Fill in your Bot's Bluetooth address only on the appropriate device. Set the actual ALSA audio device; an existing AIY setup commonly uses `plughw:CARD=aiyvoicebonnet,DEV=0`. Camera backend can be `auto`, `rpicam`, `libcamera`, or `legacy`.

Review `pi/hardware-lab.service` and `pi/hardware-voice.service` before installation: adapt `User`, paths, `XAUTHORITY`, and runtime directory to your desktop/audio user. Install only the roles needed on that device, or both on a single Pi:

```sh
sudo cp /opt/okabebot/pi/hardware-lab.service /etc/systemd/system/
sudo cp /opt/okabebot/pi/hardware-voice.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hardware-lab hardware-voice
```

The display user must have an active graphical session. The service user needs access to audio, GPIO, camera and Bluetooth hardware; use the OS's usual device groups rather than running the controller as root. Check `journalctl -u hardware-lab -u hardware-voice` if a service fails. Disable other programs that hold the audio device or draw over the display.

## Connect the controller

For local endpoints set `transport` to `local`; match `port` and `recordings_dir` to the service. For SSH endpoints set `transport` to `ssh`, `ssh_target`, optional `ssh_key`, and `remote_dir` to the directory containing `bridge.py`. Set `recordings_dir` to that device's recordings directory.

Authorize your own dedicated SSH public key with `ssh-copy-id`, and connect once interactively to verify the device's host key. The controller uses strict host-key checking and batch mode, so it will not silently accept an unknown host or prompt for a password. Keep private keys outside the repository. Both ordinary RPC and the voice tunnel connect only to loopback on the destination.

Keep clocks synchronized: animation/audio scheduling uses wall-clock timestamps across devices. `speech.sync_lead_seconds` gives remote devices time to prepare playback (default 1.5 seconds).

Characters include Okabe, Kurisu, Pip, and Sonic. Sonic uses an original code-drawn pixel interpretation and the existing warm speech preset (not a cloned character voice). Deploy `sonic_face.py` with `pip_face.py`, `scene.py`, and `service.py` on the display Pi.

After 35 seconds of quiet idle, Okabe/Kurisu silently use a phone and Sonic wags a finger for eight seconds. The scene repeats on a 48-second cycle while idle. Music, notifications, deployment activity, listening, thinking, and speech suppress these gestures. No audio or model call is made for an idle gesture.

## Speaker volume

Open **Dev → Speaker volume** to adjust 0–100% or mute/unmute. Changes apply
immediately to speech and chimes, including audio already playing. The Voice
service saves `volume.local.json` on the speaker device and restores it when
restarted. Read the current saved/live level in Dev; there is no universal safe
percentage across different ALSA mixers, and documentation does not pin a user's
changing volume preference.

The device configuration accepts `audio_mixer_control` (default `Master`) and
`audio_mixer_card` (default empty, using the ALSA default card). These select the
existing ALSA mixer; no shell commands from the browser are accepted. If the
mixer is unavailable, audio service startup continues and the Dev control shows
Unavailable. Volume is independent of microphone/capture gain.

### Match the volume mixer to the playback device

Direct `plughw:` playback bypasses the default PulseAudio mixer. A working
`amixer sget Master` does not establish that it controls the physical speaker.
For the tested AIY Voice Bonnet, use the following device settings:

```json
{
  "audio_device": "plughw:CARD=aiyvoicebonnet,DEV=0",
  "audio_mixer_card": "aiyvoicebonnet",
  "audio_mixer_control": "Speaker"
}
```

Verify with `amixer -c aiyvoicebonnet sget Speaker`. Inspect other hardware with
`amixer -c CARD scontrols` and select its actual playback control. Start near the
minimum and confirm audibly before increasing. The AIY Speaker control at 100%
reported +12 dB; at 5% it reported -43.5 dB. Percentages are hardware-specific.
The corrected control applies to file playback, streaming speech, and chimes;
the saved level is restored when the Voice service restarts.

### Native UCTRONICS display resolution

B010601 is a 480×320 panel. Verify `/sys/class/graphics/fb0/virtual_size` and
`DISPLAY=:0 xrandr`; a 640×480 framebuffer causes resampling and softer text.
For the legacy HDMI firmware configuration used by this panel, back up
`/boot/config.txt`, use `hdmi_group=2`, `hdmi_mode=87`, the existing
`hdmi_cvt 480 320 60 6 0 0 0`, and framebuffer_width=480,
framebuffer_height=320, disable_overscan=1. Remove conflicting active mode values
and reboot. Preserve the vendor overlay, SPI and camera settings. This is specific
to the legacy display setup; do not apply it to a DRM/KMS installation unchanged.

### Keep the character screen awake

`display_keep_awake` defaults to true in the device settings. After Tk opens its
X11 connection, the service wakes the monitor and disables DPMS and screen
blanking using `xset` on that same display. Run these settings after desktop
login; an early systemd `ExecStartPre=xset ...` can fail with an invalid
MIT-MAGIC-COOKIE before the desktop authentication file is ready. Missing `xset`
or unsupported extensions do not prevent the character service from starting.
Set the option false to leave desktop power settings unchanged. This controls
software blanking; the LCD's physical backlight button remains independent.
