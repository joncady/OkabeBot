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

## Conversational preference elicitation foundation

- Improved: an isolated policy can offer one optional contextual question after a
  requested recommendation or a conversation ending, with confirmed private identity,
  availability, quiet/media gates and a delivery-acknowledged daily limit.
- Improved: confirmed usual preferences update the existing recommendation store;
  current-conversation constraints stay ephemeral. Silence never writes memory.
  Speech requires both profile permission and an explicit permitted-channel flag.
- Improved: an opt-in first-door trial now connects the warm local conversation
  worker, Pi speech, push-to-talk responses and owner controls. Typed, fresh
  attention snapshots and existing focus/media/calendar/quiet gates suppress speech.
  Attempts are consumed before playback; memory still requires separate confirmation.
- Limited: no room-level recipient identity, automatic microphone listening or
  specialized hobby/goal recommendation engine. Physical conversational acceptance
  remains separate from software checks. Model output is untrusted and validated.
- Next: collect private user feedback on timing and relevance, then refine source
  health, recipient localization and one shared invitation budget across policies.

## Attention-source freshness separation

- Improved: an expired phone DND report marks that gate unknown while accepting
  the publisher's current media/focus snapshot. It no longer rejects the entire
  feed or hides unrelated source recovery. Unknown DND still suppresses speech.
- Limited: a change-driven DND value is not a communication heartbeat. Source
  health needs independently verified phone updates; no timeout was relaxed.

## Conversational reply resilience

- Improved: explicit food/drink tastes and general interests have supported private
  preference fields, still requiring separate user confirmation before persistence.
- Improved: malformed/unsupported optional memory annotations are discarded while
  preserving valid conversational replies. Malformed generated JSON asks for a
  rephrase without terminating the warm worker. No field is guessed from an alias.
- Improved: an owner-requested Resume reply action restores a recent input session
  without replaying an invitation or resetting the consumed daily attempt.
- Limited: model classification is not authoritative, and no unsupported memory
  annotation is promoted to a lasting preference. Real conversational acceptance
  remains separate from synthetic regressions.

## Natural confirmation handling

- Improved: a clear affirmative with additional supporting words confirms the
  existing pending preference without another model call or repeated question.
  Conditions, corrections, uncertainty and question-form responses stay unresolved.
- Limited: this is a bounded confirmation parser, not unrestricted semantic consent
  classification; it never saves new trailing content as an additional preference.

### Wearable presence prototype

Added a bounded, consented two-screen follow experiment with timestamp validation,
on-body gating, positive room evidence, playback/focus guards and movement cooldowns.
Synthetic regressions cover ambiguous activity and stale wearable signals. Low-power
BLE advertising requires physical calibration; no general person-localization
accuracy or automatic home-map inference is claimed.

Improved the wearable proof's freshness semantics: an unchanged on-body state uses
an independent recent device heartbeat rather than being mistaken for an offline
wearable. Added isolated coverage for stale/unknown heartbeat rejection. Ancillary
Alexa request failures now have a reversible local compatibility workaround; cloud
occupancy latency remains a limitation, not a validated responsive location signal.

Added a bounded two-anchor wearable-follow evaluator with evidence margins, dwell,
expiry and movement cooldowns. Ambiguous or absent observations hold the current
screen; no general identity or room certainty is inferred. Physical acceptance
remains separate from synthetic guard checks and scanner preparation.


### Adapter lifecycle reliability

MQTT telemetry adapters now tolerate initial broker absence without accumulating
stale state, use bounded queues and reconnect backoff, and clean up on termination.
Synthetic regressions verify private-content exclusion and offline startup behavior.
The bounded BLE proof now pauses through controller outages, requires a fresh dwell
on recovery and reaps scanner children. These source checks do not establish
unattended presence reliability or multiple Pi-screen support; physical acceptance
remains a separate checkpoint.


### Watch home-presence estimate

Added an opt-in bridge with independent radio health, conservative unknown states,
departure-intent/door correlation and restart-safe welcome consumption. It separates
read-only home estimation from movement and uses the existing generated greeting
and delivery policy. Synthetic checks cover radio loss, ambiguous absence, stale
door evidence and one-shot return eligibility. Physical return acceptance remains
pending; BLE detects the selected device and does not establish wearer identity.


### Unified presence gate and prepared announcements

The home bridge now shares observations with a controlled follow adapter instead
of duplicating scanner processes. Added owner pause/enable, manual precedence,
persisted cooldowns and final controller-side destination checks. Live conversation
delivery favors fresh qualified Watch context over stale phone state; probable
absence remains distinct from confirmed-away memory. Announcement audio is prepared
on the satellite before scheduling playback through a persistent connection, while
interactive speech keeps streaming. Isolated regressions cover gating, restart
holds, occupied destinations, prepared-audio expiry and purpose-based speech paths.
Physical listening and room-transition acceptance remain separate from software
success and connectivity checks.

- Added a silent developer conversation surface sharing explicit preference
  confirmation policy, with separate pending context from spoken sessions.
  Bounded private feedback supports owner evaluation without public trial logs.

