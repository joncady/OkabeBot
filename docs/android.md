# Personal Android companion

The native Android pilot in `android/` reuses the existing pixel renderer and
single-character handoff. It adds native text chat, a private inbox, opt-in FCM
notifications and Android picture-in-picture. It is a personal application,
distributed as a signed APK through Firebase App Distribution, not a Play listing.
Phone hardware acceptance is separate from build/emulator checks.

## Conversation tools

Both text and voice can query the controller's existing read-only tools: household
activity, current media, connected-device health, calendar, focus status, chores,
reminders, notifications, Spotify/Echo device lists, selected context feeds and
Trakt watchlist. Existing source selection and conversation consent still apply.
The model composes a reply from the returned evidence. Missing sources remain
unknown; a successful reply is not proof of complete household coverage.

The server filters the model's tool menu and validates a read-only allowlist before
execution. Phone turns cannot move devices, change volume, control playback, create
or cancel reminders, or run other home actions. The screen's explicit call/return
buttons remain separate lifecycle operations. Preference memory remains governed
by the existing private conversation settings.

## Network and authority

Install Tailscale on the controller Mac and phone and sign into the same personal
tailnet. Enable HTTPS Serve, **not public Funnel**. A stable private `https://…ts.net`
origin fronts `okabebot.mobile_proxy` on loopback port 8772. The proxy forwards only
the companion assets, paired-screen lifecycle and `/mobile/chat`, `/mobile/voice`,
`/mobile/inbox`, `/mobile/push` routes to controller loopback 8768. Dashboard,
owner settings, publishing, arbitrary moves and smart-home controls are excluded.
Tailscale HTTPS device names appear in public certificate transparency logs;
the service itself remains private to the tailnet. No router ports are opened.

The phone creates its own device credential in app-private storage. First access
registers an **Android** destination, pending owner approval in **Locations**.
Approve it and assign an available unique scene set before calling the character.
The shared catalog includes a dedicated **Pocket Nook** for each character, so
the phone can have its own reservation without displacing the TV or Mac set.
No owner/dashboard token belongs in the app. App backup and cleartext networking
are disabled. The WebView is restricted to its configured HTTPS origin and can
request only microphone access; no Bluetooth, location or background recording
permissions are requested. Changing servers requires fresh app storage/pairing
instead of sending an existing credential to another server.
The Android manifest also declares the normal audio-routing permission required
by Chromium's communication-device microphone path. It does not request volume
changes or capture the microphone in the background.

Native chat and recorded speech use a separate per-device conversation, with the
existing private profile, pause/guest and memory-confidence policy. Their tool
callback is restricted to the read-only catalog above. Voice requires the character
on that phone and uses private native streaming with a bounded WAV compatibility
path; it never plays on a fallback home speaker. See the shared streaming contract
for buffering, cancellation and platform limitations.
Uncertain submissions are claimed before generation and never automatically retried.
Chat can be used without summoning the character. Recent chat text is in-memory
in the native view; model context and learned memory remain in private Mac state.
Offline capture/share-sheet ingestion are not implemented in this pilot.

## Firebase setup

Use a separate no-cost Firebase project and register Android package
`dev.okabebot.amadeus`. Download its `google-services.json` into `android/app/`;
this file is ignored. Only the Messaging SDK is included. Analytics, cloud memory,
Firestore, cloud inference and Cloud Functions are not needed.

The Mac's optional `mobile` extra installs `firebase-admin`. Provision a dedicated
sender service account in that project with the Firebase Cloud Messaging API Admin
role (or a custom role restricted to `cloudmessaging.messages.create`). Keep its
JSON credential at `state_dir()/mobile/firebase-service-account.local.json`, mode
0600, or provide `GOOGLE_APPLICATION_CREDENTIALS` to the installed controller.
Never bundle this server credential in the APK or check it into the repository.
The client configuration file is not a sender credential. New IAM/key grants
require the owner's account authorization.

The app's **Setup → Enable notifications** choice (labelled **Quiet Amadeus notifications** in earlier APKs) is independent of screen
approval and Android's notification permission. The owner can pause/resume its
delivery through **Locations → Phone notifications**. Ordinary foreground/token
refresh preserves an owner pause; an explicit phone setting change may update it.
Existing controller source/sender rules apply before mobile enqueueing. Generic
quiet push messages carry only an opaque event ID; titles, transcripts, health
and other personal content stay in the Mac inbox and are fetched over Tailscale.
Receiving push does not summon the character or start recording/speech. Quiet
channels are subject to the phone's owner-editable Android channel settings.

The Mac stores a deduplicated per-device inbox for seven days (the first native
view shows the most recent 50), device push tokens and one-day request claims in
`state_dir()/mobile/mobile.sqlite3`. This is private runtime state, not a trial
artifact. Existing Amadeus whole-store forgetting clears its conversation/memory;
the separate notification inbox/FCM enrollment has its own lifecycle. Revoke/forget
the Android destination to deny reads and subsequent pushes. Already delivered
generic OS notifications may remain on the phone. A failed/uncertain push is not
replayed automatically; the note remains available in the inbox. Push timing is
best-effort and the Mac must stay online for generation and private fetching.

