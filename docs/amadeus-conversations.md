# Optional proactive conversations

This is a bounded first-door trial, separate from shadow habit predictions and
morning briefings. Repository defaults are off. Owner setup at `/amadeus/` offers
an explicit enable switch and an approved Pi starting destination. No cloud model,
new microphone listener or automatic TV wake is introduced.

## Flow

1. A fresh, allowlisted door-open observation after activation arms one invitation
   for that local day. Startup snapshots and duplicate openings do not re-arm it.
   This is a user-selected home proxy, not identity or room detection.
2. The controller waits for settling and a continuous clear attention window. It
   checks phone DND/report freshness, the HA focus helper, its own focus timer,
   configured household media, the primary Cast connection, busy calendar intervals,
   both quiet-hour policies, notification snooze, active turns and device readiness.
   Missing/unknown/stale gates suppress speech. An ON-only TV state is ambiguous.
3. The warm local conversation model creates one optional interest/hobby question.
   Attention is checked again after generation. The attempt is consumed before
   speech, so a crash or uncertain playback cannot repeat it. The configured Pi
   must still host the character; there is no fallback to a different room.
4. The user answers with the existing button or surface push-to-talk. There is no
   automatic recording after the invitation. Silence is accepted without a reminder.
   A bounded, short-lived conversational session handles follow-ups. Explicit
   device requests leave this session and use the ordinary validated tool path.
5. A model can propose one bounded preference with supporting words from the current
   user input. It cannot write memory. The application asks a separate confirmation;
   only an explicit affirmative to that pending question writes the usual preference. Natural affirmative sentences are accepted; conditions and corrections require clarification.
   Temporary mood/time constraints are not durable preferences. No audio sentiment
   or health inference is used. Invalid optional memory annotations are ignored without discarding a valid conversational reply. Food/drink tastes and general interests are supported alongside hobbies and media preferences.

“Not now” or “skip” ends the current exchange. “Stop asking” or “don't ask again”
during it disables the trial. “Resume reply” in private setup reopens a recent invitation’s reply session without replaying the question or rearming the daily attempt. The owner can disable it in setup at any time;
pause and guest mode also prevent invitations and preference writes. Confirmed
`context.preferences` are visible and forgettable in private memory controls.
Hobbies and personal goals can be stored, but do not yet drive specialized actions.

## Home Assistant gates

Install `examples/home-assistant/conversation.yaml` with private secrets:

- `amadeus_conversation_url`: existing controller origin plus
  `/amadeus/source/conversation`.
- `amadeus_source_token`: existing publish-only Amadeus credential.
- `amadeus_conversation_dnd_entity`: the Android Companion DND sensor.
- `amadeus_conversation_media_entities`: selected other household media endpoints.
- `amadeus_conversation_attention_entities`: DND, the focus helper and those players.

The primary Cast source is checked by the controller; avoid duplicating its
coarse ON-only HA TV state as if it were a playback signal. Other ON-only TV
states conservatively block. Choose devices explicitly; no automatic expansion of
all household entities is performed. The helper
`input_boolean.amadeus_conversation_focus` can be controlled manually or connected
to existing focus automations. It does not detect work/concentration by itself.

The publisher overwrites a small current gate snapshot, not an observation history.
It uses the phone DND entity's actual `last_reported`, rather than stamping cached
phone state as newly measured. Stale phone reports block; they mark DND unknown without discarding fresh media/focus evidence. A REST heartbeat alone
is not proof that the phone is online. The authenticated publisher cannot read
preferences, enable the trial, select speakers or submit user speech.

## Limits and acceptance

There is no room-level recipient localization in this trial. Online screens and
household occupancy do not prove where a person is; the starting location is
explicit configuration. Departure detection is not guaranteed with LAN-only phone
presence. The armed opportunity expires rather than announcing the next morning.

Automated tests cover first-door deduplication, restart consumption, attention
suppression, stale/unknown signals, private authority, separate memory confirmation
and ordinary tool routing. Actual audibility, conversational feel and interruption
quality require a user trial. Passing synthetic checks is not physical acceptance.

### Silent developer chat

The dashboard **Dev → Amadeus text lab** opens an owner-authenticated, tool-free
conversation with the selected character using the local conversation worker.
Private setup must be active, guest mode off, and preference conversations enabled.
This explicit chat does not depend on a door invitation or proactively start audio.
It shares the preference confirmation policy and confirmed preference store, while
keeping pending confirmations separate from voice sessions. Say yes or no to a
proposed memory; use Amadeus setup to inspect, correct, or forget saved preferences.
New conversation clears pending text context without deleting confirmed preferences.

The browser keeps a bounded visible chat in memory, without local-storage history.
The controller holds only bounded current reply/confirmation context in private
Amadeus storage, with a ten-minute session window and six-turn limit. Expiration is
checked on the next request. Useful/Needs work and an optional note are saved only
in ignored private state (`amadeus/text-feedback.json`, last 100 entries). Feedback
is manual review material, not automatic model training. Do not commit or export it
to public issues, PRs or progress logs. The text routes use existing dashboard owner
authentication and do not expose hardware tools or play speech.


### Confidence-based memory policy

Preference conversations now default to automatic acceptance at an evidence score
of at least 0.90. Dev → Amadeus text lab exposes an on/off switch and a threshold
from 0.90 to 1.00, shared by text and spoken preference conversations. This changes
memory acceptance only; it never enables conversations, collection or coaching.
Clear first-person taste statements whose proposed values appear literally in the
input score 0.95. Uncertainty, temporary context, quoted or third-party claims and
sensitive language reduce the score below the automatic threshold. Existing exact
evidence validation still runs first. Scores are conservative heuristics, not
calibrated probabilities. Lower-confidence proposals retain confirmation. Setting
the threshold to 1.00 requires confirmation for all current proposals.

