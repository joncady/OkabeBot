# Current deployment and configuration

Last verified: **2026-10-26**. This is the maintained inventory of the existing
installation, not the defaults for a new user. The [README diagram](../README.md#current-deployment-map)
shows the connections. Keep both documents in sync when roles or hosting change.
Private IPs, credentials, account IDs and token-bearing URLs belong in local
configuration, not this inventory.

## Devices and responsibilities

| Device | Hosted role / connection | Current state and limits |
| --- | --- | --- |
| Apple Silicon Mac, 16 GiB RAM | Controller, local transcription, conversation and speech inference, integration adapters, dashboard, private application state; separate Home Assistant Docker container | Active host. Native controller is supervised by a user login LaunchAgent; Docker/HA has a separate lifecycle. |
| Raspberry Pi Zero W Rev 1.1 | One Wi-Fi/SSH satellite running `hardware-lab` and `hardware-voice` systemd services | Reachable again during the 2026-10-27 scene acceptance pass; both services verified active. Wi-Fi logs show earlier carrier losses followed by reconnection. No conversation or speech model inference runs here. Legacy OS/AIY dependencies remain in place. |
| UCTRONICS B010601 3.5-inch LCD | Pi X11/Tk character renderer through the existing OS display configuration | Native framebuffer verified 480×320. Screen blanking disabled by the display service. Touch is not configured; no new GPIO-display conversion is claimed. |
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
| Earlier display Pi, iPad and Elegoo R3 kit | Spare/test hardware | Not required by the current pipeline; no active backend or adapter role is assigned here. |

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
A Mac login is required for the per-user LaunchAgent; Docker's restart policy
does not start Docker itself. This is not an unattended pre-login server.

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
location. Japanese speaker-embedding conditioning is an isolated private trial,
not a deployed voice change.


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
character/mode and a warm six-sample transcription check. The existing English
ICL references remain installed. Speaker-only conditioning is feasible with the
installed MLX-Audio version, but accent/tone acceptance remains a listening test.
See [comparison details and measured limits](voice-conditioning.md). No training,
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
