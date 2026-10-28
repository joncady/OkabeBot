# Configurable morning summary

The morning rule is opt-in and deterministic. It does not learn a sleep schedule,
listen to audio or infer health. Optional speech generates character framing for
the whole briefing; source facts remain grounded. Existing Amadeus habit-learning
and coaching gates remain independent. Trial observations and personal configuration
stay in private state, outside Git, issues and public progress logs.

## Behavior

1. A privately bound phone interactive sensor must change from `off` to `on`.
   Startup/reconnect/unknown states and snapshots cannot manufacture a wake event.
2. Within the configured local morning hours, compare that event with recent
   next-alarm observations. Defaults are 04:00–12:00, 30 minutes before through
   90 minutes after the alarm. This indicates a phone screen cue, not confirmed
   human awakening. The clock app's alarm allowlist should be configured on Android.
3. Retain a recent alarm across near-time dismissal/rollover. An alarm superseded
   well before its cue window is excluded. Daily preparation is durable, serialized,
   timezone-based and limited to once per local date, including DST repeated hours.
4. Prepare weather and upcoming-today calendar cards. Weather is current condition
   and outdoor temperature, not a rain forecast. Calendar uses the existing timed-
   event feed; all-day events are not supplied. Stale/unavailable sources produce
   explicit placeholders rather than invented content or claims of an empty day.
5. If automatic presentation is explicitly enabled with a configured TV destination,
   use the shared character move/handoff interface. A busy controller skips automatic
   presentation, with no delayed replay or retry to interrupt later activity. This
   can interrupt TV playback. Optional speech uses the destination’s audio route;
   preparation does not change hardware volume.
   An optional preparation binding sends a local wake packet, waits for HA power
   state, selects the configured input and checks Chromecast active-input status
   before handoff. Timeout/failure leaves the character on its existing surface.
6. On the selected full-room TV surface, shift/reduce the room into the left area
   and display two vertically stacked rotating cards in a pixel-edged rail on the right quarter. Rotation
   does not reset on state polls. After the configured window, restore the normal
   centered room. Other locations do not receive morning cards.

Pause, guest mode or revoked phone-context consent blocks preparation and display.
Revoking calendar/weather consent removes that source from the cards. Collection
permissions, morning enablement, destination selection and automatic TV movement
are separate controls. A summary prepared without a destination is not silently
retargeted by a later setting change; configure the target before the next run.

## Owner configuration

Open `/amadeus/` and use **Morning window**. The versioned example values are in
[`examples/morning.json`](../examples/morning.json). Core defaults are off and no
TV is selected; installed owner settings may differ. Configure local hours,
alarm window, temperature units, card interval, availability duration and a TV
from the destination registry. Room names/hosts are not hardcoded. Automatic
presentation cannot be enabled without an assigned unique scene for the current
character and its home. The owner API also reports readiness if scene assignments
change later, instead of silently treating a registered TV as ready. Use a Room view
for the chosen TV scene; a compact Companion view does not show the card rail.

These controls use owner-only `GET/POST /amadeus/api/morning`. Configuration is
stored under `morning.config` in the private Amadeus system preferences. Generic
user memory writes cannot change it. Current cards are derived at read time from
retention-bound observations; the daily run marker is also retention-bound. Owner
export/whole-store forgetting includes/removes these records and configuration.

## Home Assistant publisher

Install [`examples/home-assistant/morning.yaml`](../examples/home-assistant/morning.yaml)
as a private HA package. Add these HA secrets:

- `amadeus_morning_url`: controller origin plus `/amadeus/source/morning`.
- `amadeus_source_token`: existing dedicated write-only source credential.
- `amadeus_morning_entities`: exact interactive, next-alarm and weather entity IDs.
- `amadeus_morning_snapshot_entities`: next-alarm and weather only; never a screen.

Match entities in private `state_dir()/amadeus/ha-bindings.json`, using arrays named
`interactive`, `alarm` and `weather`. The receiver accepts bounded typed metadata
only, with a 60-second delivery window, exact bindings and source consent. No
geocoded location, Bluetooth identity, app names, health metrics or transcripts
are accepted. Interactive events carry their previous state. Weather details are
limited to temperature, units and provider update time; data older than three
hours is rejected. HA takes alarm/weather snapshots at startup and every five
minutes; changes also publish immediately. Raw publisher payloads are not logged.

