# Companion surface design language

The companion is a small pixel-art presence, not a status dashboard attached to a
character. Communicate activity through posture, expression and small symbols.
Keep information readable, purposeful and consistent across destinations.

## Shared vocabulary

- **Ready:** relaxed face, slow blink. A small check appears after setup/actions;
  avoid a permanent “Ready” or “Here with you” caption.
- **Listening:** attentive expression and microphone glyph. A clear pressed state
  and accessible “Listening” announcement identify real capture. Never imply a
  live microphone before permission and capture succeed.
- **Thinking:** thoughtful expression and a tiny clock/thought sparkle near the
  head. Avoid large loading banners or dots over media titles.
- **Speaking:** mouth follows the playback envelope; a small speaker glyph can
  clarify the audio destination. No fake mouth loop after playback stops.
- **Moving:** walking in the spatial direction and a small connection glyph.
  Show a character only on its owning screen; leave the away sign on the Pi.
- **Offline / needs attention:** muted connection or amber/red warning glyph.
  Retain an accessible description and actionable detail in settings. Do not
  communicate a fault by color alone or silently hide a failed permission.

Use shared square-grid icons for summon, microphone, home/return, sound,
picture-in-picture, settings and close. Shapes carry meaning without app-specific
labels. Icon buttons still have meaningful accessible names, focus states and
hover/focus tooltips; “less text” never means less accessible.

## Visual tokens and motion

`okabebot/web/surface-theme.css` owns the initial web tokens: dark blue slate
background, muted teal panels/edges, warm off-white ink, mint activity, amber
attention and muted coral errors. Character colors retain their source palette.
Use square corners, stepped edges, restrained inset shadows and crisp pixel
clusters. Avoid pill-shaped controls, large gradients, glossy cards and decorative
status paragraphs. Web controls use system monospace fonts; do not download a
font or sacrifice small-screen readability for novelty.

Draw sprites on an integer grid with nearest-neighbor scaling. UI icons use a
24-unit grid with square details. Phone/tablet targets are at least 44–48 CSS px;
Mac secondary controls may be 32 px when accessible by mouse/keyboard. Preserve
visible keyboard focus, readable contrast and OS reduced-motion preferences.
Animations should express intent, not compete with content. Idle animations are
infrequent; warnings and notifications interrupt with purpose.

## Surface contracts

| Surface | Visual role | Controls and information |
| --- | --- | --- |
| Pi companion display | Always-on pixel companion with opaque dark scene | Expression first; readable notification in lower panel, app/content assets in reserved side areas. Hardware button handles talk. No developer text or repeated setup chrome. |
| TV | Spacious pixel laboratory | Character moves between room anchors. Notifications and agenda live on in-world monitors; avoid floating dashboard paragraphs. Doorways communicate movement. Voice/MCP remain primary input on the current Vizio. |
| Native Mac | Quiet transparent desktop companion | Small borderless floating character, small six-dot drag button beside controls, icon toolbar revealed on hover/focus. No persistent heading, status sentence or permission buttons after setup. Compact notification strip remains contextual. Settings contain volume, naming and permission review. |
| Phone browser | Touch-friendly portable companion | Same icons/activity language, larger targets and an opaque readable stage. Tap/hold talk, summon, return and PiP; advanced preferences behind settings. Browser video PiP is view-only. |
| Tablet/dashboard | Controller for the whole home | Large character/location targets and shared pixel tokens. Labels remain where needed to distinguish destinations/actions. Detailed configuration and transcripts belong in dev/settings views. Do not strip useful administrative text just to meet an aesthetic. |
| Future Echo Show / Android widget | Proposed adapters | Reuse identity, activity and action semantics; respect platform controls and permissions. These are not implemented surfaces. |

These are contracts, not permission to add unrequested adapters. A shared
operation (summon/move/talk) keeps the same meaning on every surface, even when
its physical interaction differs. Location IDs, display names and spatial
coordinates remain configuration/registry data, not visual hardcoding.

## Front-loaded setup

First visit shows a small setup card: pair/approve this screen, enable sound,
and request microphone consent on an explicit button. The microphone stream used
to check permission is immediately stopped; setup never records or submits speech.
The user can deliberately choose to continue without a microphone.

