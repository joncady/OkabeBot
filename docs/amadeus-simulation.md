# Accelerated Amadeus shadow experiments

The repository includes a first local routine learner and an isolated replay harness.
This is an engineering experiment, not evidence of personal usefulness or a trained
psychological model. Live general delivery remains disabled. No cloud model,
network connection, audio playback, screen movement or hardware operation is part
of the replay. Character wording and speech quality are separate evaluations.

## What exists

`okabebot/amadeus_habits.py` reads permitted, retention-bound structured events.
It learns approximate phone-screen morning cues, home-to-away transitions and
household evening-media starts. It fits only prior local calendar days, separates
weekdays/weekends and counts at most one first cue per kind/day. Defaults require
four supporting observed days and 60% support within a 45-minute window. Support
is an observed-day fraction, **not calibrated probability**. Missing observation
coverage is not evidence that an activity did not happen.

Proposals carry learner version, evidence IDs, scope, observed/supporting-day
counts, expiry and current suppression reason. Fresh current weather and up to two
upcoming calendar facts can accompany them. Household media does not establish
viewer identity, completion, liking or subscription availability. Wake is a screen
cue, not sleep detection. The initial wake/media cue extraction uses daytime and
evening hours; irregular shifts need a different cue model before live use.

Consent revocation, pause/guest mode, quiet hours, fresh confirmed home state,
active media, calendar freshness/nearby starts, cooldown, daily budget and repeat
suppression apply. Explicit routine stop/resume and bounded postponement are
stored separately from coaching consent. Wrong predictions wait for explicit
confirmation/resume rather than automatically resurfacing unchanged after a pause. A requested short postponement can
allow one re-evaluation within the same routine window, but cannot bypass the
daily budget. Expired windows do not cause delayed surprise notifications.

The owner-only `/amadeus/api/habits` GET/POST route configures and previews this
planner; `/amadeus/api/habit-feedback` accepts explicit kind/outcome and optional
`delay_minutes`. The private setup page exposes a shadow-preview toggle. Defaults
are off. Neither endpoint grants delivery, new source permissions or a new public
listener. Evidence is recomputed rather than cached across forgetting/revocation.
These source capabilities are separate from installed deployment verification.

## Blind generation and temporal replay

1. Give fresh-context author agents only invented persona briefs and the supported
   sensor contract. Do not give them the planner, thresholds, source code or prior
   results. Each author writes telemetry and a separate hidden activity/receptivity
   record. Blinding is procedural, not a security sandbox against hostile agents.
2. Keep both streams in ignored private experiment directories. Freeze original
   files and record hashes. The runner accepts **only telemetry**, never truth.
3. Replay through the actual `Collector`, `Morning`, `Briefing` and `HabitPlanner`
   classes using injected clocks and a new private SQLite directory. Successful
   calendar/media snapshots are refreshed every five minutes under the declared
   emulator assumptions; outages withhold refresh. Physical sensor transitions are
   not invented. Duplicate/delayed inputs still traverse production validation.
4. The existing morning path dispatches only on a newly prepared wake cue. The
   harness must not invent periodic deferred speech retries. The learner is checked
   at five-minute ticks and physical events; delivery ACKs are explicitly simulated.
5. Warm up on early days, then score later days with prior-day-only rolling fits.
   Do not tune on those scored days and call them an untouched test set afterward.
6. A separate evaluator reads completed output plus hidden truth. Report activity
   timing separately from receptive help windows, unwanted overlaps, abstentions,
   source failures and unsupported capabilities. Count silent cards and spoken
   briefings separately. Agent reactions are subjective and can contradict their
   frozen windows; retain both, rather than relabeling the test to improve scores.

Example using owner-created **synthetic** files:

```sh
python scripts/amadeus-simulate.py \
  --events .local/experiment/events.json \
  --output .local/experiment/run --habits
python scripts/amadeus-evaluate.py \
  --truth .local/experiment/hidden-truth.json \
  --outputs .local/experiment/run/outputs.json \
  --after 2030-01-14 --report .local/experiment/evaluation.json
```

The legacy replay fixture explicitly opts a synthetic profile into all supported
sources and four coaching topics, with Los Angeles time and 22:00–07:00 quiet
hours. This is a declared policy-stress configuration, not a reconstruction of a
participant's consent or a fair test of every persona's preferred setup. The
installed owner's configuration is never read. Configuration-sensitive findings
must be interpreted with those assumptions.

Each output directory must be new; the runner refuses to reuse a live store.
Run without `--habits` for the existing deterministic-morning baseline. Socket
creation is disabled by the CLI. Authentication/HTTP boundaries are tested by
separate isolated regressions, not bypassed claims of physical end-to-end success.

## Closed-loop round and realism review

Return only actually delivered notifications to the author. Have it react in
character, choose explicit feedback scope and emit the next day's telemetry while
keeping new truth separate. A historical feedback command is applied only if its
referenced notification actually appeared in that replay. Never infer consent,
health-topic rejection or sentiment from free-form reaction text. Unsupported
feedback requests remain explicit; do not silently map a request to delay speech
onto a whole-day health-coaching pause.