## Build and private distribution

Use JDK 17, an Android SDK with platform 36 and the checked-in Gradle wrapper:

```sh
cd android
./gradlew testDebugUnitTest lintDebug assembleDebug
./gradlew connectedDebugAndroidTest  # a fully booted disposable emulator/device
```

For a durable personal install, create a dedicated signing keystore outside the
repository and preserve it in a private backup. Set `AMADEUS_KEYSTORE` and
`AMADEUS_STORE_PASSWORD`, then run `./gradlew assembleRelease`. Keep the same key
and increment `-PappVersionCode=N` for each distributed update. Upload
`app/build/outputs/apk/release/app-release.apk` to the project's App Distribution
page and invite only the owner. APK distribution does not require a Play listing;
installing new builds requires the phone owner's action.

In app Setup enter the private HTTPS **origin only**, save, approve the pending
Android screen in the dashboard and configure its unique scene. Enable microphone
and sound through the companion's front-loaded setup. Optional notifications ask
for Android permission separately. Saved permission choices disappear from normal
use and remain editable. Test text/preferences, call/return, tap-to-talk, phone
audio, PiP, and a generic push with Wi-Fi off/Tailscale on. These final physical
checks cannot be established from server acknowledgments.

Android tap mode uses one click to start and one to send, with a labeled recording
button and visible microphone-starting, listening and thinking states. Keep
the app running until buffered playback finishes. Switching native tabs or apps
preserves the same WebView and audio graph while the screen is awake. A bounded
paired heartbeat maintains an already-arrived destination; it does not fabricate
initial rendering readiness. Screen-off or activity close releases the destination
and cancels capture/playback. Android process termination or network loss still
falls back to the server lease timeout; background survival is best-effort without
a foreground service. Microphone capture stops when the activity loses focus. The Android document bundles its
screen scripts to avoid separate WebView script-load failures. Empty recordings
are reported separately from conversation consent or duplicate submissions; requests
are never automatically replayed.

## Persistent HTTPS service

Run the route-limited proxy with the **installed controller Python**:

```sh
python -m okabebot.mobile_proxy --hostname YOUR_MAC.YOUR_TAILNET.ts.net
tailscale serve --bg http://127.0.0.1:8772
```

Run the proxy as a user login service on macOS; the installed runtime and Tailscale
also require a user login after restart. Inspect existing Serve configuration
before adding routes. Do not overwrite another service or enable Funnel. Remote
Home Assistant access is a separate route/configuration; this restricted app
origin intentionally does not proxy HA. Disconnecting Tailscale prevents personal
content fetches while generic Firebase push may still arrive.

`python scripts/install-mobile-proxy.py --check` verifies prerequisites without
changing state. Without `--check` it creates a new user login service and refuses
to overwrite an existing one. It does not change Tailscale Serve configuration or
grant account permissions.

References: [FCM](https://firebase.google.com/docs/cloud-messaging),
[distribution](https://firebase.google.com/docs/app-distribution/android/distribute-console),
[Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve).

Private mobile synthesis holds the existing character speech lock, serializing it
with other speech and preventing the supervisor from health-restarting a busy
voice worker. A busy or failed synthesis is reported without replaying the request.

Android builds with the native reply bridge play private generated WAV replies
through Android MediaPlayer at the saved companion gain. WebView receives explicit
started/completed/failed events; failed or interrupted playback is visible and
never automatically replayed. Temporary WAVs stay in app-private cache and are
deleted on completion, failure or release. Browser-only clients retain Web Audio.

Mobile voice status includes in-memory per-stage server durations for receiving,
transcription, conversation/tool generation and synthesis. It contains no message
or audio content and resets with controller restart. Client capture, tailnet
roundtrip and native playback start are not included in server-only timings.


Capable APKs advertise native PCM streaming and request `playback_mode: "stream"`.
The generated reply then arrives through the same paired AudioHub used by other
surfaces. Native AudioTrack starts after a bounded initial buffer and reports
completion only after its playback head reaches the last content frame. Native
one-second poll wakeups help keep background reception alive while the screen is
awake; OS termination still falls back to the visibility lease. Clearing the
arrived destination lease stops native WAV and PCM playback, including queued
starts. See [streaming audio](streaming-audio.md) for the complete contract and
platform limitations. Existing APKs keep the native WAV fallback.

The Chat and Inbox screens expose the latest acknowledged proactive suggestion
through a compact explanation/feedback card. Feedback is bound to its opaque
suggestion ID; the paired route grants no owner or home-control permissions.
Uncertain submissions remain disabled until refresh rather than retrying a write.
The explanation is a recorded selection reason, not inferred emotion or attention.
