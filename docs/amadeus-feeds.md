# Amadeus context feeds

The owner-only **Amadeus setup → Context feeds** panel configures read-only
metadata adapters. These are inputs to local conversational context and silent
shadow evaluations, not independent notification or device-control workers.
Every feed choice and selected binding is editable here. New installations have
all feeds disabled. Enabling a feed explicitly permits its source metadata;
global pause and guest mode remain unchanged. Revoking an observation source in
private choices prevents both network reads and use of its retained context.

## Sources and manual setup

| Feed | Setup | Data and limits |
| --- | --- | --- |
| Tasks | Add Google Tasks or Local To-do in HA; select `todo.*` entities | Item title, hashed UID, status and optional due date. No descriptions. Google Tasks remains accessible through Google's mobile app away from HA. |
| Device activity | Enable selected phone/Mac Companion binary sensors; bind charging, focus, device-lock and optional display-awake entities | Coarse on/off/unknown; no app usage, keystrokes, GPS or sleep inference. Existing attention gates remain authoritative. |
| Room activity | Select HA `light.*`, `switch.*`, and `media_player.*` entities | Friendly label, device category and on/off/playback state only. No titles, brightness, volume, controls or occupant identity. Selected active/unknown speakers defer proactive check-ins. |
| Home devices | Add the vendor integration in HA; select `cover.*`, `climate.*` and related `sensor.*` entities | Read-only door state, thermostat mode/current/target temperature and selected sensor state. No device commands, person identity or arrival inference. |
| Appliances | Add LG ThinQ to HA; select cycle/status/error `sensor.*` entities | Friendly device label and state. Cloud upstream; no appliance commands. Alexa's ThinQ skill alone does not create HA entities. |
| Meals | Self-host Mealie, add its HA integration, select meal-plan calendars and shopping lists | Next two days of planned meals and shopping item states. Not a pantry, purchase history, nutrition or ingredient-stock inference. |
| Transit | Enable Sound Transit; select `1`, `2`, `T`, `N`, `S`, or leave blank for all rail | Current active service-alert headlines, effect, routes and known end time. Default selection is 1/2 Line; no driving/traffic provider. Agency-wide alerts remain relevant. |
| Watch history | Authorize a Trakt API application and enter its client ID/access token | Read-only latest history page within 30 days; at most 20 normalized records. Always marked partial. A watch is not a like, a shared account does not establish the viewer, and history is not streaming availability. |

HA is a shared connection for the first four feeds. In **Context feeds → Home
Assistant connection**, enter its origin and an access token privately. Prefer a
dedicated non-admin HA account; HA tokens inherit their user's permissions and are
not scoped specifically to these adapters. This code issues only allowlisted read
requests. Adding an integration or account consent in HA remains a separate step.
Google Tasks requires Google application credentials/OAuth through HA. Mealie and
Trakt are optional external accounts/services; this feature does not create them.

Credentials are stored in the existing owned 0700 Amadeus directory's 0600 SQLite
database. GET responses show whether a token is saved, never the token. Leave the
password field blank to retain it; replace it to change it. Disconnect removes the
saved connection and disables its feeds, including when environment credentials exist. Whole-store forget
removes saved feed configuration and credentials. Downloaded exports do not
contain connection secrets. The existing `.env` next to the active controller
config can also supply:

```dotenv
AMADEUS_HA_URL=http://home-assistant.local:8123
AMADEUS_HA_TOKEN=replace_privately
AMADEUS_TRAKT_CLIENT_ID=replace_privately
AMADEUS_TRAKT_ACCESS_TOKEN=replace_privately
```

Dashboard-saved values take precedence. External environment credentials survive
Amadeus forget; collection still cannot resume without fresh setup and feed
consent. Device-authorized Trakt connections refresh their tokens automatically. Manually
supplied tokens require replacement when expired. Never paste account
passwords or streaming-service cookies here. Tokens do not belong in issues or PRs.

