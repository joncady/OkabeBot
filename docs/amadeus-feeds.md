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
allowlists. At most 20 items / approximately 3.5 KiB are retained per snapshot;
truncation is marked partial. Empty successful reads supersede old items. HA
snapshots expire after fifteen minutes, rail alerts after ten minutes and history
after two hours without refresh. The transit reader additionally rejects stale
upstream GTFS timestamps and inactive alert periods. Missing data is not an all-clear.

Current permitted snapshots are available to text/voice preference conversation
context and the private shadow log. Task due-soon, explicit appliance-complete/error
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

For Trakt, create an API app, enter its client ID and private application secret,
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
