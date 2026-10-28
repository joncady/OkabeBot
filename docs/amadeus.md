# Amadeus: local proactive companion trial

Status: **proposed trial; offline foundation implemented, live collection disabled**.
Decision date: 2026-10-27. Amadeus is the learning and memory subsystem of
OkabeBot, named in reference to Steins;Gate 0. It is not another character or a
replacement for the existing local conversation and shared action interfaces.

## Trial outcome

Demonstrate that the companion can remember an explicit preference, recognize a
useful recurring context, and offer a grounded suggestion at a welcome moment.
Start with morning/arrival context, evening media choices, and dinner planning.
Learning must remain inspectable, correctable, deletable and local. A successful
trial is useful assistance with few interruptions, not the number of automations.

This document is the product specification. [The trial checklist](amadeus-todo.md)
owns sequencing and acceptance gates. [Deployment inventory](deployment.md) owns
installed state. Source implementation is not evidence of activation.

## Scope and non-goals

Initial scope: a private event ledger, explicit preferences, current-context state,
routine candidates, explainable suggestions, feedback, and bounded approved tools.
The Mac hosts storage and inference; Home Assistant supplies selected events;
the Pi, Mac, phone and TV remain presentation/input destinations. Characters share
personal knowledge but phrase it in their own personalities.

No continuous ambient transcription, camera-based identity, model training,
autonomous purchases, sensitive personal inference, cloud LLM fallback, or new
AWS infrastructure. Alexa conversation parity is paused; its accepted scene/demo
and destination behavior remain separate. Grocery/catalogue connections involve
provider clouds even when personal inference is local.

## Architecture and contracts

```mermaid
flowchart TD
    Inputs["Allowlisted HA, calendar, media and explicit user inputs"] --> Adapters
    Adapters["Validate, attribute, deduplicate and label sensitivity"] --> Events
    Events["Private local event ledger"] --> Context["Current context with freshness and unknown state"]
    Events --> Memory["Explicit and inferred memory, kept distinct"]
    Events --> Habits["Routine candidates and exceptions"]
    Context --> Planner["Opportunity planner"]
    Memory --> Planner
    Habits --> Planner
    Planner --> Policy["Attention, permission and privacy policy"]
    Policy --> Surfaces["Character icons/cards and optional speech"]
    Policy --> Actions["Existing shared actions, after approval"]
    Surfaces --> Feedback["Accept, later, wrong, never and forget"]
    Actions --> Feedback
    Feedback --> Memory
    Feedback --> Habits
```

Adapters publish facts, never authorize actions or draw UI. Each event has a
stable source/event ID, subject (including `unknown`), kind, observation time,
bounded structured payload, provenance and expiry. Late events are stored as
history, not replayed as current triggers. Source disappearance means unknown,
not away/asleep. Reconnect/backfill must not replay greetings or actions.

The first offline store accepts only explicitly allowlisted source names. It is
not an authenticated ingestion server. Future live adapters must bind source
identity and subject permissions at the controller boundary; a caller-supplied
source string or subject is not authorization.

Planned high-level operations:

| Operation | Contract |
| --- | --- |
| `observe(event)` | Validate/deduplicate an authorized observation; no side effect |
| `remember_preference(subject, key, value)` | Explicit user instruction; authoritative over inference |
| `recall(subject, context)` | Relevant, fresh, disclosure-appropriate evidence only |
| `explain(memory_or_suggestion)` | Sources, age, uncertainty and applicable permissions |
| `forget(subject, item_or_source)` | Remove records plus dependent derived artifacts |
| `propose(context)` | Reviewable candidate with reason, expiry and permission requirement |
| `feedback(proposal, outcome)` | Distinguish acceptance, timing rejection and preference rejection |

Only the offline store/CLI subset is implemented initially. Do not advertise
these planned contracts as available dashboard, voice or MCP tools yet.

## Memory model

Keep explicit preferences, observations, inferred preferences, routines,
commitments and temporary context separate. A watched title is not a positive
rating; a purchase is not consumption; a door opening is not departure. Each
derived memory needs evidence IDs, subject, confidence, last support, expiry,
model/rule version and disclosure scope. Explicit preferences carry their own
user-stated provenance and survive expiry of unrelated observations.

User corrections override inference. Conflicting explicit preferences require a
visible correction/version, not silent resolution by the LLM. Temporary context
expires; learned habits decay. Raw audio is not a memory. Initial storage supports
bounded structured events and explicit JSON-valued preferences, not transcripts,
receipt bodies, embeddings, inferred memories or arbitrary model memory writes.

Recall requires relevance, reliable attribution and utility. Limit injected
memories, show why they were selected, and do not bring unrelated personal facts
into ordinary conversation. All characters use the same subject-scoped store.

## Signals and gaps

