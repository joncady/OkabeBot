# Home integrations: Tuya, Ring, and Alexa

Spotify runs directly in OkabeBot. Home Assistant is a separate optional service for Tuya, Ring, and Alexa. The local start script below installs the container; account linking and automations still require setup.

## Start on the Mac

Run `./scripts/start-home-assistant.sh`, then open http://127.0.0.1:8123. Docker must be running. The script pins Home Assistant 2026.10.4, persists configuration under ignored `.local/home-assistant`, and reuses the existing named container. Create your owner account in the browser; never commit its configuration or credentials.

The default is accessible only on the Mac. For a new installation, `OKABEBOT_HA_BIND` can select a specific LAN interface; it adds that interface alongside loopback on creation, and does not change an already-created container. OkabeBot's tablet controller remains separate and reachable on its existing address. No public ingress is configured.

Docker's `unless-stopped` restart policy restarts the container when Docker starts. It does not itself start Docker after a Mac reboot. Stop cleanly with `docker stop -t 60 okabebot-home-assistant`. Back up `.local/home-assistant` while stopped before migrating to the Dell. Do not copy a live SQLite database.

## Architecture and hosting

Use `Tuya / Ring → Home Assistant → OkabeBot notifications` for device events. Start with the native [Alexa Devices setup](alexa.md) for Echo announcements and timer cards. An AWS-hosted skill is a separate path for exposing selected Home Assistant devices to Alexa. Linking a skill does not import all devices or announcements from other Alexa skills.

For Mac development, Home Assistant Container in the existing Docker runtime is a small starting point for these cloud integrations. Persist its `/config` directory outside the container in private, ignored storage. Publish port 8123 on a chosen local interface, and access it from the browser. Do not assume Linux host networking, Bluetooth passthrough, or automatic LAN discovery works through Docker on macOS. Container installations do not include Home Assistant apps/add-ons.

