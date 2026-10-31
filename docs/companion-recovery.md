# Companion recovery and spare-card trial

The legacy companion requires a controlled storage/OS trial before any in-place
upgrade. A hung storage path is not proof of a defective card, and successful SSH
after a reboot is not proof that the cause is fixed.

## Prepare without changing the active Pi

Use an already verified host key and the owner's SSH identity:

```sh
.venv/bin/python scripts/backup-companion-config.py USER@PI_HOST \
  --identity /PRIVATE/PATH/identity \
  --output .local/recovery/NEW_BACKUP_DIRECTORY --archive
```

This reads bounded diagnostics and archives selected boot/system configuration.
It does not include application state, recordings, reference voices or SSH keys.
Service files may contain credentials: the directory is private and files use
mode 0600. Keep it ignored and outside PRs, issues and public logs. Review any
partial archive; a failed command is not a successful backup.

Separately preserve the installed controller's private configuration and service
inventory using the deployment guide. A configuration archive is **not a full
card backup** and is not a substitute for the next step.

## Physical checkpoint: full rollback before testing

1. Shut down normally, remove the old card, and create an offline whole-card image
   on a trusted computer. Verify the image can be read and retain the old card.
   Do not image a mounted, actively changing root filesystem as a verified backup.
2. Prepare a separate card with a supported OS whose kernel and audio configuration
   support the Voice Bonnet. Do not overwrite the working card or silently migrate
   Wi-Fi credentials, host keys or application secrets into repository examples.
3. Restore selected configuration deliberately; verify new SSH fingerprints locally.
   Install dependencies and device services using the setup guide. Preserve the
   display's actual HDMI resolution and USB touch configuration.
4. Check speaker at the owner's existing volume, microphone, physical button,
   display orientation/resolution, touch, USB sensor telemetry and HA availability.
   Then test one question and a return handoff with the owner watching.
5. Check idle rendering, memory, storage waits and power flags after boot settles.
   Compare failures by subsystem; do not infer a storage fix from lower CPU use.
6. Retain rollback until a supervised soak/restart test passes. Record private
   diagnostics locally; public reporting describes capability and regressions only.

The card swap, compatibility acceptance and soak are outstanding human checkpoints.
The preparation script performs no reboot, flash, upgrade or service reconfiguration.
