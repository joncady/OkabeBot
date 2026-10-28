# Experimental Alexa session destination

Status: enabled in the development skill for supervised destination testing.
The tested controller bridge is installed, and its scoped worker is running as a
foreground test process. Both relay objects are readable through its Identity
Center profile; writing the receiver-owned session object is denied. The generic
custom-audio/animated-scene demo still passes cloud asset checks. Physical Show
arrival/return/recovery remains unverified; do not treat this as an accepted
spatial destination yet. See [deployment inventory](deployment.md).

## Supported boundary

The proposed destination is an explicitly invoked, bounded skill session on an
APL-capable Echo. It is not an always-on/wakeable replacement for a TV browser.
Alexa+ can speak a launch preamble. The destination request starts an empty room
without opening the microphone or playing speech; the controller may enter only
after the room is ready and the source has acknowledged departure. Subsequent
updates stay in that session, avoiding repeated skill launches/preambles.

One active Alexa screen session is supported by the initial two-object relay.
A deployment selects a single character/set for its static artwork. A controller
bridge must advertise those capabilities and enforce the existing unique-set
reservations. It must not offer an incompatible character/set as available, move
the actor merely on skill launch, or bypass dashboard screen approval. Supporting
multiple simultaneous Alexa sessions or live artwork switching is separate work.

## Renderer and protocol

`okabebot.alexa_destination.document(token, background, frames)` returns a silent
APL document. `update(token, phase, generation, sequence=..., receiver_elapsed_ms=...)`
returns a bounded command message. Callers use high-level phases: waiting,
entering, present, leaving and hidden. The destination has separate room and
transparent actor layers, so hiding the actor leaves the room intact.

The APL document starts with the actor hidden and independently reports image
load readiness. A normal-mode mount sequence sends bounded polls for at most one
minute. Fast-mode ticks only apply commands, animate blinking and enforce expiry;
they never send network events. The receiver rejects out-of-order commands and
commands arriving after their originating poll's visibility lease. Root-bound
values are evaluated in the root tick context, rather than incorrectly reading
them from document-level ExecuteCommands. Expiry uses elapsed time, not tick counts.
A bounded four-bit asset diagnostic reports only load/failure flags for the
background and actor; it never records URLs or device error text. The actor's display guard also checks the one-minute document limit independently of
remote responses. `closed` remains terminal for that document.

The hidden actor uses APL `display: invisible` rather than zero opacity so its
image loads before an authorized arrival. The absolute actor layer is explicitly
anchored at top/left zero to align with the background viewport. The actor uses
a validated literal source URL; bounded tick commands select the idle/blink URLs
directly rather than depending on an inherited frame-index binding. Both source departure and image-load
readiness are still required before making it visible.

Departure hides the actor first, then waits at least 100 ms in a subsequent tick
before acknowledgement. Arrival similarly waits after applying the phase.
APL lacks the browser's requestAnimationFrame interface: this is an approximate
presentation acknowledgement and still requires live Show visibility tests.
An isolated contract test does not prove actual device repaint timing.

`DestinationRelay` scopes events to an opaque document token and hashed
skill/account/device identity. Old skill-session close events cannot close a
newer session. Ready/load events do not imply arrival or issue movement. Remote
commands come only from the controller-owned command object, never intent slots.
The relay contains no household tools, transcription or arbitrary URL execution.

## Private transport and opt-in deployment

`PrivateDestinationStore` reads/writes bounded JSON objects with encryption and
no-store caching. It supports exactly `surface/session.json` and
`surface/command.json`; no list operation or caller-provided object key exists.
Session mutation uses ETag conditional writes and revalidates on conflicts, so
overlapping polls cannot undo closure, replace a newer session or overwrite a
newer acknowledgement. The cloud role can update its session object and read the
controller's command object, but cannot write commands. Artwork read permission enumerates five exact
keys. There is no new public endpoint. Logs must not include raw envelopes,
identifiers, store bodies or signed URLs.

Deployment seeds both JSON objects using conditional create-only writes before
reporting readiness. Existing session/command contents are preserved. This avoids
requiring bucket-list permission to distinguish a missing object; arbitrary access
denials are never treated as an empty state.

