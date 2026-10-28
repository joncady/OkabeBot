# Amadeus capability and engineering log

This is a declarative public log of software improvements and known regressions.
It is not a trial journal, evaluation report or anonymized participant dataset.
Private outcomes and detailed measurements remain local and are not exported here.
Entries describe what the implementation supports, where it is limited, and the
next general engineering improvement. No participant quotes, routines, health
information, behavioral counts or personal trial success/failure rates belong here.

## Offline foundation

- Improved: private event persistence, explicit preferences, source allowlisting,
  duplicate handling, recent recall, retention and subject deletion.
- Limited: no authenticated live collectors, semantic recall or routine learning.
- Next: source/privacy onboarding and bounded authenticated observations.

## Supportive coaching and publication boundaries

- Improved: an offline opt-in coaching policy supports chosen topics, quiet-card
  planning, explicit feedback, durable snooze/stop, and conservative delivery limits.
- Improved: known private artifact paths are excluded and checked at commit, CI
  and release boundaries. Declarative documentation and synthetic tests remain public.
- Limited: coaching is not connected to an onboarding UI or live notification
  delivery. Audio sentiment is not an input. Path checks cannot detect personal
  information pasted into an otherwise allowed source/documentation file.
- Next: render the invitation and controls in authenticated onboarding, then test
  policy enforcement through the shared suggestion/delivery interfaces.

Do not derive entries by uploading or summarizing participant records into the
repository, issues or PRs. Document general fixes/regressions, with synthetic
reproduction when useful. Publication of actual trial results needs a separate
explicit policy change; aggregation alone does not authorize it.

## Private onboarding and explicit memory controls

- Improved: owner-only setup supports profile/source permissions, retention,
  quiet hours and coaching choices, with setup hidden after confirmation.
- Improved: explicit memory editing, private export/forgetting and persistent
  pause/guest/coaching controls share the existing dashboard authority boundary.
- Improved: unrelated saves preserve stop/snooze; private content clears on logout,
  revoked access and late responses. Export filenames receive publication guards.
- Limited: no observation adapters, scheduled retention, inferred memory, semantic
  recall or live nudges. Recent observations are a bounded view, not a full timeline.
- Next: complete private setup review, then bind authenticated metadata adapters
  and exercise shadow context learning without unsolicited output.

## Consent-gated shadow metadata sources

- Improved: internal calendar/media/interaction hooks and a write-only, entity-bound
  HA publisher enforce consent, pause/guest mode, freshness, schemas and deduplication.
- Improved: periodic retention, complete calendar snapshots and separately displayed
  unattributed household context reduce ambiguous or stale evidence.
- Limited: source readiness does not prove live event acceptance. Routine learning,
  semantic recall, timeline filters and unsolicited suggestions remain pending.
- Next: private source acceptance, then synthetic routine/evidence evaluation before
  any proactive delivery. No personal trial outcomes are published here.

## Deterministic morning preparation

- Improved: narrowly typed phone/alarm/weather sources support a configurable,
  durable first-screen cue without sleep inference or model latency.
- Improved: selected-TV cards use the shared scene/handoff interface and a pixel
  rail; alarm rollover/cancellation, DST, duplicates and stale sources have guards.
- Limited: current-weather and timed-calendar cards only. Travel suppression,
  richer forecasts, additional cards and real-morning acceptance remain follow-ups.
- Next: private cue/display acceptance and configuration refinements; no participant
  observations, schedules or behavioral outcomes are published.

## TV preparation and household state

- Improved: optional local wake/input preparation separates command delivery from
  active-input readiness before automatic morning handoff; failure does not retry.
  TVs without CEC reporting have a separately configured, explicitly labeled fallback.
- Improved: independently consented, entity-bound TV state changes and snapshots
  omit titles/volume and retain pause, guest, freshness and retention guards.
- Limited: on-state does not establish viewing duration, viewer identity or taste.
  Standby/input model coverage and richer activity inference remain follow-ups.

- Improved: configurable TV-addressed wake packets complement broadcast delivery
  for adapters that cannot wake from broadcasts alone; synthetic ordering/packet
  coverage preserves bounded sends and existing handoff readiness guards.

- Improved: optional Cast/CEC preparation wakes a configured TV using an empty
  public page before HA confirms readiness; character travel remains separately
  acknowledged. Setup now identifies independent receiver power as a prerequisite.
- Improved: reconnecting Cast sockets no longer advertise handoff availability;
  dropped clients are recreated. Extended standby/network recovery remains a
  broader device-coverage checkpoint rather than an assumed guarantee.