For a paired policy check, replay the same telemetry with and without explicit
feedback. This tests control handling; it is not a randomized efficacy trial,
because subsequent simulated behavior may already have adapted to earlier output.

Review sensor semantics and timestamps before trusting scores: alarm rollover,
missing screens, delayed presence, shared viewers, title-clearing stop events,
calendar cancellations, stale weather, missing heartbeats, DST and overnight
activity intervals. Keep mechanical errata separate and report repaired replay
separately. Periodic emulator refreshes do not prove real provider reliability.

Commit only reusable code, invented focused regressions and declarative capability
notes. Keep generated traces, truth, reactions, reports, derived metrics and all
participant observations private. Do not enable live suggestions solely because
this simulation passes.

## Context opportunities and helpfulness extension

`ContextPlanner` is a separate opt-in shadow policy. Activity-window prediction
remains evidence about activity, while fresh device/context changes create possible
openings. It produces a quiet weather/calendar card, a conditional departure check,
or a catalogue-backed choice. It does not start playback or dispatch notifications.
The owner-only `/amadeus/api/opportunities` endpoint accepts explicit `preferences`
and `catalog` objects and returns a preview with `delivery_enabled: false`. Routine
learning must also be enabled. No new preference is inferred from household playback.

Availability is a separately consented source. Only explicitly bound coarse
DND/focus, charging and shared-room signals can enter `/amadeus/source/availability`.
Use the publish-only credential and private allowlists; never forward raw phone
attributes, app lists or audio. Unknown/stale DND/focus suppress opportunities.
The example [HA publisher](../examples/home-assistant/availability.yaml) sends
changes plus five-minute current-state snapshots. Snapshots are not new physical
transitions. A shared occupancy sensor cannot identify the viewer.

Calendar snapshots may include `end`, explicit Boolean `busy` and `all_day`.
`calendar_busy_complete: true` is a provider capability declaration, not an inference
from an empty feed: it requires ongoing intervals as well as upcoming entries.
Partial feeds cannot establish that the user is available. Playback is checked
across players, including TV state, rather than only the last app that updated.
Pauses remain protected as part of an ongoing viewing session.

For matched synthetic comparisons:

```sh
python scripts/amadeus-context-simulate.py \
  --warmup .local/experiment/events-dev.json \
  --events .local/experiment/events-test.json \
  --profile .local/experiment/profile.json \
  --catalog .local/experiment/catalog.json \
  --engine context --output .local/experiment/context-test
```

Use `--engine baseline` with the same inputs for the earlier cue-window policy.
The richer harness honors each fictional profile's explicit coaching choices.
It evaluates shadow opportunities only; it does not invent a ready TV or combine
existing morning dispatch with these cards. A deterministic fake catalogue tests
filtering, not real subscription entitlement or current provider availability.

Freeze telemetry, hidden truth, scoring rubric and then implementation before
holdout scoring. Raters should not see engine labels or desired scores. Review
**every day**, including silent days, against withheld goals and opportunities.
Proposal helpfulness is the sum of five explicit 0–2 judgments: timing, relevance,
grounding, actionability and respect. Daily helpfulness is a separate 0–10 judgment
that includes missed opportunities. `amadeus_evaluation` validates completeness
and scores; it does not infer satisfaction from silence or compute a flattering
rating automatically. Persona stories are simulated reviews, never measured
household benefit. Record inconvenient results and realism limitations privately.

The ICS adapter now also produces a separate `calendar_context` interval view,
including ongoing and all-day entries with explicit ends and transparency. Existing
future appointment reminders keep their original representation. Invalid metadata
prevents complete busy-coverage claims. This source improvement is not evidence
that the active installed worker has been updated.

A five-minute publisher heartbeat proves that HA was queried, not that a phone
recently measured a new state. Real deployment needs source-health/last-seen evidence
in addition to the emulator's declared outages. Do not promote a cached DND-off
value to proof that someone is available.


Context entertainment offers require an observed opening near a supported learned
media-start window. Discovery without history is an explicit preference, not a
fallback granted by an empty calendar. Known household playback suppresses further
watching suggestions for that local day. Weekend support accumulates separately;
a short trial can legitimately have no supported weekend routine. Quiet hours are
not silently treated as sleep times or overridden to satisfy hidden help windows.
The overview includes up to three remaining timed entries today, while runtime
filtering still uses imminent calendar commitments. Display persistence in a
persona review is an explicit emulator assumption: a proposal lease is not proof
that any physical card was rendered or remained visible.

Record output and private database hashes as well as input/implementation hashes.
Legacy event-ID ordering can vary when observations share a timestamp; an observed
control run is not proof of byte-for-byte deterministic behavior across new UUIDs.
Do not substitute a favorable rerun after seeing ratings. Explicit-intent inputs
would be a different intervention and must be evaluated separately from passive
habit prediction, rather than used to relabel a failed held-out comparison.
