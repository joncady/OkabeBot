# NFC tag mappings

The owner dashboard's **NFC tags** panel maps a Home Assistant tag to an approved
companion destination. The first action is **Call companion**, using the existing
movement API, spatial transitions, scene reservations and manual-follow hold.
A successful request is not a confirmed arrival; destination readiness still applies.

## First tag, no code

1. In the Android HA app, open Settings → Tags, add a tag and write it to a sticker.
   A valid HA tag contains the standard HA tag URL and an identifier, not a token.
2. Refresh the owner dashboard and find NFC tags below Locations.
3. Choose **Scan to register**, then scan the written sticker with the HA app.
   The private learning window lasts 90 seconds; scans during it never move the character.
4. Name the captured tag, choose an approved Destination and save the mapping.
5. Scan again to call the character, or use **Test** on the saved mapping.

The dashboard also supports editing, disabling and removing a mapping. An
unmapped latest scan exposes **Map last scanned tag**, so setup can resume
without another scan. Starting registration clears the previous captured ID and
disables Save until a tag is captured, preventing accidental reuse of an earlier
tag mapping. The sticker
need not be rewritten when its action target changes. Initially there are no mappings;
no personal room/tag IDs are shipped in repository defaults. The HA link follows
`web.home_assistant_url`, not a source-code host constant. Network access to HA is
required for phone scans; this does not provision remote HA access.

## Bridge setup

Include `examples/home-assistant/tags.yaml` as an HA package. Privately configure
`okabebot_tag_url` to the controller's `/tags/source` endpoint and
`okabebot_tag_token` to its generated `.local/tags/ha-source-token`. Reload RESTful
commands and automations after HA configuration validation. The installed local
setup has this package and scoped credential configured; a real sticker scan and
resulting handoff remain the physical validation checkpoint.

The publisher forwards only tag ID, HA event-context ID and occurrence timestamp.
It cannot submit arbitrary actions, destinations, shell commands, text or URLs.
Unknown/disabled tags do nothing. Scans must be recent, persisted event IDs prevent
immediate replay across restarts, and rapid repeated scans of one tag are debounced.
Events are consumed before dispatch; failed or uncertain actions are not retried.
Removing destination approval prevents subsequent tag calls to it.

## Private state

Mappings and the latest scan outcome live in the controller's ignored private tags
folder. A bounded replay cache retains at most 64 event IDs for up to two minutes.
Learning state is process-local and expires. This is not automatic Amadeus habit
collection: a tap requests an action, and does not prove that a person completed an
activity or occupies a room. HA may independently retain scan/event history under
its own configuration. Never commit tag mappings, private scan records or credentials.

## Follow-ups

Other action types (focus, maintenance acknowledgement, shopping and media cards),
HA room import and a richer tag-writing wizard are not implemented. Extend an
explicit action registry rather than letting tag contents name arbitrary tools.