## Streaming history recommendation

Trakt supplies a dedicated watched-history API. Its streaming sync/scrobbler is
an optional way to populate history; check supported providers, profile selection
and subscription requirements before connecting accounts. A browser-only
scrobbler does not cover arbitrary TV/phone playback. Manual Trakt check-ins or an
account export/import can be used instead. This adapter never writes watches back
to Trakt and does not scrape streaming credentials or browser sessions.

Confirmed movie titles can exclude recent watches from the saved-catalogue shadow
recommendations. Episode history does not mark an entire series watched. The
limited history window cannot guarantee that an older recommendation is new.

## Runtime and privacy

A controller background thread polls selected HA/transit feeds every five minutes
and history every thirty minutes. Browser refreshes do not initiate provider reads.
Reads have timeouts, response-size limits, no redirects, and normalized field
allowlists. The compatibility preview holds at most 20 items / approximately 3.5 KiB; its
truncation is marked partial. Complete normalized provider results are retained
separately by stable ID and retrieved in pages; the preview is not the ingestion
limit. Empty successful reads supersede old items. HA
snapshots expire after fifteen minutes, rail alerts after ten minutes and history
after two hours without refresh. The transit reader additionally rejects stale
upstream GTFS timestamps and inactive alert periods. Missing data is not an all-clear.

Conversation prompts and the private shadow log receive source availability
metadata. Item contents are available through consent-checked retrieval tools;
deterministic rules read the fresh normalized collection separately. Task due-soon, explicit appliance-complete/error
states and significant rail disruption candidates use existing home/quiet/focus/
media/calendar attention gates, in shadow only. No automatic spoken rail/task/meal
announcements or new physical actions are enabled. Context is untrusted data, not
instructions, and cannot create a saved preference without existing memory policy.
Personal outputs remain private and must never be committed.

## Extend

Declare a `Feed` in `adapters/context/__init__.py`, implement its transport reader
in `providers.py`, and add invented-wire fixtures to `test_amadeus_feeds.py`.
Transport readers return `(items, complete)`; the coordinator handles consent,
bounds, persistence and freshness. Prefer HA's shared APIs over another vendor
login when HA already exposes the needed information. Adding a genuinely new
transport requires an explicit fixed endpoint/credential contract, not accepting
URLs from titles or observations. See [adapter contracts](adapters.md).

## Upstream references

