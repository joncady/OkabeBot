# Elegoo room-sensor prototype

## Grove/Alfa USB satellite variant

Prepared source: `firmware/wio_room_sensors/wio_room_sensors.ino`, for the Twilio
Alfa / Wio LTE Cat-NB-IoT v1.0 (STM32F405). This is separate from the Uno sketch.
Example wiring uses DHT11 on A6/PA6, Grove Button(P) on D20/PB4 and Grove
Ultrasonic Ranger v2.0 on A4/PA4. Disconnect USB before changing Grove cables.
The Grove ranger uses one bidirectional signal, not HC-SR04 trigger/echo wiring.
The firmware enables switched Grove power, uses USB SerialUSB, and does not load
the cellular/GNSS SDK. No SIM or cellular account is needed for this USB route.

Use Seeed STM32F4 core 1.2.5 (`Seeeduino:Seeed_STM32F4:wioGpsM4`) from Seeed's
[legacy board index](https://github.com/Seeed-Studio/Seeed_Platform/blob/master/package_legacy_seeeduino_boards_index.json)
and the [Seeed Grove DHT library](https://github.com/Seeed-Studio/Grove_Temperature_And_Humidity_Sensor).
The Adafruit library with the same `DHT.h` name is not compatible with this legacy
core. Compile with `--clean --library /path/to/Grove_Temperature_And_Humidity_Sensor`
to prevent stale headers from selecting the wrong API. Build success is not a
physical acceptance test.

The board's original cellular demo does not implement the sensor JSON protocol.
Prepare and back up firmware before replacement. The vendor's
[BOOT0/RST procedure](https://github.com/twilio/Breakout_Arduino_Library/blob/master/IDESETUP.md#flash-the-developer-board-with-sample-applications)
enters STM32 DFU mode. Verify the target before flashing, preserve a private flash
backup when readable, and do not disable read protection to obtain one.

The prepared sketch sends distance and debounced button state every 200 ms and
climate every 2.5 seconds. Echo waiting is bounded to 30 ms; invalid distance and
climate readings are null. It does not fabricate an absent tilt sensor. Reader
source accepts climate-only room packets and a separate `button` packet with a
boolean `button_pressed`; each expires independently after six seconds. Parser
regressions use invented packets. Sensor acquisition, HA discovery and physical
button/near/far acceptance remain separate deployment checkpoints.

The upstairs variant is now installed with a persistent USB binding and the
minimal sensor RPC hook. Its existing HA telemetry publisher discovers only
observed supported fields, and forwards climate, optional distance and button
state without creating a fictitious tilt sensor. Null/stale values remain
unavailable. Telemetry is sampled every 30 seconds: the button entity is a state
snapshot, not a reliable short-press event stream or assigned action. Physical
near/far and press/release checks remain distinct from software availability.

## Uno wiring

Prepared firmware: `firmware/room_sensors/room_sensors.ino`. It preserves the
working HC-SR04 D12/D11 wiring and serial messages, adding ambient-light raw ADC,
DHT11 temperature/humidity and a debounced tilt contact. This is a diagnostic
prototype, not an enabled HA source or companion automation.

Disconnect USB before wiring. Connect the Uno 5V and GND to separate breadboard
power rails; all sensors share GND. Check whether the breadboard rails are split.
Do not use the kit's separate breadboard power supply for this initial test.

| Part | Uno connection |
| --- | --- |
| HC-SR04 | Existing VCC→5V, GND→GND, TRIG→D12, ECHO→D11 unchanged |
| Photoresistor | One leg→5V; other leg→A0; **10 kΩ resistor from A0 to GND** |
| DHT11 module | Printed `+`/VCC→5V, `-`/GND→GND, `S`/DATA→D2 |
| Two-leg tilt switch | One leg→D3, other→GND; internal pull-up enabled |

```text
5V ── photoresistor ──┬── A0
                     └── 10 kΩ ── GND

D3 ── tilt switch ── GND

DHT11 module: VCC ── 5V; DATA/S ── D2; GND ── GND
```

Photoresistor and two-leg tilt switch have no polarity. Read DHT11 **module
labels** rather than guessing left-to-right pin order. If it is a bare four-pin
DHT11 rather than a three-pin module, confirm its pinout and use a 4.7–10 kΩ pull-up
between DATA and VCC. Never plug 5V signals into Pi GPIO.

```sh
arduino-cli lib install 'DHT sensor library'
arduino-cli compile --fqbn arduino:avr:uno firmware/room_sensors
arduino-cli upload --port YOUR_SERIAL_PORT --fqbn arduino:avr:uno firmware/room_sensors
python3 scripts/read-ultrasonic.py --port YOUR_SERIAL_PORT --seconds 10
```

Readings: ultrasound about 5 Hz; room snapshot every 2.5 seconds.
The photoresistor is currently omitted: `LIGHT_ENABLED=false` reports null rather
than a floating ADC value. Enable it only after installing the divider. DHT failures
report null, not zero; light is raw 0–1023 and is **not lux**. With this divider,
brighter light generally gives a higher value. Tilt reports `tilt_closed`, not a
calibrated angle or orientation; contact bounce is filtered for 50 ms. The DHT11
is coarse room context, not a precision environmental or air-quality instrument.

Before enabling integrations, validate light by covering/uncovering, tilt by
rotating the sensor, and DHT11 by plausible stable readings. Near/far thresholds,
light calibration and any actions must be dashboard-configurable. No persistent
collector or new personal-history collection is enabled by these diagnostics.

## Pi reader, Home Assistant and wave

`pi/room_sensors.py` runs as a daemon thread inside the display service. Set
`room_sensor_port` in that Pi's `device.local.json` to the Uno's exact stable
`/dev/serial/by-id/...` path. Empty disables reading. Use a USB data hub alongside
the USB touchscreen. The reader needs serial-device permissions (normally the
`dialout` group); it reconnects after unplugging and keeps samples only in RAM.
No Arduino libraries or Python serial package are needed on the Pi.

The controller's **Wave when home and nearby** controls offer Camera + BLE or
Ultrasonic. Select Ultrasonic and configure near/leave distance, dwell and cooldown.
The current Pi destination, busy/recording and focus gates remain. Home presence
and media gates are separately configurable for silent ultrasonic greetings.
Anonymous distance is not owner identity. Returning from a wave requires leaving
the near zone before rearming; missing data does not assert absence. Camera
capture is not used in ultrasonic mode. This does not change BLE-based home/away
or automatic location-follow policy.

The existing HA MQTT facade exposes distance (mm), temperature (°C), humidity (%),
tilt contact and nearby-object occupancy under the companion device. It publishes
the same controller readings every 15 seconds; the local wave loop checks every
three seconds without waiting for HA. Freshness is checked per serial message
kind (six seconds), with HA state expiry as a second guard. Invalid or absent
measurements become unavailable, not zero/off. Values are not retained by MQTT;
HA Recorder may store their history according to HA configuration. No new Amadeus
history consent or automatic physical action is implied by sensor discovery.

Installed verification: Pi RPC and controller state returned live sensor samples;
HA registered all five entities under the companion device. Ultrasonic greeting is
enabled, but a physical approach/wave still requires user confirmation. Full
regressions passed (702 Python, 56 browser). No audio or volume test was performed.

The dashboard option **Allow silent waves during media playback** only relaxes
the wave’s music/TV gate. Home/away, focus, recording/busy and current-location
gates remain enforced. It does not alter speech, quiet hours or proactive
conversation interruption policy. Repository default is off; the active trial
explicitly enables it.

The media exception is checked at both controller and renderer boundaries.
Notification presentation, deployment animation, active speech and away state
still prevent waving; an explicit renderer refusal is surfaced in greeting status.

**Require home presence for ultrasonic waves** defaults on. Turning it off allows
an anonymous nearby object/person to trigger a silent wave without BLE evidence.
Camera mode always retains home + nearby BLE checks, irrespective of this setting.
This option does not change camera collection, speech or location-follow policy.