Only successful capability checks enable **Ready**. Confirming it removes the
setup card and its permission controls. Keep volume, talk mode, naming and
permission review under the settings icon. Remember completion and preferences
per origin/device. Stored flags are not proof that the OS still grants permission.
Recheck capabilities where supported; a revoked permission or autoplay restriction
shows a small settings/attention glyph and an explanation inside settings.
Never silently regrant OS access, replay failed audio, or continually prompt.
Browser audio may require a new user gesture after reload/suspension; this cannot
be guaranteed away by saving a preference. HTTPS/HTTP have separate identities.

On macOS, closing a consent dialog must never terminate the floating app. Only
closing the companion itself should quit it. The current development build uses
an ad-hoc signature; OS consent behavior after rebuilding is distinct from a
stable, signed distribution.

## Notifications

Notifications briefly take the character's attention and use the surface's
reserved information area. App glyph → concise title → optional short body is the
preferred order. Group related events; priority controls interruption and optional
sound, independently of character location. Keep private detail out of ambient
views unless explicitly configured. Never use narration or persistent prose for
ordinary connection/activity state.

Current compact Mac/phone cards show only a short title. Richer app logos, bodies,
counts and notification interaction remain follow-up; TV/Pi retain their existing
richer renderers. This document does not imply those renderers are identical.

## Implementation and review

The initial rollout applies shared web tokens to dashboard, TV and companion
controls; Mac/phone use the compact icon UI and capability setup flow. Pi art and
TV room retain their existing rendering systems. Future changes should reuse
these tokens and activity/action semantics rather than introduce a second visual
vocabulary. Check every change at Pi native resolution, phone touch size and Mac
over a light and dark desktop; test keyboard focus and setup success/denial.
Verify the active deployment before describing a design as shipped, and update
this guide, README topology and deployment inventory when responsibilities change.


## Character home environments

The web scene adapter selects a home environment independently of device and
movement state. Sonic uses an original Green Hill-inspired pixel landscape:
checkerboard cliffs, grass, palms, sunflowers and rings. Mac/phone receive a small
transparent island; the TV receives an outdoor scene with the same movement
anchors and an in-world wooden notification/agenda sign. Legacy deployments retain the pixel laboratory for other characters and the
original Pi portrait scene. The scene catalog below adds selectable alternatives. Scene-world setup is now
active in the maintained Mac/Pi installation; observed tests and remaining
physical acceptance checks are recorded in the deployment inventory.

`character-environments.js` owns theme selection and scenery; location adapters
and content parsers do not draw it. Compact scenes must never paint an opaque
full-canvas background on the Mac. Notification and arrival/departure contracts
continue to apply to every environment. No background music starts automatically.

Compact notifications use a shared 58-pixel canvas card with a provider glyph,
title, brief body and grouped count. It occupies the bottom band, preserves the
character face and is included in video PiP. No provider adapter draws its own
card. Long text ends with an ellipsis; detailed content stays in the dashboard.

## Sets are places

Use Room and Companion for presentation sizes. A physical location reserves one
set per character across both sizes; never imply the same place exists on two
screens. Unassigned screens have no actor. Preserve the movement owner and door
directions when changing scenery. The scene catalog, ownership rules and current
source-preview limitations are documented in [surfaces](surfaces.md#scene-sets-and-world-rules).


## Owner dashboard hierarchy

Companion and current location are primary; daily tools are a compact secondary
column. Navigation anchors preserve remembered access and restore an authorized
collapsed section without revealing a hidden owner panel. Pairing/scene/audio
configuration, notification policy, transcript and runtime diagnostics are advanced
disclosures rather than a continuous stack of forms. Amadeus sources, morning,
routine preview and memory use closed disclosures; pause/guest boundaries stay
prominent. Native details/summary preserve keyboard interaction and accessible names.

Relative-screen maps center their occupied grid in both axes. Use scrollable
internal bounds for extreme coordinates; never shrink destination buttons below
usable touch size or hide negative coordinates. Physical HA floors/rooms remain
separate from visual screen directions and from inferred presence.

Silent focus uses a small pixel hourglass/countdown and calmer idle motion. It
expires locally and yields to speech, listening, thinking, notifications, media,
deployments and travel. It neither speaks nor changes notification audio policy.
