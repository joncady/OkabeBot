# Offline prompt and tool evaluations

This is a synthetic regression benchmark for the local conversational catalog,
not a replay of household data or a claim of real-world helpfulness. The current
fixture set covers every canonical conversational tool, connected-feed source,
seeded follow-ups, casual conversation, pending memory, stop, ambiguity, unavailable
providers and untrusted source text. Raw provider MCP and camera/display maintenance
APIs outside the conversational catalog are not implicitly granted to the model.

## Turn contract

Each JSONL row in `turns.jsonl` validates against `turn.schema.json`. Expected
calls also validate against the real conversational tool schemas before inference:

```json
{
  "version": 1,
  "id": "example-volume",
  "split": "dev",
  "category": "tool",
  "tags": [],
  "input": {
    "text": "Set speaker volume to 18 percent.",
    "now": "2032-06-08T18:00:00+00:00",
    "timezone": "UTC",
    "history": [],
    "preferences": {},
    "source_context": [],
    "read_only": false
  },
  "expect": {
    "route": "tools",
    "calls": [{"name": "set_speaker_volume", "arguments": {"percent": 18}}]
  }
}
```

`input` is the only model-eligible case data. Labels, tags and expected calls never
enter the target prompt. Optional input fields include pending memory, previous
successful tools, current destination, character, action policy and synthetic tool
results. History represents actual preceding turns, not an expected answer inserted
as a hint. Source context remains untrusted facts; it is not an instruction channel.
A fixed clock supplies both tool date normalization and the isolated worker's date.

`expect.calls` is an ordered execution contract. Defaults are normalized, while
application-owned `request_id` values are excluded. Matching is exact by default.
A read case can explicitly use `argument_mode: "subset"` to test only listed
constraints while permitting an optional relevant query filter; schema validation
still applies to every supplied argument. This does not establish that arbitrary
free-text filters are semantically correct. Action parameters stay exact. Accepted
non-tool routes, forbidden tools, extra-read permission, output exclusions, memory,
session state and semantic criteria can be specified separately. Do not force one
exact string when several replies would be equally useful.

## Run

Use the app Python environment and a private config containing the local model's
`conversation.model` and argv `conversation.command`. Other provider configuration
is not imported. The worker must already be cached for offline loading. Run the CLI
in a separate process; its Python runner temporarily owns the process-wide config
environment and restores it when closed. Do not embed it inside the live server.

```sh
python -m okabebot.prompt_eval --validate
python -m okabebot.prompt_eval --model-config /private/model-config.json \
  --split dev --mode route --judge --output .local/prompt-evals/baseline
python -m okabebot.prompt_eval --model-config /private/model-config.json \
  --prompts evals/prompts/candidate-3.json --split dev --mode route --judge \
  --output .local/prompt-evals/candidate
python -m okabebot.prompt_eval --compare \
  .local/prompt-evals/baseline .local/prompt-evals/candidate
```

`route` measures the first model decision, without application shortcuts or retry
rescues. It composes conversational replies to check the real spoken-output
contract. Application-only confirmation/stop cases are excluded from this stage.
`turn` uses the real `TextConversation` and validated `LocalConversation` path,
including state, confirmations, date handling, read-only limits and continuation.
The executor returns only fixtures; missing tools fail closed. No code path falls
back to providers, hardware, live controller APIs or speech synthesis. Simulated
writes are logged so attempted intent and executed outcomes can be distinguished.

Partial diagnostic runs (`--ids`/`--limit`) never pass the benchmark gate. Raw
routing, first-model scores and final application scores are distinct: a guard
preventing an action does not make the model's decision correct. A complete run with
case errors cannot pass. Reports include
schema errors, parameter errors, unsafe requests, unauthorized simulated
executions and missing/invalid semantic judgments. A raw routing attempt is not
called an executed action.

## Tuning and held-out evaluation

`plan.json` fixes thresholds and the bounded search/plateau rule before tuning.
Tune only on `dev`; use a short coherent policy and tool schemas rather than adding
individual test utterances as phrase rules. Freeze one candidate, then run:

```sh
python -m okabebot.prompt_eval --model-config /private/model-config.json \
  --prompts evals/prompts/candidate-3.json --split holdout --mode route --judge \
  --candidate-frozen .local/prompt-evals/candidate/manifest.json \
  --output .local/prompt-evals/holdout
```

The effective prompt hash must match the frozen development manifest. Do not tune
on held-out outputs; label any later confirmation separately. Follow route-stage
selection with `--mode turn` to check the actual protected application path. A high
first-tool score is not evidence of multi-step task completion or natural replies.
A small per-tool test count is a regression signal, not a reliability guarantee.

Run directories include dataset, fixture, prompt and code fingerprints plus case
and catalog snapshots. For a legitimate label audit, `--rescore OLD --output NEW`
reuses immutable model outputs only when every selected input and split is
unchanged. Changed semantic criteria invalidate old judge scores. Keep the original
run and label-audit rationale; never rewrite labels simply to reward model errors.

## Semantic judging

`--judge` uses a tool-free local-model judge for helpfulness, grounding, continuity
and restraint. It sees the request, relevant context, actual retrieved evidence,
reply and rubric. It never authorizes a tool or changes a deterministic score.
The same model can share the generator's blind spots and inflate scores: these
ratings are advisory. `judge-calibration.json` supplies explicit good/bad contrasts
for checking that a judge detects invented actions, inferred preferences and
unsupported delivery claims. Preserve invalid judgments and report coverage.
Human review remains necessary before claiming organic conversational acceptance.

