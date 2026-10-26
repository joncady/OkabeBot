---
name: okabebot-setup
description: Set up, diagnose, or migrate this repository's personal hardware assistant on a Mac, Linux laptop, or capable Pi, with local or SSH-connected hardware and optional integrations.
---

Configure a working controller and the user's selected devices. Use this checkout's
scripts and schemas; do not assume the original author's IP addresses, accounts,
keys, character or hardware layout.

Read [the project quick start](../../../README.md) and
[device setup](../../../docs/devices.md) for the selected hardware. For Linux or a
Dell migration, also read [Linux controller](../../../docs/linux-controller.md).

- Establish whether this is a fresh setup, an existing installation, or migration.
  Inspect configuration filenames and runtime health before asking for details.
  A Pi Zero is a satellite; it cannot host the controller's transcription stack.
  A capable 64-bit Pi can combine roles, but that topology remains unvalidated.
- Create a local config from the appropriate `examples` file. Relative paths resolve
  from that file's directory. Each display/voice endpoint independently selects
  `local` or `ssh`. Preserve existing private configuration. Store API keys/feed
  URLs in local environment files, not the repository, logs or chat.
- On prepared Linux, `./scripts/start-linux.sh --bootstrap` installs the app extras,
  caches the configured speech model and starts the controller. It does not install
  OS packages, sign into accounts, authorize SSH, or make a live USB persistent.
  `./scripts/start-linux.sh --check` probes prerequisites and device status without
  pressing buttons, recording or playing sound. Ordinary subsequent start is
  `./scripts/start-linux.sh`. On macOS use the README's Python entrypoints.
- Check Codex sign-in on the controller itself. Complete account sign-in, provider
  consent and hardware host-key verification with the user when necessary. Existing
  authorization does not imply consent to grant new persistent SSH access. Use
  verified host keys; do not disable host-key checking to make pairing work.
- Before migration, preserve the inbox, profile, model cache and private integration
  state. Python virtual environments and macOS executable paths are not portable
  to Linux. Stop the old controller before the new one takes over hardware. Keep
  the Mac available until the user validates the new host; do not reformat drives
  or change Home Assistant/webhook destinations as an implied setup step.
- Verify incrementally: configuration and dependencies, read-only device status,
  display character, quiet speaker level, then a user-held push-to-talk turn.
  Start speaker tests quietly. Dev controls apply to both speech and chimes;
  completion chime gain is separately configurable. Report precisely which checks
  were automatic and which physical behavior still needs the user.

Only set up integrations the user chooses. Read the corresponding guide when
needed: [notifications/calendar/GitHub](../../../docs/notifications.md),
[Spotify](../../../docs/spotify.md), [TV](../../../docs/tv.md),
[Home Assistant](../../../docs/home-assistant.md), [Ring](../../../docs/ring.md),
[Alexa](../../../docs/alexa.md), or
[Codex completion alerts](../../../docs/codex-notifications.md).
Provider account consent and per-app metadata availability remain separate from
controller installation. Do not promise titles or team crests from an app until
its live metadata has been inspected.

For a new provider, use [adapter contracts](../../../docs/adapters.md). Provider
code returns normalized data or publishes notifications; it does not draw pixels,
choose speech policy, execute instructions in event text, or replay failed physical
actions. Keep provider failures isolated and preserve useful partial metadata.

Finish with the exact start command, private control-page location, selected
layout, completed checks, and the next concrete manual test. Leave credentials
out of public artifacts and preserve rollback material during migrations.
