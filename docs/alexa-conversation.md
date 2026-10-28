# Alexa conversational mini-cycle

Status: protocol and tool-free local-model path implemented in source, not
installed or exposed by the development skill. The accepted destination/demo
continues operating separately. This is not yet a working spoken conversation.

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

Remaining gates: durable cloud transport and scoped credentials; private local
controller adapter; audio encoding/deadlines; TalkIntent model build; Show speech
animation and follow-up listening; measured cloud/local loop; user acceptance of
two spoken questions, audibility and exit recovery. Record model, first PCM,
encoding/upload and total cloud response separately. Physical audible onset still
requires the user or an explicitly authorized recording test.

Sources: [SearchQuery carrier phrases](https://developer.amazon.com/en-US/docs/alexa/custom-skills/slot-type-reference.html#amazonsearchquery),
[response deadline](https://developer.amazon.com/en-US/docs/alexa/custom-skills/send-the-user-a-progressive-response.html),
[SSML audio and privacy requirements](https://developer.amazon.com/en-US/docs/alexa/custom-skills/speech-synthesis-markup-language-ssml-reference.html#audio).
