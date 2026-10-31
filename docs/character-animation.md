# Expressive characters and prepared work

## Research and approach

[Disney's animation process](https://disneyanimation.com/process/animation/) uses
anticipation, timing, follow-through and secondary action to make intention legible.
[Microsoft's character animation guidance](https://learn.microsoft.com/en-us/windows/win32/lwef/animation-principles)
also emphasizes personality, staging and purposeful motion. A small pause, eye
movement and settling pose can communicate more than continuously bouncing a sprite.

Modern controllers separate overlapping concerns. [Rive](https://rive.app/features)
uses state machines and layered animation; [Unreal's animation state machines](https://dev.epicgames.com/documentation/en-us/unreal-engine/state-machines-in-unreal-engine)
organize transitions rather than letting every caller draw body parts. These are
architectural references, not dependencies added to this application.

Our implementation keeps the inexpensive pixel renderer. Each character owns a `motion.json` describing clips, durations, poses and
bounded keyframe channels. The registry assembles those definitions into a catalog. Python and JavaScript sample the same smoothstep tracks.
Surface adapters own actual limb geometry, pixel rounding and props. No generic
sprite stretching or model-generated coordinates are used.

## Motion vocabulary

- Base layer: gentle breathing, offset blink timing and occasional double blinks.
- Sparse idle layer: glances, settling, reading, writing, stretching, human phone
  gestures, Sonic's foot tap/finger wag and Pip's scan panel. Character playlists
  vary the activity; an idle gesture occupies only part of each cycle.
- Work layer: research/compare → reading; drafting → writing; review → checklist.
  Blocked work has a quiet review pose instead of pretending to make progress.
- Priority: movement/handoff, conversation, notifications, deployment, focus and
  media reactions suppress ambient work/idle gestures. Existing music behavior wins.
- Accessibility: owner dashboard controls ambient animation and reduced motion.
  These suppress the new decorative layer, not existing task/audio indicators.

Head, gaze, body and hand channels have separate responsibilities. Human task arms replace both resting sleeves; shoulder/elbow/wrist anchors remain
connected. Okabe/Kurisu write on desk-bound paper with a gripped pencil or type
with two hands behind a foreground monitor. Gaze follows pencil strokes, looks
at the monitor and briefly drops toward the keyboard; furniture stays fixed.
Sonic/Pip keep their earlier simple activity poses pending backfill. Pose
entry/exit weights ease gestures. Sparse idle clips settle back to rest. Work clips
loop while a real task lease exists. There is no invented completion percentage.
Browser room, desktop and phone use the shared room renderer. Pi uses the same
catalog with its lightweight Python adapter. Alexa's separately generated APL assets
remain a follow-up; this change does not claim equivalent dynamic APL motion.

## Preparation contract

`Preparations` is a trusted adapter API, separate from conversation text:

```python
job = preparations.start(kind="shopping_list", title="Shopping list", provider="local")
job = preparations.change(job["id"], job["revision"], "progress", stage="drafting")
job = preparations.change(job["id"], job["revision"], "ready", items=["Oats", "Tea"])
# The owner may keep or dismiss this exact revision in the dashboard.
```

Stages advance monotonically. Workers heartbeat through `progress` at intervals
shorter than 30 seconds. A stale worker or changed owner setup blocks publication.
Decisions require the current revision; finished drafts cannot be edited in place.
Pause/guest mode hides private preparations. The controller publishes only kind,
stage, elapsed time and an eight-second renewable display lease; the Pi expires
that intent using its own monotonic clock. Active intent renews every five seconds;
idle settings are reasserted at most every 30 seconds to recover after a Pi restart. Titles, groceries, account identity and
provider intent are not sent as work animation data.

The dashboard offers a local list draft as an end-to-end foundation. It immediately
becomes reviewable; it does not fabricate seconds of research to show an animation.
Trusted future adapters supply real intermediate stages. The proactive scheduler and
model tools are not connected to this API in this phase.

Private drafts live in the existing subject preference store, participate in owner
export/forget, and expire after one day. Capacity is bounded to 20 drafts and 15
short items per draft; these are temporary review objects, not a replacement for
the task/history feeds. Retention cleanup continues while collection is paused.
Keeping a draft retains it locally until expiry; it never authorizes account writes,
checkout, payment, reservation or purchase.

## Next phase: grocery handoff

Direct Safeway account/cart access has not been verified against a supported public
API. The first useful adapter should build a grounded local list from expressly
allowed sources, distinguish ingredients on hand from guesses, explain substitutions,
and expose a final review. It must not infer pantry inventory from recipes or history.

[Instacart's official Developer Platform](https://docs.instacart.com/developer_platform_api/guide/concepts/shopping_list/)
documents shoppable shopping-list links, a possible approved handoff after account,
retailer coverage and pricing checks. This is an option to evaluate, not a configured
integration. Creating an external link/cart needs a **separate**, expiring approval
bound to provider, operation, exact contents and revision, with idempotency and
reconciliation after ambiguous network failures. Local “Keep draft” is insufficient.

Do not turn retry into duplicate writes. Cancellation, unavailable products, changed
prices and offline recovery belong in that adapter's contract and tests. Start with
list preparation; checkout remains a human action.

## Checkpoint and acceptance

The scoped Pi display bundle is installed as recorded in the deployment inventory.
Controller and shared web UI changes remain source-only for review; subsequent
promotions must retain compatible character assets across consumers. No hosting,
ports, audio targets or live collection settings change. Offline checks cover shared sampler parity, interruption priority,
expired leases, draft revisions/retention and readable template boundaries. Physical
Pi smoothness and prolonged idle personality still require owner review after install.

## Character directory contract

`okabebot/characters/base.py` defines the `Character` interface. Each subdirectory
exports a `CHARACTER` instance of its own subclass; package discovery builds the
registry at process startup. Adding a character does not require another global
profile list, renderer switch or copied prompt constant.

```
characters/<id>/
  __init__.py          # Character subclass; implements shapes(**state)
  art.py               # Pure Python 3.7 pixel primitives
  character.json       # Identity, capabilities, scene choices, subtle style
  avatar.json          # Browser body parts, head crop/eyes, rig palette
  motion.json          # Owned idle playlist, work mapping, keyframes
  voice.json           # Default preset and private reference-manifest key
  persona.md
  welcome-persona.md
  portrait.png         # Public original character artwork
```

The common methods expose profile/prompt, motion, avatar, scene, voice, portrait,
render and six-frame asset interfaces. Controller profiles, style validation,
portrait serving, dashboard choices, satellite rendering and offline previews
consume that registry. Existing `pi/*_face.py` imports are compatibility facades.
The standalone Pi bundle carries this same package, not an independently maintained
copy of character definitions. Restart consumers after changing bundled assets.

Prompts/art/reference metadata move with their character. Actual private voice
recordings and transcripts stay in ignored owner storage, selected through the
existing private manifest; a source refactor does not publish or replace them.
New shared environment geometry remains a separate interface from selecting an
existing character-owned scene. Dynamic APL animation and Sonic/Pip advanced work
poses remain follow-ups. Use the repository `okabebot-character` skill for additions.