- Added configurable confidence-based acceptance for clear preference statements,
  preserving clarification for ambiguity and distinguishing automatic provenance
  from explicit confirmation. No participant evaluation results are published.

- Connected developer text requests to existing validated tools with silent reply
  callbacks, explicit browser-location grounding, and bounded conversation context.
  Reduced forced character references and made private feedback contextual.

- Replaced preference-interview framing in ordinary text conversation with direct
  question answering and supplied capability context. Added a regression against
  misattributing character-directed questions as owner preference statements.

- Corrected current-location routing and calendar window grounding, and made empty
  calendar replies disclose coverage. Added phone-target discovery checks to avoid
  unintended playback fallback. Improved guidance against repetitive suggestions.

- Added an opt-in anonymous camera greeting gated by fresh home and nearby Watch
  evidence, with fail-closed capture, transient silent waves and no image storage.
  Software regressions cover blocked capture and post-inference context changes;
  physical detection remains a separate acceptance check.

- Added an explicit owner dashboard control for the proactive conversation phone
  DND gate, keeping other interruption protections independent and active.

- Added persistent opt-in shadow evaluations with bounded private decision records,
  including no-candidate outcomes, evidence recency and missing prerequisites.
  Shadow evaluation has no delivery interface; forget/revocation and retention
  apply to the derived trial log. Context attention shares the owner DND policy.

## Read-only context feed foundation

A declarative registry now describes task, coarse device activity, appliance,
meal-planning, rail-alert and confirmed-watch-history inputs. Owner setup exposes
editable per-feed bindings and write-only connection settings. Bounded snapshots
feed local conversation context and silent shadow evaluations with independent
consent, freshness, partial-data markers and empty-list clearing. Revocation and
forget are rechecked after network reads. These are capability improvements;
account integrations and useful real-world recommendations require separate
acceptance. No participant observations or trial outcomes are included here.

## Native display context and wake routing

A paired native Mac can now report only coarse display state, independently of
scene readiness. A separate owner-configurable wake rule reuses shared handoffs
and blocks busy, focus, media and manual-hold cases. Heartbeats cannot summon a
character; blocked or uncertain events are not replayed. A separate MQTT Mac sensor
is available without collecting active-application names. Unique scene assignment
remains a destination prerequisite; sensor readiness alone is not arrival proof.

A dedicated workstation set expands destination capacity without borrowing a
reserved TV scene. Both presentations use shared scene ownership and handoff
rules; sensor availability and destination scene readiness remain separate checks.

## Household recap grounding

Informal household-history questions now force a read-only recap instead of
falling through to unconstrained character dialogue. Missing coverage is explicit;
fictional status and unsupported safety claims are excluded. Character flavor is
owner-editable with a quieter default. Synthetic regressions cover read execution,
source consent, unavailable history and preference/tool routing boundaries.

## Browser chat pairing recovery

An expired or absent paired-screen registration now resolves to an unpaired
browser instead of raising a location lookup exception. Ordinary owner chat and
location selection remain usable; location-dependent movement still requires an
explicit approved destination. Synthetic regressions cover null registration,
owner application routing and the unchanged no-guessed-location boundary.

## Conversational tool summaries

Completed tool results now support a bounded local reply-composition pass instead
of mechanically reading field-oriented acknowledgements. Browser and voice paths
share this behavior, with an owner-editable fast fallback option and timing
metadata. Richer household observations can be combined into a short recap while
preserving limited coverage. Composition is isolated from tool execution and never
retries uncertain actions. Conservative checks reduce known overclaims but do not
constitute a general entailment guarantee.

- Household recaps now prioritize recorded alerts over routine state snapshots. Ring timestamp ingestion distinguishes occurrence time from reconnect time, and user-confirmed events retain separate provenance. Public regression fixtures contain invented events only.


## Guided source binding

Owner-requested HA registry previews now resolve device and entity area assignments
for domain-filtered setup suggestions. Private destination-to-area bindings retain
stable identity through room renames and flag removed areas. Discovery grants no
observation or device authority. Trakt device authorization keeps credentials
write-only and rotates refresh tokens; provider account acceptance remains a
separate manual checkpoint. Full spatial fusion and continuous registry event
subscriptions remain future work.


## Trakt onboarding compatibility

New Trakt apps no longer issue a client secret. Device authorization now permits
that public-client configuration while retaining legacy-secret support, and sends
the required application/version headers for OAuth requests. Synthetic coverage
checks both authorization and refresh without a secret. Provider approval remains
separate from enabling watch-history observation.


## Collection and retrieval separation

Added stable-ID current-item storage, observed version history, repeat-report
compaction and configurable signal interval statistics. Calendar UID/recurrence
identity preserves distinct occurrences through title/schedule edits. Source
binding/consent fences, retention reduction, exports and forgetting include these
projections. Conversation prompts receive feed availability rather than item dumps;
read-only source tools provide paged current/change/aggregate views. Synthetic
regressions cover large collections, duplicate reports, partial omissions, calendar
rescheduling, stale readings and meaningful discrete signal changes. Remaining
collectors/recording budgets and full provider pagination remain separate work.