| Domain | First signals | Gap / rule |
| --- | --- | --- |
| Morning | Explicit interaction; opt-in alarm/charging and occupancy | Awake is a hypothesis, not a phone-state fact |
| Departure/arrival | Door plus Android/router presence | Require freshness and identity evidence; retain unknown |
| Evening media | Cast title/app/state and explicit ratings | Deduplicate ads/autoplay; completion and liking are distinct |
| Calendar | Existing read-only iCal events | Plan is not attendance; cancelled/changed events invalidate proposals |
| Purchases/delivery | User-selected receipt imports, later chosen notifications | No assumed consumer order-history API; no broad inbox ingestion by default |
| Pantry | Confirmed items, quantities and consumption updates | Estimates cannot become confirmed inventory; expiry is user/product supplied |
| YouTube | Observed sessions; opt-in history export | Public API does not expose watch history; search import is optional and sensitive |

First hardware addition, if needed: one local occupancy sensor near the main
companion, combined with existing phone/door signals. mmWave occupancy does not
identify people. Router presence is supporting evidence, not reliable away proof.
No hardware purchase is required for the offline foundation.

## Routine and opportunity engine

Start with time-window and sequence statistics, separated by weekday/weekend and
calendar context. Do not train a new model. Store support count, observed eligible
days, exceptions, freshness and last change. Do not double-count repeated callbacks.
An inferred probability must be calibrated before displaying it as a percentage.

Proposed cold-start gate: at least five eligible occurrences over seven observed
days before a routine becomes a candidate for review; rare/weekend routines may
need longer. This is an initial heuristic, not a statistical guarantee. Holidays,
travel, guests, outages and schedule changes must be excluded or separately tagged.

An opportunity includes evidence, expected benefit, deadline, intended surface,
sensitivity, action plan and fallback. Policy chooses discard, defer, quiet card,
ask, or execute a specifically preauthorized action. The LLM cannot promote its
own permission. New observational learning starts in shadow mode with no output.

Default active-trial attention budget: two unsolicited suggestions per day,
one per context transition, 60-minute cooldown, quiet hours and focus/movie
suppression. Explicit requests and existing critical alerts are separate. These
are proposed defaults to approve at checkpoint A, not live settings. Ignoring a
card is not negative preference feedback. Suppress duplicate cross-surface offers.

## User stories and reviewable behavior

| Persona / story | Expected behavior | Acceptance |
| --- | --- | --- |
| Busy commuter, earlier appointment | Offer preparation reminder while still useful | Calendar provenance; no false assertion of departure |
| Remote worker, first interaction | Brief agenda only when available, not during focus | Once per morning; dismiss/later honored |
| Returning user | Relevant recap and recall of an explicit dinner request | Supported arrival; no private shared-screen disclosure |
| Weeknight viewer | A few available films fitting time and preferences | Region/subscriptions checked; played is not liked |
| Home cook | Recipe using confirmed food, questions about uncertain stock | Dietary exclusions respected; no invented ingredient quantities |
| Grocery shopper | Local draft with products, quantities, estimates and substitutions | External cart modification requires approval; checkout remains manual |
| Guest/shared household | Generic scene and non-personal notifications | Unknown identity cannot retrieve another person's memory |

Example future flow: confirm morning context → show agenda icon → user requests
briefing → changed appointment informs an optional preparation reminder. Later,
supported arrival recalls an explicit dinner plan → uncertain spinach stock is
confirmed → recipe generates a local missing-ingredients draft → user reviews
before an external cart write. At night, a film recommendation uses the selected
subscriptions and explicit feedback, without interrupting current playback.

## Privacy, security and retention

Source-level controls independently enable observation, retention, inference and
actions. Guest mode, pause learning, per-subject access and per-surface disclosure
are mandatory before live personalized output. A dedicated receipt import or
mailbox is preferable to broad Gmail read scope; label filtering is not OAuth
scope restriction. Third-party text is untrusted data, not tool instructions.

Proposed retention: raw structured events 30 days; routine summaries 90 days since
last support; confirmed preferences until changed/deleted; private exports under
user control. Retention pruning must run on a schedule before live collection;
the offline CLI prunes on each invocation. Subject deletion removes events and
preferences; derived evidence graphs, caches, embeddings and queued proposals
must participate when introduced. Backups need explicit expiry/deletion policy.

Store in a private directory, private DB permissions, encrypted host disk and
encrypted backups. SQLite is not application-level encryption. Offline deletion
removes logical records and uses SQLite secure deletion, but cannot promise
forensic erasure from SSD snapshots or backups. No personal data in public docs,
CI fixtures, logs, provider queries or model training. Public catalogue queries
and external carts disclose selected information to their providers; show that
boundary before enabling them. Network-denied local-only mode is a later gate.