The deploy script has an experimental `--destination-visuals` option. Omitting it
explicitly disables `EnableDestination`; normal generic demo deployment remains
unchanged. When enabled, it validates the selected character/set and required
layer files before adding the conditional policy and uploading generic artwork.
Do not enable this flag on the installed skill before the isolated controller
checks pass and a supervised physical handoff test is prepared. `VisitIntent` is present
in the source interaction model but is not yet built on the installed skill.
With the opt-in feature enabled, an APL LaunchRequest ("open Little Lab") prepares
an empty destination instead of the generic demo. VoiceDemo remains available as
the separate accepted demo. Audio-only Echo launch requests retain that demo.
VisitIntent explicitly requests a summon after readiness/approval; opening the
room alone does not move the character.

The new assets are generated by the existing `build-alexa-character.py` command.
`check-alexa-layers.cjs ARTWORK_DIRECTORY` reconstructs each original full frame
from the background and transparent actor, comparing pixels. It needs the same
local `@napi-rs/canvas` dependency as the exporter. This check passed for all eight
character/set combinations and all four frames. Idle background time is fixed
across mouth/blink frames to avoid unrelated scenery changes during animation.
No private reference audio is part of these assets.

## Required next checks

- Deploy the optional controller worker with scoped credentials, approve the
  discovered screen, and assign a free matching scene for physical testing.
- Verify real image load, clock bindings, poll delivery, acknowledgement order,
  return, session closure and visibility expiry on Show hardware.
- Reject stale/reordered cloud records and profile/set mismatches at the local
  bridge; exercise service restart and credential expiry recovery.
- Confirm that background remains while the actor exits, the Pi stays absent
  during the visit, and Alexa+'s preamble finishes before character speech.
- Keep live defaults/volume unchanged until these checks pass.

References: [APL component bindings and mount](https://developer.amazon.com/en-US/docs/alexa/alexa-presentation-language/apl-component.html),
[tick timing and fast mode](https://developer.amazon.com/en-US/docs/alexa/alexa-presentation-language/apl-tick-event-handlers.html),
[SendEvent](https://developer.amazon.com/en-US/docs/alexa/alexa-presentation-language/apl-send-event-command.html).

Conditional storage follows [S3 PutObject preconditions](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html).


## Controller-side worker (source prototype)

The worker uses a paired-screen credential derived from the opaque device hash.
It needs no full dashboard token and cannot approve itself, rename other devices
or run tools. Approve its pending screen in the dashboard. Assign the fixed
character/set declared by its exported artwork; unsupported choices are disabled
and rejected by the registry. The current adapter supports Room presentation only.
Forget/reapprove the screen before changing its adapter or supported artwork.
Existing browser/Mac registrations keep their prior behavior.

`ControllerDestination` uses the existing surface heartbeat and acknowledgement
API. It never claims arrival on readiness alone, and refuses malformed, stale or
closed receiver state. It rechecks the cloud snapshot before a movement request.
Restarting preserves command sequence and an explicit VisitIntent is claimed
before the scoped summon request. An uncertain summon is not automatically
replayed: use a fresh explicit visit if retrying is needed. An inactive session
stops heartbeats, allowing the existing controller to recover after visibility
leases; it does not invent a painted-departure acknowledgement.

Install the optional SDK and prepare a scoped AWS profile using
[the consumer policy template](../infra/aws/alexa-destination-consumer-policy.json).
For Identity Center, [the permission-set template](../infra/aws/alexa-destination-sso.json)
creates the same narrow policy and a user assignment; supply the instance, user,
account and private bucket parameters locally. Replace the standalone policy’s
bucket placeholder privately. It reads the two JSON objects and can
write only the command object; no bucket-list, image-write or Lambda permission
is needed. A process lock prevents accidentally starting two local workers with
the same lock path. This worker is not yet installed as an automatic service. The current supervised
test uses this runner; stopping it lets the visibility leases recover ownership.

```sh
python -m pip install -e '.[alexa-destination]'
PYTHONPATH=. python scripts/run-alexa-destination.py \
  --deployment .local/alexa-skill/deployment.json \
  --controller http://127.0.0.1:8768 \
  --profile YOUR_SCOPED_PROFILE --name 'Study Echo'
```

The controller base URL must not include a dashboard access key. The worker logs
only status/error classes, never object bodies or credentials. No transcripts,
notification cards, private reference recordings or synthesized household speech
are uploaded by this transport. Speech continues through the selected existing
location route; direct streamed conversational audio on Show is not implemented
by this worker. Installed volume and voice references remain unchanged.
