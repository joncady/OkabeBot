# Experimental Alexa session destination

Status: bounded development-session destination accepted on Show 15. The user
confirmed custom voice/scene playback, character presence on Show while the Pi
was away, and automatic Pi return after Alexa exit. The controller also verified
an explicit return and a second arrival. The scoped worker is installed/running
as a manual test process, not a login service. This is not an always-on screen.
See [deployment inventory](deployment.md) for installed state and test evidence.

## Supported boundary

The supported prototype is an explicitly invoked, bounded skill session on an
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
background and actor; it never records URLs or device error text. The opaque cover's visibility guard also checks the one-minute document limit independently of
remote responses. `closed` remains terminal for that document.

The actor preloads behind an opaque copy of the background, which remains in
front until image readiness, source departure and a valid visibility lease are
confirmed. Until the cover itself loads, the actor is invisible. This avoids
relying on hidden-image loading behavior. The deploy script rejects a background
with transparency. All three layers share the viewport origin. Trusted literal
idle/blink URLs avoid an inherited source-index binding.

Departure hides the actor first, then waits at least 100 ms in a subsequent tick
before acknowledgement. Arrival similarly waits after applying the phase.
APL lacks the browser's requestAnimationFrame interface: this is an approximate
presentation acknowledgement. Direct Show arrival/exit recovery is user-confirmed;
this does not prove frame-perfect repaint ordering across all devices.
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

## Acceptance and remaining boundaries

- Scoped object reads succeeded and writing the receiver-owned session was denied.
- Both image layers loaded on a real Show; two arrivals, an explicit return and
  automatic recovery after Alexa exit were observed. The user confirmed Show
  presence/Pi absence and the final return.
- Isolated regressions cover stale/reordered records, unsupported scene profiles,
  worker restart sequence preservation, uncertain summon non-replay, and closure.
  Local review findings for cancellation and mismatched layer geometry are fixed.
- The worker is manually started. Autostart, longer sessions, multiple concurrent
  Echo screens, dynamic artwork, live notifications and conversational Show audio
  remain follow-up work. Identity Center credentials still require renewal.
- Alexa+ owns its launch preamble; no bypass is claimed. Destination startup is
  silent, and household speech is not relayed through this prototype.
- The TV's original café reservation and the Pi's speaker level were preserved.
  Show is approved but currently unassigned; reserve a free matching set before
  visiting. The source VisitIntent is not built into the installed model yet;
  use “open Little Lab” then the existing dashboard/voice/MCP movement interface.

References: [APL component bindings and mount](https://developer.amazon.com/en-US/docs/alexa/alexa-presentation-language/apl-component.html),
[tick timing and fast mode](https://developer.amazon.com/en-US/docs/alexa/alexa-presentation-language/apl-tick-event-handlers.html),
[SendEvent](https://developer.amazon.com/en-US/docs/alexa/alexa-presentation-language/apl-send-event-command.html).

Conditional storage follows [S3 PutObject preconditions](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html).


## Controller-side worker

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
