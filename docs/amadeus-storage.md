# Amadeus collection, compaction and retrieval

## Contract

Collection scope, retained detail and prompt size are separate controls. All
existing consent, pause, guest, retention and forgetting boundaries still apply.
Connecting a source or widening a selection does not enable raw audio, camera,
transcript, browser-history or location recording. This change adds no background
model summarizer and does not infer personal preferences from repeated signals.
Private records, diagnostics, exports and migration backups must remain local.

## Implemented record paths

- **Distinct feed items:** current normalized records are keyed by source, subject
  scope and stable provider item ID. Repeated polls update last-seen/freshness and
  report counters. Changed content produces a retained version; identical titles
  with different IDs are never merged. First observed is not creation time.
- **Calendar:** ICS UID plus original recurrence identity separates occurrences.
  Non-recurring UID survives rename/reschedule. Repeated current checkpoints are
  replaced, with distinct observed versions retained in the compact store. Missing
  upstream UID still uses the prior title/time fallback; it cannot provide strong
  identity across edits. No cancellation is inferred from falling outside the
  two-day collection window. Calendar notification scheduling stays independent.
- **Noisy feed signals:** selected device-activity/appliance states retain current
  state and interval buckets with report/transition counts, first/last values and
  numeric minimum, maximum, sum and sample count. The default is 15 minutes,
  editable from Context feeds (1–60 minutes). Window size is part of bucket identity.
  Discrete state changes, including errors/completion, remain separate observations;
  numeric drift is aggregated. These are polling samples, not time-weighted averages
  or continuous physical measurements. Different sensors or measurement units are not averaged together.
- **Removal:** an absent item is retired only after a complete authoritative feed
  snapshot. Partial reads do not imply deletion, task completion or an empty list.
  A record can be retained but stale; retrieval exposes that distinction.
- **Legacy migration:** distinct still-retained feed/calendar versions are preserved
  with original observation/expiry timestamps before repeated checkpoints are
  replaced. Migration does not invent viewing, completion or event-creation dates.

Source-owned IDs are preferred over text hashes. Cross-source duplicates require
an explicit provider identity mapping, not fuzzy title similarity. Existing
media/Ring/door/interaction event collectors retain their established event
semantics; they have not all been migrated into these buckets. In particular,
real repeated door/ring occurrences must not be mistaken for duplicate heartbeats.

## Storage, logs and recording

The private Amadeus SQLite database holds current records, meaningful changes and
signal buckets. All use the owner's existing retention horizon. Reducing retention
shortens expiry; revocation/disconnection clears the relevant projection. Repeated
saves and added bindings preserve history; removing bindings conservatively clears
the source projection. Widening a selection invalidates its completeness marker
until the next successful fetch.
Pause prevents new collection and tool access. Whole-store and subject forgetting,
private exports and scheduled pruning include the new tables. External exports,
backups and HA's own recorder remain separate ownership/retention boundaries.

Routine diagnostics should contain source health, batch counts, latency, failure
category and opaque operation IDs. They should not duplicate provider bodies,
titles, list contents, credentials or transcripts. Existing speech/debug recording
settings are unchanged; this is not a claim that all pre-existing diagnostic logs
or audio files now follow Amadeus retention. A unified recording-budget/rotation UI
is follow-up work. Never silently delete distinct private recordings as deduplication.

## Retrieval and prompts

`get_context_feed(source, query, offset, limit, view)` supports current items,
observed changes and signal aggregates. Literal search and paging keep reads
bounded (20 by default, up to 50); results report stale/partial coverage and a next
page. Offset paging reads current state and is not a frozen historical snapshot.
Source and subject consent are checked for every call. Source text is untrusted.

Ordinary preference/conversation prompts receive feed availability metadata, not
all source items. The local tool shortlist includes targeted source retrieval for
task/list/appliance/transit/history questions. Tool reply composition receives only
a bounded human-facing projection. Existing calendar/media tools remain available.
Deterministic proactive rules can inspect the full fresh normalized collection
with an explicit internal safety ceiling; the owner preview remains small.

The old 12-entity product restriction is removed. Owner selections permit up to
1000 identifiers per field and the save request has a 256 KB safety ceiling.
These are abuse/memory guards, not prompt budgets. A shared datalist avoids creating
one full option inventory per selected entity. Complete normalized provider results
are stored before generating the small compatibility preview. Source transport
limits still apply: Trakt history remains a partial bounded upstream page, for
example; this change does not claim complete provider pagination.

## Next consolidation work

1. Add resumable transport pagination and per-entity failure isolation for large
   source sets, with explicit collection coverage and backoff.
2. Map known cross-provider identities before correlating playback reports.
3. Migrate remaining heartbeat-heavy collectors after validating existing timing/history consumers. Shadow feed diagnostics
   now retain source availability metadata instead of repeated item bodies.
4. Add recording byte/time budgets and rotation controls, plus private storage
   usage breakdown. Raw recording stays separate from normalized memory.
5. Add historical period filters and snapshot-consistent cursors where needed.

No participant results or household inventories belong in this document or tests.
