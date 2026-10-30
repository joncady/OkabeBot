# Amadeus trial checklist

Specification: [amadeus.md](amadeus.md). Owner: OkabeBot controller. Status as of
2026-10-27: private setup, shadow source hooks and retention installed; no proactive output.
The [GitHub roadmap](https://github.com/users/joncady/projects/4) contains
Amadeus A0–A8 work packages; this checklist owns detailed
acceptance and makes partial completion explicit.

## Priority order for the next cycle

1. **P0: publication and consent boundaries.** Keep personal trials private;
   explicit coaching opt-in, supportive wording, stop/snooze and identity gates.
2. **P1: authenticated onboarding and controls.** Source/subject/privacy selection,
   optional goal/topic selection, private timeline and correction/deletion UI.
3. **P2: live adapters and shadow context learning.** Freshness, provenance,
   unknown identity, replay protection and synthetic replay before observation.
4. **P3: quiet suggestions and explicit recall.** Shared attention limits and
   feedback; integrate the offline coaching policy without enabling it by default.
5. **P4: media, pantry and shopping drafts.** Keep approval and provider boundaries.
6. **Deferred: audio sentiment.** Separate opt-in and local uncertain/abstaining
   evaluation; no raw audio retention or emotion-based escalation.

- [x] Add offline supportive coaching policy and synthetic regressions.
- [x] Guard known private artifact paths at commit/CI/release boundaries.
- [x] Add declarative public capability/regression log; personal results remain local.
- [x] Wire invitation, establish/reaffirm choices and topic controls into owner-only onboarding.
- [ ] Add detailed user-defined habit goals/cues after topic onboarding review.
- [ ] Integrate proposal/ACK delivery with shared attention budget and authenticated scopes.
- [ ] Test character wording, private surfaces, accessibility, and snooze/stop physically.
- [ ] Evaluate optional response sentiment separately; do not treat it as consent.

## A0 — specification and offline foundation

- [x] Define local-first architecture, memory types, personas and permission gates.
- [x] Define a 14-day conditional trial and human checkpoints A–E.
- [x] Add private SQLite events and explicit preferences; reject unallowed sources.
- [x] Add stable deduplication/conflict checks, recall, expiry and subject deletion.
- [x] Add offline CLI and synthetic regression fixtures; no hardware/network actions.
- [ ] Human A: approve source/identity/disclosure/retention scope before live collection.

## A1 — live observations and privacy controls

- [x] Add private setup schema for one profile, source permissions,
  retention, quiet hours, timezone and coaching choices; capture starts paused.
- [ ] Connect permissions to authenticated source bindings and network-denied local-only mode.
- [x] Bind HA/calendar/media/interaction adapters to authenticated source scopes.
- [x] Enforce payload schemas, field redaction, clock skew and backfill rules.
- [x] Expose recent structured observations, explicit memory CRUD, pause/guest settings,
  full-profile export and whole-store forgetting through owner-only routes.
- [ ] Add timeline filters and source/evidence explanations once adapters exist.
- [ ] Add voice/MCP recall and explicit preference tools through shared actions.
- [x] Schedule structured-event retention on the existing source-poll loop.
- [ ] Integrate future caches/derived artifacts with deletion.
- [ ] Test restart, source dropout, DST, duplicate and reordered callback behavior.
- [x] Verify synthetic source contracts exclude raw audio, transcripts, account tokens
  and forbidden fields. Physical source acceptance remains a separate checkpoint.
- [x] Test owner/surface/publish scope separation, cross-origin rejection, retention
  shortening, protected consent, logout/revoked-access clearing and in-flight UI responses.

## A2 — context and shadow routines

- [ ] Model home/away/unknown, identity, availability and source freshness separately.
- [ ] Keep existing after-3-p.m. welcome shortcut separate from inferred presence.
- [ ] Learn time windows/sequences, observed-day denominators and exception tags.
- [ ] Store evidence references and reproducible learner versions.
- [ ] Replay synthetic traces, then observe at least seven eligible days.
- [ ] Show hypothetical suggestions without sending cards/audio/actions.
- [ ] Human B: review evidence, false associations and missing data.

## A3 — explicit recall and quiet proactive suggestions

- [ ] Retrieve relevant, current, subject-scoped memory with explainable provenance.
- [ ] Enforce per-surface privacy, guest mode, quiet/focus/movie suppression.
- [ ] Add expiry, daily interruption budget, cooldown and cross-surface deduplication.
- [ ] Feedback: useful, later, wrong, dislike, never, correct and forget.
- [ ] Prevent third-party content/model output from granting permissions.
- [ ] Human C: approve and physically evaluate quiet cards before optional speech.

## A4 — evening media recommendations

- [ ] Maintain observed sessions separately from completed/liked/disliked titles.
- [ ] Confirm subscriptions/region and obtain metadata-provider credentials if needed.
- [ ] Rank available titles by explicit preferences, time available and novelty.
- [ ] Validate provider attribution and fresh availability; never infer entitlement.
- [ ] Optional user-provided YouTube export with preview/redaction; no history scraping.
- [ ] Expand cross-app/guest/ad/autoplay tests without polluting personal preferences.

## A5 — pantry, recipes and reviewable shopping

- [ ] Human D: choose a small pantry set, dietary exclusions, servings, budget/store.
- [ ] Add selected receipt import with local extraction and confirm-before-save.
- [ ] Track quantity confidence, consumption, stale stock and supplied expiry dates.
- [ ] Generate grounded recipes and missing-ingredient local drafts.
- [ ] Validate QFC/Kroger OAuth/catalogue/cart API on the selected store.
- [ ] Evaluate Safeway via supported Instacart links; do not promise direct API access.
- [ ] Show quantities, substitutions, estimate age and external disclosure before write.
- [ ] Deduplicate approved cart writes; uncertain responses must not cause blind retries.
- [ ] Keep checkout, payment and pickup slot confirmation manual.

## A6 — acceptance and operation

- [ ] Time-split evaluation against fixed schedules with counts, errors and usefulness.
- [ ] Privacy/deletion/unauthorized-action regressions and network-denied mode.
- [ ] Installed deployment verification, private backup/restore and rollback guidance.
- [ ] Human E: review trial outcomes; accept, adjust or stop each routine separately.
- [ ] Revisit dedicated local occupancy hardware only if trial evidence requires it.
- [ ] Revisit hosting capacity after measuring the Mac's added CPU/storage/latency.

## Deferred independent work

- Alexa conversational parity: asynchronous/deferred generated-audio delivery,
  physical flicker check, two replies, follow-up listening and exit recovery.
  Keep the accepted destination/demo separate from unaccepted conversation.
- Live consumer order history, automatic YouTube search collection, broad inbox
  ingestion, camera identity and any autonomous checkout remain out of this trial.

## Deterministic morning checkpoint

- [x] Typed, consent-gated phone-interactive/alarm and outdoor weather inputs.
- [x] Configurable local hours/window, durable once/day rule and alarm rollover guards.
- [x] Owner controls for units, card rotation/expiry and optional configured-TV movement.
- [x] Selected-TV pixel card rail; pause/guest/revocation and stale-source fallbacks.
- [ ] Private eligible-morning acceptance and user-directed configuration refinements.
- [x] Two vertically stacked briefing cards with rotation, less unused padding and distance-readable typography.
- [x] Grounded event countdowns, pending-important-notification counts and device-connection cards.
- [x] Private opt-in named persona greeting and bounded spoken rundown, quiet-hours respecting and once per day.
- [x] Optional supportive morning invitation with existing coaching consent and delivery limits.
- [x] Manual re-show of an existing daily briefing, without a fabricated wake cue.
- [ ] Forecasts and richer source-backed briefing prioritization.
- [ ] Additional card sources and travel suppression.

This rule does not complete routine learning or general proactive delivery work.
See [morning.md](morning.md); personal trial observations remain private.

### TV preparation and household state

- [x] Optional destination-bound wake/input preparation with acknowledged input readiness.
- [x] Independently consented HA TV power/availability changes and snapshots.
- [ ] Broader standby/wrong-input device coverage and recovery acceptance.
- [ ] Define evidence rules for TV activity intervals; never equate power with personal viewing.

## Initial shadow learner and replay checkpoint

- [x] Add prior-day cue-window learner, observed-day support and evidence references.
- [x] Add default-off owner previews and explicit routine feedback; no general delivery.
- [x] Add network-denied temporal replay and separate hidden-truth scoring tools.
- [x] Preserve title-clearing stop state without interpreting it as completion.
- [ ] Learn or explicitly configure receptive times separately from activity times.
- [ ] Unify morning, coaching and learned proposals under one attention ledger.
- [ ] Add explicit defer/dismiss scope for morning speech versus silent cards.
- [ ] Add source coverage/health evidence and shift-aware, alarm-relative wake cues.
- [x] Add shadow gates for explicit calendar end/busy coverage, DND/focus and shared-room context.
- [ ] Validate those gates against actual selected HA entities before live delivery.
- [ ] Add a fresh streaming-availability catalogue adapter with explicit provider entitlements.
- [ ] Distinguish recipient identity from shared room/TV activity before personalized proactive delivery.
- [ ] Evaluate stale sensors, multi-player disagreement and household ambiguity without fabricating availability.
- [ ] Expand realistic household/ad/autoplay, DST, travel and sparse-data holdouts.
- [ ] Confirm privacy/surface and recipient identity gates before any general notifications.

Synthetic replay cannot replace the human acceptance checkpoints or prove an
available streaming catalogue, a preferred title, a health need or observed sleep.
- [ ] Distinguish publisher heartbeat from underlying phone/sensor last-seen time;
  a refreshed HA cached value must not silently prove a device is still reporting.
- [ ] Add explicit helpful/later/not-me card feedback without inferring sentiment
  or health consent from silence, phone activity or shared media.
- [ ] Validate wake intent with an alarm-dismissal or explicit sleep-mode cue;
  sustained DND can also be work focus and does not prove sleep or waking.
- [ ] Add retained/requestable entertainment shortlists and a browsing-intent
  signal before broadening autonomous media suggestions.
- [ ] Evaluate an operational-day agenda for overnight shifts, explicitly dating
  commitments beyond midnight instead of silently assuming a midnight boundary.
- [ ] Distinguish verified companion-owned rendering sessions from entertainment
  playback before sharing attention gates with the live Cast morning workflow;
  do not use a broad TV-power or app-name bypass.
- [ ] Make legacy same-time event ordering deterministic and retain frozen replay
  output hashes; input hashes alone do not cover randomly generated event IDs.
- [ ] Add a separately consented explicit-intent adapter for preparation and media
  choice requests (for example HA buttons or NFC), instead of treating occupancy
  or focus-off as a request. Keep user-initiated help distinct from proactive delivery.
- [ ] Separate preparation, retained passive cards, presentation leases and alerts;
  expose why no candidate was created, not only why a candidate was suppressed.
- [ ] Add explicit per-channel quiet rules for passive screen information versus
  spoken/attention-seeking delivery; never infer an exception from a desired goal.
- [ ] Display observation age and busy/optional calendar status; calibrate freshness
  against provider reporting cadence rather than calling a refreshed cache current.
- [ ] Scope attention to verified recipient/destination areas before household-wide
  playback gates are relaxed; unknown room or viewer identity remains explicit.
- [x] Wire the bounded first-door preference trial into the local conversation harness with explicit
  opt-in, skip/stop and confirmation before remembering. Keep temporary
  mood/time constraints in the conversation, not durable preference fields; use
  hobbies/goals only through supported recommendation capabilities. Revalidate
  attention/quiet/media state before the invitation, with a bounded daily trial budget.

- [ ] Extend proactive conversations with verified room/recipient localization, correction of individual confirmed preferences, shared prompt budgets and private real-use feedback.

## Home map and room-aware delivery (proposed)

- [ ] Read-only HA floor/area/device/entity registry sync with event-driven refresh,
  stable identity reconciliation and a self-service unassigned-device review tray.
- [ ] Home-map dashboard with acknowledged character position, explicit/inferred/
  unknown person-device states, evidence age, floor tabs and room detail panels.
- [ ] Separate physical room adjacency from per-room screen orientation; portable
  displays inherit device room estimates without silently changing the house plan.
- [ ] Calibrated HA room presence in shadow; evaluate fixed BLE proxies/Bermuda,
  distinguishing device proximity, household occupancy and actual person identity.
- [ ] Optional native Mac BLE room estimate from known fixed anchors; front-loaded
  permissions, mobile-versus-fixed scanner roles, sleep expiry and calibration.
- [ ] Opt-in room-aware audio routing after wrong-room, ambiguity and stale-signal
  acceptance, preserving media/focus/quiet/permission and character handoff rules.

See [home-map design](home-map.md). Portal navigation is implemented separately;
registry sync, map tracking and Mac BLE scanning remain planned.

## HA companion follow-up

- Import approved HA area/device bindings into the private home map; keep stable destination IDs.
- Export calibrated BLE proximity and explicit Pi power/temperature telemetry through the bounded facade.
- Consolidate selected HA event publishers after parity tests; retain one owner for speech and screen handoffs.

## Next reliability and destination checkpoints

1. [Presence health and lifecycle controls (#15)](https://github.com/joncady/OkabeBot/issues/15):
   expose scanner heartbeat, stale/ambiguous evidence, pause reasons and explicit
   enable/pause state before unattended following. Reconnect handling is not proof
   that an unresponsive remote scanner is healthy. Add manual-move precedence.
2. [Approved HA room/device sync (#14)](https://github.com/joncady/OkabeBot/issues/14):
   supported read-only API, stable area identity and a self-service mapping review.
3. [Multiple Pi display destinations (#13)](https://github.com/joncady/OkabeBot/issues/13):
   per-screen transport and ready acknowledgment, scene reservation, single actor
   ownership, optional local audio, and destination-loss recovery. The current
   registry intentionally supports one Pi display; an extra scanner is not another
   configured screen. Existing display transport can be replaced independently,
   but keeping both Pi screens requires this work.
4. Room-aware Amadeus delivery after the above physical acceptance: use qualified
   location evidence and explicit fallback policy; preserve focus/media/quiet rules.

Completed source reliability work: bounded MQTT queues, asynchronous initial broker
connection and reconnect backoff, interruptible adapter shutdown, bounded scanner
cleanup, and controller-outage pause with fresh-dwell recovery. Only the read-only
HA bridge updates are installed; updated BLE trial lifecycle awaits physical
acceptance. Device-follow trial mode remains distinct from person localization.


Presence-control checkpoint: owner follow controls, current health/pause status,
manual holds and persisted request cooldowns are implemented in the home bridge.
Amadeus live delivery uses the qualified Watch estimate; read-only HA room-map
sync and multiple Pi screens remain next milestones. Complete multi-direction,
manual-override, disconnect/reconnect and interrupted-playback physical acceptance
before treating following as dependable unattended person localization.

## Next private shadow checkpoint

- Review several ordinary days of private candidate and no-candidate decisions.
- Choose additional context integrations with the owner before adding consented
  sources: task/to-do lists, selected charging/focus signals, appliance events,
  recipe/shopping context, optional travel time and verified media catalogue.
- Keep candidate evaluation distinct from any future live delivery rollout; do not
  infer success or helpfulness from silence or copy participant reports here.

## Context-feed onboarding follow-up

- [x] Declarative read-only adapters for HA tasks/device activity/ThinQ/Mealie,
  Sound Transit rail alerts and Trakt recent watch history; owner-editable setup.
- [x] Synthetic consent, failure, freshness, normalized-wire and conversation checks.
- [ ] [#16](https://github.com/joncady/OkabeBot/issues/16): Guided HA entity picker with room/provider labels and connection checks.
- [ ] [#17](https://github.com/joncady/OkabeBot/issues/17): Trakt interactive authorization, safe refresh and configurable/paginated
  history import; preserve explicit partial coverage and household attribution.
- [ ] Help owners connect Google Tasks OAuth, optional Mealie and Trakt accounts;
  verify real entities without copying participant results into public artifacts.
- [ ] Design user-controlled relevance/delivery for transit/task/meal suggestions;
  existing feed-derived opportunities stay in silent shadow evaluation.


## Current release checkpoint

- Implemented: owner-requested HA room/entity preview, domain-filtered entity
  suggestions and private destination-to-area bindings. Room renames preserve IDs;
  removed assignments require review. Explicit refresh is supported; continuous
  registry subscriptions and the complete spatial map remain open (#14).
- Implemented: bounded selected-feed connection checks, Trakt device authorization
  and persisted rotating refresh credentials. Provider account consent, selected
  entities and real-account acceptance remain owner setup checkpoints (#16, #17).
- Physical checks outstanding: automatic ultrasonic approach wave and new-screen
  touch accuracy. Existing sensor API health does not establish those behaviors.
- Source setup outstanding: Google Tasks OAuth,
  selected ThinQ entities and optional Trakt/Mealie account configuration. Do not
  enable unrelated feeds or infer completion from available adapter code.