- [HA Google Tasks](https://www.home-assistant.io/integrations/google_tasks/)
- [HA To-do API](https://www.home-assistant.io/integrations/todo/)
- [HA LG ThinQ](https://www.home-assistant.io/integrations/lg_thinq/)
- [HA Mealie](https://www.home-assistant.io/integrations/mealie/)
- [Sound Transit official feeds](https://www.soundtransit.org/help-contacts/business-information/open-transit-data-otd/otd-downloads)
- [Trakt developer documentation](https://developer.trakt.tv/)

### Dashboard layout

Trakt credentials sit inside its watch-history card beside connection status. HA credentials are shared above the HA-backed feeds. Select transit lines with checkboxes and add HA entities one per row, with individual removal controls. Use Refresh rooms and entities for domain-filtered entity suggestions and room labels. Trakt offers a separate code-based sign-in. These UI changes preserve existing saved arrays and do not enable any feed automatically.

## Guided connections and room preview

Install the `home-assistant` extra for registry discovery. After saving the shared
HA connection, choose **Refresh rooms and entities**. The owner-only preview uses
HA's authenticated WebSocket registry API, shows room names and availability, and
provides entity suggestions filtered to each field's supported domain. Raw current
states and attributes are not returned to the picker. Discovery does not enable
feeds or change observation consent. Refresh is explicit, not a continuous registry
subscription; HA edits appear on the next refresh.

Approved screen destinations can be assigned to imported rooms in that same panel.
Bindings use stable area IDs and remain separate from display orientation, scene
reservations, movement and speaker routing. Renamed areas retain bindings; removed
areas are flagged for review. This is a setup overlay, not a room-presence estimate
or a full floor-plan editor.

For Trakt, create an API app and enter its client ID. New apps have no client
secret; leave that optional legacy field blank. For a legacy app, use its existing
private secret if required,
and choose **Sign in with Trakt**. Visit the displayed activation link, enter the
code, approve access, then choose **Check approval**. The controller enforces the
provider polling interval and expiry. Access/rotating refresh credentials stay in
private SQLite; approval alone does not enable watch-history collection. Disconnect
cancels pending authorization and removes the saved connection. A failed or
uncertain single-use refresh requires reauthorization rather than repeated retries.
The manual access-token path remains available for existing installations.

Google Tasks and ThinQ account consent happen in HA, not inside Amadeus. Add those
integrations in HA, then refresh discovery and select the specific lists/status
sensors. Optional Mealie requires its own server; it is not provisioned here.


## Collection and prompt budgets

The former 12-entity selection limit is removed. Select all discovers supported
entities on demand; Save feed still applies the explicit observation choice.
Current records, meaningful changes and signal aggregates share the private store
and existing retention. A separate storage-policy control adjusts aggregation
windows. Owner exports and forgetting include these projections. Conversation
prompts use source availability metadata and `get_context_feed` for current,
change-history or aggregate pages. Deterministic rules can inspect full fresh
collections independently of the bounded owner/model preview. See
[storage contract](amadeus-storage.md). Upstream partial coverage, including the
current bounded Trakt history reader, is still explicit.


## Bounded Trakt history and date-unknown lists

The watch-history feed offers `history_days` (1–365), a shared `page_budget` (1–20)
and up to 19 explicitly selected owned `watched_lists`. Defaults remain 30 days,
one history page, no custom lists. The page budget must cover at least one request
per selected source; remaining requests advance sources round-robin. The owner
picker loads one page of owned list metadata only after an explicit click. List
names are not remembered as observations until selected and separately consented.

Provider pagination headers determine exhaustion, including server-clamped page
sizes. Missing/changing metadata, failed pages or budget exhaustion retain partial
coverage and successful records; they do not falsely delete prior unseen items.
Complete means the configured history-window/list union, never lifetime coverage.
Selected list membership is `watched_date_unknown` with list provenance; `listed_at`
is never treated as a watched date. Unchecked/want-to-watch remains a different
on-demand library tool. No streaming entitlement or viewer identity is inferred.

Pause, guest, forgetting, disconnect and account rebinding are rechecked between
network reads and before persistence. Refresh rotates credentials without changing
account generation; owner rebind/revoke changes generation and cancels stale reads.
Narrowing collection scope clears excluded source context. Large/lifetime imports,
resumable cursors and historical snapshot consistency remain issue #18.

## Garage and Watts thermostats

**Home devices** is a separate owner-selected HA context feed. Its controls choose
cover, climate and related sensor entities independently. Source consent, pause,
guest mode, retention and stable-ID retrieval match the other feeds. Household
recaps can use retained state; observations never establish who operated a door
or whether someone arrived. No automatic garage or thermostat actuation is added.

Aladdin Connect exposes a garage cover through HA. Watts Home (Tekmar) 564 can use
the community `bhamiltoncx/ha-watts-home` integration: install its custom component
in HA, restart HA, then add **Watts Home (Tekmar)** and enter credentials privately.
The upstream integration supports controls, but Amadeus reads selected metadata
only. Vendor cloud access and HA configuration remain separate from observation
consent. Watts account credentials belong in HA, never this repository.

NextCentury gateways have a cloud API for usage and alerts. API documentation
requires an Admin/Developer account in its web portal; an NCSS login alone does
not establish access. No NextCentury collector is implemented or enabled here.

## Room activity

Owner-selected lights, switches and speakers use the same read-only HA connection
and stable-ID records. Polling is once a minute with 150-second freshness; it is
not an immediate transition log. Noisy repeated readings are aggregated by the
existing context storage policy. Dashboard selections and feed consent remain
editable, and pause/guest/revoke/forget apply normally.

The conversation tool retrieves `room_activity` explicitly. Household recaps may
include recorded states, with partial coverage; a light or speaker does not
establish room occupancy, identity, sleep or a physical arrival. Sonos track titles,
media URLs, brightness and volume are excluded from this feed.

For proactive check-ins, selected speakers must have a fresh complete snapshot in
an idle/paused/off/standby state. Playing, buffering, unknown, unavailable, missing
or stale states defer invitations. A lights-only selection adds no speech gate.
This additional gate does not replace existing media/focus/quiet-hours policies or
change output routing. No automatic light switch-off, energy-saving prompt or
room-presence inference is implemented by enabling this source.

### Health: private wellbeing totals

The optional **Health** HA feed reads one explicitly selected source per metric:
daily steps, sleep duration in minutes, and daily active minutes. Select a
daily-reset step total; the Android hardware step counter can instead count since
reboot. Wear OS daily steps and Health Connect are different upstream sources.
Unavailable Health Connect entities are not evidence of successful synchronization.
No heart rate, weight, raw sleep stages or other sensor attributes are imported.
Sensor timestamps and units are retained; stale/previous-day totals cannot establish
a current goal achievement. Daily source values are not added together.

**Today → Health** shows an owner-only summary. **Amadeus → Health** exposes a
user-chosen step goal, an earliest local invitation hour, enablement and an
**Others detected** override. Zero means no goal. No goal or coaching topic is
inferred from readings. Feed consent, health-goal enablement and existing coaching
opt-in/stop/snooze are separate controls. Current goal-backed support covers
movement; sleep/activity readings supply private context, not inferred diagnoses
or recommendations. Invitations are optional and nonjudgmental; fresh completion
can receive positive acknowledgment. Proactive health offers share attention,
quiet/focus/media, presence, delivery budget and the daily coaching cooldown with
morning coaching. No new notification or audio route is added.

Others detection defaults **false** as a prototype configuration, not proof that
someone is alone. An owner can override it or bind optional binary sensors that
specifically mean *another person is present*. General occupancy cannot distinguish
the owner from guests. Any bound on/unknown/missing/stale signal suppresses health
model/tool context, morning coaching and health check-ins. Bound signals are read
through HA; their current state is fresh only while the health snapshot is fresh.
A pending health offer is checked again before output, and a health conversation
is discarded when this gate closes. Actual multi-person identification and sensor
fusion remain future work; configure those signals before relying on automatic
shared-room privacy. Raw personal readings, goals and outcomes stay in private
local state, with existing retention/forget/revocation controls. No participant
records belong in the repository or issue tracker.

Entity suggestions are tailored to each field using HA registry semantics and
units, rather than listing every sensor in the domain. Health fields show only
compatible metrics; phone steps-since-reboot and sleep-confidence percentages are
not daily steps or sleep-duration candidates. Source labels distinguish Health
Connect from direct wearable/hardware sensors. Health Connect provenance does not
prove which upstream app wrote a record; verify Samsung Health sharing on the
phone separately. Existing selected custom IDs are preserved. Other semantic
pickers offer an explicit advanced domain-wide view for custom integrations;
Select all uses the currently filtered candidate set. Discovery reads metadata
only and does not enable collection or overwrite selections.

With a configured others-present binding, disabling the health feed or
disconnecting HA keeps health discussion suppressed until that binding is
explicitly removed or valid clear readings return. Health sessions also end on
coaching stop/snooze/topic removal, goal support disablement or source revocation,
including changes during reply generation. Normal delivery cooldowns do not end
an already-consented conversation.
