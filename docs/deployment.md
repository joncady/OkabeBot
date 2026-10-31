# Current deployment and configuration

Base hosting inventory verified: **2026-10-26**; later sections distinguish
subsequent source changes and installed checks. This is the maintained inventory of the existing
installation, not the defaults for a new user. The [README diagram](../README.md#current-deployment-map)
shows the connections. Keep both documents in sync when roles or hosting change.
Private IPs, credentials, account IDs and token-bearing URLs belong in local
configuration, not this inventory.

## Personal Android and private HTTPS pilot (2026-10-30)

The separate Firebase project has an Android registration and a privately signed
pilot APK uploaded to App Distribution with only the owner invited. It remains on
the no-cost plan. A dedicated sender uses a project custom role containing only
`cloudmessaging.messages.create`; its service-account key is stored privately at
`state_dir()/mobile/firebase-service-account.local.json`, mode 0600. The installed
Mac environment includes the optional Firebase Admin SDK. An API dry-run using an
invented invalid device token reached device-token validation. A later generic
per-device push request was accepted by FCM; display on the physical phone remains
a separate acceptance check.

Tailscale is connected on the Mac with private HTTPS Serve enabled and public
Funnel disabled. The new `dev.okabebot.mobile-proxy` user LaunchAgent runs the
installed `okabebot.mobile_proxy` on **127.0.0.1:8772**, forwarding an explicit
mobile/surface route allowlist to **127.0.0.1:8768**. Live HTTPS checks returned the
companion page and denied the owner state route and unauthenticated mobile inbox.
A separate private HTTPS Serve listener on **8443** now forwards to HA on
**127.0.0.1:8123**. HA trusts only the observed Docker host gateway for forwarded
headers; its ordinary account authentication remains required. Neither listener
exposes arbitrary controller routes. The hostname belongs in private app/service configuration, not this file.

The controller's Android registration, isolated preference/context sessions,
bounded private voice replies, private mobile SQLite inbox and optional FCM worker
are installed. An idle supervised controller restart preserved the warm voice
worker, source choices and speaker settings; core/database, model, speech, Pi and
configured HA readiness were checked afterward. No speech was played during this
installation. The character was returned home before restart to avoid leaving an
orphaned Cast page. Generic pushes do not transfer character ownership.

Build, lint, synthetic authorization/retention regressions and fresh emulator
startup passed. The Android endpoint is installed, paired and enrolled for
notifications, with a dedicated Pocket Nook reservation. The updated APK includes
the native audio-routing permission required by WebView's microphone path.
Physical microphone and native buffered reply audio have been accepted. Native PiP
and foreground/background notification acceptance remain separate checks. Buffered Android
voice, manual APK updates and the lack of offline capture/share ingestion remain
pilot limitations. See [Android setup and authority boundaries](android.md).

## Amadeus setup boundary (2026-10-27)

[Amadeus](amadeus.md) now provides an owner-only setup page at `/amadeus/` on the
existing controller origin. The private routes share dashboard host/token checks
and reject paired-screen, publish-only and cross-origin access. Public static
markup contains no private settings. The native Mac installation was updated and
its authenticated settings API verified. Shadow metadata hooks are installed; the
software exposes availability separately from the saved pause/guest controls.
A controller-only supervised restart preserved the separate inference worker and
device settings. No physical source-event or audio acceptance is claimed here.

Settings, explicit preferences and coaching consent live in private SQLite under
`state_dir()/amadeus/`. The UI provides source permissions, pause/guest controls,
retention, timezone, quiet hours, coaching choices, memory CRUD and private export.
Existing calendar/media polling and interaction lifecycle hooks feed a consent-
gated collector; no additional provider polling or microphone capture was added.
Retention pruning runs on the existing source-poll loop, including while paused.

Home Assistant's metadata-only package is configured privately from
`examples/home-assistant/amadeus.yaml`. Its REST publisher and automation were
reloaded without restarting HA. The same controller port exposes
`POST /amadeus/source/ha`; a dedicated write-only credential and exact private
entity bindings are owned by `state_dir()/amadeus/ha-source-token` and
`ha-bindings.json`. HA owns corresponding private secrets and the installed package.
The publisher cannot read memory, edit setup or perform device actions. Missing
setup, revoked source permission, pause or guest mode prevents observation writes.

Door, presence, media and interaction observations remain unattributed household
context; they do not prove personal arrival, attendance, viewing or preference.
Calendar snapshots have completeness markers. Habit learning, semantic recall,
voice/MCP memory tools and learned proactive/health nudge delivery remain pending.
Whole-store forgetting removes data, consent and SQLite-stored feed credentials;
external environment/file-based integration credentials, downloaded exports and
backups remain. Private trial outcomes and setup choices stay local.

Privacy/source checkpoint A must precede live collection. Subsequent trial gates
cover shadow prediction, quiet cards, media/pantry trials and final acceptance.
See [the detailed checklist](amadeus-todo.md). The 14-day timeline begins after
source/privacy review and sufficient observation, not automatically on publication.
Alexa conversation work is paused with its failed audio-deadline acceptance
recorded below; this does not remove the accepted Show demo/destination. Pausing
development is not evidence that its manually launched cloud workers were stopped.

## Home Assistant portal navigation (2026-10-28)

The installed dashboard header now exposes the configured `web.home_assistant_url`
through the owner-authenticated state response. It opens HA's existing portal in a
separate tab, using its own sign-in; it does not transfer credentials or grant API
access. The client-reachable local hostname URL returned HTTP 200 during setup.
No new listener or integration route was added. An idle controller-only restart
preserved the existing proactive-trial configuration, state and speaker settings.

The [home-map design](home-map.md), HA registry sync, room-level person/device
fusion and native Mac BLE positioning remain proposals. Reading the locally mounted
HA registries for this audit is not evidence that a supported registry connector is
installed. Public documentation includes no household floor plan or inventory export.

## Door-armed conversational trial (2026-10-28)

The installed Mac controller now has an explicitly enabled, owner-configurable
first-door conversation trial; new-install defaults remain off. It uses the existing
warm MLX worker for tool-free invitation/reply generation, the existing Qwen speech
worker, and the configured Pi destination and push-to-talk input. There is no
ambient recording, automatic TV wake or new process/listener. Speaker levels and
ordinary action approval controls were preserved during deployment.

Home Assistant owns the optional `conversation.yaml` package, a restorable focus
helper and exact private phone/media entity selections. Its scoped publisher
updates `/amadeus/source/conversation` on the existing bridge with bounded current
DND/report freshness, focus and aggregate media gates; it cannot enable the trial,
read memory or choose a speaker. A refreshed server cache is not treated as a new
phone report. The original entity-bound door observer arms the invitation; recovery
snapshots are marked separately. Existing arrival greetings defer to the trial
while enabled, preventing a second immediate welcome.

Enable/destination state is stored as `conversation.live`; the consumed daily
attempt, short reply session and current gate snapshot remain private. Pause,
guest mode, source revocation, quiet hours, calendar busy/unknown coverage, stale
phone reports, focus, media and device/route readiness protect delivery. The Pi
must remain the current character destination; audio resolution explicitly rejects
relocation instead of falling back. No room-level recipient localization is claimed.
The power-only secondary TV source is excluded from this trial’s media gate; its
morning wake/control path remains configured. Expired DND is marked unknown without
rejecting the publisher’s current media/focus snapshot. No timeout was relaxed.
The installed reply path supports food/drink tastes and general interests; invalid
optional memory annotations do not discard a valid conversational reply. Clear
affirmative sentences confirm the pending meaning without another model call;
conditional/corrective responses remain unresolved. Owner
“Resume reply” restores recent input context without replaying invitations.
Confirmed usual preferences enter `context.preferences`; temporary mood and silence
do not. Owner memory controls expose forgetting of that preference object.

Verified in software: installed owner configuration/API, live authenticated HA
attention ingestion, healthy model/device services, synthetic button-response and
confirmation paths, and valid local speech PCM discarded without playback. Physical
invitation timing, audibility and conversational acceptance await the user trial.
The source, HA secrets/package and private database have local rollback backups.
See [conversation setup and limits](amadeus-conversations.md).

## Additional HA source survey (2026-10-27)

A read-only registry/recorded-state survey verified native LG ThinQ appliance and
Met.no weather integrations are configured in the existing HA container. This
adds vendor-cloud context upstream of HA, not a new Amadeus ingestion permission.
An Echo ambient-temperature entity and native media-player entities are available;
individual freshness/capability and physical accuracy require separate acceptance.
No new collector, device action or health alert was enabled by this survey.
Printer/BLE discovery and richer household source normalization remain planned.
Public documentation contains capability status only, not the private device map,
current readings, person state, schedules or trial outcomes.

## Deterministic morning checkpoint (2026-10-27)

The installed controller now includes a consent-gated phone-screen/alarm rule and
weather/calendar card builder. Owner configuration lives in private Amadeus system
preferences (`morning.config`), not the public controller defaults. The installed
metadata package was configuration-checked and its REST publisher/automations
reloaded. Automatic presentation uses the existing configured-TV registry and
character handoff; it adds no port, inference model or speaker action. See
[morning setup](morning.md) for the typed envelope, private bindings and controls.

Software/API readiness and isolated synthetic cue-to-summary regressions were
verified. The native deployment enables authorized collection and opt-in morning
preparation/presentation; personal selections and live source readings are not
reproduced here. The separate speech worker and device settings were preserved.
Physical acceptance of an eligible real morning, TV legibility and return to the
normal layout remains a private human checkpoint. This deterministic rule does
not enable routine learning, general proactive suggestions or health coaching.

## TV preparation and state source (2026-10-27)

The native controller includes optional per-destination TV preparation. Private
`state_dir()/tv-preparation.json` owns the local HA webhook binding, timeout and
optional TV Wake-on-LAN MAC, direct host and broadcast address. Direct and
broadcast packets are bounded to one per distinct configured target. An optional
`wake_cast` flag launches an empty, unprivileged preparation page over the existing
Cast connection for HDMI-CEC wake before HA verifies power/input. The installed
HDMI receiver uses independent power; standby behavior remains part of private
physical acceptance. Cast pools now exclude disconnected/reconnecting clients and
recreate dropped sessions instead of exposing stale availability. Warmup and
subsequent dashboard launches use fresh DashCast sessions; stale launches cannot
replace a newer visit. An already-active destination refreshes its own scoped
receiver page with a new capability, revoking unload callbacks from the old page
without changing character ownership. Long-standby and overnight acceptance remain
separate from software readiness and immediate power/input checks. HA owns the
selected Samsung media/remote entities,
input key and local-only webhook secret in its private package/secrets. The source
publisher credential can acknowledge a pending nonce but cannot initiate actions.
HA input delivery and Chromecast active-input readiness are separate checks;
automatic morning handoff aborts if either fails. A private per-TV opt-in can
accept unavailable CEC status after the HDMI mapping is physically checked; known
false input still blocks, and the owner test labels unverified fallback distinctly. No extra listener, model or
speaker route is introduced. The warm speech worker remains independent.

The Samsung integration and the preparation/state packages are installed in HA.
Owner UI exposes an explicit preparation test; standby/wrong-input physical
acceptance remains a separate checkpoint. TV history uses a separately consented
`tv_usage` source, exact private entity bindings and the existing metadata receiver.
Only power/availability states and snapshot/change markers are collected. Endpoint
references and observations stay private; on-state does not identify a viewer.
See [morning setup](morning.md) for configuration and readiness limitations.

## BLE proximity trial capability (2026-10-27)

A standalone Python-3.7-compatible BlueZ D-Bus scanner is installed alongside the
satellite scripts. The Pi adapter and target advertisement reception were checked;
existing display/voice services remained active during the setup checks. A bounded
Mac CLI trial can consume target-only events over existing SSH and request one
configured Pi handoff. It uses no new listener, pairing, persistent SSH permission,
Amadeus collection scope or startup service. Close/far calibration and physical
handoff acceptance are private trial checks, not published outcomes. Continuous
following and sustained radio/GATT/audio coexistence remain unaccepted. See
[proximity setup](proximity.md); beacon identifiers and samples stay private.

## Mac startup and Pi display night mode

The installed runtime owns a configurable `caffeinate -s -w <supervisor-pid>`
child. With AC sleep prevention enabled it recreates the assertion after runtime
replacement or login, while permitting normal Mac display sleep. Explicit sleep,
lid closure and operation without AC remain outside the hosting guarantee.
A user login is required after reboot; this is not a pre-login server.

The dedicated Docker login LaunchAgent opens Docker without foregrounding its UI.
Existing HA/MQTT containers retain their `unless-stopped` restart policies. The
unloaded duplicate controller entry was archived outside LaunchAgents and disabled;
only the installed controller entry should own the hardware. Runtime policy is
private `state/runtime/policy.json`, editable in dashboard Dev.

Pi night mode sends timezone-resolved UTC intervals to the display service, which
persists an eight-day horizon locally and controls HDMI firmware power with X11
DPMS fallback. Audio, sensor collection and networking remain running. Touch,
keyboard input or push-to-talk temporarily wake the screen; the wake duration,
night hours, timezone and enable switch are editable in Dev. Initial installed
hours were copied from private quiet-hours settings; later edits are independent.
Defaults keep night mode and Mac startup options off until explicitly enabled.
An offline controller cannot extend the saved schedule beyond its horizon.

The runtime restart, loaded login helper, policy delivery and display power command
acknowledgments were checked locally. User-confirmed screen sleep/touch wake and a
subsequent Mac reboot/login were followed by read-only database/service/connection
checks. These validate installed recovery, not every physical integration action.
No volume changes are part of this update.

## Devices and responsibilities

| Device | Hosted role / connection | Current state and limits |
| --- | --- | --- |
| Apple Silicon Mac, 16 GiB RAM | Controller, local transcription, conversation and speech inference, integration adapters, dashboard, private application state; separate Home Assistant Docker container | Active host. Native controller is supervised by a user login LaunchAgent; Docker/HA has a separate lifecycle. |
| Raspberry Pi Zero W Rev 1.1 | One Wi-Fi/SSH satellite running `hardware-lab` and `hardware-voice` systemd services | Reachable again during the 2026-10-27 scene acceptance pass; both services verified active. Wi-Fi logs show earlier carrier losses followed by reconnection. No conversation or speech model inference runs here. Legacy OS/AIY dependencies remain in place. |
| ELECROW 5-inch HDMI/USB touchscreen | Pi X11/Tk character renderer through the existing OS display configuration | USB QDtech MPI5001 touch driver and MPI5006 EDID detected. EDID reports 1024×600; previous output was 480×320. Native-mode boot configuration saved with a rollback copy. After a delayed reboot reconnect, firmware and X11 report 1024×600 at 60 Hz; renderer reports output 1024×600, canonical canvas 480×320, no animation error, and both hardware services active. No throttling flags were reported. Physical image quality and touch calibration still need user validation. |
| Google AIY Voice Bonnet, speaker, microphone and large button | Attached to that same Pi; ALSA audio and AIY button input | Hold-to-talk capture, streamed PCM playback and local music energy metering. PTT preempts the music meter. Dev volume controls the physical speaker mixer and persists on the Pi. |
| CSI camera and infrared LED boards | Attached to the same Pi; camera tools invoked by `hardware-lab` | Still capture/recording tools available. Night illumination depends on the physical IR boards and lens adjustment; it is not an always-on camera stream. |
| SwitchBot Bot | Direct Bluetooth LE from the Pi; legacy `gatttool` adapter | Press mode with application-owned request IDs. A SwitchBot hub is available for future pairing, but no hub migration is enabled. The Tuya Zigbee gateway is not its current transport. |
| Vizio TV, named JC tv | Local Cast metadata callbacks and explicitly launched companion dashboard; Home Assistant TV integration is separate | Titles, app identity, progress and reactions depend on each app's metadata. Spotify Cast observation and authorized API playback control are configured; a receiver is not necessarily an available Spotify Connect target. Scoped TV page and bidirectional Pi handoff verified; visual timing review remains. |
| Tuya gateway and door contact | Tuya cloud integration in Home Assistant | Door state feeds silent cards and the afternoon welcome shortcut. No general Bluetooth scanner/proxy or Tuya scene control is enabled. |
| Ring doorbell/camera | Ring integration in Home Assistant | Doorbell notifications use the event-to-card path. Grouped door/Ring physical acceptance remains separate; camera video is not automatically relayed to the character. |
| Echo / Echo Show and other imported Alexa devices | Alexa Devices integration in Home Assistant | Named Speak routing is available; Show speech was heard in a prior test. Silent timer/reminder schedule-card automation is enabled; real Show timer and reminder events reached delivered cards in backend verification. Context-aware room speech remains opt-in. The installed voice-history command handler is disabled. A skill-scoped AWS development endpoint serves generic Qwen audio and an APL pixel scene. Custom voice/scene, two bounded destination arrivals and Pi recovery after Alexa exit are physically accepted. The optional scoped Mac worker is manually started; one-minute, fixed Okabe/café artwork, one active session. Show remains approved but unassigned after restoring the TV café. Local household-tool/conversational-audio transport to Alexa remains follow-up. |
| Sonos Beam and bonded home-theater speakers | Mac native Sonos audioClip overlay trial | User confirmed audible Qwen speech. Trial level adjusted separately from master volume; permanent audio-routing UI and voice-following are not enabled. No native Sonos HA integration was added. |
| Native Mac companion app | AppKit floating panel with WKWebView, loopback controller HTTP 8768 | Built and opened; approved paired location, fresh launch and direct Mac ↔ TV arrival confirmed. Qwen-to-WebAudio completion verified; user confirmed a full microphone turn and audible Mac reply after the permission-dialog lifecycle fix. |
| Android phone | Home Assistant Companion app/person tracker; paired browser character target | Browser location approved and user confirmed visible animation. Phone PiP confirmed floating/animating; voice input confirmed; routed output retest pending. HA away updates remain unreliable with LAN-only access; automatic presence welcomes cannot be assumed. |
| HP Stream 7 Windows tablet | Intended browser-only dashboard console | Restart/power stability remains unresolved. It does not host the backend. Other browsers can use the same dashboard. |
| Dell Inspiron 7559 | Previous Linux/controller experiments | Not the active controller. Live-USB persistence and Linux inference compatibility remain migration work; do not start a competing controller. |
| Earlier display Pi and iPad | Spare/test hardware | Not required by the current pipeline; no active backend or adapter role is assigned here. |
| Elegoo Uno R3 + HC-SR04 | Pi USB room-sensor satellite | Uno firmware sends 115200-baud JSON to the companion Pi display service. Distance, DHT11 and tilt are published through the existing controller MQTT facade; ultrasonic wave physical validation is pending. No automatic location-follow or new Amadeus-history collector is enabled. |

Both SSH role endpoints target the same Pi. The deployed display role lives at
`/home/pi/hardware-lab`; the audio/button role lives at `/home/pi/hardware-voice`.
Each has its own private `device.local.json`. Verified selected device settings:

```json
{
  "audio_device": "plughw:CARD=aiyvoicebonnet,DEV=0",
  "audio_mixer_card": "aiyvoicebonnet",
  "audio_mixer_control": "Speaker",
  "button_backend": "aiy",
  "camera_backend": "legacy"
}
```

These are settings for the existing legacy satellite, not a recommendation to
apply legacy camera/AIY drivers to a new OS. The Bot BLE address and SSH target/key
remain private configuration. Pin assignments for a generic GPIO button are not
the active Bonnet configuration.

## Mac processes and model settings

| Component | Current setting | Configuration / ownership |
| --- | --- | --- |
| Controller / dashboard | `okabebot.bridge`, trusted-LAN bind on port 8768 | Installed private `okabebot.local.json`: `web`, `devices`, `approvals`, `notifications`, `spotify`, `character` |
| Speech recognition | Faster Whisper `base.en`, English, CPU `int8`, beam size 1 | `transcription`; model cache on the Mac |
| Conversation | Direct MLX worker, `mlx-community/Qwen3-4B-Instruct-2507-4bit` | `conversation.backend: local`, `model`, `command`; separate `.chat-venv` |
| Speech synthesis | Warm MLX-Audio Qwen3-TTS 12Hz 0.6B Base, 4-bit, streamed 24 kHz PCM | `speech.engine: local`, `worker_command`, `local_socket`; separate `.voice-venv`, private reference manifest and pinned revision |
| Character voices | English-reference Okabe, Kurisu and Sonic; original synthetic-reference Pip | Worker reports all four ready. Sonic/Pip generated samples passed transcription checks; subjective voice quality still needs user listening. Reference audio remains private. System fallback covers future unsupported characters. |
| Welcome personality | Selected profile's `welcome_persona`, with normal persona as fallback | Separate tool-free local intro generation/editing; known inbox recap appended outside the model. `notifications.generated_welcomes` enables it; fixed quips are failure fallback. Personality quality is still being tuned. |
| Codex | Optional alternative conversation backend and stdio MCP client | Repository default for fresh installs, not the active button backend. Codex conversation uses its remote service; credentials remain separate. |
| MCP server | `okabebot-mcp` / `python -m okabebot.server` when a client launches it | Stdio, no public MCP port. Local conversation uses MCP-derived schemas and the same application/server functions, without a second MCP agent loop. |
| Standard MLX HTTP adapter / advanced harness | Optional adapter evaluated; not running in production | See [runtime comparison](local-runtime-evaluation.md). Direct MLX remains selected; advanced harness is backlog work. |
| Home Assistant | Container `okabebot-home-assistant`, port 8123, pinned 2026.10.4 installation | Separate Docker restart policy and private `/config` mount; existing Alexa backport is documented in [Alexa setup](alexa.md) |

The native Mac installation is in `~/Library/Application Support/OkabeBot`.
Its `.local` contains durable inbox/clip state, notification preferences, references,
tokens and runtime metadata. The development checkout is not the running controller;
editing source does not automatically deploy it. Home Assistant currently mounts
the development checkout's ignored `.local/home-assistant` as `/config`, rather
than the native controller's installation directory. Back up both state locations.

The current source package was copied coherently into the native installation for
the TV checkpoint, with the previous package/configuration retained in a private
backup. The Pi display service gained the leased movement renderer, shared
artwork export and guarded frame scheduling; its voice service and speaker setting were preserved. Sender-rule
and regression code is now included in that package, but this TV deployment does
not imply every earlier integration received a new physical acceptance test.
The Pi reconnected after a user power-cycle during the room checkpoint; both
services were rechecked, and the SSH warning dialog was dismissed without
changing SSH configuration. A controlled receiver quit reached rendered home
in about 2.7 seconds. The speech worker was initially preserved; the existing supervisor subsequently
recovered it during testing, and its health was verified ready again.

## Integration flows and configuration

| Integration | Where it runs / source | Relevant configuration and status |
| --- | --- | --- |
| GitHub failures/deployments | GitHub → signed AWS Lambda receiver → encrypted private SQS → outbound Mac queue consumer | `notifications.github_queue_*`, repository allowlist, private signing secret. Region `us-west-2`; scoped Identity Center consumer credentials require periodic renewal. GitHub API polling is disabled in this deployment. Queue long polling remains necessary and is not GitHub API polling. |
| Calendar | Mac fetches the private Google iCal feed periodically | `.env` `ICAL_FEED`, `notifications.calendar: env:ICAL_FEED`, reminder lead 10 minutes. Calendar is read-only; OAuth/additional providers remain follow-ups. |
| Spotify observation | Mac subscribes to TV/Cast state | `spotify.source: cast`; the configured API polling interval does not make API observation active in Cast mode. |
| Spotify actions | Mac calls Spotify Web API with privately stored OAuth tokens | `spotify.playback_control: true` and explicit tool approval. Authorization callback port 8769 is used during sign-in, not as the dashboard. |
| Listen-along | Pi microphone computes an energy signal; Mac updates character activity | `spotify.listen_along: true`; dashboard Music mic can disable this separately from push-to-talk. No raw ambient stream is sent to the model. |
| TV content reactions | Mac normalizes Cast/HA metadata and resolves content/team assets; Pi renders the scene | App metadata quality varies. No always-on video/audio content recognition or movie-facts inference is implied. See [TV](tv.md) and [content reactions](content-reactions.md). |
| TV companion surface | Explicit Mac Cast launch → TV page on controller port → scoped state/readiness/animation ACKs | `surfaces.receiver: dashcast`, configured `locations` names/aliases, existing Cast connection and LAN dashboard bind. `travel_side` and duration configure pacing; `lab` selects the pixel room/title. Voice/MCP and dashboard share the named-destination operation. Voice/MCP location control passed simulated button trials in both directions. Vizio direction/OK keys were not forwarded in the physical test; experimental remote controls are off. Confirmed receiver close requests return immediately; an offline Pi retains a pending return until reconnection. Pi renders an away sign; leased commands return it on disconnect. The TV page has no transcripts or full controller credential. See [surface guide](surfaces.md). |
| Beam announcements | Native Mac → Sonos audioClip; temporary private-LAN WAV fetch during trial | Audible trial accepted. No HA Sonos integration, master-volume change or automatic routing is claimed. Audio-routing source scaffolding remains experimental; Pi remains the normal production speech/chime route. |
| Door/Ring notifications | HA package automations POST with publish-only credential to the Mac | Shared notification policy governs card grouping, quiet hours and audio. See [HA](home-assistant.md) and [Ring](ring.md). |
| Afternoon welcome | HA `door_welcome.yaml` sends an arrival-scoped request to Mac | Enabled: first closed→open door event after 15:00 HA local time, once per calendar day with restored helper. Fresh local-model character intro plus today's grounded important inbox recap; does not establish identity or absence. |
| Phone-based welcome | HA person state plus nearby door event | Installed/enabled, but reliable away/home transitions still need remote connectivity/background location validation. Cross-trigger overlap suppression prevents two greetings within three minutes. |
| Alexa speaking | Mac shared action → private HA webhook → allowlisted named Speak entity | Explicit selection only. No automatic geofence is claimed. A separate AWS custom development skill and bounded visual destination are deployed; see the acceptance notes below. |
| Codex/job completion | Local hook/wrapper → Mac inbox → Pi screen/chime | Session/job title card and configured chime, not TTS by default; same physical speaker volume control applies. |

Detailed instructions: [devices](devices.md), [notifications](notifications.md),
[local conversation](local-conversation.md), [Spotify](spotify.md),
[Home Assistant](home-assistant.md), [Alexa](alexa.md),
[Codex completions](codex-notifications.md), [Linux migration](linux-controller.md).

## Ports, private files and restart boundaries

| Endpoint / state | Location and scope |
| --- | --- |
| Dashboard 8768 | Chosen trusted-LAN address on Mac; full private URL is in installed `.local/ptt/control.json`. The URL fragment is a credential. Defaults for new installs remain loopback-only. |
| Home Assistant 8123 | Mac loopback and explicitly published LAN interface; HA account authentication is separate from the dashboard token. No remote ingress is configured. |
| Hardware 8765 / voice 8766 | Pi loopback only, reached over verified SSH. The two role configurations point to the same Pi but retain separate service directories. |
| Qwen speech socket | Private Unix socket in installed `.local`; no LAN speech endpoint. |
| Voice/character preferences | Installed local JSON, private profile/state, Pi `device.local.json` and saved `volume.local.json`; read Dev for current values instead of pinning changing volume in this doc. |
| HA packages/secrets | Ignored HA `/config` directory; arrival credential and publish-only credential are distinct. Neither is the full controller token. |
| AWS relay | Public signed-webhook receiver only; dashboard, HA, SQS and Pi services are not public. Queue/DLQ and consumer profile are private configuration. |

Start native runtime with the installed `scripts/start-mac.sh` or its login service;
use the [README supervisor instructions](../README.md#quick-start). It supervises
the controller and Qwen speech worker. The conversation worker is owned by the
controller. Home Assistant starts separately after Docker is available, and Pi
services start under systemd after the required desktop/audio setup is ready.
A Mac login is required for the per-user LaunchAgent. The optional Docker login
helper starts Docker; container restart policy alone cannot do so. This is not an
unattended pre-login server.

After changes verify: selected backend and voice readiness; both device health
checks; both Pi services; framebuffer size; HA automation enable states; queue/auth
health; then an authorized button or door test. Do not reset the daily welcome
helper or replay an uncertain physical action just to obtain a passing test.

## Keeping this current

For every hosting, hardware, service, port, model or integration-routing change:

1. Update this inventory and the README diagram in the same change. Distinguish
   configured, observed working, proposed and awaiting human validation.
2. Update the applicable setup guide/examples; preserve portable defaults rather
   than copying this installation's private addresses or credentials.
3. Verify the running installation before changing this page's deployed claims or
   verification date. Document any untested physical behavior explicitly.
4. Use the repository commit hook. Topology-affecting files require an inventory
   update or an explicit `Topology-Reviewed:` trailer explaining why it remains
   accurate, independently of the README review requirement. The hook checks review
   evidence, not the truth of the topology.

Future agents/contributors should follow [repository instructions](../AGENTS.md).

### Surface renderer polish (verified 2026-10-26)

Updated the native Mac's room web renderer and confirmed a fresh Cast arrival.
The shared preview displayed a real silent notification from the live inbox.
The room geometry is centered; Kurisu's blouse, projected door plaque and stray
floor artifact are corrected. No hosting, ports, ownership, audio routing or
volume changes. Echo Show/mobile possibilities in `surface-options.md` remain
research only; neither is registered as a live destination.


### Paired browser and Mac surfaces (verified 2026-10-26)

The native controller package now includes persistent discovery/approval and spatial
layout for browser/Mac adapters. A first visit to `/companion/` creates a pending
screen; approval is separate from discovery. The live Mac floating app was built,
approved and visibly received the character. A separate local browser test target
was approved and received a confirmed handoff from the Mac. The physical Android phone was subsequently discovered, approved as a separate
location, received the character and was confirmed visibly animating by the user.
The user also confirmed floating, animated phone PiP over other apps. A later secure phone-page voice input reached transcription and a model reply;
routed playback is being verified separately.

The existing LAN HTTP listener remains on 8768; a loopback listener on that same
port supports the native secure-context microphone page. An optional TLS listener
is enabled on 8780 with private certificate/key paths in `web.tls`; its chain was
validated using the generated local CA. No CA was installed into OS trust.
`web.allowed_hosts` includes the private mDNS hostname. The phone still needs CA
trust and microphone consent. Screen credentials live in device storage; hashes,
approvals, names and coordinates live in `.local/surface-devices.json` under the
native controller's state directory. Back up that file with the other private state.

The Pi display movement module supports vertical as well as horizontal travel and
was copied to the satellite with the previous file backed up; hardware-lab was
restarted and confirmed active. Speaker volume and voice service were unchanged.
Reply output now follows the per-location routing described below; announcement
routing remains separate. Alexa surface/skill work remains backlog only. See
[browser surfaces](browser-surfaces.md) for setup, ports, trust and test limits.

### Stable dashboard bookmark (2026-10-26)

The native dashboard client remembers successfully verified full-control access
in per-origin browser storage and cleans the setup fragment from the URL. New
browsers require the existing authorized link/key once; paired character-screen
credentials remain separate. The server still checks the persistent controller
token and trusted Host on each request. Hosting, ports, model workers and device
roles are unchanged. README's browser edge reflects remembered authentication.


### Per-location reply audio (2026-10-26)

The Mac controller now owns a bounded in-memory PCM relay for paired browser/Mac
speakers. Location `audio_target` preferences persist with the registry; reply
routing resolves the current stable owner at speech start. Browser/Mac locations
select their own output by default, gated on a recent explicitly enabled audio
session. Pi/TV defaults retain the existing speaker preference. Announcements do
not automatically follow the owner. Pi hardware volume was preserved.

Phone playback requires Enable sound; linked headphones/Bluetooth speakers follow
the phone's OS route. A browser gain slider is separate from Pi volume. Main-page
capture now supports non-selectable hold controls and tap-to-start/tap-to-send.
The user's first physical test confirmed touch behavior but no sound; investigation
found the ordinary command-body limit rejected PCM chunks. A separate bounded
PCM route and regression fix were deployed; physical playback retest is pending.
Sonos remains unconfigured in the active `audio.sonos_host`, so the Beam choice is
unavailable here until configured, even though the prior standalone overlay trial
was audible. No new Sonos or Bluetooth pairing was performed.

### Paired screen self-summon

The companion page now exposes Call companion here using authenticated
`POST /surfaces/summon`. Approved screen credentials can request movement only to
their own location; no microphone session or new full-controller privilege is
created. Ports, hosting and device responsibilities are unchanged. Isolated HTTP
tests cover unapproved/preview rejection and forbidding another destination.


### Direct transfers and native Mac audit (2026-10-26)

Deployed a direct external-screen handoff coordinator: target readiness precedes
source departure, and target entry follows the departed acknowledgement. Live
Mac → TV → Mac testing passed with Pi status continuously away; no intermediate
Pi arrival. Preparation failure preserves the source; later failure uses leased
Pi recovery. Stale acknowledgements, revoked targets and stale Cast ownership
have isolated regression coverage. Return direction is recalculated from layout.

The Pi display service was also updated and restarted to repair a notification
PhotoImage lifetime fault that prevented departure acknowledgement. Its loop
reported no animation error after repair. The native Mac app was rebuilt with
explicit initial web-view bounds and resizing. Generated Qwen speech completed
through its enabled WebAudio receiver; this proves delivery and client completion,
not a human hearing or microphone check. Phone speaker playback remains pending
because the phone page was offline during this audit. Pi hardware volume and saved
layout were preserved. Hosting, ports, model workers and topology edges are unchanged.


The first physical Mac microphone permission test revealed a native lifecycle
bug: AppKit's last-window-close policy quit the accessory app when the consent
dialog closed. The panel now owns its explicit close-to-quit behavior; closing
auxiliary permission windows no longer requests application termination. This
was a clean exit, not a backend crash. Physical speech validation follows this fix.


Mac physical speech checkpoint: after the permission-dialog lifecycle fix, the
user confirmed that Little Lab stays open and a fresh spoken question receives
its reply through the Mac. Native display, direct TV transfers, microphone input
and streamed reply output are now verified for the current installation. Phone
output and extended background/lock tests remain open; this does not establish
notarized distribution or unattended login startup of the floating app.


### Ambient companion presentation (2026-10-26)

The installed Mac/phone web companion now uses shared pixel icon controls and
explicit capability setup; its permission-only microphone stream is stopped
without recording. The native Mac app is rebuilt as a transparent borderless
floating panel with a drag grip, compact mode and expanded setup/settings. Sound
and microphone controls leave the ambient view after confirmation. Native media
capture remains limited to the configured main-frame origin and OS microphone
consent; camera requests remain denied. Dashboard/TV controls share pixel tokens.
No changes to hosting, ports, model workers, audio preferences or spatial layout.
See [design language](design-language.md) and [browser surfaces](browser-surfaces.md).


Ambient UI verification: native Swift build passed; installed expanded settings
and compact transparent character arrival were visually checked. A live reply
showed speaking and playback completion in the compact UI. Permission onboarding
is covered by setup-success, denied/skip and immediate-track-stop regressions;
phone physical output and sustained background tests remain separate checks.


### Character-switch voice recovery (2026-10-26)

Live diagnosis found the worker healthy but limited to Okabe/Kurisu references;
selecting Sonic caused voice availability to fail and disarmed hardware capture.
Deployed per-character local system fallback (`speech.local_fallback: system`).
Real generation without playback passed Kurisu → Sonic → Pip → Okabe → Kurisu;
Qwen served its referenced characters, macOS say served Sonic/Pip. Live dashboard
character switches through all four profiles reported available speech; restored
the user's Sonic selection. Controller status returned to ready. The warm Qwen
worker was preserved, as were audio routes and volumes. System fallback now has
bounded 24 kHz PCM support for browser/Beam sinks. No private reference audio was
added or published. README adds the already-local system-speech route; hosting
and ports are unchanged. Physical post-fix button review remains a user check.


### Sonic/Pip Qwen references and drag correction (2026-10-26)

Added private Sonic and original synthetic Pip references to the installed worker
manifest and restarted the supervised voice worker once to warm all four profiles.
Okabe/Kurisu references were preserved. A distorted robot-seed Pip candidate was
replaced with a clearer original synthetic reference before acceptance. Final
Sonic/Pip samples transcribed correctly; warm first-chunk times were 1.06/0.49 s,
with total generation 2.51/2.15 s for roughly 3.5/3.4 s of speech. These are short
synthesis samples, not full button-roundtrip benchmarks. No new model training,
paid service or reference audio publication occurred.

The native Mac grip moved from above the canvas to beside its icon toolbar and
uses explicit pointer-delta movement, including unfocused first clicks. User
confirmed dragging works; then requested a bolder button, implemented with a dark
pixel panel, border and brighter larger dots. Sonic's shared web avatar now uses
its existing sprite palette, peach belly/arms, white gloves, red striped shoes and
an uncropped head silhouette rather than generic human clothing. This changes
Mac, phone and TV avatar rendering; Pi art remains its original style. Hosting,
ports, configured locations and speaker volumes are unchanged.

### Sonic environment checkpoint — 2026-10-26

The Mac controller’s installed web assets now include Sonic’s Green Hill-inspired
scene. Mac and phone companions render a transparent grassy island; the TV
renderer uses an outdoor landscape with the existing movement anchors and an
in-world notification sign. Other characters retain the pixel lab. This is a
presentation change; hosting, ports, model workers and integration routes are
unchanged. The Pi portrait renderer is unchanged.

The installed static asset returned HTTP 200. Compact and TV canvas previews were
rendered and visually inspected, and isolated web and HTTP tests passed. The Mac
companion was reopened to load the assets. A physical TV handoff and phone review
of this scenery remain unverified; no TV playback was interrupted for testing.

### Surface notifications, routing and recovery — 2026-10-26

Installed on the Mac controller: shared compact notification cards (provider
glyph, title/body and grouped count), reply routing that waits up to eight seconds
for movement to settle, and browser back/forward-cache recovery. Announcements
retain their configured speaker; streams already underway stay pinned to their
original sink. A failed route lookup no longer silently redirects speech.

The bounded browser audio relay now expires buffered speech after a four-second
receiver gap, including reconnects using the same session. Cached-page suspension
uses a fresh audio session and rejects late responses. No hosting, ports, model
workers, location configuration or volume settings changed; README topology
reviewed and remains accurate.

Verification: 301 Python tests and 32 web tests passed, including isolated direct
handoff/audio resolution and recovery regressions. Compact canvas card preview
was visually inspected. Wheel and source package audits passed. Installed static
assets returned HTTP 200, the controller retained the selected character and Pi
owner, and live read-only reply resolution returned the configured Pi route. The
Mac app was reopened for fresh assets. Physical phone audio/background/lock/Wi-Fi
and Mac sleep/wake acceptance remain open; these were not simulated as physical
success.

### Rejected-recording animation cleanup — 2026-10-26

An observed no-speech recording returned the controller to Ready while leaving
the character thinking. The Mac controller now clears activity for recordings
that do not reach a model turn, including transcription errors, and resets the
desired activity on turn completion/cancellation/failure. Deployed after the
subsequent live turn finished; 302 Python tests and package audits passed. The
installed cleanup and live controller/display idle status were checked. Hosting,
ports, integration routes and volumes are unchanged; README topology reviewed.

### User surface acceptance — 2026-10-26

The user reported testing everything in the preceding surface acceptance round
except Mac wake. With no further failures reported, phone audio, background/lock
return and Wi-Fi recovery are recorded as user-accepted. This is physical user
feedback, not an automated observation. Mac sleep/wake remains unverified. No
runtime configuration, volume, hosting or integration routes changed.

### Mac silent-playback recovery — 2026-10-26

A user reported mouth animation without audible Mac speech. The controller
routed that turn to the Mac and received playback completion; Little Lab gain
and system speaker output were both 50%, with system mute off. These signals
did not establish audible playback. After rebuilding the native app/playback
graph, the user confirmed hearing the short Mac audio test. A stale local output
path is suspected, not proven as the underlying cause.

Installed recovery recreates Web Audio on native wake, explicit Enable sound,
and after submitted microphone capture closes its recording context. It preserves
gain and invalidates old speech sessions. Swift typecheck and 33 web tests passed.
No controller/model restart, volume change, output-device change or permission
expansion was needed. Physical full sleep/wake recovery remains pending, as does
a fresh microphone-to-speaker check after this recovery change. Hosting and ports
are unchanged; README topology reviewed.

### Permission persistence audit — 2026-10-26

Observed native build is ad-hoc signed with a binary-specific designated
requirement. No valid Apple Development or Developer ID Application signing
identity was found. Rebuilding/re-signing can therefore affect privacy-consent
persistence; this is distinct from the misleading setup state after an unavailable
browser permission query.

Source-only changes add trusted native read-only microphone status for setup,
plus the optional `OKABEBOT_MAC_SIGN_IDENTITY` build setting. Swift typecheck
and 34 web tests passed. These changes have **not** replaced the running app or
its web assets: the working audio deployment was preserved to avoid another
ad-hoc rebuild and possible permission prompt. A consistently signed build and
relaunch/permission acceptance remain follow-ups. No permissions, certificates,
volumes, hosting or integration routes changed; README topology reviewed.

### Alexa read-only audit — 2026-10-26

Home Assistant is running; its Alexa Devices UI lists eight devices and 108
entities. Show reports Connected and Idle, and has a recent voice event. Five
controller speaker destinations pass local dry-run validation; no new speech
was sent and this does not establish present playback on each device.

Recent container logs repeatedly report failed communications-settings refreshes
using cached values. The installed sensor implementation marks notification
sensors unavailable when there is no next occurrence, so the empty Show timer,
alarm and reminder sensors alone are not proof of a broken integration. An
active-timer test remains needed. No Alexa timer/voice-event automation is
installed in the mounted packages; named-speech webhook and optional context
speech packages are present. The example timer bridge requires review for this
version’s idle-unavailable behavior before installation. Runtime settings,
volumes, permissions and topology were unchanged by this audit.

### Alexa timer/reminder schedule cards — 2026-10-26

Installed `examples/home-assistant/alexa.yaml` into the active Home Assistant
package directory and validated the complete configuration. Reloaded RESTful
Command and Automations without restarting Home Assistant or the controller.
The UI confirms `OkabeBot - Alexa timer and reminder cards` is enabled.

The automation discovers only imported Alexa Devices next-timer/next-reminder
sensors, accepts idle-unavailable to future transitions, skips initial creation
and non-state changes, and publishes silent normal-priority cards through the
existing publish-only credential. Due timestamps are normalized for persistent
deduplication. No completion/cancellation alarm or countdown is inferred from
stale polling data; Alexa still handles real alarms. No new port, AWS resource,
account permission, speaker route or volume setting was added. README topology
now labels Alexa schedules on the existing HA-to-controller edge.

Verification: HA configuration check passed, 305 Python tests passed, and the
actual HA REST action returned HTTP 200 for a clearly labelled silent bridge-test
card that the controller marked delivered. A real ten-minute timer and
fifteen-minute reminder on Show were requested for physical acceptance; their
Amazon-to-sensor-to-card path remains pending. Polling may delay discovery by
five minutes and exposes only the next schedule per device/type.

Live Alexa schedule acceptance update (2026-10-26): after the user created a
ten-minute timer and fifteen-minute reminder on Show, the existing authenticated
Amazon notification API returned both as active and matching Show. No credentials
or reminder content were printed by the read-only diagnostic. Home Assistant
then updated its sensors and both real schedule cards were received and marked
delivered by OkabeBot with silent audio. Physical visual confirmation is separate.

The installed HA coordinator debounces requested refreshes for 300 seconds, and
its device refresh waits for communications settings before publishing sensor
data. Therefore a manual entity refresh is not immediate and five minutes is a
polling interval, not an end-to-end latency guarantee. No polling interval or
Amazon dependency was changed.

### Deliberate Alexa voice bridge checkpoint

Installed the scoped `/alexa/events` controller route and Home Assistant voice
package. Active configuration initially allowed Show’s voice-event entity; the user subsequently added the upstairs Echo below. The bare
summon default is the existing configured Pi destination; qualified movement
resolves names/aliases from the registered location inventory. The HA enable
helper was verified off on first load, then enabled for the requested test.
Repository defaults remain disabled with an empty device allowlist.

The route accepts only fresh allowlisted phrases, uses a separate local bearer
credential, claims event timestamps persistently before side effects and rejects
busy/ambiguous/unapproved targets. It does not expose general tools or arbitrary
conversation input. Explicit voice welcomes reuse the existing generated intro,
important-update recap and speech/quiet policy. No ambient room speech is enabled.

Deployment copied only backend modules/configuration, preserving the working
web/native audio deployment and source-only permission-status fix. Controller
restart retained the warm model worker, selected character, Pi owner and volume.
HA configuration validation and 312 Python tests passed. A fresh unmapped request
returned HTTP 200 with accepted=false, without an action; physical welcome and
movement phrase checks remain pending. No new port, AWS service or public ingress
was introduced. The README diagram now labels the scoped HA command route.

Schedule-card acceptance clarification: the user saw one schedule card and assumed
the other appeared. Backend delivery of both timer and reminder is verified, but
only one card has explicit physical visual confirmation.

The actual HA `rest_command.okabebot_alexa_voice` action also returned HTTP 200
with accepted=false/unmapped=true for an inert probe, confirming the new scoped
credential and route without triggering speech or movement.

The user subsequently selected an upstairs Echo for testing. Its imported voice
event was added to both allowlists alongside Show; the configured speaker route
was preserved. HA configuration check passed and automations were reloaded.
The first upstairs phrase attempt did not produce a fresh voice event or claimed
controller action. HA logged an Amazon connection failure; event-feed recovery
is being checked before treating the phrase mapping as physically verified.

Alexa feed recovery: reloading only the existing Alexa Devices entry completed
without reauthentication and restored device connectivity entities to on. The
user was asked to repeat the upstairs phrase after reconnection. A restored
connectivity state is not yet proof that voice-event delivery or phrase mapping
works; those checks remain pending.

Voice-event compatibility hardening: live upstairs events used generic
voice_command=Request with the actual user utterance in voice_reply. Enabled
Request/subtitle interpretation only for that verified source. Source inspection
also confirmed HA event state is receipt time, not Amazon record time, so added
the version-guarded `source_timestamp_ms` compatibility patch to the existing
HA 2026.10.4 event adapter. Original file is backed up in the private HA mount.
No dependency, account permission or credential change was made. Missing original
time now fails closed; the controller also persists a per-source timestamp
watermark, including a conservative migration barrier for older event ledgers.
Commands were temporarily disabled during the change, then re-enabled after
317 Python tests passed. Restarted the HA container to load the small event
attribute patch; the Mac model workers stayed running. Physical acceptance is
still pending after this recovery/format change.

Latest Alexa phrase verification remains incomplete: the upstairs Echo entity
exposed the new original-source timestamp attribute, confirming the compatibility
patch loaded, but its retained utterance was old and no voice action was claimed.
The replay/freshness guard correctly left it unexecuted. Subsequent inspection
found Amazon connection/DNS failures in HA and an unreachable companion Pi.
The Alexa entry was reloaded after outbound Amazon connectivity recovered; a
fresh physical phrase and companion playback still require verification. Do not
record the welcome bridge as end-to-end accepted from Alexa's spoken “OK” alone.


### Alexa custom-skill prototype checkpoint (2026-10-27)

At the user's request, disabled `alexa_voice.enabled` in the installed private
configuration and restarted only the controller under its existing supervisor.
Verified the authenticated history endpoint rejects requests with HTTP 403.
The HA history automation/package and compatibility source remain installed but
cannot execute controller actions while this handler is disabled. Other Alexa
schedule/Speak routes are unchanged. README's active topology edge excludes
history commands now.

Source-only `okabebot/alexa_skill.py` and the local CLI implement synthetic Alexa
request envelopes, skill/account/freshness checks, narrow read-only shared health
and location tools, session replies, and a generic voice-demo response. This is
not an authenticated Internet ingress: production needs ASK verification or a
skill-scoped Lambda trigger, a durable replay policy, and scoped transport.
No Amazon developer skill, endpoint, S3 audio object or new AWS infrastructure
was created. No physical Echo playback or APL rendering is claimed.

Silent local trial: status request/reply 0.025 s, locations 0.006 s; existing
Qwen worker first PCM 0.971 s and complete MP3 2.545 s. A disconnected first
worker attempt and a missing encoder were resolved before that successful trial;
these are warm successful-run timings, not cold-start or cloud round trips.
Generic audio decoded successfully as approximately 3.98 s, 24 kHz mono MP3 at
48 kbps. Artifact stays private/local and contains only a generic lab greeting.
322 Python tests passed, including five new skill protocol tests. The public
Alexa audio rules exclude customer-specific/sensitive information from SSML MP3s;
private tool replies use native Alexa text speech in this prototype.


### Alexa generic-voice skill deployment (2026-10-27)

Deployed CloudFormation stack `okabebot-alexa-skill` in `us-east-1`: one Python
3.12 Lambda, a private encrypted S3 bucket, and a seven-day CloudWatch log group.
The only external invoke permission is Alexa Skills Kit with the supplied skill
ID as EventSourceToken. No Function URL, API Gateway, local port forward, or new
access to controller data was added. Lambda can read only `generic/demo.mp3`;
it cannot upload audio or list the bucket. Signed HTTPS GET URLs expire after
300 seconds. Public bucket access is fully blocked. The bucket is retained if
the stack is deleted; cleanup requires explicitly removing the retained generic
asset/bucket after any rollback is no longer needed.

The selected generic Okabe greeting was uploaded. It contains no household data
or private reference clips. Cloud handler returns that audio for Launch/VoiceDemo;
status/locations explicitly report that local tools are not linked yet. Stop,
Help, fallback and session end are handled without invoking local actions. The
old history-command route remains disabled. Local conversation/audio routing and
speaker volumes were not changed by this deployment.

A 128 MiB/5 s cold trial timed out; configuration now uses 512 MiB and a 7 s
Lambda timeout. Successful direct IAM test: demo invocation round trip 2.413 s,
status 0.706 s, signed asset download HTTP 200 in 0.477 s, 24,140 bytes with an
exact local hash match. These CLI measurements include AWS client overhead and
are not Echo end-to-end latency. Verified Lambda's resource policy is restricted
to the supplied skill. Private deployment outputs remain under
`.local/alexa-skill/deployment.json`, including the endpoint ARN; no account IDs
or signed asset URLs belong in public documentation.

Configured that endpoint in the signed-in Alexa Developer Console, imported the
checked-in English-US interaction model, and observed a successful skill build.
Enabled Development testing. Simulator “open little lab” and “ask little lab for a voice demo” returned custom
audio successfully. Physical Echo audio acceptance remains pending; no
production publication is implied. All 327 Python tests passed.


Remote Show trial (2026-10-27): at the user's request, sent exactly one
`alexa_devices.send_text_command` for “ask little lab for a voice demo” to the
configured Show. A fresh Lambda invocation followed and completed successfully
in 40.03 ms. This verifies remote skill invocation, not audible playback. The
companion Pi failed both SSH and reachability checks; no matching Pi SSH identity
was discovered elsewhere on the local subnet. Therefore no microphone capture
was attempted, no recording exists, and acoustic acceptance remains open. Speaker
volume was left unchanged. Repeat with a bounded Pi microphone capture only once
that satellite is reachable; do not substitute simulator audio for a recording.


### Alexa APL character checkpoint (2026-10-27)

Enabled Alexa Presentation Language in the development skill and observed a
successful rebuild. Updated the existing AWS stack with `EnableVisuals=true`.
Launch/VoiceDemo now return an inline APL 1.8 scene only when the device advertises
APL support. Four generic 960×540 PNG frames come from the existing Pi artwork
and web lab renderer, selected as Okabe at deployment. They add a short mouth
animation and bounded idle blinks, not measured lip synchronization. The scene
uses demo labels rather than frozen clocks or claims about live device health.
The renderer's `lab.showcase` source option is used by this asset export; the
installed Mac/native/Pi deployment was not broadly replaced to obtain the frames.

The same private bucket stores the four `generic/scene/` frame objects alongside
the generic MP3. Lambda GetObject access enumerates exactly those five objects;
no List/Put permission was added. GET/HEAD CORS allows screen runtimes to load
signed assets without making objects public. Signed URLs remain five-minute
URLs. No private controller/HA data is uploaded and no local-tool transport exists.

Verified screen-mode Lambda response and all four HTTP-200 downloads against
local SHA-256 hashes. Direct IAM screen request round trip was 1.123 s in that
run, not physical Echo latency. The simulator visibly rendered the complete lab
and Okabe; observed viewport label was Hub Landscape Medium. A separate text
command sent to the real Show after deployment reached Lambda and completed in
43.10 ms. Physical Show rendering/audio remain unobserved because the Pi is
offline and the user is away. No camera/microphone recording is claimed.

Screen responses omit reprompt/shouldEndSession to allow Alexa's extended visual
session without immediately opening the mic. The document recommends a two-minute
idle timeout, which Alexa may override. It is not an always-on registered surface:
no spatial ownership transfer, notifications, touch actions or character-picker
synchronization are installed for the Show. Existing character locations and
speaker volumes are unchanged. 330 Python tests, 11 room-renderer tests and the
package build passed. Preview evidence remains private under `.local/alexa-skill/`.

### Scene-world installed acceptance pass — 2026-10-27

Updated the installed Mac controller/web package, matching native Mac app and Pi
display service with rollback copies of code and private configuration/state.
The warm speech worker and Pi voice service were preserved. Hosting, model
ownership, ports and topology edges are unchanged. Scene setup was explicitly
activated: each character's first set is reserved on the Pi and second set on the
TV. Other screens remain unassigned under the two-set uniqueness rule. The native
Mac temporarily reserved the TV sets for testing, then released them back.

Observed all four character profiles complete simulated recorded-input voice
turns through the current transcription, local conversation and Qwen output path.
Completion times were 10–26 seconds including full speech; these are not
time-to-first-audio measurements. The initial destination question produced a
generic answer instead of a tool call. The installed correction routes this
argument-free discovery through the validated live tool; its retest executed the
tool in 4 ms and completed speech via the Mac sink in about 10 seconds. No physical
microphone/button test is claimed from simulated input.

Live testing caught a scene-only keyword passed to the Pi portrait walking
renderer, which prevented departure acknowledgements. Fixed and installed;
regression exercises real departure/away frame branches for all four styles.
Subsequent controller-confirmed TV arrivals took 8.8–9.4 s including receiver
startup, and returns 5.6–6.3 s. The user confirmed all four physical TV departures/arrivals/returns looked
right with no duplicate actor. Native Mac arrival, compact cafe, room-mode Kurisu
and silent notification card were visually checked. The Mac audio sink reported
Playback finished. A real phone microphone clip subsequently completed a local
conversation turn, and the user confirmed phone character, microphone and speaker
audio all worked. Phone PiP was confirmed in an earlier session, not repeated
in this pass. A fresh native Mac microphone/physical audibility check remains
separate from its observed audio completion.
Pi status reported no render error, roughly 25–28 FPS in observed samples and a
480x320 output. The user reported the existing speaker level was too loud; it was
lowered and verified against the physical AIY mixer. Do not use this record to
reset the user's mutable volume preference.

Direct IAM Alexa prototype checks passed for voice/status/APL replies, signed
MP3 and four image downloads with matching hashes. This is not physical Echo
Show playback, a connected local-tool bridge or spatial registration. The Show
remains a standalone prototype. No household data was uploaded for that test.
See [surface rules](surfaces.md#scene-sets-and-world-rules).

After phone acceptance, temporary reservations were released back to the TV and
Okabe was restored to the Pi once the active user turn completed. The Samsung
TV/two-TV adapter expansion is a separate backlog item; no Samsung discovery or
configuration was attempted during this pass.


### Second TV and arrangement checkpoint (2026-10-27)

Installed the independent Cast connection pool and grid arrangement editor on the
Mac controller. The first TV retains its existing Cast media-observation route;
additional `surfaces.locations[].cast_host` entries establish exact-host passive
connections independently. Controller/model hosting, ports and audio routing are
unchanged. The dashboard fits all screen tiles into view, rejects occupied grid
cells and supports cardinal placement relative to any registered screen.

Discovered a Samsung Q60B with local Tizen REST capability and a separate HDMI
Chromecast. The user moved that dongle from the Vizio to the Samsung. Both the
Vizio built-in receiver and the additional Chromecast report connected. The first
Samsung visit loaded a receiver page but returned before accepted arrival; a
standby flag without confirmed active input caused the return. The installed fix
trusts standby only after active input has been observed, while retaining app-exit
and visibility-lease recovery. The second visit timed out waiting for page readiness. A third visit completed
receiver readiness, Pi rendered-away acknowledgement and TV entered acknowledgement,
then remained at the Samsung destination. The user confirmed the café appeared on Samsung with the character absent
from the Pi. Return reached the Pi rendered-home acknowledgement and the original
first-TV set reservations were restored. Cold/repeated-launch reliability remains
a test item.

Existing two-set-per-character uniqueness remains enforced. Second-set reservations
were temporarily moved from the first TV to the Samsung for testing and restored
after the confirmed return. No voice defaults or speaker volume were changed. Echo Show still
uses its separate static APL skill prototype and is not a registered spatial
location. At that checkpoint, Japanese speaker-embedding conditioning was an
isolated private trial; see the current voice-conditioning inventory below.


### Alexa visual/audio diagnosis and voice experiment (2026-10-27)

The user confirmed the Show loaded the character and moved its mouth; audible
custom speech remains unconfirmed after clarifying the earlier response. Deployed
bounded capability/known-intent/session diagnostics and a single delayed APL mount
callback in the existing skill Lambda. No IAM resources, public endpoints, local
controller access or audio destination settings changed. The callback is delayed
six seconds on a separate sequencer to avoid a request during the fixed short demo.
Mount is not proof that artwork is visible and cannot transfer spatial ownership.
The Show remains a standalone, session-scoped demo; a live voice retest is pending.

The private Japanese-reference experiment completed two English sentences per
character/mode and a warm six-sample transcription check. At that checkpoint the existing English
ICL references remained installed. Speaker-only conditioning is feasible with the
installed MLX-Audio version, but accent/tone acceptance remains a listening test.
See [current conditioning configuration and limits](voice-conditioning.md). No training,
model upgrade or cloud GPU was started, and no private audio was committed.


Three subsequent silent Samsung arrival/return cycles completed with rendered
acknowledgements: arrivals 9.15/9.23/9.21 seconds, returns 5.90/5.13/5.90 seconds.
These are observed controller timings rather than performance guarantees. The
Pi and original first-TV scene reservations were restored afterward. Screen
arrangement now refits on the next state update after browser/tablet resize; its
focused browser regression covers that behavior. No hosting or port changes.


### Echo Show physical acceptance (2026-10-27)

The user confirmed the custom voice and animated character together on Show 15
using “Alexa, open Little Lab” and allowing playback to finish. Deployed logs
also show APL capability followed by the delayed document-mount callback. This
completes the voice/visual demo acceptance, not spatial destination ownership.
The user observed Alexa+'s spoken “say exit” preamble slightly overlapping the
skill opening. Home Assistant's documented text-command action follows normal
Alexa invocation; no documented preamble-suppression option was found. Preserve
this timing issue for the session-destination implementation, which should wait
until ready and avoid relaunching the skill for every subsequent update.


### Alexa destination source work (not installed)

Added an opt-in session renderer, separate room/actor layer export, bounded private
store protocol and conditional exact-object IAM policy to source. These changes
are not deployed: the active Echo Show skill remains the accepted generic demo,
and the Mac controller does not route spatial movement through this relay. No
live volume, voice reference, host, port or device state changed. Renderer layers
reconstruct the original room frames across all eight character/set combinations.
The controller-side worker and physical Show handoff/recovery remain incomplete.
See [prototype boundary](alexa-destination.md) before enabling deployment flags.


The optional controller-side Alexa worker is now implemented in source and passes
an isolated round trip through the real location registry/handoff state machine,
a fake Pi, and loopback HTTP boundary tests. It has no full dashboard credential.
Alexa registrations declare fixed artwork capabilities, require approval and a
unique matching scene, and support Room presentation. A CLI/process lock and a
scoped two-object consumer-policy template are provided. None of these source
changes is installed/running yet; the live skill's destination flag was read and
confirmed disabled. No live scene, voice, volume, host or port change was made.


### Alexa destination development deployment (2026-10-27)

The tested controller bridge/registry/HTTP changes are now installed on the Mac.
The controller restarted and reported Pi ownership with the existing speaker
level preserved. The development skill's optional destination flag is enabled
with Okabe/café artwork. An Identity Center permission set and local named profile
scope the test worker to reading the two relay objects and writing only the
command object. Live reads succeeded and a session-object write was denied.
The worker is running as a supervised foreground test, not a login service.
Generic voice-demo invocation, MP3 hash and four image hashes passed after the
cloud update. No Show destination handoff has yet been physically accepted.
Existing TV and voice routes remain unchanged; the Alexa spatial route is an
experimental two-object S3 link over HTTPS to this optional Mac worker.

The first supervised Show destination launch rendered an empty café and sent
live poll events, but never asserted combined image readiness. The controller
kept the character on the Pi and a requested visit remained blocked during
preparation; it was canceled safely. A bounded asset-load diagnostic is being
deployed to distinguish actor/background loading before another handoff test.
This is not evidence of a completed Show destination visit.

The asset diagnostic on a direct Show launch reported background loaded and
actor neither loaded nor failed. The renderer now uses `display: invisible` for
the hidden actor (APL documents that this state still loads sources), instead of
zero opacity. The change passes renderer/relay tests and is deployed for retry;
it is not yet confirmed to resolve readiness on hardware. Home Assistant text
invocations created a skill record but produced no screen callbacks, so they
cannot substitute for the direct launch in this physical test.

Local review found that explicit Stop/Cancel could leave the destination record
open after a skill-initiated end. The handler now closes it before ending speech,
and a real-relay regression verifies that later polls cannot revive it. The fix
is being deployed before the physical cancellation/recovery check.

The direct retry still reported only the background loaded. Source inspection
found the absolute actor overlay lacked explicit top/left anchors; it now anchors
at viewport origin, with a regression check. This is a candidate fix pending
deployment and direct Show verification, not a confirmed diagnosis.

The anchored retry still reported background-only readiness. The next diagnostic
renderer removes the actor's inherited frame-index source expression: its initial
source is the validated idle URL, with explicit idle/blink source commands. This
remains a candidate fix until a fresh Show launch reports the actor loaded.

The direct-source retry still reported background-only readiness. The renderer
now preloads the actor behind a matching opaque background cover, exposing it
only on the original readiness/ownership/lease checks. The test background alpha
range was verified as 255..255; the deployment helper now rejects transparency.
This new loading strategy remains pending direct Show verification.

Covered preload resolved the measured image-readiness gate on a direct Show
launch: background/cover and actor flags were both loaded, and `ready` was true.
The installed controller then reached Show ownership (`tv` phase for the paired
Alexa screen) and returned to Pi ownership after an explicit return, with no
controller errors. Private arrival/return receipts were saved locally; speaker
level remained 26%. The user confirmed Okabe visible in the Show café with the Pi away.
Closure/expiry recovery remains required before accepting the checkpoint.

A second direct launch also loaded both image layers and reached Show ownership.
The session subsequently reported closed and the controller recovered Pi
ownership without error. The original Vizio café reservation was restored after
the test; Show remains approved but unassigned, preserving unique scene rules.
The Pi speaker remains at its prior 26% measured level. Physical confirmation of
the closing/return behavior is still pending. The test worker is a manual process,
not an automatically installed service, and the Show session is limited to one
minute with one fixed character/set artwork profile.

### Four-checkpoint acceptance closeout (2026-10-27)

The user confirmed Show presence with Pi absence and automatic Pi return after
Alexa exit. Both backend arrival/return and physical recovery now pass for the
bounded manual-worker prototype. The final local review also required identical
actor/background geometry; deployment validation rejects mismatched frames and
transparent covers before any AWS operation. All installed layers were separately
verified as 960×540 and byte-identical to their local exports. The Vizio café
reservation is restored, Show is approved/unassigned, and Pi volume remains 26%.

Samsung via the relocated HDMI Chromecast, cardinal non-overlapping arrangement,
and the accepted Japanese-reference English comparison complete the other three
checkpoints. No voice manifest changed. Longer-running Alexa/service lifecycle,
dynamic artwork and voice optimization remain backlog enhancements rather than
claims about this installed checkpoint.

### Private Alexa conversation checkpoint (2026-10-27)

The Mac controller enables `conversation.alexa_enabled` and owns a mode-0600
Unix socket under its private state directory (`alexa/conversation.sock`). It
shares the warm local conversation and Qwen workers, with tool-free, isolated
follow-up history and deadline-bounded MP3 generation. The installed encoder
extra is present. No new LAN port or dashboard credential is exposed.

A separate AWS conversation stack now hosts an encrypted FIFO request queue,
a private DynamoDB request/reply ledger, and a private generated-audio bucket in
the skill's region. The manually run `scripts/run-alexa-conversation.py` consumer
uses the dedicated `okabebot-alexa-conversation` Identity Center profile. Its
permissions are receive/delete, ledger get/update, and generated-audio-prefix
upload only. This is separate from the existing visual destination worker.
The consumer is not installed as an automatically restarted service.

Real silent queue/local/media trials completed two warm turns in 5.030 and 2.793
seconds, with MP3 fetches adding about 0.27 seconds. A cold turn timed out safely.
No physical playback occurred; these are not Alexa round-trip measurements.
The live Lambda handler is now connected to this transport with scoped
queue/ledger/audio permissions. Its English (US) Alexa TalkIntent model is now built; Show
two-question physical acceptance remains pending. An IAM-only fixed-question
Lambda harness returned generated audio for two warm turns in 4.285 and 4.707
seconds, plus roughly 0.25–0.33 seconds to fetch each MP3. The ephemeral harness
was deleted and does not prove real Alexa recognition or playback. The handler
uses Lambda-aware deadlines and a separate APLA audio track; its speaking cue
requires an already-visible, current, matching actor and never summons it.
The installed Alexa model prompt requests a shorter sentence to fit the deadline.
Voice references, volume and Pi ownership were preserved. See [conversation cycle](alexa-conversation.md) for boundaries,
retention and detailed evidence.


The Developer Console confirms successful English (US) build 4 at 8:27 PM local
on 2026-10-27, with the new TalkIntent/SearchQuery carriers. The deployed handler
also handles the automatically added NavigateHomeIntent as exit/cancellation.
For the physical test, Okabe's café reservation was temporarily moved to
Show instead of the living-room TV. After the failed retry, original assignments
were restored from the private backup. Other character reservations and
Pi speaker volume are unchanged. No new physical acceptance is claimed yet.


The first conversational physical attempt reached Show, but the user reported
flicker and the question routed to FallbackIntent; no generated answer was
accepted. The Mac visual relay worker was refreshed to coalesce newer valid
receiver polls instead of starving renewals during controller reads. The Lambda
renderer now preloads four actor poses behind the cover and animates opacity,
while retaining the same four-second visibility lease and session limits.
Display polls skip conversation transport initialization. Fallback/Help keeps
listening without inference. Both changes are deployed and 432 isolated tests
pass; physical stability, custom-voice playback and follow-up listening remain
pending. The temporary Show café reservation was later restored to the TV after the failed retry.

The next physical retry reached TalkIntent twice but missed both audio deadlines;
custom conversational playback is still unaccepted. A receiver trace confirmed a
temporary visibility-lease lapse. Installed private RPC diagnostics now identify
model/synthesis/encoding failures without exposing utterances or exception messages.
Silent timing reproduced a synthesis timeout even with shorter replies, so that
experiment was discarded. The isolated-tested remaining-grant lease correction deployed after AWS
reauthorization; its physical stability is not yet accepted. No ownership topology, voice
reference, or volume setting changed. Further physical retries are paused.

## Morning speech and Cast audio responsibilities

The native controller now enriches the configured morning rail with two stacked
cards, available status counts and explicitly authorized supportive coaching.
An independent private voice preference enables a once-daily named greeting and
grounded rundown. Character framing runs on the existing local conversation
worker using required placeholders and a coarse weather category, without tools,
names or raw source content; synthesis remains on the existing warm
speech worker. Core defaults remain speech-off and quiet-hours-respecting.

Both Cast destinations use their scoped TV receiver page as a streamed PCM sink
for replies, with per-location software gain stored in the private location
registry. HDMI carries audio to the TV’s configured output, including linked
speakers. This uses existing controller HTTP routes and browser audio transport;
no new port or worker is introduced. Active receiver tokens are limited to their
own destination; previews cannot receive audio. Announcement routing is unchanged.
The installed TV routes select their own device output with separately configured
software gain. Source changes and installed configuration are distinct from physical audio
acceptance, which still requires listening at each TV. Hardware volume is unchanged.

### Selected-person greeting identity

The installed HA package publishes a single explicitly bound person's display
name to `/amadeus/source/person` using the existing write-only source credential.
Only entity ID, display name and snapshot time cross that route; tracker, GPS
and account attributes are excluded. The controller stores the name as a private
profile-linked preference, not an observation history. Active consent, pause,
guest, freshness and deletion controls apply. The morning greeting resolves this
first name unless a private spoken override is set. Owner-requested replay is
separate from automatic daily delivery and does not reset its durable marker. No additional listener or HA owner
credential is introduced. See the portable person-name publisher in the morning
guide for new installations; the selected entity remains private configuration.

## Current supervised character voice conditioning

The installed Mac Qwen worker supports a single private manifest with explicit
`speaker_only` and backward-compatible `icl` modes. Okabe and Kurisu now use
Japanese audio with speaker-only conditioning and English output; reference
speech tokens/transcripts are omitted. Their per-reference temperature is 0.3.
Pip and Sonic retain their existing ICL entries. The model, revision, Unix socket,
controller host and streaming transport are unchanged. No cloud or training job
is involved, and no speaker volume was changed for this promotion.

The existing supervisor restarts and warms the worker after manifest updates.
Local worker status exposes loaded modes, not private paths or transcripts. One
private rollback manifest/script is retained. Superseded comparison helpers and
generated trial audio were removed from the active workspace; the older manual
voice smoke script is replaced by the maintained regression harness. Physical
quality remains a listening checkpoint, separate from readiness and PCM checks.

The supervisor's health gate also checks the existing character-speech file lock
for speech requested outside controller turns. It skips conflicting health probes
while that lock is held; a stale unlocked file does not inhibit recovery. No new
worker, socket or service is introduced.

### TV speech continuity and whole-briefing framing

The installed TV Web Audio receiver prebuffers each bounded utterance before
joining PCM into a single playback buffer. This avoids dependence on per-chunk arrival
latency after playback begins, at the cost of waiting for synthesis/transfer to
complete first. The existing audio relay, scoped receiver capability, per-location
gain and HDMI output remain unchanged; phone/Mac streaming is unchanged.

The morning composer now styles the whole rundown around validated placeholders.
Private source values fill the slots only after generation. Current weather can
supply conditional rain/cool-temperature clothing advice; no forecast provider,
new source consent or external model service is added. Empty calendar language is
limited to the connected timed-event feed. Public reporting remains declarative;
recordings, generated utterances and listening outcomes stay private.

Speaker-only synthesis now uses short sentence segments through the model's
existing newline split behavior. ICL references retain their prior generation
path. This is a worker input change, not audio filtering or a new model. The
complete-utterance PCM cap remains enforced.

The installed speaker-only path decodes complete clauses before emitting PCM and
rejects token-limit termination. One bounded higher-temperature retry is allowed; repeated
failure aborts the utterance. Existing ICL streaming is unchanged. This changes
worker decoding/buffering, not model ownership, ports or reference storage. Morning
private diagnostics now distinguish failed delivery from in-progress synthesis.

## Source-only shadow routine experiment

The checkout now contains a local prior-day routine planner, owner-only preview
and explicit-feedback routes on the existing web listener, plus a socket-denied
accelerated replay/evaluator. It reuses private SQLite and existing source consent;
there is no new model, cloud service, port or background collection worker.
Defaults are off and general proactive delivery cannot be enabled by these routes.
This change has not been installed into the active controller. The current README
topology therefore remains unchanged. See [experiment protocol](amadeus-simulation.md).

The source-only context extension adds an owner preview and a publish-only coarse
availability route on the existing bridge listener. Its HA example requires
separate consent and private entity bindings. Calendar busy coverage is explicit;
existing future-only feeds are not silently promoted to complete availability.
No installed publisher, device setting, worker or notification dispatcher was
changed for the isolated replay. Catalogue fixtures do not represent a deployed
streaming provider connection.

## Companion MQTT facade

The installed Mac now runs a separate launchd-supervised companion MQTT facade.
It reads the existing local controller state through its authenticated API and
publishes eight bounded HA entities grouped as a companion satellite device.
The private installation assigns the user's selected room through MQTT Discovery.
An authenticated Mosquitto container persists discovery on the Mac, shares a Docker
network with HA, and exposes port 1883 only on host loopback. HA's MQTT integration
was configured through its UI. Docker startup remains a prerequisite after reboot.
The facade uses the controller environment's Python/paho-mqtt dependency; it does
not require a new Pi process or change existing speaker settings.

Speech/model/scene ownership is unchanged. HA area synchronization, raw satellite
telemetry and an HA Bluetooth-proxy adapter are not deployed. See the
[responsibility audit](ha-companion.md). Source tests cover discovery grouping and
bounded commands; no speaker playback or physical movement test is implied.

An opt-in, bounded two-destination wearable/room-motion proof is prepared using
the existing Pi target-only scanner and HA MQTT automations. A separate foreground
controller trial consumes on-body and motion signals; no persistent follow service
or full home-map fusion has been installed. Live HA wearable and occupancy entity
bindings remain private. BLE identity detection and publisher delivery are verified;
physical room discrimination and both movement directions remain pending validation.

The local Alexa dependency now has an optional source-guarded communications-request
deadline compatibility patch, backed up privately before application. It bounds
ancillary preference retrieval during sensor startup; it does not change Amazon
authentication or sensor polling intervals. A process restart loads it; image updates
replace it. See [Alexa compatibility notes](alexa.md#optional-communications-request-deadline).
Wearable following now uses a fresh non-health device heartbeat alongside the
unchanged on-body state, avoiding false staleness from event-driven wearable sensors.

## Second BLE observation satellite

The previously separate display Pi is reachable again and has the existing
Python-compatible target-only BLE scanner copied into its hardware directory.
Bluetooth and DBus/GLib prerequisites were verified. It is being evaluated as a
second fixed BLE observation point through bounded SSH scans; no persistent scanner
service, new radio pairing, room-inference service or automatic two-anchor following
has been installed. Existing display service state was observed, not migrated or
reconfigured. Model workers, active display/audio duties and collection consent
remain on their existing hosts. Private radio measurements and room calibration
results remain in ignored local state.

A bounded Mac two-anchor follow prototype now compares both prepared Pi scanners
and requests existing destination handoffs. It is launched explicitly for testing,
not supervised as an always-on service. HA contributes the scoped wearable-worn
and device-heartbeat feed; native Echo occupancy is not consumed by this variant.
Physical two-direction movement validation remains pending. No display/audio role
migration, new port or additional model worker is involved.

The supervised two-anchor movement trial temporarily follows the selected beacon
as a device because wearable heartbeat delivery is sparse. Its private bounded
configuration disables worn-state gating for that test only; source default remains
required. This is not a deployed unattended person-presence rule.

## Upstairs satellite HA registration

A separate Mac launchd agent now runs `okabebot.ha_satellite`, reading fixed
diagnostics over the existing verified SSH key and publishing four read-only MQTT
Discovery entities for the second Pi. The installed HA device is named Upstairs
BLE Pi and uses the owner-selected TV room. Published values are SSH connectivity,
Wi-Fi signal, CPU temperature and uptime; no raw Bluetooth identity, movement
history, commands or media content are exposed. Availability describes successful
SSH diagnostic delivery; it does not claim a BLE scan is running. The broker and
HA integration are reused; there is no new satellite listener or cloud dependency.
The agent is supervised across Mac logins; Docker must be running. The bounded
two-anchor follow trial is a separate process and is not made permanent by this
telemetry registration.


## Adapter lifecycle reliability update

The installed read-only companion and satellite MQTT agents now use asynchronous
broker connection, bounded publish queues and reconnect backoff. They avoid
queueing stale telemetry while disconnected, establish offline availability before
fresh health on reconnect, and handle SIGTERM/SIGINT with interruptible waits and
bounded shutdown publication. Both agents were restarted and read-only telemetry
recovery checked. Neither controller/device placement nor volume was changed by
the update. No new ports, roles or cloud integrations were added.

Source-only BLE follow improvements handle termination by reaping scanner children,
pause when the controller API is unavailable, reset dwell after recovery, stop if
a scanner exits, validate thresholds and cap sample memory. These changes are not
an enabled unattended service. The temporary movement trial was stopped during the
maintenance pass; no character handoff, playback or TV wake was used for validation.
Fault-injection regressions use invented fixtures and local fake transports.


## Watch home-presence return trial

The installed Mac now supervises `okabebot.home_presence` through a separate login
agent. Both satellite scanner scripts have a five-second heartbeat that checks
powered/discovering radio state. This service observes only the configured target,
cycles bounded SSH scans and publishes a separate MQTT home estimate and scanner
health count. The HA door publisher was configuration-checked and loaded without
restarting all integrations. Current private state and bindings remain outside Git.

An explicit return trial uses the existing dedicated arrival capability through a
new bounded `ble_presence` trigger. The installed controller has the arrival change
loaded; normal announcement output, speaker volume, quiet policy and generated
welcome/recap behavior remain unchanged. The older generic door/person arrival
paths still defer to the Amadeus conversation trial when enabled; the explicitly
armed BLE welcome is independent. No new listener or cloud resource is introduced.
This is a device-presence estimate, not canonical person tracking or always-on
character following. Synthetic gate/arrival tests pass; physical return speech is
pending the user's next real arrival. Scanner disconnection and missing observations
must remain unknown rather than being labeled a confirmed departure.


## Current supervised following and announcement rollout

This checkpoint supersedes the earlier bounded-only following stage for the
installed home bridge: following is owner-enabled through the dashboard, shares
the existing two scanner streams and persists manual holds/request cooldowns.
The standalone BLE trial command remains bounded. The controller owns final
movement validation, including idle active Cast input and approved-pair checks.
There is no new listener, credential grant or model process.

Amadeus live conversation delivery now uses the expiring Watch home estimate when
configured. Installed private presence observer bindings select the derived sensor;
phone/person entities are no longer that observer's presence source. HA Person
itself is unchanged. Existing source consent, quiet, focus and media rules remain.

The active Voice service now loads `prepared_audio.py` and supports bounded
single-use upload/playback. Pi announcements use one persistent tunnel and the
returned device clock for scheduling. Normal replies still stream. Installed
controller and Voice updates were checked with a silent preparation probe and a
short real announcement; software reports playback and animation success. Human
confirmation of audible smoothness is tracked separately. Mixer settings were
preserved. Device/code backups are private. Runtime data, audio and calibration
remain outside public documentation.

### Silent Amadeus developer chat

The existing controller serves owner-authenticated text conversation and private
feedback routes in its dashboard Dev panel. It reuses the Mac's warm local
conversation worker and private Amadeus preference store; it introduces no new
listener, model worker, cloud route or hardware service. Spoken invitation context
is separate from the text session. Source and installed state should be verified
independently when deploying this panel.

The installed Mac controller now serves this panel. A silent browser request was
verified through the local worker and returned character-styled text. Synthetic
checks cover explicit preference confirmation and spoken-session isolation. No
hardware audio test is needed for this text-only surface.


Preference memory acceptance now shares a private confidence policy across text
and spoken conversations. Auto-accept defaults on at 0.90, with owner controls in
the Dev panel. Existing consent, guest and pause controls remain required. This
uses the same controller/store/worker; hosting and integration topology are unchanged.

### Dashboard chat tool dispatch

The existing Mac controller now implements silent text tool turns on its shared
local conversation worker, with the same grounded MCP tool implementations and
approval policy used by voice. Browser-paired or explicitly selected location
context resolves movement to "here"; no user-location sensor or additional network
listener is introduced. Text session context and response feedback remain private
controller state. No new Pi service or changed audio routing is required.

The installed controller was verified with a silent calendar read followed by a
relative-date follow-up; both used the calendar tool. Browser-location resolution
is served by the owner API, and unpaired browsers require an explicit selection
before movement to "here". No physical device action was used for this verification.

The text conversation prompt and capability context use the existing local Qwen
worker. No model, hosting, network or device-role change is introduced by this
conversation-quality update.

Text/voice tool grounding now resolves common calendar windows against the same
configured private feed, reports live companion position, and validates Spotify
phone targeting using on-demand Connect discovery. This changes no hosting roles,
ports, configured calendars, device assignments or volume settings.

### Optional gated camera greeting

The Mac controller now has an opt-in background anonymous face detector using the
`vision` extra (OpenCV's bundled cascade). The companion Pi serves bounded,
stdout-only 640×480 camera frames over its existing verified SSH RPC transport.
The existing Watch home bridge publishes a current nearby-anchor projection;
fresh home plus strong companion-anchor evidence gates capture. An independent
three-second display gesture waves silently and never actuates the SwitchBot.
No new port, cloud service, image archive or identity model is introduced.

The source default is disabled; the private owner control is in the dashboard Dev
panel. See [camera greeting](camera-greeting.md) for gating, cooldown, privacy and
physical acceptance checks. A missing BLE anchor blocks detection rather than
falling back to phone presence or camera-only monitoring.

Installed rollout: the Mac vision dependency, controller greeting worker, nearby
Watch projection and companion Pi camera/display changes are installed. The private
owner setting is enabled. At the latest software check, one BLE anchor was
unavailable, so the live status correctly waited for home/nearby evidence. No real
camera detection or physical wave is claimed from that blocked state; the owner
must complete the near-camera acceptance check when both anchors recover.

The main dashboard now exposes a private per-profile phone DND gate for proactive
conversations. It uses the existing owner HTTP control and private store; no phone
setting, Home Assistant configuration, device route or hosting role is changed.

### Private shadow evaluation worker

The existing Mac controller owns an optional five-minute habit/context evaluator.
It writes `shadow_decisions` to the existing private Amadeus SQLite database and
exposes a current operational summary in the owner dashboard. It does not call
models, speakers, displays, notifications or device actions. Enabling shadow mode
turns on planner evaluation only; existing consent and minimum-history thresholds
remain authoritative. No additional service, credential or network listener is
required. See [shadow trial](amadeus-shadow.md) for retention and review boundaries.

Installed shadow rollout: enabled on the current Mac controller. The background
worker and initial private decision record were verified, with delivery explicitly
false. The new Dev control exposes pause/status; the trial did not add observation
sources or change device state. Existing briefing, arrival and conversation flows
remain separately configured.

## Read-only Amadeus context feeds

Source implementation adds an optional controller-owned background reader and
owner routes `/amadeus/api/feeds` and `/amadeus/api/feed-connection` on the existing
listener. No new port, Pi service or model worker is introduced. The registry
supports selected HA to-do/sensor/calendar reads, Sound Transit public rail alerts
and Trakt recent history. Credentials, entity bindings and enable choices belong
to private Amadeus SQLite (or private environment), not repository defaults.
Provider account setup and installed/connected verification are separate from
source availability. See [context feed setup](amadeus-feeds.md). The optional
feed reader is represented as such in the README diagram; no account connection
or physical test is implied by that node.

Installed verification (2026-10-29): the Mac controller's feed registry and
owner-only configuration route responded after a supervised idle restart. The
public rail adapter produced a fresh normalized snapshot. Other account-based
feeds remain available but unconnected pending private credentials and entity
selection. The live setup page rendered the registry controls. Pi services,
volumes, model selection and device bindings were not changed for this install.

## Native Mac display signal

Source now connects Little Lab's native display wake/sleep notifications through
its existing paired-screen HTTP connection to a bounded current-state tracker.
The existing MQTT facade has an additional Mac device/sensor projection. No new
listener, vendor login or active-application collection is introduced. The owner
`/mac/screen` route configures automatic wake following on the shared movement
interface; defaults remain disabled. Display state is transient, not a restored
presence assertion. Installed verification is recorded separately after rollout.

Installed verification (2026-10-29): the rebuilt Little Lab app reported a fresh
coarse display-on snapshot to the installed controller. The existing MQTT facade
registered its separate Mac display entity in HA. Automatic wake following is
owner-configurable; a physical wake-to-arrival check remains pending a unique
Mac scene assignment. No microphone capture, speech or TV wake was used to verify
the state signal.

The scene catalogue adds a character-independent Desktop Nook for approved Mac
visits, with both compact and room presentations. This expands available world
capacity without changing existing TV reservations. Selection remains owned by
private surface layout, editable from the dashboard. Source renderers support
this set on the controller and Pi; Pi source support is not evidence of a satellite
rollout, and no Pi set is reassigned by this change.

Installed desk verification (2026-10-29): the controller catalogue and browser
renderers were installed, and the approved Mac was assigned the new unique desk
set without changing TV reservations. The controller confirmed arrival and the
native Mac window visibly rendered the character and desk. Display wake routing
has a scene-ready destination; a physical screen-off/wake cycle is still a
separate acceptance check. No Pi renderer rollout or microphone/audio test was
performed for this scene change.

## Household recap and personality control

Source adds the read-only `get_home_activity` MCP/local tool over existing private
observation storage and household notification titles. It does not add a network
provider or history collector. The owner `/character/tone` route stores private
Plain/Subtle/Playful prompt preference in `state_dir()/personality.json`; defaults
are Subtle. Existing workers consume the selected persona per turn. Deployment
requires a controller restart to register the tool and updated worker prompts;
source availability alone is not evidence of an installed reply.

Installed recap verification (2026-10-29): an idle controller restart registered
`get_home_activity` and the updated persona controls. A silent owner text request
executed that read tool and returned an explicit coverage limitation. No speech,
volume change, device action or participant result is included in this verification.
The existing topology, ports and worker roles remain unchanged.

## Local tool-result composition

Source adds a tool-free reply task to the existing warm MLX conversation worker.
The controller projects bounded human-facing result fields and composes the
user-facing response after the tool finishes; structured MCP results are unchanged.
No new worker, port, cloud provider or device authority is introduced. Owner
`personality.json` also stores the dashboard's natural-tool-replies preference,
on by default. The existing README topology therefore remains unchanged. A model
or validation failure uses the already known outcome without replaying the action.

Installed composition verification (2026-10-29): the Mac controller and existing
MLX worker were updated. A silent owner text request executed its read tool and
used the generated summary rather than the formatter fallback. Operational timing
metadata confirmed the composition path. No spoken audio/device action was used
for this check, and participant facts/drafts are not included in public evidence.

Ring household history: the installed metadata observer now watches Ring activity timestamps under door/presence consent. It stores bounded occurrence records, deduplicates reconnects, and rejects stale live events. No new hosting service or network route is required. Delivery confirmations remain private and distinct from sensor detections. The installed controller recap was silently verified to retrieve a confirmed household event; no speaker, volume or device-state test was performed. The existing README HA → controller route remains accurate.

Context-feed dashboard cleanup uses the existing owner API and installed controller: provider-local credentials/status, shared HA credentials, entity rows and transit checkboxes. No hosting, port, model or topology changes.

The Uno room-sensor extension compiled and was uploaded from the Mac. Serial diagnostics verified continued valid ultrasound samples, and valid DHT11 temperature/humidity samples after correcting orientation. Tilt contact changes were physically verified in both user-selected orientations. Photoresistor is intentionally disabled (null rather than floating ADC values). Wiring diagnosis, calibration and HA integration remain pending; no persistent collector or actions are enabled.

### Prepared Uno-to-Pi migration

Source now includes a dependency-free Pi serial reader inside the display service, bounded room-sensor RPC, five HA MQTT-discovered sensor entities through the existing facade, and an ultrasonic wave option with editable hysteresis/dwell/cooldown. No separate broker, listening port or model worker is introduced. The Uno is now attached through a USB hub alongside the touchscreen. The installed Pi display service reads its stable serial path, and the installed controller/facade deliver all five sensors to HA. Fresh distance, DHT11 and tilt values were verified through Pi RPC, controller state and HA Recorder. Ultrasonic wave is enabled with dashboard-editable thresholds; its physical approach/wave test remains pending. The voice service and volume were unchanged.

Silent wave media exception: installed greeting configuration allows visual
waves during TV/music playback. Dashboard can disable it. Speech policy, volume,
hosting and integration routes are unchanged; README topology remains accurate.

Wave media-policy repair: the installed controller now passes an explicit visual
media exception through to the Pi renderer. The renderer accepted a direct silent
wave request; automatic approach triggering still preserves the configured home
gate and requires user validation. Notifications, active speech and away state
remain renderer blockers. Focused checks and 704 Python regressions passed.

Anonymous ultrasonic greeting is now enabled in the installed private config
(`require_home=false`). The owner can restore home-only behavior from the
dashboard. Nearby visitors/objects can trigger only the existing silent visual
wave; speech, camera capture, BLE scanning and location-follow settings are
unchanged. No topology, device endpoint or hosting changes.

### NFC dashboard mapping

The installed Mac controller owns private NFC mappings and a separate publish-only
HA scan endpoint on its existing web listener. The installed HA tag package
forwards scan IDs/times with a scoped private token. RESTful commands and
automations were reloaded without restarting HA; its tag bridge is observed on.
The owner dashboard exposes scan-to-register, name, approved destination, enabled
state, edit/remove and test controls. No mapping is configured until the owner
saves one. API, HA configuration validation, 710 Python and 58 browser regressions
passed; the installed panel was visually checked. The owner subsequently confirmed
that the second tag was working. No model, volume or device deployment
role changed. README includes the additional HA-to-controller tag route.


## Context-feed onboarding and HA room preview

The installed controller now includes owner-only HA registry preview and private
screen-to-area bindings through `/amadeus/api/ha-inventory`, and Trakt device
sign-in through `/amadeus/api/trakt-auth`. These reuse the existing owner listener;
no new port, HA package, Pi service or model worker is introduced. Optional
`aiohttp` in the `home-assistant` extra supplies the authenticated WebSocket read.
Registry preview is explicitly refreshed, not a background subscription. Imported
rooms do not change orientation, observation consent, device control or routing.

Installed source rollout: modules and dashboard were copied with rollback material
and the idle controller restarted. The live owner-only registry route returned room, entity and approved-destination
metadata using the saved private HA connection. Provider authorization and selected
feed acceptance remain separate manual checkpoints. Source regression
success is not account-onboarding or physical acceptance. See
[feed onboarding](amadeus-feeds.md). Private room bindings and provider credentials
belong to local Amadeus SQLite; they are not repository configuration.


Trakt onboarding compatibility: the installed controller accepts new public-client
apps without an issued secret, supplies Trakt application/version headers, and
keeps legacy-secret connections supported. Device authorization and a bounded
history API read were verified independently of observation enablement. No account
identities, credentials or private history results are included in this inventory.
The existing controller listener and private credential ownership are unchanged.


## Compact context records and on-demand retrieval

Source implementation adds current-item, observed-change and signal-aggregate
projections in the existing private Amadeus SQLite database, plus an owner-only
paged retrieval route and shared read-only MCP/local-conversation tool. The old
small feed-selection restriction is removed; prompt/preview budgets remain bounded.
The owner can adjust signal bucket size in Context feeds. Calendar occurrence
identity now uses ICS UID/original recurrence metadata when available. Retention,
revoke/rebind/disconnect, exports and forgetting cover the added tables. Existing
model workers, Pi services, listener ports and raw recording settings are unchanged.
README's context-feed edge and conversation retrieval edge reflect this data path.
Source availability is not evidence of installed migration or physical acceptance.
See [storage/logging contract](amadeus-storage.md) for remaining collector/recording
work and the private migration/rollback boundary.


Installed context-store verification: the Mac controller was restarted while idle
with a matching private SQLite rollback backup and module backups. Owner retrieval
and storage-policy routes responded, and an isolated silent local conversation
selected the shared context retrieval tool and composed a response. Existing feed
permissions and selections, device state and volume were preserved. No raw audio,
transcript or camera collection was enabled. Broader recording budgets, remaining
heartbeat collectors and resumable transport pagination remain tracked in #18.
Rollback should restore matching code and database backup together; older code
alone does not manage the new projections' forgetting/retention lifecycle.


Checkpoint reliability source changes preserve unchanged connection state and
separate authoritative feed coverage from a bounded preview, with read-time expiry
guards. These changes do not move hosting, listeners, model workers, credentials
or device responsibilities; the README topology remains accurate. This checkpoint
is prepared for PR review and has not been installed as part of the reliability
audit. The earlier installed context-store verification above remains distinct.


## Structured local conversation checkpoint

Source changes replace text/proactive-voice keyword eligibility with the shared
local tool loop. The existing MLX worker consumes typed capability schemas and
bounded result projections; there is no added service, port, model or external
account. README's conversation-to-context retrieval edge still describes this
route. Action approval, source consent, private storage and raw recording ownership
are unchanged. See [conversation contract](conversation-agent.md). This source
checkpoint requires matching controller/worker modules during installation; source
tests alone do not prove installed or physical acceptance.

Installed verification for this checkpoint: the idle Mac controller and local
worker were restarted with matching modules after a private database/module backup.
An authenticated silent dashboard-chat request selected the connected-source tool
and returned a completed reply. Separate read-only local model probes exercised
transit, household history, connected lists and preference handoff. Physical
microphone/speaker acceptance was not performed; output volume, device actions and
source permissions were unchanged. Private traces and source contents remain local.


On-demand Trakt watchlist reads reuse the existing private OAuth connection and
local tool executor. They add no service/port, scheduled collection or provider
write. Pause/guest checks and in-flight connection revalidation guard results;
controller wrappers share token-rotation locking. Dated history and date-unknown
list membership remain distinct. Recommendation routing was checked with the
local model using a read-only tool; private result titles remain untracked.
Installed follow-up verification: matching controller/worker modules were loaded
while idle with private rollback backups, and an authenticated silent dashboard
recommendation request invoked the Trakt watchlist tool. This does not enable
scheduled watch-history collection or validate streaming-service availability.


## Local pre-review privacy and credential fixes

Source-only review fixes include `household` records in owner memory/export,
include/delete the private feedback sidecar, and require source consent before
inbox alerts supplement a household recap. Trakt refresh coordination now uses a
bounded private file lock in addition to the controller's thread lock, preventing
concurrent controller/standalone MCP token rotation. This adds a credential-free
lock file under the existing private Amadeus directory, not a process, port or new
credential owner. README topology remains unchanged. These review fixes are
prepared for merge; no live services or physical hardware were changed during
the local review.


## Readiness and HA push diagnostics

The installed controller owns bounded read-only readiness probes, exposed in its
existing authenticated `/state` response and dashboard. SQLite quick/foreign-key
checks cover application databases at startup and hourly; transient failures retry
at the health interval. These do not replace backups or check HA recorder storage.
HA `/api/config` must report `RUNNING` outside safe/recovery mode. Pi display/audio,
conversation process, speech worker, configured GitHub delivery and feed coverage
remain separately reported. Failed local HA feed reads retry after at most 30 seconds
instead of waiting their normal collection interval; successful reads restore that
interval. Consent and pause gates still apply. No new listener or observation consent is introduced.

The initial controller recovery window is three minutes. Its first successful core
check writes `Startup complete` to the controller log and records the timestamp in
memory for the dashboard. A later fault does not erase that startup milestone.
This means core dependencies answered probes, not that every physical action or
cloud integration has been tested. Partial watch-history coverage is distinct from
a disconnected feed. A bounded HA current-run log sample produces fixed diagnostic
labels, never raw logs, credentials, device names or event text. A stopped Firebase
listener remains an attention item; recovered recorder sessions and callback error
history are shown separately. Absence from the sample is not proof of no faults.

The active HA 2026.10.4 container uses an optional compatibility backport for
firebase-messaging 0.4.5, installed with `scripts/patch-ha-ring-push.py --apply`.
It selects named Web Push header parameters and restores omitted base64 padding,
following [upstream PR 43](https://github.com/sdb9696/firebase-messaging/pull/43).
It also skips/acknowledges malformed encrypted packets with a rate-limited warning
rather than terminating the notification listener. It does not weaken decryption,
change credentials, replay physical actions or invent camera capabilities.

The script defaults to a dry run, rejects unvalidated package versions/source,
backs up into private `/config/.local-compat-backups`, and requires an HA restart.
The patch survives container restart but **not container replacement/upgrade**;
review upstream versions and rerun the guarded check after an image change. Restore
the backed-up Python file and restart HA to roll it back. Other Alexa backports
retain their existing independent lifecycle. `scripts/check-ha-ring-push.py` runs
inside the container with generated keys and synthetic payloads, without network
or physical events. Core startup, app database probes and synthetic encrypted push
handling were checked; real doorbell notification acceptance remains separate.

Known provider limits: ThinQ may return `2201 / Not provided feature` for a device
profile (including devices without ThinQ cloud support), which cannot be repaired
by changing local credentials. Local-only appliances require a separate supported
local interface; their appearance in an account/device list does not create one. Unknown Ring model
kinds remain explicitly unclassified rather than being assigned guessed capabilities.


## Dashboard/integration reliability checkpoint: source versus installed

The checkpoint adds in-process private disposable-file maintenance under the
existing authenticated owner application. It does not create a listener, change
ports or grant capture/source permissions. Policy defaults disabled; eligible
local files and protection boundaries are described in [private storage](private-storage.md).
The README topology remains the same hosts, routes and model workers; only the
controller's administrative responsibilities expand. HA floor/device inventory
reads use the existing authenticated registry connection, not a new discovery agent.

The dashboard has centered arrangement and progressive disclosure. Trakt source
options default to the existing 30-day, one-page read with no newly selected lists.
Larger owner-requested budgets are bounded across the history/list union; partial
coverage, account generation changes and watched-date provenance are explicit.
No automatic provider enrollment, account writes or cloud appliance enablement is
part of this change. Source/tests do not prove provider or physical acceptance.

Focus visual projection adds a high-level Pi `focus` operation with local absolute
expiry and a small countdown. Controller sync deduplicates by display session and
timer state, and only addresses a Pi reporting focus support. Existing Pi services
remain compatible without repeated unsupported RPCs. Compact browser/Mac and TV
renderers use a coarse media/presentation gate, not additional media titles.
The Pi code is source-validated; the installed satellite is intentionally unchanged
in this unattended checkpoint, so its focus badge requires the normal later update.
No speaker test, volume adjustment, display restart or physical handoff is claimed.

The reviewed Mac controller/dashboard package is installed under the existing
supervisor, with private module rollback material preserved. Authenticated startup,
readiness, new dashboard assets, disabled cleanup policy and read-only HA floor/device
schema checks passed; configured source feeds reconnected. The speech worker stayed
running. These are service/contract checks, not physical speaker/surface acceptance.
No account writes, source selections, capture permissions or volume were changed.
The Pi satellite remains at its previous installed service as described above. Protected-state
backup/restore drills remain planned in issue #81; broader collection/storage
consolidation and lifetime-history imports remain issue #18.


## Chores and configurable check-in cadence

The chore source changes use the existing Mac controller, private Amadeus SQLite
preferences and scoped HA tag route. They add owner-only chore management endpoints
under the existing port, not a new service or capture permission. Plans and latest
completion/reminder state are private per-profile records; exports/forgetting cover
them. Existing tag configuration remains separate and missing chore references are
inert. No provider or hardware state is used to infer completion.

Morning and proactive paths read grounded overdue task state; successful speech
alone acknowledges a reminder. Source-level privacy/availability gates and the
shared durable invitation budget apply to general and chore check-ins. Owner
frequency controls preserve enabled state, destination, session state and budget;
repository defaults remain conservative. Actual owner cadence choices and chore
plans are private configuration and must not appear in this inventory.

The Mac package is installed and owner-authenticated checks confirm the chore API,
configurable cadence readback, controller readiness, speech readiness and existing
feed/device connections. The controller child alone restarted; the model worker,
source consent, destination and volume were preserved. No real NFC scan or speaker
test was performed. Pi/HA tag firmware/automation configuration does not need new
permissions for the action. See [chore behavior and API](chores.md).

## HA home-device context

The home-device adapter uses the existing Mac HA read connection and private
Amadeus store; it introduces no service, port or actuation route. Owner selections
are dashboard editable. HA vendor integration installation is separate from
source consent. The Mac adapter is installed and an owner-selected garage cover
returned a valid state through the consented read path. Source collection choices
remain private and dashboard editable. No physical actuation was performed.
The Watts Home community component is installed in the private
HA configuration; account setup and live thermostat reads remain unverified until
the owner signs in. No vendor credentials or household bindings are in source.
NextCentury API access is a pending account capability check, not a deployed feed.

## Watts and TP-Link HA onboarding verification

Watts Home account setup is complete: its HA entry is loaded and selected climate,
room-temperature and floor-temperature entities returned available metadata through
the home-device feed. Selection remains private and editable in Context feeds.
Diagnostic entities may have separate capability limits; loaded state does not
prove every optional vendor sensor works. No setpoint or heating-mode change was tested.

TP-Link Smart Home now has configured legacy Kasa switch entries loaded through
local discovery. Credential-dependent Kasa switches were subsequently onboarded
using the owner-saved TP-Link connection; all switches found in that bounded scan
now have loaded HA entries. Discovery
used bounded SSDP/mDNS and TP-Link read-only queries on the current LAN. No light
was toggled, no new light-observation feed was enabled and no new network service
was exposed. Household addresses, names and scan details stay in ignored state.

## Sonos HA local integration

HA's native Sonos integration is installed and loaded. It exposes the room
coordinator as a media player; bonded surrounds/subwoofer are not independent
playback destinations. Read-only diagnostics confirm coordinator availability,
active event subscriptions without subscription failure, and received event/cache
entries. This is service-level validation, not an audible playback test.

The Docker container retains the same image, configuration volume, environment,
restart policy and HA HTTP bindings. It additionally publishes Sonos TCP 1400 on
the controller's specific LAN address. Private HA Sonos configuration supplies
manual speaker hosts and the advertised LAN callback address, avoiding Docker
multicast discovery limitations. A stopped pre-change container is retained
privately for rollback. Only one HA container is running against the volume.

The optional `OKABEBOT_HA_SONOS_BIND` launcher setting reproduces the callback
mapping for a new container; it defaults off and rejects unspecified, public or
loopback addresses. See the Sonos section of [HA setup](home-assistant.md).
No volume, grouping, playback, Amadeus source consent or existing character
announcement route was changed.

## Amadeus room-activity source

The source adapter adds selected HA lights, switches and speaker states through
the existing Mac-to-HA read connection. It shares the private stable-ID store,
retention and noisy-signal aggregation; there is no new service, port or credential.
The owner dashboard edits selections and consent. Track titles/URLs and light
brightness/speaker volume are excluded. Source permission does not authorize
actuation or infer occupancy/identity.

The additional proactive speech gate defers on selected playing/buffering speakers
or incomplete/expired/unknown playback evidence. Polling is once a minute and
freshness is 150 seconds; immediate detection is not promised. Existing attention
gates and audio destinations remain unchanged. The Mac adapter is installed; an
owner-authenticated feed read confirmed complete minimized records for explicitly
selected primary light-switch and Sonos player entities. HA configuration/diagnostic
switches were excluded from the private selection. No actuation or audible test
was performed.

## Household nudge planner

An opt-in planner uses the existing Mac controller, HA context feed store and
per-profile private preferences. It introduces no service, port, new source
permission or hardware-control route. Away-light candidates are readable private
Today dashboard notes only. Bedtime and room-comfort candidates use the current
proactive delivery path, shared budget, attention/home gates and output destination.
All choices are owner editable in Amadeus setup. Floor readings are never compared
to room thresholds. Climate readings without units may use HA's fixed config API
for its temperature unit; no other HA configuration fields are retained.

The Mac package is installed. Owner-authenticated readiness and settings readback
confirm the planner is available and observing permitted sources; existing
voice/display and feed connections recovered. Private owner choices remain in
local state. No physical acceptance, audible test or device-control action was
performed; volume, destinations, source scope and health preferences were preserved.
See [household-nudge semantics and privacy](household-nudges.md).

Household comfort presentation uses Fahrenheit in its controls and spoken notes;
canonical Celsius threshold storage and unit-aware comparison remain internal.
This changes no thermostat setpoint or device unit setting.

## NFC tag-area inheritance

The controller refreshes HA tag registry area metadata via its existing authenticated
HA read connection. No new host, port, credential or source-observation permission
is added. A five-minute in-process metadata refresh maintains a private ten-minute
connection-generation-scoped cache under the existing tag state directory. Owner
refresh uses `/tags/refresh-areas`; HA's publish-only scan key cannot invoke it.
Stable tag IDs associate mapped actions and current chores with HA room/floor IDs.
The cache stores configuration metadata only, never scan activity or presence.
Chore due/completion state and saved movement destinations remain independent.
The Mac package is installed. An owner-authenticated live registry refresh verified
assigned area metadata on existing mapped tags and the chore room projection.
Controller, speech, Pi and configured feed readiness recovered. No tag scan, chore
completion, screen movement, volume change or audible acceptance test was performed.

## Explicit NFC room cues and following

The existing controller/tag ingress can optionally resolve selected tags through
HA areas and the saved screen room bindings. No new endpoint, service, credential
or radio scanner is introduced. Each tag remains off until explicitly selected.
The owner tag configuration controls cue duration and an optional same-room screen
choice; room ambiguity never selects an arbitrary display.

The current expiring cue is private tag state, scoped to the owner profile revision
and current metadata/mapping. It is presented as scanner evidence with unknown
identity, separate from home/away estimates and retained observations. Movement
uses the existing high-level surface command/handoff, with no new playback, speech
or volume action. The Mac package is installed and owner-authenticated checks
confirm the room-cue schema and opt-out preservation on existing mappings.
Controller, speech, Pi and existing source readiness recovered. No selected tag
was scanned, no cue was fabricated and no physical move or audio test was sent.
Room bindings/explicit target selection remain owner setup; isolated tests do not
establish physical acceptance.

NFC screen resolution now prefers a unique same-area screen, or an explicit
same-area choice when several exist. With no same-area screen, only an explicitly
saved approved fallback may be used across areas. Destination labels show HA area
names from the metadata cache. Room cues still refer to the scanned tag’s area;
this adds no implicit adjacency, area merge or automatic cross-room fallback.

The installed owner API was checked for destination-area labels and explicit fallback resolution without replaying a scan or requesting a handoff. Physical acceptance of the fallback remains an owner check.

### Private health context and encouragement

The controller's existing HA read connection can collect owner-selected daily
wellbeing totals through the context-feed registry; no new service, port, cloud
processor or device transport is introduced. Goals, shared-room overrides and
source bindings live in private Amadeus state and are editable in owner dashboard
controls. Movement encouragement reuses proactive/morning coaching delivery and
its consent, timing and audio routes. Other-person detection is a configurable
input gate, not an installed identification system; it defaults false until the
owner binds signals. Source implementation and actual configured collection must
be verified separately. The existing README topology remains valid.

Installed capability checks confirmed controller startup, existing source feeds,
speech and Pi connectivity after the health UI/adapter update. Health collection
and goal-backed support remain disabled by default pending private source/goal
selection. No health speech or physical device change was used for acceptance.

Owner HA registry previews now include bounded classification/unit hints for
field-specific feed selectors; no raw sensor values or registry unique IDs are
added to discovery output. Hosting, ports, routes and source ownership are
unchanged. Source provenance labels do not attest upstream Health Connect writers.

Health review hardening keeps ongoing conversation consent separate from offer
cooldowns: stopping/snoozing coaching, disabling goal/source support or revoking
the source discards pending health context/replies. A configured privacy-sensor
binding remains fail-closed when its feed is disabled or HA is disconnected. The
MCP health retrieval schema and reply projection now match the registered feed.
Hosting, ports, device state and installed configuration are unchanged by this
source review fix; no live deployment or physical acceptance is claimed here.

### Morning digest and weather presentation refresh

The Mac controller's morning adapter can read fresh selected task, transit and
meal-plan context through the existing private stable-item store. Owner section
settings use `morning.digest`; no new collector, network route, port, credential
or HA transport is added. One optional spoken highlight is revalidated before the
existing destination audio route. Weather sprites are authored canvas pixels in
the existing TV lab renderer, with no downloaded assets or external requests.
README topology nodes/edges remain unchanged. Source checks and synthetic visual
preview are distinct from installed-state and physical wake/audio acceptance.

Installed Mac owner-API checks confirmed the new report-section controls,
consented-context card selection and served weather-sprite asset. Controller,
speech, Pi links and existing feeds recovered after the idle update. No report
was presented or spoken as part of these checks; physical wake, rendering and
listening acceptance remain separate.

TV launch hardening in source waits for the warmup-page send acknowledgment
before proceeding to dashboard handoff. An already-live matching morning
receiver can bypass redundant wake/reload preparation. Request counters now
include explicitly configured secondary Cast hosts rather than only the primary
media receiver. The diagnostic counter and launch/replay hardening are installed on the Mac
controller. Owner API checks confirmed service recovery and a fresh destination
connection; physical output acceptance is separate. No new ports, devices or ownership routes are added.
Controller-restart reconciliation remains tracked separately.

### Android read-only conversation tools

Android text and voice use the existing local conversation worker with a per-turn
read-only tool menu and an execution allowlist. They can read connected household
context without gaining owner authority or device-control operations. The private
HTTPS proxy, pairing, consent, storage and Firebase routes are unchanged. Physical
phone audio acceptance has been confirmed; read-tool deployment verification is
recorded separately from source tests. Installed controller startup, speech readiness
and existing feed connections were checked after installation. Source regressions
cover the mobile read-only callback and action rejection; a phone lookup remains
a separate user acceptance check.

Android lifecycle source preserves the paired WebView across native tab changes
and ordinary app backgrounding, with screen-off/close release and a bounded
heartbeat for an already-arrived destination. No new hosting, port or permission
is introduced. Private reply playback is isolated from unrelated audio-hub polling
failures. Android physical lifecycle acceptance remains separate from regressions.

Private mobile synthesis now participates in the existing shared speech lock used
by Mac supervision. A busy local voice worker is not health-restarted during that
generation. Hosting, audio targets, permissions and model selection are unchanged.

Android native reply playback is a client capability, separate from synthesis
on the Mac. Generated WAVs use the phone media output and saved companion gain,
with explicit completion/failure events and private-cache cleanup. No server
routing, hosting, source consent or device-volume default changes are required.

Mobile voice diagnostics expose bounded in-memory stage durations only; this does
not add a history store, cloud telemetry, new port or integration route. Server
durations exclude phone capture, network roundtrip and native playback startup.

Private HA remote access verification confirmed HTTPS frontend and auth responses,
authenticated WebSocket access, and explicit promotion of the managed HTTP proxy
configuration after restart. Existing private Serve 443 remains configured; public
Funnel is disabled. Remote phone acceptance remains a user check.


## Shared streaming audio checkpoint

Source changes unify mono 24 kHz PCM delivery for native Android and the existing
Mac/browser/Pi streaming paths. Android opts into incremental mobile replies only
when its APK advertises the native PCM capability; older APKs retain the working
WAV path. The shared relay adds bounded backpressure, session/consent/destination
cancellation, sequence validation and playback-drain acknowledgment. A short first
packet reduces avoidable producer buffering for Pi reply streams. Prepared Pi
announcements, Beam overlays and Alexa conversational responses keep their current
buffered adapters; no model/reference/volume changes are part of this checkpoint.

TV's conservative full-buffer playback remains the default. Explicit startup
metadata can opt a stream into incremental delivery, but no TV sound-quality
acceptance is inferred from browser or emulator regressions. The shared streaming
contract and platform exceptions are in [streaming audio](streaming-audio.md).

Automatic source checks include Python and web regressions, signed Android build,
unit tests, native silent-PCM emulator drain tests and Python release packaging.
Installed state and physical acceptance are recorded below after installation;
source changes alone do not establish platform playback quality.

Installed checkpoint verification: the Mac package was installed while idle and
only the controller child restarted. Core startup, speech readiness and the
existing device/feed connections passed checks afterward. A synthetic isolated
receiver exercised the installed incremental relay against the local voice worker
and acknowledged ordered delivery; no speaker or household destination was used.
Android 0.1.5 build 7 was privately distributed through the existing Firebase
project. Phone installation/listening and refreshed Mac/Pi playback remain manual
acceptance checks. The model worker and private reference manifest were unchanged.


Proactive opener source now filters newly learned preference fields using private
per-field recency metadata and a dashboard-editable cooldown. Legacy last-memory
metadata supplies a conservative fallback. This changes opener-context selection,
not collection consent, direct recall, destinations, ports, or health/chore gates.
Source checks cover cooldown expiry/disable, preserved direct recall, skipped
empty-context openers, and metadata deletion. Installed acceptance is recorded
separately from these synthetic checks.

The opener freshness change is installed on the Mac. Core startup, speech readiness
and the private conversation API confirmed the default cooldown after installation.
No unsolicited speech or physical-device test was initiated for this verification.

## Proactive conversation feedback checkpoint

Source adds a bounded private delivered-suggestion journal, paired Android
explanation/feedback routes and local-time optional chat windows. Grounded
watchlist recommendations reuse the existing Trakt adapter and permitted cached
history. These are controller/model and paired-client responsibilities; no new
host, port, provider credential or collection consent is introduced. The shared
model worker validates dynamic tool schemas per request so read-only turns cannot
poison later tool definitions. Private synthetic persona exercises use isolated
state and fake read providers; they do not exercise household devices or prove
physical speech/timing acceptance. Installation is verified separately below.

Installed verification for this checkpoint: the idle Mac controller was restarted
with the updated package and paired proxy. Core startup, speech readiness, Pi
voice/display connectivity and configured feed connections passed read-only checks.
Android 0.1.6 build 8 was privately distributed through the existing Firebase
project. New explanation/feedback UI and recommendation listening still require
phone acceptance; no household speech or volume test was initiated here. The
hosting diagram remains unchanged.

## Offline prompt evaluation capability

Source provides a disposable local-model evaluation process, separate from the
installed controller and its conversation state. A run imports only local-model
settings, creates synthetic configuration/state, uses fixed turn clocks and
closed-world provider results, and performs no hardware/provider calls or speech
synthesis. It is not a resident service and adds no listener, device, credential,
or integration route. Candidate prompt files, including an optional tool-free
intent-classification stage, are offline source proposals. They are not evidence
of an installed prompt or model change. Runtime outputs remain private/ignored;
core fixtures and instructions are in [the evaluation guide](../evals/README.md).
Run durations are diagnostics under shared Mac resource contention, not physical
button-to-speaker benchmarks. The existing deployment diagram remains valid.


## Owner text-lab prompt treatment capability

The controller's owner-only `/amadeus/text/treatments` operation stores treatment
selection/custom drafts in private Amadeus state. The existing local worker accepts
request-scoped conversation/routing/continuation policy text for the owner text lab;
other surfaces keep their normal policies. Non-default text experiments enforce
read-only tools and suppress memory writes in application code. No new service,
port, external provider or credential is introduced; the README topology remains
unchanged. Source and installed activation must be verified separately. See
[controls and limitations](conversation-agent.md#owner-prompt-treatments).

Installed Mac activation was verified on 2026-10-30: the owner treatment operation
returned all four presets, production default remained selected after a silent
text-model smoke check, and the dashboard rendered the controls. Existing speaker
volume was preserved; no hardware speech test or change to other surfaces' policies
was performed. Subsequent prompt edits take effect per request without restart.


## Upstairs USB developer-board observation

A read-only check on 2026-10-30 found a USB STM32 CDC ACM serial device on the
upstairs Pi with a persistent by-id path. It is consistent with the pictured
Grove/Alfa kit, but generic USB descriptors do not uniquely identify board firmware
or attached Grove sensors. The Pi has no power-throttling flags; no process is
consuming the serial device, and its room-sensor port is unconfigured. No serial
port was opened, firmware flashed, service restarted or peripheral claimed working.
The README map now records the detected physical attachment separately from a
configured collector. Sensor models and socket assignments are a manual prerequisite
for safe firmware setup. A local USB JSON → existing satellite/HA path is proposed;
cellular service is unnecessary and has not been configured.

Follow-up photos and the owner's wiring confirmation identify the Twilio Alfa /
Wio LTE Cat-NB-IoT v1.0 board with DHT11 on A6, Grove Button(P) on D20 and Grove
Ultrasonic Ranger v2.0 on A4. A bounded serial read finds the original Breakout
cellular demonstration firmware, not sensor JSON. USB-only replacement source is
`firmware/wio_room_sensors`; it compiles with Seeed STM32F4 1.2.5 and the Seeed Grove
DHT library. The reader accepts climate without a fabricated tilt contact and
separately expiring button samples. Compilation alone was not treated as evidence
of sensor accuracy; installed verification follows below. No cellular account or
new automatic action is configured.

Installed follow-up: the original flash was privately backed up, USB-only firmware
was uploaded through STM32 DFU, and fresh JSON climate/button packets were read.
The upstairs Pi now runs the tested reader with a persistent USB by-id binding;
its older installed display service received only the minimal sensor RPC hook and
configuration key. Unrelated renderer code was preserved. The separate HA satellite
publisher now forwards validated optional readings under the existing satellite
device. Temperature, humidity and released button state are available in HA;
distance discovery exists but missing echoes remain unavailable. Hand-distance
accuracy and a physical button transition require the separate manual check.
The six-second local freshness gate and 45-second HA expiry apply; HA snapshots
arrive on the existing 30-second telemetry interval, so brief button presses are
not guaranteed HA events. No movement, wave, speech or Amadeus collection rule was
enabled by this sensor setup.

HA's container had lost membership in the shared private MQTT Docker network.
The existing network link was restored, DNS and MQTT reconnection were verified,
and prior satellite telemetry became available. The corrected start helper is
installed and preserves or repairs that membership; it was syntax-checked without
recreating HA. This does not introduce public ingress or change
published ports. Firmware and service rollback copies remain in private state.

## Conversation state/resolution source checkpoint

Source now has bounded expiring query-task state, deterministic calendar and named
speech-target binding, per-field notification PATCH updates, and separate operational
routing/optional character-style prompt assembly. These are internal responsibilities
of the existing Mac controller/model worker, not new hosts or listeners. Offline
runs use synthetic private configuration, fake tool executors and injected target
registries; they do not actuate devices or import household history. The checkpoint
has not yet been promoted merely because its source exists. Installed acceptance
must be recorded separately after verification.


## Room-aware selected sensor retrieval

The installed controller now enriches selected HA home-device and room-activity
readings with assigned room metadata via a bounded metadata-only HA template read.
No new host, listener or credentials are introduced; the existing HA feed route and
dashboard selection remain authoritative. Retained-record and synthetic-executor
search use literal keyword conjunction across room/measurement fields. Source
fixtures are invented; private live readings and chat verification remain ignored.

Deployment is scoped to feed schemas/providers, record retrieval, post-tool reply
grounding and a room-temperature routing clarification. The broader experimental
conversation-state architecture has not been promoted by this change. Existing
controller/model processes were restarted while idle to load those scoped edits;
speaker volume and location policy were preserved. README topology nodes/edges
remain unchanged because hosting and integration responsibilities are unchanged.


## Pooled SSH recovery hardening

The installed controller now rate-limits repeated failed pooled SSH handshakes
with a monotonic exponential cooldown from two to thirty seconds per endpoint.
Success resets the cooldown. Only a later separate request may reconnect; failed
physical operations are not replayed, and an uncertain operation on an existing
tunnel retains its prior no-replay recovery behavior. Focused synthetic regressions
cover throttling, reset, bounded delay and action non-replay. Hosting, credentials,
verified host-key policy and README topology responsibilities are unchanged.

A live diagnosis found the companion endpoint responsive to ICMP while new SSH
connections stalled before a server greeting/authentication. Temporarily pausing
automatic connection producers did not restore access. This does not establish
an OS, memory, power or credential cause: those require device-side logs. The
backoff is a controller-side mitigation, not a claim that the Pi is repaired.


Follow-up recovery verification: an owner reboot restored SSH, display/voice
connectivity and fresh numeric room-sensor records. Retained syslog evidence showed
a kernel worker blocked in the SD-card detection / MMC host-claim path, followed
by the logging service watchdog timing out. This is evidence of a storage-path
stall, not proof of failed media or a specific driver defect. The endpoint runs
legacy kernel 5.4.51+; current-boot power flags are clear, which does not establish
previous-boot power health. Private logs and a configuration-only backup were
preserved. A full offline card image, replacement-media test and supported OS/AIY
compatibility validation remain planned, not performed.

## Reliability checkpoint: source versus installed state

The checkpoint source adds an opt-in `presence_history` HA feed and the read-only
`get_presence_history` conversational tool. It reads only selected person/zone
entities, with a bounded history window covering local today/yesterday. It stores
stable occurrence IDs without coordinates or entity attributes, using generic person labels. Baseline
snapshots, changes, zone counts and person reports remain distinct; unknown states
break reported-away intervals. The owner's consent, pause/guest mode, retention,
source revocation and private source picker remain authoritative. Existing installed
latest-state collection is not evidence that this history feed is enabled.

Cast source now records exact launch session receipts in private
`state_dir()/cast-ownership.json` (0600). On startup with receipts it reports
`reconciling`, holds the Pi away and retires only an exact configured Cast/session
match. A different session/app is left alone. Unreachable or removed destinations
remain an explicit recovery fault, rather than being silently declared home. Return
still requires the existing Pi render acknowledgement. Fresh URLs and audio sessions
are obtained on the next requested visit; expired tokens are not adopted. Manual
follow holds, destination settings and volume are preserved. This cannot identify
an orphan created before receipts were installed; do not stop an app by name alone.

Conversation source also adds short constraint-removal follow-ups, bounded immediate
notification pause/resume phrasing and guards that separate quoted message payloads
from requested actions. These are source changes, not a production model/prompt
promotion or proof of broad conversational accuracy.

The [configuration collector and spare-card runbook](companion-recovery.md) prepare
private read-only diagnostics and selected configuration backup. They do not perform
an OS migration or full offline card image. Spare-card Voice Bonnet compatibility,
restarts under an active owned Cast session and physical recovery remain acceptance
checkpoints. Newly added reliability source has not been deployed merely by opening
a PR. Existing installed-state sections above remain scoped to their stated checks.

README topology was reviewed: these changes reuse the existing Mac controller,
private store, HA read connection, SSH path and Cast adapters; no new host, listener
or credential is introduced. Android/Tailscale/FCM and upstairs sensor responsibilities
remain as shown in the maintained diagram.

Calendar reply follow-up source rejects scope-only/technical-header answers and
provides a natural empty-calendar fallback. This changes composition on the existing
controller only; it adds no collection, route or inference worker. It has not been
installed by updating the checkpoint PR; physical playback is a separate check.

Installed calendar/audio follow-up: narrowly deployed the calendar reply validator,
natural fallback and length-aware Qwen clause token budget. The controller child and
voice worker were restarted while idle, with private rollback copies. Startup checks
confirmed model, speech and both companion endpoints available. Silent invented-text
synthesis exercised completed PCM after the budget adjustment; it did not play audio
or establish physical phone listening acceptance. Volume, reference conditioning,
source consent and other experimental conversation/recovery modules were preserved.
The broader checkpoint remains source-only where noted above. README topology is
unchanged: the same Mac controller and existing local speech worker own these paths.

Installed shared-surface alert follow-up: companion assets now clear errors by the
operation that recovered, updating the main notice, settings notice, setup error
and status indicator consistently. Successful network polling does not dismiss an
unresolved audio or permission failure. Only the two static companion JS files were
updated, with rollback copies; no service restart, volume or device-state change.
The Android inline document was fetched to verify updated assets and no-store
responses. Already-open views need a reload/reopen; no APK update is required.
Hosting, listeners and README topology remain unchanged.

Installed Pi thinking-cue follow-up: the satellite renderer now adds a small animated
pixel thought bubble for every character's thinking activity, above the shoulder
and clear of the lower media/notification region. Only the scoped scene helper and
its thinking-state composition call were installed, preserving other deployed Pi
renderer differences. The display service was restarted while idle; the voice
service and volume were unchanged. RPC activity and a digital preview verified the
cue with no renderer error, then idle was restored. Physical button-turn visibility
is a separate owner check. No hosting/transport or README topology changed.

Android notification pilot acceptance now includes system-alert presentation,
tap-to-open and retrieval of the private test note from the inbox. Enrolled-phone
notification enablement is independent of pairing and OS permission; it must be
explicitly enabled. The source APK toggle is now labelled `Enable notifications`,
with separate no-sound explanation; that label ships with the next APK, not by
changing server assets. Existing inbox entries persist under normal retention and
are not evidence of duplicate sends. Widget and broader lifecycle coverage remain
open. No notification bodies, participant records or device identifiers are recorded
in this public inventory; hosting and README topology are unchanged.

## Expressive work foundation — source checkpoint

Readable prompt Markdown is bundled with the controller package. Directory-owned character definitions assemble the motion catalog served through
existing surface assets. `scripts/package-pi.py` copies the same character package
beside satellite Python files. There are no new ports or hosting roles;
the README deployment topology was reviewed and remains unchanged. Deploying this
source requires coordinating controller/web assets and the complete Pi bundle.

The controller's private Amadeus preference store owns temporary preparation drafts
and motion settings. An isolated renewer sends content-free work stages over the
existing display RPC; device-local expiry prevents stuck work after disconnects.
Owner-only dashboard draft routes are not added to the mobile proxy allowlist.
No retailer adapter, proactive preparation schedule or new collection is enabled.
The controller preparation/UI changes remain source-only; the scoped Pi display
installation is recorded below. No full-controller promotion or physical acceptance
is claimed by this checkpoint. Alexa dynamic work animation remains planned.

## Directory-owned character display update (2026-10-31)

The companion Pi's display subset is now installed: character interfaces and owned
art/motion files, compatibility face facades, scene composition, leased work state
and the display service's required focus helper. Python 3.7 import/render preflight
passed on the satellite; its display service and RPC recovered, and automatic
status reported no animation error after restoring the selected character. A local
rollback copy of the prior display files remains on the Pi. The voice service was
not restarted or replaced, and no audio/volume configuration was changed.

This is a scoped Pi display installation. The controller's new dynamic character
chooser, registry-backed portrait routes and private preparation dashboard remain
source changes in the PR; the existing installed controller and model workers were
not replaced. Advanced browser/desktop workbench rendering is also source-only.
The Pi can show the new golden work poses through its leased work interface and
idle catalog. Grocery adapters/proactive preparation jobs remain planned. Physical
elbow/gaze/pacing acceptance is separate from automatic service/render checks.

README topology reviewed: existing display RPC, hosting roles and ports are unchanged.
