# Spotify companion

The character stays onscreen, gently bobs with music notes, and shows a scrolling song/artist footer. Notifications temporarily replace the music presentation. Playback is read-only; this connector cannot start or change your music. Updates normally arrive within 15 seconds. Private sessions are hidden.

## One-time setup on the Mac

1. Create a Web API app at https://developer.spotify.com/dashboard. Spotify requires Premium for development-mode app access. If another account will authorize, add it to the app's allowed users.
2. Register this exact redirect URI: `http://127.0.0.1:8769/spotify/callback`.
3. Add `SPOTIFY_CLIENT_ID=your_client_id` to `.env` beside `okabebot.local.json`. No client secret is needed; authorization uses PKCE.
4. Open the controller page in a browser **on the Mac**, click **Connect Spotify**, and authorize playback-state access. Close the confirmation tab and return to the controller.
5. Play music in Spotify. The Pi and tablet should update within about 15 seconds.

The HP tablet can display playback, but the one-time authorization must run on the controller computer because the callback is loopback-only. After migrating to the Dell, authorize in a browser on the Dell.

## Configuration

Optional `spotify` configuration:

```json
{"callback_port":8769,"poll_seconds":15,"device_name":""}
```

An empty device name follows playback across your account. Set an exact Spotify device name to restrict it. Polling accepts 10–300 seconds and backs off on rate limits. A custom callback port must also be registered in your Spotify app.

Refresh tokens are stored in the ignored state directory as `spotify-tokens.json` with owner-only permissions. They are not sent to the tablet or model. To revoke access, remove this app from your Spotify account's Apps page, stop the controller, and delete that token file.

Sources: [Spotify PKCE flow](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow), [redirect URI rules](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri).

## Listen-along microphone

`spotify.listen_along` defaults to `true`. While Spotify reports playback, the
Voice Pi measures short microphone buffers locally and sends only a 0–1 sound
energy value to the display. The character bobs with louder attacks; this is a
simple reactive animation, not exact BPM or beat prediction. No music audio is
saved, uploaded, or transcribed. Put the Voice Pi within hearing distance of the
speaker. Quiet playback falls back to gentle movement when the meter is unavailable.

Use **Music mic: off** on the dashboard to stop ambient listening. This switch
controls music listening only; the separate push-to-talk button remains available.
Set `spotify.listen_along` to `false` in the configuration to default it off after
restart. Background listening stops for push-to-talk and speech playback, and its
three-second lease expires if the controller disconnects. Spotify pause detection
still follows the playback polling interval (normally 15 seconds).

This approach avoids Spotify audio-analysis availability restrictions and a large
beat-tracking model. A future more exact implementation could analyze an audio
loopback on the playback device; the current setup can hear any Spotify speaker.
When updating a Voice Pi, copy `pi/music_meter.py` together with
`pi/voice_service.py` into its service directory.

## Experimental local expressions

`MusicExpression` maps microphone pulse activity to our own enum: unknown→neutral, calm→neutral, lively→happy, energetic→excited. It smooths over four seconds, warms up for six seconds, and requires a stable candidate for three seconds. Disabling capture resets the estimate. Speech and notifications take priority; stale display samples expire after two seconds.

This is a room-audio activity heuristic, not genre/valence recognition: volume, microphone placement, speech, and other noise affect it. Spotify still provides catalog metadata; its restricted Audio Features endpoint is a separate capability. Do not label these estimates as Spotify-provided features.

Evaluation candidate: [DEAM](https://cvml.unige.ch/databases/DEAM/) offers 1,802 tracks/excerpts annotated for arousal and valence. This implementation has synthetic signal/state tests but has NOT been benchmarked on DEAM. For a real evaluation, use licensed audio and time-aligned arousal labels, split by song before tuning thresholds, compare with a constant baseline, and report correlation plus three-bin confusion matrices. Repeat at multiple gains and with room playback to quantify sensitivity. Do not evaluate valence with this energy-only heuristic or treat web genre tags as mood ground truth.

## Local TV push alternative

Install `pip install '.[cast]'` on the controller, then configure:

```json
"spotify": {
  "source": "cast",
  "cast_host": "192.0.2.10",
  "device_name": "Living Room TV"
}
```

Use your TV's own IP and exact Cast name. Restart the controller after changing sources.
Cast mode subscribes to local receiver/media callbacks and makes no Spotify Web API
polls or OAuth requests. The display checks the in-memory snapshot every two seconds.
The connection maintains heartbeats and reconnects; this is not beat timing.
Only Spotify content is treated as music. Pause, other apps, and disconnects clear
music animation. The existing mic still supplies beat/energy animation.

This mode covers only the configured TV; it does not follow playback to a phone or
other speaker. Receiver metadata availability depends on the app. It does not expose
the Web API's private-session flag; disable music display when you do not want local
TV metadata shown. Set `source` back to `api` for the account-wide polling mode.

## Optional music control with passive Cast updates

Cast remains the preferred passive observer for a TV. Selecting Spotify tracks is
separate: enable `spotify.playback_control: true`, then run
`python scripts/connect-spotify.py` on the controller. Open its authorization URL
there and grant Spotify playback permission. This works with `source: cast` and
adds no playback polling. Premium and an active Spotify Connect device are needed.

The MCP `control_spotify` tool accepts `play`, `pause`, `next`, and `previous`.
`play` can take a `spotify:track:…`, album, playlist, or artist URI and an optional
Spotify device ID. No device ID follows the active Spotify device. The tool is
not automatically approved by the default hardware allowlist. Control is off by
default, requires fresh OAuth consent, and was live-tested with pause/resume on a Spotify Connect TV while Cast
remained the metadata source. Track selection and other device types still need
validation. Successful API acceptance does not prove the speaker played audio.
