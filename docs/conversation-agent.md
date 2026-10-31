# Local conversation tool loop

Text chat and ordinary button/voice turns share the local MLX tool executor.
The model sees the registered capability schemas on every routing turn, regardless
of phrasing or tense. A tool-free conversation marker hands text/proactive dialogue
back to the existing preference policy; it does not claim a lookup happened or
save memory. Read-only tools no longer require a keyword whitelist. Existing
explicit-action, schema, approval and destination checks still govern every write.

## Execution contract

1. Choose a native typed tool call, a clarification, or ordinary conversation.
   Connected facts must use tools. Free-form factual claims from the routing pass
   are rejected rather than shown as checked answers.
2. Validate registered name/arguments. One invalid read can receive schema feedback
   before execution; invalid writes are not repaired/retried. Provider exceptions
   become bounded unknown/unavailable evidence, without exposing exception text.
3. Return a bounded, human-facing projection of results to the model. It can make
   another read or answer from evidence. Tool output cannot authorize an action.
4. Stop after three executed calls or a 60-second orchestration budget. Identical
   calls are not replayed. One explicit write can execute on the initial step;
   subsequent steps expose read tools only. Physical action uncertainty is never
   retried or reported as success. Synchronous provider execution retains its own
   timeout; the orchestration budget is not an interruptible transaction deadline.
5. Validate composed scope and reject dangling promises. If composition fails,
   return the known tool outcome rather than abandon a successful read. A final
   chat reply does not leave a background lookup pending.

The worker prepares routing and read-continuation prefix caches at startup without
executing tools. Text supplies its own bounded history; ordinary voice uses a
separate short, character-scoped history. Alexa's isolated skill conversation is
unchanged. Tool results are not automatically saved as preferences or transcripts.

## Evidence limits

- Connected task/shopping lists use `get_context_feed(source="tasks")`; local
  scheduled companion reminders use `list_reminders`.
- A current transit feed cannot establish that there were no notices earlier in
  the day. Retained changes are observed history, not exhaustive provider history.
- Household recap includes period-filtered, consented occurrence counts separately
  from its small prose sample. Provider, category and provenance remain distinct.
  User-confirmed delivery records are not Ring package detections. Motion and
  doorbells do not establish deliveries, identity or a complete visit count.
- Output checks are conservative safeguards, not proof of semantic entailment.
  A small model can still choose an irrelevant tool or misread evidence; expand
  invented evaluation fixtures when a failure is found. Never publish participant
  traces, recordings or derived personal metrics as evaluation examples.

Synthetic checks cover tense/indirect requests, read chains, invalid arguments,
call budgets, duplicate suppression, failed generation/providers, unexecuted
claims, write injection, preference handoff and the shared voice path. Live
read-only probes and physical microphone/speaker acceptance are separate checks.

## Trakt recommendations

`get_trakt_watchlist(kind, page)` reads the connected owner's want-to-watch list
on request. It uses existing Trakt authorization and respects pause/guest/setup
boundaries, without enabling scheduled watch-history observation or modifying
Trakt lists. Results have stable provider IDs and page boundaries; they do not
prove streaming availability, completion or taste. Recommendation composition
must name a returned title. Private chat history follows the existing chat policy;
this read does not add the full watchlist to the context event store.

Dated watch history, want-to-watch membership and a custom date-unknown watched
list are distinct. A list's added timestamp is not a viewing date; placeholder
Unix-epoch timestamps must not be presented as actual viewing dates. The history
API does not establish which streaming provider supplied an entry.


## Owner prompt treatments

Dashboard → Dev → Amadeus text lab → **Prompt treatments** has production-default,
candidate conversational-style, best native-tool candidate and custom choices.
Edit the conversation/preference response, post-tool continuation and optional
routing text, then explicitly apply or save as custom. Applying starts a fresh
text session and discards pending confirmations; confirmed preferences remain.
Restore production default switches back without deleting the saved custom draft.

