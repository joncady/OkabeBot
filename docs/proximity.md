# Bounded phone-to-Pi BLE proximity trial

The Pi satellite can read BLE iBeacon advertisements through BlueZ D-Bus while its
existing display/voice services run. This is an opt-in experimental proximity cue,
not GPS, authenticated identity, exact distance or a home/away signal. A copied
beacon could trigger the same cue; never use this for locks, security or purchases.

Enable the Android Companion app's **BLE transmitter** sensor. Ordinary Bluetooth
being on is not enough. Its UUID/major/minor identifies the configured beacon even
when the phone's Bluetooth address changes. Keep that identifier private. Leave
geocoded location, Health Connect and unrelated scan sensors disabled if unneeded.
The transmitter's power and advertise mode affect battery use and signal strength.
See the [official sensor documentation](https://companion.home-assistant.io/docs/core/sensors/#bluetooth-sensors).

## Trial setup

1. Copy `pi/ble_proximity.py` to the display satellite's configured `remote_dir`.
   The initial trial uses an SSH-connected Linux Pi, BlueZ, `python3-dbus` and
   `python3-gi`. It does not install packages, pair devices, change adapter power
   or restart hardware services. It does not make the Pi an HA Bluetooth proxy.
2. Copy `examples/proximity.json` to an ignored private file. Set the phone's
   beacon UUID/major/minor, adapter and an existing Pi destination ID from the
   location registry. No author-specific hosts, room names or identifiers ship.
3. Configure the controller normally (`OKABEBOT_CONFIG` if needed), then run:

   ```sh
   python -m okabebot.proximity_trial --settings .local/proximity/settings.json --seconds 120
   ```

   This reads targeted signal samples only; it does not move the character.
   Calibrate close and far readings before choosing `enter`/`exit` RSSI thresholds.
4. For one authorized handoff, add `--follow`. Several strong samples and a dwell
   period are required. Median filtering, separated thresholds and cooldown reduce
   bouncing. A timer can complete dwell from already received fresh samples; it
   never invents new packets from a cached RSSI value. The controller uses `/surfaces/move`, preserving existing handoff and
   single-character ownership. The Pi never receives the owner key or destination.

Each invocation lasts 5–900 seconds and permits at most one move. There is no boot
service or permanent follow mode. Busy/transitioning controllers skip the cue;
ambiguous moves are not blindly retried. A noticed manual destination change
suppresses movement for the rest of the trial. Missing advertisements mean unknown;
there is no automatic move-away action. Beacons/names from other devices are not
logged, and no proximity observations are ingested into Amadeus.

## Acceptance and next steps

Validate target matching, near/far separation, a real arrival, and display/voice
service health. Wi-Fi shares the small Pi's radio environment; coexistence with
SwitchBot GATT commands and sustained audio remains separate testing. Do not claim
RSSI maps to meters, or enable continuous following based on one strong packet.
Persistent configurable following, manual-override leases, HA proximity entities
and dashboard controls remain follow-ups after the bounded hardware trial.
Private beacon IDs, samples and household trial outcomes must not enter public
code, documentation, PRs or issues.
