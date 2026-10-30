# Ultrasonic proximity prototype

The Elegoo Uno R3 reads the kit's HC-SR04 and sends bounded distance metadata
through USB serial. It detects a reflecting object, not a named person or reliable
home/away state. No movement, camera capture, speech or HA observation is enabled
by uploading the firmware.

Wire with USB/power disconnected: HC-SR04 VCC → Uno 5V, GND → GND,
TRIG → D12 and ECHO → D11. Do not connect the 5V ECHO directly to Pi GPIO.
Initially connect the Uno to the controller computer over USB; attaching it to a
Pi with a USB touchscreen requires a suitable USB hub and power arrangement.

```sh
arduino-cli core install arduino:avr
arduino-cli board list
arduino-cli compile --fqbn arduino:avr:uno firmware/ultrasonic
arduino-cli upload --port YOUR_SERIAL_PORT --fqbn arduino:avr:uno firmware/ultrasonic
python3 scripts/read-ultrasonic.py --port YOUR_SERIAL_PORT --seconds 10
```

Firmware reports newline-delimited JSON at 115200 baud, approximately five samples
per second. `distance_mm: null` means absent/invalid echo, never proof that a room
is empty. Echo timeout is 30 ms; valid samples are limited to 20–4000 mm. Opening
the serial port may reset the Uno and restart its sequence/uptime.

Calibrate with an unobstructed forward-facing sensor, a hand or person at several
known distances, and an empty scene. Future integration should provide dashboard
controls for enabled state, endpoint, distance threshold, dwell, hysteresis and
cooldown. Stale/disconnected sensors must become unknown. Preserve attention and
home-consent gates; do not automatically replace identifying BLE evidence with an
anonymous object detector. HA discovery and companion movement remain pending.