Automatic saves retain the natural generated response rather than inserting a
verbal confirmation question. The text panel shows the saved values and score;
review and forget are available in private setup. Auto-accepted provenance is
recorded privately, distinct from an explicit confirmation. No model self-rating
can override the application evidence checks. Earlier explicit-confirmation-only
behavior described above applies when auto-accept is disabled.

### Tool-enabled dashboard chat

The developer text lab now dispatches explicit device and state requests through
`LocalConversation.text_turn`, sharing the voice path's tool schemas, grounding,
approval policy, single-action limit and no-retry behavior. It replaces the earlier
text-only, tool-free limitation. Replies stay silent; a requested tool can still
cause physical effects. The panel shows the tool used. The local tool shortlist
remains authoritative; arbitrary Home Assistant service calls are not exposed.
Calendar follow-up questions can retain the previous calendar domain. Preferences
continue through the evidence/confirmation policy and never execute device tools.

"Here" means the approved companion screen paired to the browser's existing
credential, or the location explicitly selected in the text lab. Selection is
saved per browser. With neither, the dashboard remains unlocated and movement to
"here" asks for a location; it never substitutes the character's current screen or
an inferred room. This establishes a command target, not physical user presence.

For conversational continuity, the controller retains at most eight short recent
messages, pruned to fit its bounded private record, for up to a thirty-turn,
ten-minute text session. It is isolated from the spoken invitation state. Reset
clears recent context and pending confirmation; confirmed preferences remain.
Feedback includes the most recent exchange in private local storage so the owner
can relate a rating to its response. These records are participant data, not public
regressions or documentation material. Character guidance prioritizes useful,
understated conversation rather than recurring catchphrases.

Ordinary text conversation now prioritizes answering the current question over
eliciting preferences. The model receives the actual local capability names and
descriptions, and character-directed questions cannot create owner memory proposals.
The local model remains small and may still produce weak answers; tool results can use the bounded natural reply-composition pass described below,
with deterministic factual acknowledgements as a configurable fast fallback.

Grounding refinements: “where are you” uses the live location tool and reports the
confirmed current screen, or explicitly says it is unconfirmed. Common calendar
windows (today, tomorrow, this/next week, next seven days, this month) resolve to
explicit local date boundaries and query the configured feed, including all-day
and already-started events. Week windows run Monday through the exclusive next
Monday. Replies disclose the range and single-feed scope; an empty cache is not a
claim about every calendar. Unsupported broad windows ask for dates rather than
silently defaulting to today.

A Spotify request explicitly targeting a phone requires one currently discovered,
unrestricted Smartphone endpoint. It cannot silently use the configured default
speaker. Unverified model-generated device IDs are rejected. No playback is
retried after an uncertain result. Conversational guidance avoids recycling a small
saved-interest list as if it were the user's entire personality.

### Optional phone DND gate

The main dashboard's **Respect phone Do Not Disturb** switch controls whether
Amadeus proactive conversations require a fresh phone DND reading of `off`.
Repository default: on. The owner may turn it off when that signal is not useful;
this ignores both active and unknown/stale DND for this conversation gate. It does
not change Android settings or bypass consent, home presence, general attention
freshness, quiet hours, focus, media, calendar, destination or audio-readiness checks.
The private profile setting is `conversation.interruptions.respect_dnd`, persisted
separately from conversation enablement so reconfiguring conversations preserves it.

## Grounded household questions and character flavor

Questions such as “did anything happen around the house today?” route directly
to read-only `get_home_activity`, including informal greetings. The read happens before reply composition; the model cannot skip it.
Summaries retain explicit uncertainty and have a deterministic fallback. Supported periods are
today, yesterday and the last 24 hours, using the private profile timezone. The
recap returns selected recorded door/presence, TV/media and appliance observations,
plus recent recognized household notification titles. Coverage is explicitly
partial and bounded; missing input never means the house is safe or nothing
happened. Pause/guest/no setup makes this recap unavailable. It does not query
unapproved sensors, infer viewer identity, or claim real-time state from old data.

Dashboard **Character flavor** offers Plain, Subtle (default) and Playful. This
private setting affects prompts, not voice identity or physical-device settings.
Factual tool replies remain grounded regardless of tone. Repeated lore, fictional
sensor readings and unsupported completed actions are prohibited in every mode.
Owner-only `/character/tone` changes this setting; new installs default to Subtle.

### Natural tool-result replies

Local voice and browser-chat tools now have a second, tool-free MLX pass that
turns the completed result into a short conversational answer. It uses the current
character flavor, the question, a grounded reference and bounded human-facing
fields. This applies to read and action tools. It cannot execute a tool or replay
an action; composition failure uses the known formatter result. Accepted requests
remain distinct from confirmed arrival/playback. Household coverage stays explicit
and missing records never become an all-clear.

**Natural tool replies** is on by default beside Character flavor and can be
switched off for lower latency. The preference is stored with `personality.json`;
`/character/tone` accepts `natural_tool_replies` independently of tone. The model
pass adds bounded generation time; local timing events and browser-chat
`reply_composition` report whether composition was used or a fallback occurred.
No new model service, cloud call or data collector is introduced. Tool protocol
results remain structured; only the conversation's user-facing reply is composed.

Result text is untrusted context, not instructions. Projections omit transport
configuration, credential/URL fields and internal IDs. Conservative output checks
reject tool syntax, unsupported digits and several known overclaims. These checks
are not a general semantic-proof system: useful paraphrasing and grounding still
need synthetic and owner acceptance checks as models change. Composition has no
access to the tool dispatcher or generic conversation history.
