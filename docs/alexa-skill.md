# Alexa custom-skill prototype

The repository contains a local, silent protocol harness and a generic-audio
AWS development-skill adapter. The installed development endpoint is deployed;
physical Echo playback still requires acceptance. The local harness has no HTTP
listener. The history-based command bridge is disabled in the current deployment.

## Run locally

Use the active private controller configuration, without copying its credentials:

```sh
python -m pip install -e '.[alexa-prototype]'
OKABEBOT_CONFIG=/path/to/private/config.json PYTHONPATH=. python scripts/prototype-alexa-skill.py --voice-output .local/alexa-skill/demo.mp3
```

The controller must be running and the configured Qwen worker must be warm.
The script calls the real shared **read-only** device-health and screen-location
tools, handles synthetic skill envelopes, and generates a generic greeting using
the selected character. It does not move the character, play sound, upload audio,
or create cloud resources. Without `--voice-output`, it skips synthesis.
The optional extra supplies an encoder if `ffmpeg` is absent from PATH.

The protocol covers Launch, Stop/Cancel, unknown-intent fallback, status,
registered screens and VoiceDemo. Private screen names are returned as native
Alexa text speech, never embedded in the generic uploaded-audio candidate. Status
confirms controller response, not that every satellite is healthy. No freeform
LLM tool selection is wired into this first skill harness.

## Measured checkpoint

On the existing Mac, one successful warm local run measured status 25 ms,
locations 6 ms, first Qwen PCM 971 ms, complete MP3 2.545 s. Encoding produced
24 kHz mono, 48 kbps MP3, approximately four seconds long; decoding passed.
These numbers exclude Amazon routing, Internet transit, asset upload and Echo
buffering. Cold model recovery is not covered by that timing. Generic responses
should be cached ahead of requests so they do not depend on model startup.

## Move to a real development skill

1. In the Alexa Developer Console, create a **Custom**, English (US) development
   skill named Little Lab. Use an own-hosted endpoint for the planned AWS Lambda
   adapter. No public certification or store release is needed for account tests.
2. Import `infra/alexa/en-US.json` as the interaction model. Build it and supply
   the resulting skill ID so the Lambda trigger can be restricted to that skill.
   Do not send Amazon account tokens or login credentials to chat.
3. Deploy a skill-scoped Lambda adapter and a narrow authenticated request/reply
   transport to the Mac. The existing GitHub webhook queue is not that transport
   and must not be repurposed to execute skill requests. Use bounded deadlines,
   durable request IDs, account pairing and explicit tool permissions. Do not
   expose the controller or this harness directly to the Internet.
4. Host **only the generic** MP3 at a trusted public HTTPS endpoint; set the
   adapter's audio URL. Use native Alexa text speech for private tool results.
   Expiring asset URLs must remain valid long enough for Alexa to fetch them.
5. Test “Alexa, open little lab,” then “Alexa, ask little lab for a voice demo”
   and “Alexa, ask little lab for lab status.” Record cloud latency and physical
   playback before adding actions, freeform conversation, or Show visuals.

Production needs more than the harness's application/user ID checks: for HTTPS
use the ASK SDK's signature/certificate and timestamp validation, or a Lambda
Alexa Skills Kit trigger restricted to the skill ID. The process-local response
cache here is deliberately sufficient only for read-only local tests.
An acknowledgment does not extend Alexa's approximately eight-second deadline;
late or uncertain tool actions must not be retried automatically. Use prebuilt
audio or a native Alexa fallback when generation cannot meet that deadline.