Check HA configuration, then reload RESTful Command and Automations. Add
`phone_context` and optional `weather` to private Amadeus source choices, enable
morning preparation, then resume collection when ready. Saving config does not
change source permissions or override pause/guest mode.

## Checkpoints and refinements

- Engineering: isolated HTTP source-to-rule regression, deduplication/restart,
  alarm cancellation/rollover, pause/revoke/forget, DST, concurrent wakes and TV
  layout/rotation tests. Generic artwork previews contain invented data only.
- Private trial: verify a real eligible morning cue, source freshness, selected-TV
  handoff, legibility and return to the normal layout. Adjust configuration from
  user feedback. Do not publish the observations or behavioral success metrics.
- Planned layout refinement: two vertically stacked rotating cards in the rail,
  reduced empty padding and distance-readable text. This is not the installed layout.
- Planned content refinement: curate source-backed forecast, event-countdown and
  relevant device-health/action cards; retain freshness, consent and missing-data states.
- Follow-up: optional forecasts, configurable extra card sources, explicit manual
  re-show/dismiss, home/away suppression for travel, and more physical TV coverage.
  Missing input means abstain, not an inferred habit.

## Optional TV power and input preparation

Install [`samsung_morning.yaml`](../examples/home-assistant/samsung_morning.yaml)
as a private HA package. Set secrets `morning_tv_entity`, `morning_tv_remote`,
`morning_tv_hdmi_command`, a random `morning_tv_webhook_id`, and
`amadeus_tv_ready_url` (controller origin plus `/amadeus/source/tv-ready`). Reuse
only the existing write-only source token. The webhook is local-only and accepts
one bounded request nonce; it cannot select arbitrary devices or commands.

Configure `state_dir()/tv-preparation.json` privately, keyed by destination ID:

```json
{
  "example-tv": {
    "url": "http://127.0.0.1:8123/api/webhook/REPLACE_WITH_PRIVATE_WEBHOOK_ID",
    "timeout_seconds": 45,
    "wake_mac": "02:00:00:00:00:01",
    "wake_cast": true
  }
}
```

The MAC above is invented; use the TV's actual network interface privately.
`wake_mac` is optional for already-awake displays. An optional `wake_broadcast`
overrides the default broadcast address. An optional `wake_host` adds a TV-addressed
UDP packet before the broadcast;
use the TV's reserved local IP when broadcasts alone do not wake it. Each distinct
target receives one packet, without a retry loop. The controller sends the packets;
HA then waits up to 35 seconds for power state and sends the configured remote key.
A matching completion only confirms command delivery. Chromecast must additionally
report `is_active_input=true` within 12 seconds by default. Missing or false readiness
aborts presentation without a later retry. For a TV physically checked to use the
right HDMI port but lacking CEC status, private `allow_unknown_input: true` permits
an unknown status after HA confirms the input command; a known false status or
missing Chromecast still blocks. The owner test reports this fallback distinctly
from verified input. Unbound destinations retain existing behavior.

`wake_cast: true` optionally launches an empty public preparation page on the exact
configured Chromecast before the HA power wait. This invokes HDMI-CEC wake without
showing a character, exposing a receiver token or moving it from its current screen.
An existing character visit to the same destination refreshes its own dashboard
session instead of showing an empty warmup or moving the actor to another screen.
This also supports waking a TV that was switched off during an existing visit. Otherwise the
existing receiver app is stopped once before a fresh launch so a retained DashCast
session cannot silently suppress CEC activation. This can interrupt Cast playback,
just like automatic presentation itself; it is not a background retry loop. The Chromecast
must have independent wall power and the TV's HDMI-CEC option (Samsung Anynet+)
must be enabled. TV USB power can disconnect the receiver during standby, making
CEC wake impossible. A missing/disconnected Cast client fails preparation before
HA input commands; cached reconnecting clients are not reported as available.
The temporary page has no private data, microphone, audio or control API calls.
Physical power/input readiness is still checked through HA before character travel.
The subsequent dashboard handoff also starts a new DashCast session after the warmup
page; canceled/stale handoff launches cannot stop a newer receiver session.
If preparation fails, the character stays put; a successfully loaded empty warmup
page may remain on the TV and can be closed normally with its remote.

