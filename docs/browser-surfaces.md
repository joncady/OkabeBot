# Phone and native Mac companion destinations

The companion page has a stable local path: `/companion/`. It stores a random
screen credential in that browser's local storage. Reloading or restarting the
backend keeps the same identity; clearing website data creates a new pending
screen. Different origins (HTTP vs HTTPS, hostname vs IP) have separate storage,
so bookmark the final HTTPS hostname once microphone access is configured.

## Pair and arrange screens

1. Open `http://<controller-local-name>:8768/companion/` on a phone/browser.
2. Open the authenticated dashboard, then **Locations**. First visits appear as
   pending devices; they cannot read notifications or submit voice until approved.
3. Approve the intended screen. Rename it if desired; voice commands use that
   configured name. Other approved screens are not automatically selected.
4. Drag screen tiles in the layout, or use the accessible arrow buttons. Left/right
   and above/below coordinates persist in the controller's private state.
5. Choose **Move here**, or say “Move to [location name]” from an active microphone.
   The destination must be open and online. The origin leaves before arrival.

Existing Pi and Cast adapters remain configured in `surfaces.locations`. Browser
and Mac instances are discovered dynamically and stored in
`state_dir/surface-devices.json`, including approvals, names and spatial positions.
Only credential hashes are persisted there; credentials stay on the device and
are never sent to the local model or included in dashboard links. **Revoke** drops
a browser's access. **Forget** removes an unused browser entry; revisiting requires
new approval. First-visit discovery is bounded to 32 devices. New screen names
receive a numeric suffix if they collide with another location name, ID or alias
(including persisted renames). Approval also rejects legacy ambiguous names;
rename the pending screen before approving it.

Layout coordinates determine the dominant travel axis. A receiver left of the
origin enters from its right; one above enters from below. The Pi supports all
four directions. The TV room uses its two wall doorways (vertical arrangements
select a corresponding wall); phone/Mac close-ups enter at the actual screen edge.
Movement between external screens is direct: the destination renders a ready
frame, the source confirms its exit, then the destination enters. The Pi keeps
its away sign throughout. A failed destination before departure leaves the
character at its source; failure after departure recovers to the Pi after the
visibility lease. Late acknowledgements cannot complete a newer transfer.

Availability is based on recent page activity, not network discovery alone.
Closing or losing the owner returns the character to the Pi after the visibility
lease. Browser background suspension can interrupt presence; phone PiP/background
reliability needs physical testing and is not guaranteed.

## Phone microphone and trusted HTTPS

The main mobile page has **Hold to talk**. It captures only during an explicit
hold, stops the microphone tracks on release, resamples to bounded mono 16 kHz
WAV and submits through the existing transcription/tool/speech pipeline. It
requires the companion to be present on that approved screen and rejects requests
while a turn is busy. There is no automatic replay. Permission rejection is shown
in the page. Replies now follow the location audio choice described below; browser playback
requires Enable sound.

Browsers require a secure context for microphone capture. Plain LAN HTTP supports
the character view but disables the mic. `localhost` qualifies on the Mac; it
means the phone itself when entered on a phone, so it cannot reach the Mac there.

For local HTTPS, use an already trusted certificate or generate a private LAN CA:

```sh
python scripts/setup-surface-tls.py --hostname your-computer.local --ip YOUR_LAN_IP
```

This creates private files in ignored `.local/surface-tls` and prints settings to
merge into your private config:

```json
{
  "web": {
    "allowed_hosts": ["your-computer.local:8768", "your-computer.local:8780"],
    "tls": {
      "port": 8780,
      "certificate": ".local/surface-tls/server.pem",
      "key": ".local/surface-tls/server.key",
      "ca_certificate": ".local/surface-tls/ca.pem"
    }
  }
}
```

Paths resolve relative to the configuration file. Use the generated absolute
paths when the config is in a separate installed directory. Restart the controller.
The existing HTTP/Cast routes stay available; HTTPS adds a listener on port 8780.
The controller also binds loopback on its HTTP port for the native Mac client.

Only install the CA on a phone you control after verifying it came from your
local installation. A CA grants certificate trust; keep both private keys private.
The setup script never installs a CA or alters OS trust. If configured,
`http://<controller-local-name>:8768/companion/ca.cer` serves the public CA
certificate for transfer to the phone. On Android, install it using Settings →
Security/Encryption & credentials → Install a certificate → CA certificate
(wording differs by device). Then open
`https://<controller-local-name>:8780/companion/` and allow microphone access when
you deliberately hold the button. Do not bypass browser certificate warnings.
Certificates expire; regenerate the server certificate before its one-year expiry.
Reserve the controller's LAN address or update the private listener/certificate if
DHCP changes it. The hostname path stays stable unless the computer is renamed.

