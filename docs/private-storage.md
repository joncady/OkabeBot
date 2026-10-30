# Private disposable-file budgets

Dashboard Dev → **Private storage** shows content-free local usage counters and
owner-editable age/size budgets. Automatic cleanup defaults **off**. Enabling it
allows irreversible deletion of eligible old recording files and trimming of
diagnostic logs; it does not grant microphone/camera access or start collection.
Saving disabled limits only changes policy. There is no public telemetry export.

## Scope and protection

The controller checks only application-owned `state/audio/*.wav`,
`state/recordings/*.mp4`, `state/runtime/*.log` and
`state/ptt/transcript.jsonl`. Databases, source memory, credentials/configuration,
model caches, voice references, private exports, rollback backups and Pi remote
files are outside this cleanup scope. They are not part of the displayed totals.
Only regular single-link files are eligible. Symlinks and symlink directories are
excluded; hard-linked logs cannot cause another file to be truncated.

Cleanup runs once per minute while the controller is idle. Recordings newer than
two minutes are protected against in-flight use. Age expiry removes eligible
recordings; over-budget eviction uses oldest eligible files first. Protected recent
files can temporarily exceed a budget. Rotated previous logs can be removed;
active logs use bounded-memory copytruncate so existing append-open descriptors
keep working. Concurrent diagnostic writes are best effort, not lossless audit
storage. This policy is not suitable for a transaction log or sole backup.

The scan has a fixed entry bound. Usage reports explicit partial coverage if the
bound is reached or eligible entries cannot be read; it is not a whole-disk size
claim. Cleanup failures are content-free status, never raw filenames or file data.
A process/file lock prevents overlapping passes, and changed inode/size/time checks
avoid deleting files modified after the scan. Unreadable/malformed policy fails
closed to cleanup off. New policy does not change recording permission or remote
satellite retention.

## API and migration

Authenticated owner operations use `/storage/usage` with an empty POST body and
`/storage/policy` with the exact fields `enabled`, `recordings_days`,
`recordings_mb`, `logs_days`, `logs_mb`. Days accept 1–365 and MB accept 1–4096.
Policy is stored privately in `state/storage-policy.json`; no usage counters or
personal outcomes belong in repository docs, issues or PRs.

This is a bounded disposable-file feature, not completion of the broader
[collection/storage work package](https://github.com/joncady/OkabeBot/issues/18).
Provider resume cursors, remote Pi retention and protected export/backup lifecycle
remain separate. [Isolated backup/restore drills](https://github.com/joncady/OkabeBot/issues/81)
are a distinct planned milestone; no automatic backup or deletion of backups is
introduced here.
