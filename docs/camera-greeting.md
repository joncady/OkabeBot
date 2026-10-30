# Gated camera greeting

An optional silent wave acknowledges a frontal face near the companion display.
It does not identify the person, record video, save frames, or call cloud services.
It can acknowledge a guest when the owner's Watch is nearby; it is not identity
verification. Frontal face detection can miss profiles, poor lighting or occlusion,
and can mistake a face in a picture for a person.

## Processing and permissions

Install the controller's `vision` extra. The existing Mac controller loads OpenCV's
bundled frontal-face cascade only after the gates permit detection. The Pi's new
`camera_probe` RPC captures one 640×480 JPEG directly to stdout, under its existing
camera lock. No frame is written to the camera archive or application logs. The
controller decodes and detects locally, then discards the image. Normal explicit
camera photo/recording tools remain separate and keep their existing behavior.

Repository default: off. Enable or disable **Camera wave when home and nearby** in
Dev. The owner choice is private `camera-greeting.json` in the controller state
folder. The dashboard shows whether detection is blocked, checking or unavailable.

Every capture requires all of these:

- Fresh home-presence state, at most ten seconds old, reporting `home` and both BLE
  scanners healthy.
- At least three recent target Watch observations at the companion anchor, median
  RSSI at least −75 dBm and an eight-dB advantage over a competing anchor under the
  existing default follow gate. This is a conservative proximity heuristic, not a
  measured distance. The nearby projection remains independent of follow cooldown.
- An approved Pi destination currently hosting the character, in its settled Pi
  phase. No move to a camera or speaker is performed automatically.
- No active recording, model turn, focus session or reported media playback.

Unknown, stale, ambiguous, weak or away evidence prevents capture. The controller
checks again after capture/inference and before waving; the Pi independently
rejects the wave while busy, presenting a card, playing media or away. An in-flight
bounded capture can finish after a gate changes; its result is discarded.

## Behavior and limitations

Polling waits three seconds between completed checks; SSH and exposure add latency.
A frontal face must persist across multiple checks for at least two seconds in the
central 80% of the image, with a minimum face size of 45 pixels. A greeting is a
three-second wave with an automatically expiring pose. It does not replace speech
state, press the SwitchBot or play sound. All four characters have a wave pose.

The controller consumes a two-minute cooldown before dispatch, without uncertain
retries. It rearms after at least fifteen seconds of observed absence or blocked
home/proximity context; fresh face dwell and cooldown are still required afterward.
Restarting the controller resets this ephemeral greeting gate. No camera-derived
occupancy history or Home Assistant entity is published in this initial version.

## Verification

Synthetic regressions cover permission rejection without camera calls, stale and
ambiguous Watch evidence, post-frame gate changes, dwell/cooldown/rearming and
animated wave rendering for all characters. A blank generated image verifies the
local detector loads without detecting a face. Real lens orientation, lighting,
face detection and the physical wave require the owner near the companion after
both BLE scanners reconnect. Do not bypass the gates to perform this check.

## Alternative: ultrasonic wave

The shared greeting controls can select an ultrasonic trigger instead of camera +
nearby BLE. Distance thresholds, hysteresis, dwell and cooldown are editable in the
dashboard. It preserves the fresh home and current Pi/attention gates, but never
opens the camera. See [room-sensor setup](room-sensors.md). Source support alone
does not prove installation or physical validation; check deployment inventory.