## Context-store checkpoint reliability

- Improved: unchanged connection saves preserve retained records and private OAuth
  refresh metadata; actual connection changes retain the clearing boundary.
- Improved: feed health and tool availability distinguish full source coverage
  from bounded UI previews. Expired coverage markers are ignored before pruning.
- Validation: synthetic save/rebind, large-source and expiry regressions cover
  these boundaries. No new observation consent or device behavior is enabled.
- Remaining: resumable provider pagination, recording budgets and broader collector
  compaction remain separate backlog issues. Roadmap scope now uses repository
  issues with a project status view.


## Shared structured conversation tools

- Improved: model-selected capability routing replaces keyword read eligibility
  for text and ordinary/proactive voice. Bounded read chaining, schema repair,
  duplicate suppression and explicit failure replies prevent abandoned lookups.
- Improved: source coverage remains distinct from current snapshots; task providers
  and local reminders have separate semantics. Retained household occurrence
  counts preserve provider/category/provenance rather than guessing deliveries.
- Limited: local model relevance and semantic grounding still need ongoing
  synthetic evaluation. Alexa's isolated conversation is outside this change.
- Privacy: no new collection source, recording consent or public trial artifacts.


## Grounded entertainment recommendations

- Improved: recommendations can retrieve connected Trakt want-to-watch titles
  through a paged read tool instead of improvising from a small preference profile.
- Boundaries: existing authorization, pause/guest gates and private state ownership
  apply; no background history collection or provider write is enabled.
- Limited: list membership is not viewing history or streaming availability.
  Unknown viewing dates and provider provenance must remain explicitly unknown.


## Pre-review privacy and credential boundaries

- Improved: owner memory/export includes both household subject labels; private
  text feedback is exported and forgotten with the configured store. Feedback
  writes serialize with forgetting and require setup to prevent re-creation.
- Improved: household recap inbox supplements require the corresponding source
  consent; generic publisher labels do not imply permission for history access.
- Improved: bounded file locking serializes Trakt token refresh across local
  controller/MCP processes, supplementing thread-level coordination.
- Validation: invented export, forget, revoked-source and independent-lock tests.
  Review fixes are source changes, not new physical acceptance or personal trials.


## Readiness and integration fault isolation

- Improved: owner dashboard distinguishes core startup, current dependency faults,
  partial source coverage and historical HA notices, with bounded read-only probes.
- Improved: an optional version-guarded push compatibility backport preserves valid
  encrypted messages and prevents malformed packets from terminating dispatch.
- Limited: core readiness does not certify physical actuation, every model variant
  or cloud-provider profile support; container replacement requires patch review.
- Next: prefer released upstream fixes and validate real notification delivery
  independently of synthetic crypto and service-level health checks.


## Administrative hierarchy and source coverage

- Improved: dashboard and private setup separate daily controls from advanced
  detail; relative screens retain centered, usable targets across viewport sizes.
- Improved: HA inventory includes floor context and explicit unassigned review;
  source permission remains separate from registry discovery.
- Improved: Trakt pagination, date-unknown provenance and account-generation checks
  preserve explicit coverage and cancel stale reads across account changes.
- Improved: optional disposable-file limits expose content-free private counters
  without broadening capture or treating protected state as a cleanup target.
- Limited: very large historical imports, remote recording budgets and isolated
  backup/restore are separate planned work. Broader coaching and sentiment remain
  open; finishing administrative controls does not imply autonomous health advice.


## Explicit recurring task support

- Improved: NFC and dashboard completion share stable chore identities and durable
  recurrence. Reminders do not masquerade as completion, and stale plans cannot
  be resurrected by a late scan or delivery acknowledgment after forgetting.
- Improved: due tasks can be woven into morning/proactive framing with local fact
  slots, repeated gently under task cadence and shared invitation budgets.
- Improved: check-in frequency is editable without resetting privacy choices,
  session state or durable rate limits. Pending/uncertain delivery is distinct from
  successful reminder delivery.
- Limited: latest task state is not a lifetime activity history or identity proof;
  conversational agreement does not complete tasks or grant preference consent.

- Added owner-selected read-only home-device context for HA covers, thermostats and related sensors, with explicit observation scope and household recap support. Device state is not treated as identity or arrival evidence. Vendor account authorization remains separate.

- Added minimized room-activity context with editable HA light/switch/speaker selection, existing aggregation/privacy controls, grounded household recap retrieval and a conservative speaker-availability gate for proactive invitations. Activity is not occupancy evidence.

- Added optional grounded household suggestions with private dashboard away-light notes, shared-budget bedtime/comfort speech, strict room-versus-floor temperature handling, sampled evidence continuity, editable policy and source/forget revalidation. General household assistance remains separate from health coaching consent.

- Household comfort controls and spoken notes now present Fahrenheit while preserving unit-normalized comparisons and existing saved threshold meaning. Fractional conversions are validated without changing thermostat settings.
