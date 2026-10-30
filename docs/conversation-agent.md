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