## Phone picture-in-picture

**Picture in picture** captures the character canvas as a video stream and asks
for video PiP. Support is feature-detected and errors remain visible. Standard
video PiP is view-only: it cannot contain our custom clickable mic button. Return
to the main page to talk. A native Android app would be needed for a reliable
custom PiP action and background microphone lifecycle. Document PiP support must
not be assumed on a phone. No such native Android app is installed here.

The in-app browser used for development rejects video PiP, so the fallback was
verified there. The user subsequently confirmed that the physical Android phone
floats the character and keeps animating over another app. Check
animation while switching apps, closing PiP, locking the phone and changing Wi-Fi.

## Native Mac floating window

```sh
./scripts/start-mac-companion.sh
```

This builds and ad-hoc signs `~/Applications/Little Lab.app` using the installed
Swift command-line tools, then opens a floating, resizable AppKit panel containing
a WKWebView. Once built, reopen it from Applications; it does not host another
model or backend. It uses `http://localhost:8768/companion/?native=1` by default.
The panel stays above ordinary windows and can join Spaces/fullscreen spaces.
Its icon toolbar exposes **Hold to talk** and **Return companion** through accessible names/tooltips. Microphone access
uses the normal macOS/WebKit consent prompts and is restricted to the configured
origin; camera access is denied. It does not request Accessibility or screen
recording permission. macOS physical mic capture still needs user acceptance.

First launch registers a pending Mac location. Approve it in the same dashboard.
The app's website data preserves its identity. The native panel and browser page
share rendering and movement logic; neither receives the full dashboard token.
This is a local development app, not notarized distribution or an automatically
started login app.

## Verification

Native Mac compilation, fresh launch, visible character arrival and live direct
Mac → TV → Mac transfers passed. Pi status remained away throughout both direct
transfers. A generated Qwen reply streamed to the native Mac WebAudio sink and
received its playback-completed acknowledgement; the user subsequently confirmed an actual Mac microphone turn and audible reply
after the permission-dialog lifecycle fix. Browser discovery,
approval and actual Mac-to-browser handoff passed on the local Mac. TLS was
validated against the generated CA without installing system trust. Regression
coverage includes pending-device isolation, revocation, persistent layout,
readiness before departure, scoped HTTP boundaries and renderer failure. These
checks do not establish phone speaker audibility or long-running background reliability.

The user also confirmed visible animation on the physical Android phone after
first-visit discovery, approval and a live character handoff. Phone PiP was separately confirmed floating and animating. A later phone
voice test reached transcription and model response; playback retest is described below.

## Android / Samsung home-screen widget: proposed next step

A normal Android App Widget is suitable for a character portrait, latest short
status, **Summon here**, **Talk**, and **Open PiP** actions. Samsung One UI supports
standard home-screen widgets; no Samsung-specific backend is required. This needs
a small installed Android app (for example Kotlin with Jetpack Glance). Merely
bookmarking the current page creates a shortcut, not a native widget.

Keep continuous character animation in the app/PiP activity rather than treating
the widget as a live browser canvas. Widget touch/scroll and layout support are
restricted. The Talk action should open a visible recording activity, request mic
permission, and begin capture only on user action. Continuing capture in the
background requires the appropriate microphone foreground-service lifecycle;
Android's background/while-in-use restrictions still apply. Do not silently start
an always-listening service from the widget.

Reuse the existing approved-device identity and spatial location. Add a narrow
self-summon operation for deliberate widget taps; do not embed full dashboard
credentials in an Android app. This is design/backlog only, not an installed APK.
For an immediate shortcut, use Chrome's Add to Home screen on the stable page.

