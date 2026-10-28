# Additional character surfaces: feasibility

Research checked 2026-10-26. Alexa remains proposed. Browser/Mac destinations are now implemented; see
[browser surfaces](browser-surfaces.md) for deployment and remaining phone tests.
The base configuration has one Pi and one Cast destination; approved browser/Mac
instances are added through the persistent registry.

## Echo Show 15

Start with a manually opened Silk browser proof of concept, reusing the Canvas
renderer and a dedicated limited surface capability. Amazon documents Silk on
Echo Show. Test the actual Show's firmware, LAN access, audio unlock, idle timeout,
screen dismissal and reconnection before treating it as a dependable destination.
A browser page does not itself create an Alexa voice skill or grant access to the
Show microphone. Do not promise always-on kiosk behavior.

A native custom skill can use APL images, animation, video and audio. It needs a
separate APL presentation adapter rather than executing our Canvas JavaScript.
Retain our high-level scene and movement contracts. Begin with one arrival,
idle loop, spoken clip and departure acknowledgement. Compare audio/visual sync
and cold-start latency on the physical Show before expanding the room.

Custom Qwen voice audio can be encoded for Alexa and delivered through trusted,
internet-accessible HTTPS. SSML audio supports clips up to 240 seconds, with
format constraints and a prohibition on customer-specific or sensitive content.
Consequently, a generic character demo is a better initial test than personalized
calendar notifications. AudioPlayer is aimed at long-form streams; it is not a
replacement for our existing low-latency PCM speech transport. APL audio can
coordinate visuals with audio, but neither documentation nor the existing Beam
speech test proves incremental Qwen streaming on the Show. Benchmark a short
encoded clip first, then investigate streaming transport separately.

The HTML/Web Audio alternative, Alexa Web API for Games, supports Echo Show and
would reuse Canvas, but Amazon explicitly restricts it to games. Do not select it
for a general assistant/dashboard. Its configurable inactivity timeout is also
bounded at 30 minutes; it is not an always-on surface API.

A skill would require an Alexa developer app, development-mode device access,
HTTPS assets/audio, and an authenticated cloud-to-local route. Keep synthesis on
the Mac. Existing GitHub webhook infrastructure does not automatically provide a
safe bidirectional surface or audio gateway. Do not expose controller credentials,
private messages, reference recordings, or the entire local API.

Sources:
- [Amazon Silk overview](https://docs.aws.amazon.com/silk/latest/developerguide/what-is-silk.html)
- [APL visuals and audio](https://developer.amazon.com/en-US/docs/alexa/alexa-presentation-language/add-visuals-and-audio-to-your-skill.html)
- [Integrate APL audio and visuals](https://developer.amazon.com/en-GB/docs/alexa/alexa-presentation-language/integrate-apl-audio-visual-response.html)
- [SSML audio requirements](https://developer.amazon.com/en-US/docs/alexa/custom-skills/speech-synthesis-markup-language-ssml-reference.html#audio)
- [Audio options](https://developer.amazon.com/en-GB/docs/alexa/custom-skills/add-audio.html)
- [HTML runtime restrictions, including games-only eligibility](https://developer.amazon.com/en-US/docs/alexa/web-api-for-games/alexa-games-build-your-webapp.html)
- [HTML skill/session configuration](https://developer.amazon.com/en-US/docs/alexa/web-api-for-games/alexa-games-build-your-skill.html)

## Phone browser and picture-in-picture

First add a paired mobile browser destination with a responsive character close-up,
not the entire room shrunk into a phone-sized window. Opening a browser page is
not arrival: retain render-ready and transfer acknowledgements before hiding the
origin character. Show a return action and recover ownership on disconnect.

For Android, prototype video PiP: draw a compact character canvas, capture it as
a MediaStream, attach to a playing video, and offer an explicit PiP button where
supported. Chrome documents canvas streams in video PiP. This is a feasibility
path, not evidence that it works on the user's phone. Feature detection and a
physical Android test are required. Document PiP (arbitrary HTML) is documented
as a desktop launch and must not be assumed on Android. Browser/OS can restrict
PiP, and a user action is normally required. A PWA alone does not guarantee
background execution.

Test animation and speech with the main browser backgrounded, phone locked,
network switched, and PiP dismissed. Canvas animation and timer throttling may
freeze the source; if so, try a server-rendered video stream or a small native
Android client. The latter can use Android's native PiP lifecycle but adds an app
to install and maintain. Start with browser-only and avoid promising an always-on
floating assistant before these tests pass.

Sources:
- [Chrome video PiP and canvas streams](https://developer.chrome.com/blog/watch-video-using-picture-in-picture/)
- [Chrome Document PiP scope](https://developer.chrome.com/docs/web-platform/document-picture-in-picture)
- [Android native PiP](https://developer.android.com/develop/ui/views/picture-in-picture)

## Shared adapter design and remaining work

A persistent registry now extends the base Pi/Cast pair with approved browser/Mac instances.
Expose configured IDs, labels, availability and capabilities (visual, audio,
input, visibility lifecycle); do not hardcode Show, phone or shelf in callers.
Persisted coordinates now determine the dominant travel axis. Explicit neighbor edges and richer exit/entry anchors remain follow-up. Proposed physical order:
**Show ← TV ← companion display**. A mobile destination has no fixed position
unless explicitly configured. Add a second door only when its neighbor is paired
and available. Door labels come from location configuration.

Keep one authoritative character owner, prepare/render-ready/exit/enter ACKs,
limited per-surface credentials, and recovery to an available origin. Visibility
leases must reflect each adapter: a background phone playing PiP should not be
judged by TV foreground-frame rules. Audio follows the owner only when that
adapter confirms playback capability; announcement routing remains independent.
