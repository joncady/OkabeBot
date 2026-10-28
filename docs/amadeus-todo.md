# Amadeus trial checklist

Specification: [amadeus.md](amadeus.md). Owner: OkabeBot controller. Status as of
2026-10-27: offline foundation in source; no live collector or proactive output.
The [GitHub roadmap](https://github.com/users/joncady/projects/4) contains seven
Amadeus A0–A6 work packages; this checklist owns detailed
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
- [ ] Wire invitation, establish/reaffirm goal choices and topic controls into onboarding.
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

- [ ] Add controller configuration schema: disabled by default, source capabilities,
  subject bindings, retention, local-only mode and private storage location.
- [ ] Bind HA/calendar/media/interaction adapters to authenticated source scopes.
- [ ] Enforce payload schemas, field redaction, clock skew and backfill rules.
- [ ] Expose timeline, explicit memory CRUD, pause/guest mode, export and forget UI.
- [ ] Add voice/MCP recall and explicit preference tools through shared actions.
- [ ] Schedule retention; integrate all future caches/derived artifacts with deletion.
- [ ] Test restart, source dropout, DST, duplicate and reordered callback behavior.
- [ ] Verify no raw audio, transcript, account tokens or forbidden fields enter store.

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