The official macOS route is Home Assistant OS in a VM; use the architecture matching the Mac. This provides the managed OS experience and is preferable if add-ons become necessary. See [macOS installation](https://www.home-assistant.io/installation/macos/) and [Container installation](https://www.home-assistant.io/installation/linux/#install-home-assistant-container).

For the Dell, migrate the private configuration/backup to a persistent Linux Container or HA OS VM. Keep OkabeBot a separate service. The live Ubuntu USB currently needs manual recovery after reboot, so it is not yet an unattended home-automation host. Test restoration before moving automations that matter.

## Tuya hub and door sensor

The linked [B0BBG3ZRQY listing](https://www.amazon.com/dp/B0BBG3ZRQY) identifies an **ORIKLON ZH-WiFi Bluetooth** gateway. It advertises Zigbee and Bluetooth Mesh support, restricted to compatible Tuya products. This is a listing identification, not verification of the physical unit or firmware.

Bluetooth Mesh support does not establish that the hub offers a general-purpose Bluetooth scan API or Home Assistant Bluetooth proxy. Start by inventorying devices already paired in Tuya. Nearby phones, headphones, and arbitrary BLE devices should not be assumed discoverable through it. Keep the door sensor paired to the existing hub while testing.

Manual steps after Home Assistant starts:

1. In Tuya Smart/Smart Life, open **Me → Settings → Account and Security → User Code**.
2. In Home Assistant, select **Settings → Devices & services → Add integration → Tuya**.
3. Enter the User Code there and scan the displayed QR code using the Tuya app. No credentials should be posted in chat or committed.
4. Inspect the imported door sensor and verify one open/close transition. Reload the Tuya integration after adding devices in the app.

The standard integration does not expose every Tuya feature. Inspect device diagnostics if the contact sensor is missing; do not assume cloud linking grants generic radio access. [Tuya setup and limitations](https://www.home-assistant.io/integrations/tuya/)

## Ring silent cards

Add **Ring** under Home Assistant integrations and enter the Ring account credentials and two-factor code in that UI. Test the actual doorbell/event entity before creating an automation. Ring's event entities include doorbell and motion events; do not infer person recognition from a generic motion event. Recording access has separate subscription requirements. [Ring integration](https://www.home-assistant.io/integrations/ring/)

For the first automation, send a normal-priority notification with a short expiration when the doorbell event changes. Normal priority is visual-only in the current notification implementation. Add a cooldown to avoid duplicate alerts. Keep sound a separate opt-in policy; do not reuse the `important` priority for a silent Ring card.

Home Assistant can call OkabeBot with a [REST command](https://www.home-assistant.io/integrations/rest_command/). The current contract is documented in [notifications.md](notifications.md): POST `/notifications`, `X-Hardware-Token` header, JSON body. Until a dedicated Ring source exists, use `source: "system"`. Store the token in Home Assistant secrets. Use the persistent publish-only token from the controller state directory’s `notification-token` file as `X-Notification-Token`; the browser control token still rotates. Do not expose port 8768 publicly to make Alexa work.

## Optional later: Alexa skill using your own AWS account

For the initial native integration, follow [Alexa Devices](alexa.md); no AWS skill is needed. The separate skill route below avoids a Home Assistant Cloud subscription but still requires AWS resources and an internet-reachable Home Assistant HTTPS endpoint with a trusted certificate. AWS Lambda alone cannot reach a private Mac LAN address. Choose the domain and secure ingress arrangement before provisioning. [Home Assistant Alexa requirements](https://www.home-assistant.io/integrations/alexa.smart_home/)

Manual setup sequence:

1. Create/sign into an Amazon Developer account using the account that owns the Echo devices.
2. Create a Smart Home skill/add-on. For an English-US account, use a Lambda in **us-east-1** and restrict its Alexa trigger to this skill ID.
3. Configure the Lambda proxy, its least-privilege execution role, and the skill endpoint ARN.
4. Configure account linking to Home Assistant's `/auth/authorize` and `/auth/token` endpoints. Enable the development skill in Alexa and sign into Home Assistant there.
5. Expose only selected helper/script entities initially. Verify discovery and one harmless routine action before adding devices.

Follow the complete [Home Assistant skill guide](https://www.home-assistant.io/integrations/alexa.smart_home/) for exact fields and [Amazon's Lambda implementation guide](https://developer.amazon.com/docs/alexaplus/smarthome/implement-addon-tutorial) for AWS setup. Console labels may say “add-on.” Keep request debug logging off after setup; directives can contain authorization data.

If direct Ring integration fails, test an Alexa Ring-triggered routine that activates an exposed helper. This depends on the triggers/actions available for the account; it is not a general subscription to Alexa announcements.

## Arrival/departure follow-up

Use a Home Assistant person entity backed by phone presence, then correlate it with door transitions. A door contact alone cannot determine direction or identity. Combine a recent away-to-home change with opening the door for a welcome; wait for confirmed away state after closing for departure. Add cooldowns and quiet hours. A deliberate “I'm leaving” Alexa routine is better for an immediate audible goodbye because presence updates can arrive after the person has left. [Person tracking](https://www.home-assistant.io/integrations/person/)

## Manual prerequisites still needed

- Home Assistant first-run account and location/timezone setup.
- Tuya User Code plus phone QR approval; Ring login plus two-factor approval.
- Preferred authenticator MFA and account login for native Alexa Devices. Domain/HTTPS ingress and Amazon Developer/AWS setup apply only to the optional skill.
- Phone companion-app location permissions if arrival/departure detection is desired.

No hub inventory, Ring connection, AWS skill, or Home Assistant service is claimed as completed by this guide.

## Door card package

`examples/home-assistant/okabebot.yaml` is a Home Assistant package with a reusable notification action and a silent door-open card. Include the package under `homeassistant.packages`, and set `okabebot_notification_url` and `okabebot_notification_token` in HA secrets. Change the example entity ID to your contact sensor. The URL must use the controller’s configured host (including port); keep it on the trusted LAN.

The automation requires an actual `off` → `on` transition, ignores startup/unavailable changes, and has a 15-second cooldown. Cards expire after 60 seconds rather than arriving much later. Arrival/departure greetings still require a person tracker; the contact sensor alone never identifies who came home.

## Android presence setup

Connect the official Companion app to the LAN Home Assistant URL while on Wi-Fi. Enable Background Location and Location Zone sensors; Zone Name Only is sufficient for home/away detection. Link its device tracker to your person under Settings → People. Check the home zone and location permissions on the phone.

A LAN-only server cannot receive updates while the phone is away from Wi-Fi. Reliable departures require a private VPN or another chosen remote HTTPS path; do not infer departure just because a phone becomes unreachable. Until that is configured and tested, the installed automation only shows door-open cards.

## Additional integration packages

- [TV context](tv.md): verified playback titles first, opt-in movie facts planned.
- [Ring](ring.md): silent doorbell cards with cooldown.
- [Alexa Devices](alexa.md): native account integration and timer cards.

Tuya scenes are deferred; the existing door notification stays enabled. These optional packages require account/device setup and real entity IDs before enabling.
