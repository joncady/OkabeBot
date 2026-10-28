# Alexa conversational mini-cycle

Status: the private Mac adapter is installed for silent timing tests. The
separate queue, ledger and private audio bucket are deployed, and a manually run
scoped consumer passed silent cloud/local tests.
The Lambda conversation handler is connected and passed an IAM-only silent smoke
test. The English (US) Alexa interaction model built successfully on 2026-10-27
with TalkIntent. Real Show conversation, follow-up listening and recovery are now
awaiting physical acceptance. The accepted destination/demo continues separately.

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

Remaining gates: physical Show speech
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
The dedicated cloud resources and scoped Mac consumer credentials are deployed.
The consumer is manually started. The Lambda handler is connected, but its Alexa
interaction model is built; physical conversational acceptance is pending.

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

The dedicated transport and Identity Center consumer permission set were deployed
on 2026-10-27. The encrypted FIFO queue retains requests for one minute. The
request ledger uses five-minute TTL markers; DynamoDB deletion is asynchronous.
The private generated-audio bucket expires objects after one day. Its signed GET
URLs last two minutes. The consumer can receive/delete requests, read/update
ledger records, and upload only generated conversation audio. It cannot send
new requests, invoke household tools, or access the visual mailbox.

## Silent cloud/local benchmark (2026-10-27)

The real queue → scoped Mac consumer → installed local adapter → private media
store loop completed two warm public turns in 5.030 and 2.793 seconds. Fetching
the resulting MP3 added 0.270 and 0.276 seconds. First-turn local stages were
model 2.208, first PCM 0.926 after synthesis start, synthesis 1.617 and encoding
0.056 seconds; follow-up stages were 0.770, 0.340, 1.287 and 0.031 seconds.
First PCM is included in synthesis, so these columns must not be summed.
An earlier cold cloud turn timed out safely at six seconds. These observations
exclude Lambda startup, Alexa recognition, Show buffering and audible onset.
They are not physical end-to-end acceptance. No test audio was played.

Stop/Cancel and SessionEnded record a paired-session cancellation marker. Closed
sessions cannot claim queued work or return a ready answer; an inference that
finishes after exit cannot upload new audio or publish a ready reply. New sessions
remain independent. Cancellation cannot recall audio already delivered to Alexa.
Only built-in public character personas are sent to this path, never a user's
configured persona or ordinary household conversation context.

Local review found that ordinary SDK defaults could outlast the response budget.
The exchange now bounds each call with the remaining request time, limits
outstanding calls, and uses a factory with 300 ms connect/read timeouts and one
SDK attempt. A blocked-call regression proves timeout fallback returns without
waiting for a late SDK completion. Late enqueues retain the expired deadline and
cannot become a fresh inference request.


## Lambda integration checkpoint (2026-10-27)

The skill-scoped Lambda now has only the dedicated conversation queue send,
ledger put/get and generated-audio-prefix get permissions it needs. Its existing
visual destination and fixed generic demo remain separate. The identity pairing
parameter is hidden in CloudFormation output. The installed Mac adapter/worker
and manually refreshed consumer now return selected character and measured PCM
duration with each encoded reply. Speaker volume remains at the observed 26%;
no benchmark played audio or changed voice references.

An ephemeral IAM-only Lambda used the production handler and scoped role with
fixed public questions and a test-only identity adapter. It had no ASK permission,
Function URL or arbitrary-prompt input, and was deleted after each trial. It
proves handler/queue/local/audio wiring, **not** real Echo identity acceptance,
Alexa recognition, animation, microphone behavior or audible playback.

After fixes, its cold test returned generated audio in 6.918 seconds. Two warm
same-session questions returned audio in 4.285 and 4.707 seconds; downloading
those MP3s added 0.254 and 0.327 seconds. Their local stages were model
1.508 / 0.823 seconds, synthesis 1.292 / 2.406, and encoding 0.025 / 0.051.
The first-PCM times (included in synthesis) were 0.606 / 0.279 seconds.
These are observations, not latency guarantees.

Earlier Lambda trials timed out or returned native fallback. The handler now
reserves cleanup/response time from Lambda's actual remaining execution budget,
which can shorten the usual six-second generation deadline on a cold invocation.
The Alexa-only model prompt requests one sentence of at most ten words, with a
48-token generation limit; normal conversation and welcome limits are unchanged.
Malformed or late output returns a truthful fallback rather than extending the
Alexa deadline. Cold startup remains a risk to measure on the physical Show.

