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

The replay fixture explicitly opts a synthetic profile into the seven supported
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