Treatments apply only to owner text-lab requests. They are immutable per-turn
snapshots, sent to the existing worker without restart; no global worker prompt is
mutated. Voice, Android and proactive/morning requests retain their normal policies.
The full candidate is an experimental native prompt, not the separate offline
intent-gated prototype and not a claim of production acceptance. The conversational
style option keeps normal routing while changing conversation and grounded replies.

All non-default treatments are read-only and suppress new memory proposals in
application code. Tool schemas, consent, response validation and existing budgets
remain authoritative. Prompts cannot add tools or authorize actions. The production
default retains the existing owner-approved action/memory policy. The worker's
bounded cache separates system prompts; a treatment never becomes the next caller's
default. Private configuration, a bounded custom-revision trail and feedback hashes
stay in the Amadeus state directory and are removed by whole-store forgetting.
No prompt editor is exposed to paired surface or notification-publish credentials.

## Architectural direction

Keep a small application-owned workflow: resolve turn context → choose/read tools
→ validate targets/arguments → compose from evidence → stream speech. Maintain
separate conversation task state (intent, constraints, prior tool arguments, target,
missing slots) instead of reconstructing everything from transcript text. Derive
short capability descriptions from the tool registry; keep persona tone separate
from operational policy. Use deterministic temporal and entity resolution where
possible and let the model handle language and judgment within those contracts.

Constrained decoding is a useful next backend experiment for valid envelopes and
schema-shaped arguments; it cannot prove that an otherwise valid target or date
matches the user's intent. Continue held-out semantic/authorization tests. Compare
models behind the existing adapter before changing the whole harness. Independent
judge calibration and owner feedback remain necessary for conversational usefulness.
These are next-step directions, not installed new routing/decoding capabilities.

References: [small composable workflows and routing](https://www.anthropic.com/research/building-effective-agents),
[llama.cpp constrained decoding](https://github.com/ggml-org/llama.cpp/blob/master/docs/llguidance.md).


## Structured turn state and resolution

The new source checkpoint keeps a small versioned task object beside each expiring
conversation. It contains a primary read capability, allowlisted query arguments,
constraints, source target and missing slots, or a quoted conversational topic.
Only actual successful, validated call receipts can seed reusable read arguments.
Provider responses, model assertions and assistant prose never become authority.
An explicit follow-up can change query kind/genre/runtime while retaining relevant
constraints. Calendar follow-ups receive a newly resolved date window. An action,
failed turn, expired session, privacy closure or new conversation clears reusable
query context. Ordinary voice state is per character and expires after ten minutes;
text/mobile/proactive dialogue uses its existing private session boundary.

The request envelope exposes current_request, bounded recent_dialogue and task_state.
The source of each remains explicit: a task is prior query context, not proof of a
provider fact or authorization for an action. Routing is character-free. Reply
composition combines operational grounding/output contracts with a separate optional
style reference. This reduces operational policy being displaced by roleplay while
preserving character flavor in the spoken answer.

Temporal slots use local civil dates and exclusive API end boundaries. Spoken
inclusive ranges are converted once; explicitly exclusive API-keyed ranges stay
exclusive. Unclear or unsupported ranges ask for clarification. Named speech
destinations bind to one full configured name in the current user's destination
span, never to words inside the message. Current-request action framing is checked
independently of tool selection: reports and quoted speech cannot authorize a write.
Read-only callers receive an immediate limitation for an explicit known action,
without substituting an unrelated read.

Notification source and sender identity are separate slots. Delivery changes use
PATCH semantics: omitted enabled/audio/priority fields preserve existing values,
including a disabled source. Empty changes are rejected by conversational MCP
setters. Source/sender ambiguity asks for clarification rather than broadening scope.

These rules use the existing controller, local worker, tool registry and private
store; no new model service or network listener is introduced. The implementation
is a bounded workflow, not a general autonomous planner. Unrecognized language still
needs model routing and remains subject to synthetic evaluation and owner feedback.