## Trial timeline and human checkpoints

Indicative **14-day trial starting after checkpoint A**, not a promise of
unattended future work. Calendar dates shift with review and data availability.
Implementation can continue on synthetic fixtures while waiting for reviews.

| Window | Deliverable | Human involvement / gate |
| --- | --- | --- |
| Preparation, beginning 2026-10-27 | Spec, backlog, offline foundation, regressions and PR | Review source scope and privacy at A before live collection |
| Days 1–3 | Allowlisted live adapters; timeline, correction/deletion UI; freshness health | A: choose identity, sources, retention, quiet hours, shared-screen rules |
| Days 4–7 | Shadow routine candidates and hypothetical suggestions | B: inspect evidence and wrong assumptions; no unsolicited output yet |
| Days 8–10 | Quiet cards, explicit recall, feedback and interruption controls | C: approve a small suggestion budget; physically review timing/privacy |
| Days 11–14 | Movie shortlist and pantry/recipe/local shopping draft trial | D: confirm subscriptions, dietary constraints, pantry subset and store |
| End of trial | Evidence-based accept/adjust/stop decision | E: usefulness review; enable selected routines only |

External OAuth consent, receipt/history imports, missing hardware signals and
physical UX tests are the other reasons to request help. No need for the user to
participate in routine coding, synthetic evaluations or documentation work.
If seven observed days do not support a habit, extend observation rather than
lowering confidence requirements to meet the timeline.

## Evaluation and release gates

Use synthetic clocked traces before live data: normal day, remote-work day,
holiday, guest, DST/timezone change, duplicate/late event, offline phone, restart,
unknown identity, changed calendar, stale pantry and interrupted action. Replay
must not send audio, cloud writes or hardware actions. Split prediction evaluation
by time, not random events from the same day. Compare to a simple fixed schedule.

Proposed trial targets: zero unauthorized actions or cross-person disclosures;
zero duplicate suggestions on replay/restart; every suggestion explains evidence;
all forget/retention regressions pass; at least 80% of reviewed eligible context
triggers correct; at least 60% of reviewed suggestions useful; no more than two
unwanted unsolicited interruptions in a week. Report sample sizes and uncertainty;
small samples cannot establish general accuracy. Latency and time-to-usefulness
are measured separately from voice synthesis. No outcome is assumed in advance.

## Research and connector feasibility

- [HA person](https://www.home-assistant.io/integrations/person/),
  [Android sensors](https://companion.home-assistant.io/docs/core/sensors/) and
  [local LD2410 occupancy](https://www.home-assistant.io/integrations/ld2410_ble/).
- [YouTube API history limitation](https://developers.google.com/youtube/data/revision_history).
- [TMDB watch providers](https://developer.themoviedb.org/reference/tv-series-watch-providers):
  regional listings, not entitlement; JustWatch attribution required.
- [Kroger public cart operation](https://www.postman.com/kroger/the-kroger-co-s-public-workspace/request/mwiie4o/add-to-cart):
  validate QFC store/account access before promising it; no checkout claim.
- [Instacart shopping-list links](https://docs.instacart.com/developer_platform_api/api/products/create_shopping_list_page):
  candidate Safeway route, subject to local retailer/fulfillment verification.
- [Grocy](https://grocy.info/): optional local pantry backend, not a required service.
- [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes):
  general read-only scope is mailbox-wide, not confined to a chosen label.

No new provider account, paid resource, store cart, sensor capture or live
learning was enabled to prepare this specification.

## Running the offline foundation

From an installed development environment, use a disposable private directory:

```sh
python -m okabebot.amadeus --folder .local/amadeus-demo remember \
  --subject trial-user --key media.subtitles --value true
python -m okabebot.amadeus --folder .local/amadeus-demo --allow-source synthetic observe \
  --source synthetic --external-id demo-door-1 --subject trial-user \
  --kind door --payload '{"state":"open"}'
python -m okabebot.amadeus --folder .local/amadeus-demo recall --subject trial-user
python -m okabebot.amadeus --folder .local/amadeus-demo forget --subject trial-user
```

The CLI creates its directory with mode 0700 and database with mode 0600; existing
non-private paths are rejected. Sources default to none. It has no network,
hardware or LLM integration. Each invocation prunes expired observations; explicit
preferences persist until corrected/forgotten. Recall is recent structured history
and explicit preferences, not semantic or relevance-ranked retrieval. Stable event
IDs deduplicate retries; conflicting payload/subject/timestamp reuse is rejected.
If no source timestamp is supplied, retries retain the first local observation time.
Use fixtures rather than personal imports before checkpoint A. No background task
is installed by these commands. Run `python -m unittest tests.test_amadeus -v` for
isolated persistence, privacy-boundary, retention and CLI checks.