Sources: [Amazon request/response schema](https://developer.amazon.com/en-US/docs/alexa/custom-skills/request-and-response-json-reference.html),
[HTTPS request verification](https://developer.amazon.com/en-US/docs/alexa/custom-skills/host-a-custom-skill-as-a-web-service.html),
[SSML audio requirements and privacy restriction](https://developer.amazon.com/en-US/docs/alexa/custom-skills/speech-synthesis-markup-language-ssml-reference.html),
[progressive responses and deadline](https://developer.amazon.com/en-US/docs/alexa/custom-skills/send-the-user-a-progressive-response.html).


## Deploy the generic-audio checkpoint

```sh
PYTHONPATH=. python scripts/deploy-alexa-skill.py --skill-id YOUR_SKILL_ID --audio .local/alexa-skill/demo.mp3
PYTHONPATH=. python scripts/test-alexa-skill.py
```

Use only the generic synthesized demo, never a reference clip or private tool
response. The deployment script uses the configured AWS credentials, defaults
to `us-east-1` for North America, and saves endpoint/bucket outputs privately in
`.local/alexa-skill/deployment.json`. It is idempotent for the selected stack.
The direct-IAM smoke test verifies response JSON, the exact signed audio download
and the skill-scoped Lambda permission. It is not proof of Alexa invocation or
physical playback. The checked-in template has no public Function URL; a private
S3 bucket supplies five-minute signed GET URLs for its single generic asset.
The Lambda currently uses 512 MiB and a seven-second timeout; its role can only
read the generic clip and write bounded logs. Deleting the stack retains the
bucket intentionally; inspect and remove the retained generic object/bucket
separately when no longer needed. No local-tool relay is installed by this script.

In the console, select **AWS Lambda ARN** under Endpoint and paste the private
`FunctionArn` output as Default Region. Import the model JSON, Save and Build,
then set Test to **Development**. This enables account development tests without
publishing a store skill. No browser microphone permission is needed for typed
simulator tests. The cloud handler supports the generic demo and truthful
unlinked-tool replies; the local harness's real health/location tools are not
exposed in the cloud.


## APL character prototype

The generic AWS adapter optionally attaches an APL 1.8 `RenderDocument` on Launch
and VoiceDemo when `context.System.device.supportedInterfaces` contains
`Alexa.Presentation.APL`. Audio-only requests never sign/fetch scene images and
retain their existing speech/session behavior. Enable **Alexa Presentation
Language** under Build → Interfaces in the developer console, Save, and rebuild.

Generate the shared renderer's generic room/character frames locally, then deploy:

```sh
# Node must be able to resolve @napi-rs/canvas (install it locally or set NODE_PATH).
PYTHONPATH=. python scripts/build-alexa-character.py --character okabe
PYTHONPATH=. python scripts/deploy-alexa-skill.py --skill-id YOUR_SKILL_ID --audio .local/alexa-skill/demo.mp3 --visuals .local/alexa-skill/visuals
PYTHONPATH=. python scripts/test-alexa-skill.py
```

The export reuses `pi/pip_face.py` and `web/lab-room.js`. It produces four 960×540
PNG frames: idle, two mouth shapes and blink. No Pi connection or live household
state is used. `lab.showcase` suppresses live clock/health/calendar claims and
shows explicit demo signage. Okabe is the current deployed illustration; the
build command can select Kurisu, Pip or Sonic for a subsequent deployment. That
selection is static at deployment and is not automatically synchronized with the
Mac character picker or its voice references.

`okabebot/alexa_visuals.py` is the high-level response adapter. It accepts a
trusted fixed-frame signer and handles capability fallback, responsive image fit,
a bounded decorative speaking loop, and slower idle blinking. No animated GIF,
web browser runtime, background polling, touchscreen tools or open microphone is
involved. On screens it omits `shouldEndSession` and reprompt so Alexa can leave
visuals up without immediately requesting speech. The two-minute document timeout
is only a recommendation; actual session/display lifetime is controlled by Alexa.
This is **not an always-on surface** and it does not transfer ownership away from
the Pi, Mac, phone or TV. Movement, notifications and precise audio-envelope lip
sync are follow-up work. Speaking animation currently assumes the fixed short
voice demo and starts when the document mounts, not at a measured speaker onset.

The private S3 bucket adds GET/HEAD CORS support for APL renderers; this does not
make objects public. Lambda read permissions enumerate exactly the generic MP3
and four PNGs. Image GET URLs expire in five minutes. The deploy script's
`--visuals` flag enables this response; omitting it disables APL in the AWS
adapter while preserving the voice demo. Disabling the interface in the developer
console is a separate rollback step. Old generic assets remain private in S3.

References: [APL interface and capability check](https://developer.amazon.com/en-US/docs/alexa/alexa-presentation-language/apl-interface.html),
[dynamic Image sources](https://developer.amazon.com/en-US/docs/alexa/alexa-presentation-language/apl-image.html),
[screen-session behavior](https://developer.amazon.com/en-US/docs/alexa/custom-skills/manage-skill-session-and-session-attributes.html),
[recommended document timeout](https://developer.amazon.com/en-US/docs/alexa/alexa-presentation-language/apl-document-v1-8.html).