- [Android widget types and limitations](https://developer.android.com/develop/ui/views/appwidgets/overview)
- [Samsung Galaxy widgets](https://www.samsung.com/us/support/answer/ANS10000945/)
- [Microphone/foreground restrictions](https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start)

## Stable authenticated dashboard bookmark

Bookmark `http://<controller-local-name>:8768/` (or the configured HTTPS origin).
The dashboard imports the existing setup link's fragment only after an API
request authenticates successfully, remembers it in that browser's local storage,
and removes the fragment from the address. The controller credential already
persists across backend restarts; no public unauthenticated control endpoint was
added. A fresh browser shows **Connect this browser**, accepting the authorized
setup URL or access key once. **Forget browser access** clears only that browser's
stored credential; it does not rotate the controller credential or revoke other
browsers. Clearing website data also requires setup again. HTTP, HTTPS, IP and
hostname origins have separate browser storage. Use only trusted personal devices
for remembered full dashboard access; paired character screens remain separately
scoped and do not automatically gain dashboard access.

## Audio destinations and mobile talk controls

Each location exposes `audio_target` in the location API and an **Audio destination**
selector in the dashboard. Approved browser/Mac locations default to **This device /
linked speaker** (`device`); configured Pi/TV locations default to the existing
speaker preference. `pi` selects the Pi speaker; `beam` selects the configured
Sonos clip sink and is disabled until `audio.sonos_host` is configured. `default`
uses the existing purpose-specific preference. Announcement routing remains
separate from replies and does not automatically follow the character.

On a phone or Mac page, tap **Enable sound** once to satisfy browser autoplay
requirements. **Hold to talk** also enables the speaker on that user gesture.
The device's Bluetooth/wired speaker follows its OS audio route; the page does
not select arbitrary Bluetooth devices or bypass pairing. The page has a separate
speaker gain slider (default 50%, remembered per origin), independent of the Pi's
hardware volume. Neither changes the phone's system volume.

Speech uses bounded mono 24 kHz PCM chunks, not a complete-file wait. The server
relays chunks only to that paired device's current enabled audio session. The
browser schedules buffers using Web Audio and supplies the playback envelope to
its own character. Completion is acknowledged after scheduled buffers finish.
Revoked credentials, reconnecting sessions, suspended audio and failed playback
do not cause an automatic replay or fallback through another speaker. Losing the
page during speech can stop the reply. A new page session cannot consume old PCM.

Only successfully paired screens can poll audio. Audio upload/relay writes require
full controller authority; paired screens cannot inject arbitrary PCM. Audio
commands have their own bounded HTTP body limit; decoded chunks and total speech
length are separately checked. Short-lived capability WAV URLs support the optional
Sonos sink without exposing the dashboard token. Streaming remains experimental
until physical output has been confirmed on the selected device.

Mobile hold-to-talk blocks text selection, touch callouts and context menus. For
an easier gesture, choose **Use tap mode**: tap once to record and again to send.
Blur/cancel stops capture without submission. Recording remains capped at 20
seconds. HTTPS/permission requirements remain unchanged. Standard phone video PiP
is still view-only: return to the page for the mic controls.

## Call companion here

The companion page's **Call companion here** button summons the character onto
that approved screen through the existing movement coordinator. It does not start
a voice call, recording, or a hands-free microphone session. The button shows
**Companion is coming…** while arriving and **Companion is here** after arrival.
An unapproved screen cannot summon. The paired `/surfaces/summon` operation accepts
only an empty object and always targets the authenticated device's own location;
it cannot name another destination or substitute a preview/controller credential.
The existing prepare/render-ready/departure/arrival acknowledgements still apply.


## Implementation audit (2026-10-26)

Movement uses one controller-owned state machine, a separate direct-transfer
coordinator and the shared location registry. Voice/MCP, dashboard and paired
self-summon all call the same move operation. Names and directions come from
configuration/registered layout; the current base-adapter limit is still one Pi
and one Cast receiver, plus approved browser/Mac screens.

The live audit also repaired a Pi notification-image lifetime bug: clearing a card
could release the PhotoImage while its hidden Tk item still referenced it, blocking
movement acknowledgements. The item now rebinds before the old image is released.
Native Mac windows initialize the web view at a nonzero size and resize it with
the panel. No speaker volume or saved layout was changed.

Remaining tests: phone speaker retest, extended
background/lock/Wi-Fi recovery, and mobile/desktop multi-client contention.
Reply routing resolves once when speech starts; a reply beginning during a
movement without a stable owner now waits up to eight seconds for a confirmed
location. If it cannot settle, speech fails explicitly instead of choosing an
unrelated fallback speaker. An already-started stream stays on its original sink.
Announcements deliberately retain their independent route. These are distinct
from interactive phone PiP controls and automatic prior-TV-app restoration,
which remain follow-ups.


The first physical Mac microphone permission test revealed a native lifecycle
bug: AppKit's last-window-close policy quit the accessory app when the consent
dialog closed. The panel now owns its explicit close-to-quit behavior; closing
auxiliary permission windows no longer requests application termination. This
was a clean exit, not a backend crash. Physical speech validation follows this fix.


The user confirmed the post-fix Mac speech round trip: the panel stays open,
accepts the microphone question and plays the response on the Mac. The Mac's
current core paths are tested; phone speaker and prolonged background tests stay open.


## Ambient surface UI

Mac/phone controls now share pixel-grid icons, accessible names and the palette in
[surface design language](design-language.md). Native Mac uses a transparent,
borderless 240×310 companion with a pixel drag button and hover/focus icon toolbar.
Settings/setup expand the panel to 320×480; confirming setup restores its compact
size. Drag using the six-dot button left of the icon controls; the close icon quits the native app.
Empty areas of the window still participate in its rectangular mouse hit area;
this is not an OS desktop widget or per-pixel click-through overlay.

First use presents explicit pairing, sound and microphone checks. The permission
stream is stopped immediately and never submitted to transcription. **Ready**
dismisses setup only after capabilities succeed, or after explicitly choosing
without-microphone mode. Setup completion and tap/hold preference persist per
origin. Advanced volume, naming and permission review move under the gear icon.
Native microphone requests reuse this app's OS consent for the same restricted
origin; a new OS request occurs only when consent is undetermined. Denial never
silently grants access. Browser autoplay may still need a fresh tap after reload.

Activity is shown by the avatar and small glyphs; textual status is retained for
assistive technology and explanations remain in setup/settings. Notification
titles remain visible, since they are content rather than persistent status.
Dashboard/TV controls share square-corner tokens; Pi/TV scene renderers retain
their established pixel art. This is a shared direction, not a claim that every
surface has identical density or all future designs are implemented.


### Sonic's Green Hill scene

The compact Mac/phone page renders a small transparent grassy checkerboard island
around Sonic's feet. The TV renderer selects a larger Green Hill-inspired outdoor
scene, with its notification/agenda board and existing spatial movement anchors.
This is original code-drawn pixel scenery; other characters retain their lab.
Refresh an existing companion page to load the new environment module; a fresh
TV handoff fetches it on launch. The Pi's existing portrait renderer is unchanged.

### Compact cards and recovery

Mac and phone canvases show a shared pixel notification card: provider glyph,
readable title, one body line and a grouped-event count. Unknown providers receive
a generic glyph. Text is fitted to the 320-pixel canvas and never interpreted as
HTML; the card remains inside the captured video PiP frame.

Returning from the browser back/forward cache re-registers and polls the screen
again. In-flight responses from the old page generation are ignored. Cached-page
suspension creates a new audio session; a receiver gap of four seconds expires
old speech even when the browser retains its session identifier. Returning online
allows fresh speech, never a replay of a partially delivered sentence. A browser
may require another Enable sound tap after suspension.

Automated acceptance covers direct screen-to-screen movement during reply route
resolution, expired receiver leases, late network responses, cached-page restore,
and stale audio rejection. Physical phone lock/unlock, Wi-Fi off/on and Mac
sleep/wake still require acceptance on the actual devices.

Rejected microphone recordings (no clear speech) and transcription errors clear
the thinking expression even though they never create a conversation turn. A
completed, cancelled or failed turn also resets the desired idle activity so
device recovery does not resurrect an old loading expression.

Acceptance update (2026-10-26): the user reported completing the surface checks
except Mac wake, with no additional failure reported. Phone audio and
background/lock/Wi-Fi recovery are user-accepted; Mac sleep/wake remains open.

Mac audio recovery: the native app dispatches a wake event that rebuilds the
Web Audio playback graph, retaining the saved gain and starting a fresh session.
Enable sound explicitly rebuilds that graph too. After a submitted microphone
capture closes its separate recording context, playback is rebuilt before the
recording is sent. This handles a suspected stale local output path; a running
AudioContext or completed-buffer acknowledgement alone does not prove audible
speaker output. Physical listening remains the acceptance signal.

### Mac permission persistence

macOS microphone consent, WebKit origin permission and the setup UI are separate
layers. Native capture requests already reuse authorized OS consent for the one
trusted main-frame origin. The source now projects read-only native permission
status to the setup UI rather than treating a failed browser Permissions API
query as a new permission requirement. This check never opens the microphone.

Development builds default to ad-hoc signing. Their designated requirement is
tied to a particular binary, so native rebuilds can lose privacy-consent identity.
Use `OKABEBOT_MAC_SIGN_IDENTITY` with a consistent installed Apple signing
identity when building to preserve a stable identity across updates. It defaults
to `-` for local development; no certificates or privacy databases are created
or modified by this option. Keep the same bundle ID and app path.

See [Apple’s code-signing requirements note](https://developer.apple.com/documentation/technotes/tn3127-inside-code-signing-requirements).