Samsung input key support and network wake vary by model/configuration. Configure
an explicit input key for the physical HDMI port and enable network wake on the TV
if necessary. The owner-only **Test TV power and input** button exercises preparation
without moving the character or fabricating a morning observation. Test standby
and a different input physically before relying on automatic morning presentation.
These controls add no speaker action or volume change.

## Optional TV-state observations

[`tv_usage.yaml`](../examples/home-assistant/tv_usage.yaml) publishes only state
changes and five-minute snapshots for `amadeus_tv_entities`. Bind the same exact
entities under `tv` in private `amadeus/ha-bindings.json`, and opt into `tv_usage`
in owner setup. Existing source credentials, pause, guest mode, retention and
freshness guards apply. Titles, applications, volume and attributes are excluded.
The opaque endpoint reference is stable and private, not anonymous. TV-on is
household context, not proof of viewing, identity, preference or watched duration.

## Optional spoken briefing

Owner-only morning voice settings (`POST /amadeus/api/morning-voice`) are saved
privately under `morning.voice`: enabled, spoken name, coaching inclusion and an
explicit quiet-hours override. Speech defaults off; quiet hours are respected by
default. A tool-free local model receives the persona, required placeholder names
and a coarse weather category to frame the whole briefing conversationally. Names,
temperatures, event titles and notification contents remain outside its prompt.
Every required placeholder must occur exactly once, and the rendered speech must
fit the bounded output contract; malformed output falls back to grounded speech.
Verified source facts fill those slots afterward, with status counts and an
optional supportive invitation from explicitly opted-in coaching topics.
Existing coaching pause, stop and daily limits still apply. No inferred health
assessment or audio sentiment is used.

Speech waits for arrival and a ready destination speaker. It does not fall back to
the Pi if a TV receiver is unavailable. Notification snooze, quiet hours, guest
mode, collection pause and source permissions are checked before delivery. A
private durable daily claim prevents duplicate or uncertain playback from being
automatically replayed. Coaching delivery is recorded only after playback completes.

The owner’s **Show today’s briefing** control reopens an existing real daily run;
it does not fabricate a wake observation. It respects the same once-daily speech
claim. An explicit owner-only `POST /amadeus/api/morning-present` with
`{"replay": true}` permits a requested replay without clearing the daily marker;
quiet hours, consent, arrival and speaker readiness still apply. Source freshness
still applies, so missing sources remain explicit.

### Name from the selected Home Assistant person

The first whitespace-delimited part of the selected `person.*` entity’s
`friendly_name` is the default greeting name. Hyphenated first names stay intact;
a spoken override is used verbatim.
A Home Assistant login account is not automatically the current household person;
explicitly bind the intended entity as `greeting_person` in private
`amadeus/ha-bindings.json`. Install
[`person_name.yaml`](../examples/home-assistant/person_name.yaml) with private
secrets `amadeus_person_entity`, `amadeus_person_name_url` (controller origin plus
`/amadeus/source/person`) and the existing write-only `amadeus_source_token`.
This publisher sends only entity ID, display name and snapshot time—never the
person's tracker, coordinates, user ID or complete attributes. It imports no
other people and needs no owner dashboard credential or HA account token.

Name refresh requires active collection, door/presence consent and non-guest
mode. The private profile-linked name expires after 24 hours without refresh;
a missing, rebound or consent-revoked person is not guessed. Forgetting removes
the cached name with other private preferences. Clear **Spoken name override**
to follow Home Assistant; a nonempty override takes precedence for pronunciation
or a preferred spoken name. The setup page displays which source is active.

### Practical weather guidance

Fresh current conditions can add conditional outdoor advice: an umbrella for
rainy/pouring conditions and a jacket at or below 15°C. This is current weather,
not a forecast or a prediction that the user will go outside. Unknown/stale
weather cannot produce gear recommendations. Spoken temperatures use plain unit
names rather than display symbols. An empty timed-event feed is described as
that feed's coverage, never proof that the user's whole day is free.

TV receivers prebuffer the short bounded utterance before playback, joining its PCM into one audio buffer rather than playing each chunk as it arrives. This trades additional
startup delay for resilience against receiver/network stalls; phone and Mac
receivers keep their existing streaming behavior. Readiness and playback receipts
still do not establish physical audio quality. Private capability diagnostics
record whether framing was generated and whether delivery completed, without
spoken content or source facts.