On a screen-backed reply, custom audio uses an APLA response track instead of
simultaneous SSML audio. The visual room is not replaced. A bounded mouth-animation
cue is applied only to the current fresh, ready, already-visible screen token
with matching character artwork. Stale/unowned/mismatched rooms receive no actor
cue; this path never summons the character or grants ownership. The cue accounts
for time since the last screen poll. It is duration-based decoration, not phoneme
lip sync, and its coexistence with live polling still needs physical acceptance.
Use the existing visit/handoff flow before testing a visible Show conversation.

Explicit Stop/Cancel can close the current document even when the voice request
has a newer Alexa session, but only with the matching current APL token and Echo
identity. A stale SessionEnded callback cannot use that shortcut. Local review
found the animation-clock issue; a regression covers it. The supported Python
3.10 future-timeout exception is normalized as well. The project virtualenv's
full regressions pass; the separate review runner lacked dependencies and used
an unsupported system Python, so its attempted test run is not acceptance evidence.


## Interaction model build (2026-10-27)

The signed-in Developer Console saved the model and Build History confirms
successful English (US) build 4 at 8:27 PM local time. It adds TalkIntent with
an AMAZON.SearchQuery slot and the `tell me`, `explain` and `answer` carriers.
Amazon's only warning was automatic addition of AMAZON.NavigateHomeIntent;
the tracked model now declares it, and the deployed handler treats it like
Stop/Cancel for both request cancellation and destination cleanup.

The console utterance profiler still reported “no model built” despite the
successful build/history, so no profiler success is claimed. The next gate is
actual spoken routing on the paired Show. For that test, Okabe's café reservation
was temporarily moved from the living-room TV to Show; the original assignments
are backed up privately for restoration. Other characters, Pi ownership and the
observed 26% speaker setting were preserved during preparation. The first physical attempt below is not accepted.


## First physical attempt and flicker corrections (2026-10-27)

Show accepted VisitIntent and the controller acknowledged arrival with the Pi
away. The user reported that the actor flickered. The attempted question reached
AMAZON.FallbackIntent, not TalkIntent, and no local conversation inference ran.
The controller subsequently returned to the Pi. This is a failed conversation
acceptance attempt, not evidence of custom reply playback or follow-up listening.

The receiver's recorded event gaps were approximately one second (maximum 2.03
seconds in the bounded visit window), so there is no evidence of a four-second
cloud polling gap in that sample. Source review instead found that the Mac worker
could skip a renewal whenever a newer Show poll arrived during controller I/O.
An isolated regression reproduces that starvation. The refreshed worker now
coalesces the newer validated poll, while still refusing closed, expired, changed
or older sessions. The four-second visibility lease and timeout recovery remain
unchanged; this is not a longer lease hiding lost connectivity.

The deployed renderer now preloads all four fixed actor poses at opacity one
behind the room cover. Readiness requires all poses to load. Blink/speaking ticks
switch a local frame index and opacity, never remote image sources. This removes
pose-fetch latency from animation, but physical stability still needs the user.
The Lambda no longer initializes the conversation SDK/ledger on display polls.
Fallback/Help retains listening without queuing or replaying a model request.
The refreshed cloud renderer and Mac worker are deployed; 432 isolated tests
passed and local review found no actionable regression.

The subsequent physical retry reached TalkIntent twice with the full six-second
generation budget, but neither attempt produced audible generated speech. Both
missed the response deadline. A bounded receiver trace also recorded an
entered → departed → entered sequence during the visit, so flicker remains open.
Silent tests with the recognized short queries took 5.34 and 3.60 seconds locally,
before cloud queue, upload and response overhead. A shorter-reply experiment still
timed out during synthesis; it is not a sufficient fix and was discarded.

The installed private adapter now reports only a fixed failure stage and elapsed
time, without exception messages or utterance content. Source includes a lease
headroom correction: translate the remaining wall-clock ownership grant into the
current receiver clock rather than subtracting two mailbox trips from its lifetime.
Repeated stale commands cannot renew that grant. After AWS reauthorization, the lease correction deployed successfully with previous
stack parameters preserved. Physical retries are paused until the audio deadline
path is reliable; the lease correction still requires a physical stability check. No voice
reference or volume setting was changed.

The temporary Okabe café reservation was restored to the living-room TV after
the failed retry. The next implementation step is a bounded, cancelable Show
response path that does not require complete speech synthesis inside the initial
intent deadline. This is planned work, not deployed behavior.