## Privacy and extension

Only invented cases and core code belong in Git. All run outputs stay under the
repository's ignored `.local/` directory, including synthetic trial scores and raw
text. Do not paste participant transcripts or private observations into a fixture,
issue, PR or public progress log. New tools need schema coverage in both splits,
source-success and source-failure fixtures, contextual references and safety
negatives. Recommend one canonical conversational capability instead of exposing
overlapping raw provider APIs without a clear distinction.

## Optional intent-gated prototype

`evals/prompts/intent-gated-v2.json` adds an `intent` policy. The first, tool-free model
call classifies conversation/lookup/action/clarify. Lookup narrows the subsequent
native router to existing read capabilities; action never broadens caller
permissions. Invalid intent output fails the case. Raw stage traces and model-call
counts are retained. Neither the archived prompt candidates nor this prototype are
accepted production defaults. This is a two-stage harness strategy, not a one-pass prompt
improvement; it is disabled unless explicitly selected in the offline runner and
has not been installed in the controller. First-model tool scores are intentionally
not reported for this policy; compare complete policy outcomes separately.

To check semantic-judge calibration without generating assistant replies:

```sh
python -m okabebot.prompt_eval --model-config /private/model-config.json \
  --calibrate-judge --output .local/prompt-evals/judge-calibration
```

An owner-configured independent judge can be selected with
`--judge-command '["python", "/private/judge_client.py"]'`. It receives one JSON
request on stdin and returns JSON with `scores`, `issues` and `reason` on stdout.
The four score keys are `helpfulness`, `grounding`, `continuity`, `restraint`, each
an integer 0–10. This command is supplied by the operator, never by case data; no
shell is used. Its local/offline or network behavior depends on the chosen client.
The default judge remains the cached on-device model, with no account or API key.

## Acceptance and next corpus revisions

Promotion requires a complete error-free protected-turn run as well as the frozen
routing thresholds. A correct tool name with an incorrect write target is an
unauthorized simulated action. Keep route-stage and protected-turn gates separate.
A provider fixture correction requires a clearly labeled rerun; it does not permit
retuning the generator or changing held-out expectations.

Future corpus revisions should broaden paraphrases and multi-step tasks, test
source-versus-sender identity binding, inclusive date ranges and contextual weekday
references, and distinguish current state from the absence of historical events.
Recommendation cases should cover explicit saved tastes, declined assumptions,
missing inventory/time/energy, and consent boundaries. Add a fresh untouched split
before using previous held-out failures for prompt development. Resolve ambiguous
product semantics with the owner, retain the original benchmark, then version the
contract rather than rewriting its scores.

## Display intent

“Show my agenda” requests a visible agenda on the current character surface when
no destination is named. Resolve the destination from the turn/application context;
ask only when there is no usable current surface. Reading the agenda aloud or in
chat alone does not satisfy this display request. Explicit destination names take
precedence over the current surface.


## Multi-turn replay

`input.task_state` can explicitly seed a bounded synthetic prior read query. For
stronger continuity tests, `--sequence --mode turn` replays a JSONL scenario in order
and carries actual prior sandbox history, query state, preferences and pending memory.
Expected calls/replies are never used as previous-turn input. Expired conversational
context is cleared while persistent synthetic preferences remain. Each scenario
starts fresh; run separate files for unrelated conversations. Initial examples are
in `evals/sequences/watch.jsonl`, `calendar.jsonl` and `chat.jsonl`:

```sh
python -m okabebot.prompt_eval --model-config /private/model-config.json \
  --dataset evals/sequences/watch.jsonl --sequence --mode turn \
  --output .local/prompt-evals/watch-sequence
```

Sequence mode is recorded in manifests and cannot be silently paired with isolated
turn mode. Composition traces and original outputs remain private, including failed
spoken-output contracts. Action grounding and target/date normalization are application
behavior; report protected-flow improvements separately from raw model selection.
Changing tool schemas (for example field-preserving PATCH parameters) changes the
catalog fingerprint and is a system comparison, not a prompt-only paired result.


### Room-temperature regression slice

`evals/room-temperature.jsonl` contains six invented development cases, also
included in `turns.jsonl`: room-assigned ambient readings, alternate rooms, missing
selection/coverage, stale observations, ambient-versus-floor selection and explicit
floor-temperature requests. They check the `home_devices` tool source and room /
measurement query keywords, plus reply values and scope. These are development
regressions, not a newly blinded validation set. No live household readings or
participant results are fixtures. The fake feed executor uses the same literal
keyword conjunction semantics as retained-record retrieval.

```sh
.venv/bin/python scripts/evaluate-prompts.py --dataset evals/room-temperature.jsonl --validate
.venv/bin/python scripts/evaluate-prompts.py --dataset evals/room-temperature.jsonl --mode turn --model-config PRIVATE_MODEL_CONFIG --output .local/room-temperature-eval
```

## Subsequent source extensions

`dataset-freeze.json` records the original benchmark, not a claim that later cases
were frozen before earlier tuning. Room-temperature and presence-history JSONL
files are labelled regression extensions. The main catalog now includes the
read-only presence report tool in both splits; this is coverage, not fresh blind
validation. Historical exposed holdouts remain diagnostic when rerun. Keep runtime
outputs private and report focused cases separately from full benchmark gates.
