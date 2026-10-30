# Recurring chores and NFC completion

Chores are explicit private task plans. They are not inferred from presence,
appliance use, conversational agreement or who scanned a sticker. A completion
updates the latest recorded state and sets the next due time; reminding never
marks the chore done.

## Set up a tag without code

In the owner dashboard, open **Locations → NFC tags**, register/scan a tag, then
choose **Chore reminder**. Select an existing chore or create one inline. Choose
the title and delay in days or weeks; the initial default is two weeks. Set the
repeat interval for reminders while undone. Tag enablement and chore-reminder
pause are separate controls. Existing **Call companion** tags keep their behavior.
No access key is written to the sticker; the existing scoped HA tag ingress is reused.

Saving creates a plan, not a completion. Its initial due time is the save time
plus the interval. A later real scan or explicit **Mark done** records completion
and starts the interval again. Editing cadence anchors to the last completion, or
the original plan creation if never completed; saving an unchanged plan does not
move its date. One chore can be completed from more than one mapped tag.

**Today → Chores** supports edit, Mark done, pause/resume, a configurable snooze,
and deletion. Snooze temporarily suppresses reminders without inventing completion
or changing its original due date. A tag's chore action uses **Mark done**, not a
misleading dry-run/Test label. Learning/registering a tag never completes a chore.

## Gentle persistent reminders

Overdue enabled chores remain pending until completed, paused, snoozed or removed.
They can appear on the morning card rail and in the spoken rundown when space and
repeat eligibility permit. Proactive reminders batch a few chore names and use the
existing configured location, speech opt-in and availability controls. They do not
require a new door opening when fresh permitted home/attention evidence already
exists. They do not enable speech, move the character or choose another speaker.

Quiet hours, focus, calendar availability, media playback, presence uncertainty,
pause/guest mode and audio readiness remain gates. Daily proactive invitation
count and minimum spacing are owner-editable under **Amadeus → Proactive
conversations**, shared by general check-ins and chore invitations. The default
preserves one invitation per local day; opting into a higher count does not waive
other gates or reset the durable budget. Failed/uncertain attempts consume the
shared invitation allowance; they do not count as successful chore reminders.
The per-chore repeat interval remains a separate limit.

Morning previews, rendering, generation and polling do not acknowledge reminders.
Only successful speech updates the per-chore reminder timestamp. Completion,
edits, snooze, pause, forgetting or profile changes invalidate stale facts before
speech and acknowledgment. Multiple undone chores rotate fairly, prioritizing
those not yet reminded. There is no unbounded queue of future duplicate alarms.

Persona generation supplies framing around local fact slots, not invented chores,
completion, urgency, blame or user behavior. A conversational “sure” is not a chore
completion or a preference-consent signal. Use the tag or dashboard to change task
state. The read-only `get_chores` tool can retrieve due/upcoming records for ordinary
chat and voice; it never marks done or snoozes a task.

## Private state and API

Latest plan/completion state lives under the current private Amadeus profile in
`chores.item.*` preferences, so normal memory export/forgetting includes it. The
store keeps only latest completion and reminder state plus bounded opaque replay
IDs, not a lifetime activity journal. Direct owner task actions remain usable
while background Amadeus is paused; private reminder delivery is suppressed.
Forgetting removes task plans. NFC mappings are separate device configuration;
a surviving mapping to a missing chore is inert and cannot recreate erased plans.
Remove/rebind it through the tag controls as needed.

Owner-only `/chores` reads plans. POST `/chores/save` accepts an optional stable
32-hex `id`, `title`, `interval_days` (1–365), `repeat_days` (1–30), and `enabled`.
Stable draft IDs make retried creation idempotent. `/chores/complete` and
`/chores/remove` accept `id`; `/chores/snooze` accepts `id` and `days` (1–30).
A successful create/update returns `item` plus the current `items` snapshot; a
concurrent forget/profile change can return `context_changed` without echoing an
erased item. At most 100 explicit plans are configured.

An NFC mapping uses `action: "chore_reminder"` and opaque `chore_id`, with the usual
`tag_id`, `name`, `enabled`. Publish-only HA credentials cannot enumerate plans or
change mappings. Duplicate event IDs, bounce scans and completion retries do not
postpone the due date twice. All configuration and task contents remain private;
public code/tests use invented tasks and accelerated clocks only.

## Inherited tag rooms

Map the NFC tag as usual and assign its `tag.*` entity an Area in Home Assistant.
The controller joins that entity's stable `unique_id` to the mapped scan tag ID,
never a friendly name or slug. Room/floor names are read-only HA metadata, not
duplicate manually edited chore settings. Renames and moves appear after refresh;
unassigned, removed or ambiguous tag entities contribute no guessed room.

The NFC panel offers **Refresh HA tag rooms**; the controller also refreshes every
five minutes. Cache validity is ten minutes, tied to the saved HA connection
generation. Disconnect/forget/rebind invalidates old account metadata immediately.
A failed refresh can retain last verified metadata only within that validity; it
does not establish a newly verified room. Registry reads use the existing private
HA connection and do not collect scans, infer presence or authorize more actions.

A chore linked to several tag areas retains their unique room associations. Removing
a tag mapping removes its association without deleting or completing the chore.
Owner cards and the consent-checked chore tool expose room/floor context; reminder
slots include a bounded room phrase and revalidate it before speech. Existing
completion dates, recurrence, delivery policy and action destination are unchanged.

The cache and tag mapping remain private configuration outside the Amadeus memory
store, like existing NFC mappings. They are not new participant observation history;
whole-store forgetting removes chores and the HA connection, making this cache inert.
No real tag scan or device action is required to refresh room metadata.

## Selected NFC room check-ins

Room-following is **off for existing tags**. In the NFC panel either choose
**Check in to this room & call companion**, or enable **Also use this chore scan
as a room cue** on an individual chore tag. Saving or testing a mapping does not
simulate a scan. Chore completion through the ordinary dashboard also does not
claim room presence. Only an accepted real HA scan runs this combined behavior.

Assign the tag entity to an HA Area, then bind approved screens to that area in
**Amadeus setup → Context feeds → screen room bindings**. Automatic routing works
only with one approved screen in the room. If several screens share the area,
choose one on the tag. If the area has no screen, you may explicitly select an
approved screen in another area as a fallback. A newly available unique same-area
screen takes priority over that fallback. Unapproved/unavailable destinations are
never guessed, and the room cue always remains the tag’s actual area.
Missing/unassigned/stale tag metadata or unavailable browser surfaces never cause
a guessed cross-room move. TVs may wake and replace their current app; the UI
explains this before enabling the action. Ordinary fixed-destination tag actions
remain unchanged.

A real selected scan supplies an expiring **scanner room cue**, ten minutes by
default and editable from one to thirty minutes. It is exposed to the owner NFC
panel, room preview and companion-location tool as `explicit_nfc_scan`, with
identity unknown. It never writes a home/away estimate, identifies a person, arms
a return greeting or starts continuous tracking. Cues are current private state,
not retained scan history. Private setup revisions (including pause/guest/profile changes), disabling/removing
the tag, expired/rebound HA metadata and expiry invalidate the cue.

A valid cue can exist even if no room screen is configured or movement fails.
Chore tags complete first, then make at most one movement request. Existing
freshness, durable deduplication and consume-before-action semantics prevent
automatic replay after uncertain failure. The normal surface handoff owns travel,
readiness, audio routing and its existing manual-follow hold. Cue expiry does not
force a return movement or extend that hold. No speech or volume change is added.