- Improved: warmup-to-dashboard and repeated dashboard visits explicitly restart
  navigated-away receiver sessions; stale launch requests abstain before receiver
  control. Synthetic session/ownership regressions cover the transition.

- Improved: refreshing an existing destination rotates its scoped capability so
  unload events from the replaced page cannot cancel the new visit. Regression
  coverage checks ownership preservation and old-capability revocation.

## Grounded morning presentation and local destination speech

- Improved: two stacked rotating cards, private named greeting preferences and a
  bounded source-grounded rundown share the existing morning eligibility gates.
- Improved: optional supportive coaching respects topic consent and delivery
  limits; quiet hours apply by default, with no inferred health or sentiment.
- Improved: Cast replies use their own authenticated audio receiver and software
  gain; missing receivers cannot silently redirect a briefing to another device.
- Limited: current weather and timed events remain the source coverage; forecasts,
  all-day events and richer briefing prioritization remain follow-up work.

## Explicit person identity for greetings

- Improved: selected HA person names can supply greetings through a bounded,
  write-only publisher, with an optional spoken override and visible source.
- Improved: entity/profile binding, freshness and consent checks prevent choosing
  another household person from activity or forwarding complete HA attributes.
- Limited: identity still requires explicit setup; presence does not identify a
  speaker or imply that the logged-in HA account is the current user.

## Shared voice configuration maintenance

- Improved: one supervised worker supports explicit speaker-only or transcript
  conditioning, with validated references and visible loaded modes.
- Improved: obsolete voice experiment helpers and duplicate manual smoke tooling
  are removed; maintained protocol and end-to-end regressions remain.
- Limited: reference conditioning is not fine-tuning, and physical audio quality
  still requires listening rather than treating a playback receipt as acceptance.

- Improved: the existing speech lock also protects direct tool calls from
  conflicting supervisor health probes, without adding another service.

## Whole-briefing character framing and playback continuity

- Improved: character framing surrounds the full briefing, with exact fact slots
  rather than a styled greeting followed by an unstyled list. Source values stay
  outside the tool-free model prompt.
- Improved: fresh rain/cool conditions can produce conditional outdoor gear advice;
  missing weather and limited calendar coverage remain explicit.
- Improved: TV-only prebuffering separates audio continuity from chunk-arrival
  timing. Other interactive surfaces retain streaming playback.
- Tradeoff: TV speech starts after complete synthesis/transfer; physical quality
  still requires listening and is not inferred from transport acknowledgements.

- Improved: speaker-only synthesis uses short sentence segments through the
  existing model API; ICL behavior is unchanged. This bounds problematic long
  decoding contexts without filtering waveforms or cutting words from recordings.

- Improved: speaker-only clauses reject token-limit termination and allow one
  bounded retry before audio publication. Complete clause decoding avoids relying
  on incremental codec seams. Repeated failures remain explicit instead of
  silently substituting another voice.
- Regression risk: clause buffering and retries can increase speech startup time;
  source completion, delivery acknowledgement and perceived quality remain
  separate checks.

## Isolated routine-learning and feedback foundation

- Added: prior-day shadow cue-window learning with versioned evidence, distinct-day
  support and explicit abstention; source permissions and forgetting remain authoritative.
- Added: private owner previews, repeat/attention gates and explicit routine feedback,
  including bounded postponement without granting new collection or delivery rights.
- Added: accelerated telemetry replay and a separate hidden-truth evaluator;
  physical effects and network connections are excluded from the local harness.
- Improved: title-clearing media stop observations can retire a playing session
  without asserting that any particular person completed or liked the content.
- Remaining: receptive-time learning, richer context, shared attention with existing
  morning output, shift-aware cues and physical delivery acceptance. Activity-window
  accuracy must not be treated as usefulness or certainty about a person's state.

- Improved: rest coaching is phrased as an optional invitation rather than an
  assertion that the user's schedule allows a slow start.

## Context-aware shadow opportunities

- Added: separately consented coarse availability and explicit busy/end calendar
  metadata, preserving unknown state and partial coverage.
- Added: opt-in, owner-only context previews with useful bounded facts and explicit
  preference/catalogue filtering; delivery remains disabled.
- Improved: recommendation timing considers ongoing meetings and multiple players;
  quiet-room observations remain distinct from recipient identity or receptivity.
- Added: matched offline replay and an anchored helpfulness rubric that includes
  silent days and missed opportunities, with hidden truth separate from input.
- Remaining: real provider coverage, recipient identity and human acceptance;
  synthetic persona reviews cannot establish real-world usefulness.
