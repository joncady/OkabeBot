# Alexa conversational mini-cycle

Status: the private Mac adapter is installed for silent timing tests. The
request/reply exchange is implemented and regression-tested but not deployed.
The live Alexa skill is not connected to it yet, so spoken conversational turns
are not available. The accepted destination/demo continues separately.

## Target experience

Ask Little Lab a general-knowledge question, receive a fresh answer in the
selected character's Qwen voice, ask a follow-up, then exit and recover the Pi
owner. Alexa supplies recognized text; the Mac does not transcribe it again.
The first cycle has no household tools, calendar, notifications or private chat
history. It must not acquire those capabilities through the visual relay worker.

## Boundaries and implementation sequence

1. Add `TalkIntent` with an `AMAZON.SearchQuery` slot and supported carrier
   phrases such as `tell me {Query}`. Pair a specific Echo identity before
   admitting conversation requests. Do not log utterances or raw identifiers.
2. Use a separate encrypted request queue and durable request/reply ledger,
   not the existing two-object destination mailbox or GitHub queue. Claim once
   before inference, preserve the original deadline, reject conflicting bodies,
   and do not replay uncertain work. Scope the Mac consumer and skill roles to
   their separate queue/ledger/audio responsibilities.
3. Call `LocalConversation.compose_alexa` on the existing warm worker. It has no
   tools and no access to the ordinary conversation history. Only eligible public
   exchanges enter a bounded, separate history keyed by session and character.
   A late result is consumed before releasing the model, never reused as the next
   turn. A busy model fails truthfully rather than starting a competing turn.
4. Generate and encode short Qwen audio only when eligible and before deadline.
   The application owns the audio object key, not the model or intent slots.
   Upload only non-sensitive response audio, use expiring GET URLs, and expire
   transient relay/media objects. Native Alexa text speech handles private or
   uncertain results; the optional audio path must not become a privacy bypass.
5. Integrate thinking/speaking states with the accepted Show ownership protocol.
   An unready/unassigned screen cannot display a second copy of the actor.
   Keep follow-up listening within the skill session and preserve exit recovery.

The cloud budget is six seconds for the request/worker exchange, leaving margin
inside Alexa's approximately eight-second response window. A progressive response
cannot extend it. Each network call needs a bounded timeout; expired/late output
must not start playback or execute actions. The existing model read can continue
in its isolated worker thread to consume an already-running result after the
caller has timed out. No cancellation may kill an unrelated conversation.

## Audio eligibility

Amazon's SSML audio rules prohibit customer-specific or sensitive information in
uploaded response audio. Public general-knowledge answers can use the character
voice. The model is prompted to return explicit eligibility, with a conservative
input/output detector as a second gate; malformed/uncertain output fails closed.
These checks are not a proof of semantic privacy detection. Private information
is never supplied from household tools or other chat histories, and this cycle
must not claim unrestricted private conversational audio support.

## Evidence and remaining work

Isolated tests cover skill/device pairing, opaque request/session identities,
conflicting replay bodies, fixed audio keys, timeout fallback, explicit audio
eligibility, cross-session isolation, sensitive-input fallback, malformed model
output and late-reply consumption. No audio was uploaded or played by these tests.

Remaining gates: deploy the durable cloud transport and scoped credentials; install/benchmark
the complete cloud/local audio deadlines; TalkIntent model build; Show speech
animation and follow-up listening; measured cloud/local loop; user acceptance of
two spoken questions, audibility and exit recovery. Record model, first PCM,
encoding/upload and total cloud response separately. Physical audible onset still
requires the user or an explicitly authorized recording test.

Sources: [SearchQuery carrier phrases](https://developer.amazon.com/en-US/docs/alexa/custom-skills/slot-type-reference.html#amazonsearchquery),
[response deadline](https://developer.amazon.com/en-US/docs/alexa/custom-skills/send-the-user-a-progressive-response.html),
[SSML audio and privacy requirements](https://developer.amazon.com/en-US/docs/alexa/custom-skills/speech-synthesis-markup-language-ssml-reference.html#audio).

Install the optional consumer/encoder dependencies on the controller with
`python -m pip install -e '.[alexa-conversation]'`. The adapter remains opt-in;
installing the extra does not enable it or grant cloud permissions.

## Local adapter and durable exchange

`conversation.alexa_enabled` defaults to false and requires the local conversation
backend. When enabled, the controller owns a mode-0600 Unix socket in the private
state directory under `alexa/conversation.sock`. It accepts only text, opaque
session ID and a short deadline, never an operation/tool name. It calls the same
warm model and Qwen worker without invoking physical playback. The selected voice
identity is pinned for the entire reply. PCM reads and MP3 encoding respect the
remaining deadline; late audio is rejected. It adds no LAN port or dashboard key.

`ConversationExchange` is the SDK-injected DynamoDB/SQS adapter. Conditional
create/claim/complete operations preserve the original deadline and make each
request terminal after one claim. Retried sends use a FIFO deduplication ID.
Replies stay in the private ledger; only eligible audio enters the media store.
Expiry and permission errors are distinct, with no fallback that replays inference.
The cloud resources, consumer and IAM wiring are not deployed yet.

## Silent installed benchmark (2026-10-27)

Two consecutive public questions in one isolated session generated complete MP3s
locally without playback or upload. The first encoded turn took 4.480 seconds
(model 1.672, first PCM 1.143 after voice start, synthesis 1.961, encoding 0.841).
The follow-up took 2.268 seconds (model 0.761, first PCM 0.406, synthesis 1.470,
encoding 0.034). These are individual warm observations, excluding Alexa, cloud
transport, upload and Echo buffering; they are not full round-trip guarantees.
An earlier cold trial exceeded six seconds. A missing encoder dependency was
installed in the app environment before these successful measurements.

A calendar question returned native-text-only eligibility with no synthesis.
The model has no calendar access in this path. Speaker level and Pi ownership
were preserved; no test audio was played. Broader privacy/latency evaluation is
still required before claiming general conversational parity.

The dedicated cloud transport template is prepared and passed AWS template
validation, but has not been deployed. It defines an encrypted FIFO queue with
one-minute retention, an encrypted request ledger with five-minute TTL markers
and a private generated-audio bucket with a one-day lifecycle. DynamoDB TTL
deletion is asynchronous, not an immediate five-minute purge. No public ingress
or household-tool permissions are created by this template. Scoped runtime IAM
and skill/consumer wiring are still required.

Local review found that ordinary SDK defaults could outlast the response budget.
The exchange now bounds each call with the remaining request time, limits
outstanding calls, and uses a factory with 300 ms connect/read timeouts and one
SDK attempt. A blocked-call regression proves timeout fallback returns without
waiting for a late SDK completion. Late enqueues retain the expired deadline and
cannot become a fresh inference request.
