# Notifications and tablet controller

Run the controller on one host at a time. The current Mac controls one combined
display/voice Pi over SSH; separate Pis remain supported. See the
[deployment inventory](deployment.md) for active settings. Migration to a different
controller is a separate step.

## Tablet access

The controller defaults to loopback. For a tablet on your trusted home network, set `web.host` to the controller's specific LAN IPv4 address (not `0.0.0.0`). Open the complete printed control URL on the tablet, including its `#` token. Use a current browser. Keep the controller awake while using it.

The URL grants controller access. This LAN mode is HTTP, so use it only on a trusted network; do not forward its port to the Internet. Use a private HTTPS reverse proxy or VPN for other networks. Dev mode hides diagnostics for convenience; it is not a separate permission level. The control token persists across restarts in private `state/controller-token`; stop the controller and delete that file to rotate it.

The home view has large character portrait buttons, microphone pause, stop response, and a notification inbox. Dev reveals transcription, approvals diagnostics, timings, voice settings, and a test card. Actual approval requests remain visible outside Dev.

## Sources

Install `pip install -e '.[voice,notifications]'`. Configure in the ignored local JSON:

```json
{
  "notifications": {
    "github": "all",
    "calendar": "env:ICAL_FEED",
    "calendar_lead_minutes": 10,
    "speak_important": true
  }
}
```

GitHub uses `gh` authentication on the controller. It reads account notifications across repositories without marking them read. Mentions, review requests and CI notifications are important; others are visual. Events depend on your GitHub notification subscriptions. The first run establishes a baseline rather than replaying old messages.

Deployment polling uses GitHub Deployment records for owned/collaborator repositories. A paginated GraphQL query checks up to three recent deployments per repository every approximately 90 seconds plus request time. Recent pending/in-progress deployments show a subtle thinking expression on the Pi and a badge in the tablet UI. Workflows that do not create GitHub Deployment records do not animate this indicator.

A separate Actions workflow monitor detects failed, timed-out, action-required,
startup-failure and stale completed runs, independent of notification subscriptions.
It checks a configured repository or, for `github: all`, active owned/collaborator
repositories accessible to the signed-in `gh` account. Discovery refreshes every
15 minutes. The first check per repository establishes a baseline; new failures
create important cards with a chime, deduplicated by run ID and attempt. Failed
requests preserve their cursor and are retried on the next poll. The created-run
lookback is `notifications.workflow_lookback_days` (default 30, range 1–90): reruns
of runs created before that window are outside coverage. All pages within the window
are read, so large repositories may consume substantial GitHub API quota. Access
failures appear in source health; this does not cover third-party check providers.
These paragraphs describe the optional polling adapters. The current deployment
instead uses the signed AWS webhook/SQS path below with GitHub API polling
disabled; it does not run both observation approaches by default.

Google Calendar starts with its read-only private iCal feed. Put `ICAL_FEED="https://..."` in `.env` beside the local JSON, or set the environment variable. Never commit the secret feed. Google Calendar → Settings → calendar → Integrate calendar → Secret address in iCal format. Do not make the calendar public.

The adapter fetches every approximately 90 seconds, expands recurring timed events for the next two days, and schedules local reminders. Calendar event timezones are honored; display times use the controller's local timezone. All-day events are not spoken. Updates reconcile pending reminders and cancellations. Already delivered, failed, or uncertain announcements are not automatically replayed. Feed refresh latency means last-second changes may not be seen immediately.

The source adapter boundary produces inbox records, independent of the renderer and speech engine. Other providers can implement the same scheduling/deduplication contract. OAuth and per-calendar controls remain follow-ups.

## Delivery preferences

The tablet's **Notification preferences** panel configures quiet hours, snooze,
and per-source card/audio settings. Quiet hours silence all notification audio,
including urgent alerts, while cards still appear. Set an IANA timezone or `local`
for the controller timezone; overnight ranges are supported. Button replies are
unaffected. Snooze defers all new cards/audio until it ends; expired reminders are
skipped. Source audio can follow priority defaults, stay silent, chime, or read aloud.
Explicitly silent event payloads always stay silent. Disabled sources remain in
history with `suppressed` status. Settings affect future deliveries and persist in
private `state/notification-policy.json` independently of provider configuration.

Interactive-token API routes: POST `/notifications/preferences` with a partial
`quiet_hours` object and/or `sources: {"github": {"enabled": true, "audio": "chime"}}`;
POST `/notifications/snooze` with `{"minutes": 15}` (0 resumes, maximum 1440).
The publish-only integration credential cannot change preferences.

## API

POST `/notifications` with `X-Hardware-Token` (interactive controller) or `X-Notification-Token` (publish-only integration) and JSON:

```json
{"source":"system","title":"Backup complete","body":"All files verified.","priority":"normal","dedupe_key":"backup-42"}
```

Sources: `system`, `github`, `calendar`. Priorities: `low` (inbox), `normal` (card), `important` and `urgent` (card plus speech if enabled). Important notifications wait until conversation and recording are idle; urgent currently shares that behavior rather than interrupting live audio. Optional Unix-second `due_at` and `expires_at` schedule and expire a record. Dismiss with POST `/notifications/dismiss` and its `id`.

MCP `publish_notification` uses the same persistent inbox. The controller must be running to deliver queued items. Notification text is never submitted to Codex as instructions. Delivery is claimed before actuation; ambiguous failures and crashes are surfaced, not replayed automatically.

`okabebot.scene` is the intent-level interface: `set_activity`, `present`, `dismiss`, `set_deploying`; `okabebot.character.speak` handles speech and lip sync. Renderers own pixel geometry. `pi/scene.py` composes the animated character above a bottom card, with presenting arms and pixel source icons. The overlay survives mouth/activity updates and expires independently.

Upgrade the display Pi with both `pi/service.py` and `pi/scene.py`. Its X11 screen timeout can be disabled with `xset s off`, `xset -dpms`, and `xset s noblank` in the desktop autostart configuration.

The controller creates an owner-only `notification-token` file in its state directory. Unlike the browser token, it survives controller restarts. Copy its contents privately into Home Assistant secrets. This credential only permits POST `/notifications`; it cannot read state, change characters, dismiss cards, or invoke tools. Delete the file while stopped and restart to rotate it, then update integration secrets.

## Long-running command completion

Run a command with the standalone wrapper (no extra Python dependencies):

```sh
python3 scripts/notify-command.py --title "Build" --state-dir .local --url http://CONTROLLER_HOST:8768/notifications -- make build
```

Use your actual controller URL and state directory. Successful commands produce a silent card; failures produce an important notification, spoken if important speech is enabled. The wrapper preserves the command's exit code even if delivery fails. It sends only the supplied title, elapsed time and exit code—not command arguments or output. The controller must already be running. Cards expire after five minutes. For shell pipelines, explicitly supply `sh -c 'your pipeline'` after `--`.

## Focus timer

The dashboard offers 5-, 25-, and 50-minute sessions and Cancel. Starting another session replaces the pending timer. The durable inbox preserves it across controller restarts; completion uses an important reminder, which waits for conversation to finish and follows the existing speech preference. If the controller returns more than 15 minutes late, the reminder expires instead of announcing an old break.

Authenticated POST `/focus/start` accepts `{"minutes":25}` (integer 1–180); `/focus/cancel` accepts `{}`. The publish-only notification credential cannot control timers. A timer already claimed for delivery cannot be recalled by Cancel.

## Codex completion alerts

Use the [Codex notify adapter](codex-notifications.md) for session-name cards and a short local completion chime. It preserves an existing hook and sends no prompt or response text. The optional `audio` field accepts `default`, `silent`, or `chime`; the latter two suppress TTS at every priority.

## Related event cards

Publish `group_key` and optionally `group_title` to collect related events:

```json
{"source":"system","title":"Door opened","priority":"normal","audio":"silent","group_key":"front-door","group_title":"Front door activity","dedupe_key":"unique-opening"}
```

Matching source/group keys arriving within the collection window share one card
(for example **Front door activity (2)** with **Door opened · Someone is at the
door**). Each original event remains in history with its own title, dedupe key
and delivery status. Finishing/failing a batch updates all its members;
dismissing any member dismisses the visible batch. Unknown delivery after a
restart is marked uncertain and is not replayed.

Set `notifications.group_window_seconds` in local JSON (default 3, range 0–10;
0 disables collection). Urgent notifications bypass grouping. Unrelated pending
events can be delivered while a group is collecting. Grouping does not alter
the existing policy of waiting for conversation/recording and the active card
to finish. Events after the window form another card. Silent members keep a
group silent. The Home Assistant examples opt the door and Ring doorbell into
the `front-door` group; other publishers are unchanged.

After upgrading, restart controller/MCP publisher processes together so every
publisher uses the current queue schema. Back up the inbox before migration.
For live review, open the front door and press the Ring doorbell within three
seconds; expect one silent bottom card with the character still visible, and
two separate history records.

## Signed GitHub webhooks

POST `/webhooks/github` accepts GitHub `workflow_run` and `deployment_status`
events. It verifies HMAC-SHA256 over the original request bytes with
`X-Hub-Signature-256`, before decoding JSON. Set a random
`GITHUB_WEBHOOK_SECRET` in the controller's private `.env`, and explicitly list
allowed `notifications.github_webhook_repositories` as `["owner/repository"]`.
Without both, the receiver rejects events. Never use the dashboard/publisher token
as the webhook secret. Restart after changing credentials or the repository list.

Workflow failures share the polling adapter's run/attempt dedupe keys. Deployment
transitions update the animation immediately, persist across restarts, ignore older
status timestamps, and publish silent start/success cards or a failure chime.
Signed-body digests dedupe redeliveries even if an unsigned delivery header changes.
Recent webhook state takes precedence over stale polling state for that deployment.
Polling remains enabled for repositories without hooks and missed deliveries.

GitHub needs an externally reachable HTTPS URL. Configure a TLS reverse proxy or
relay that forwards **only** `/webhooks/github` to this path on the controller;
do not expose the dashboard or other controller routes. Choose JSON content and
subscribe to Workflow runs and Deployment statuses in repository webhook settings.
Use the same secret on GitHub and the controller. External ingress, repository
hook registration, and a real GitHub delivery are separate deployment steps; a
successful local signature test does not prove internet reachability. No public
ingress is created by the installer. The current receiver limits bodies to 1 MB;
oversized events are rejected and workflow polling can recover their failures.

Reference: [GitHub signature validation](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries).

## Agenda first pass

The tablet's **Your day** panel shows remaining timed events today and a live
next-meeting countdown. **Show agenda on Pi** queues a silent calendar card;
existing notification priority/snooze rules still apply. Authenticated POST
`/agenda/show` accepts `{}`. Calendar titles are displayed as text, never executed.
The publish-only credential cannot request an agenda. All-day events and already
started appointments are excluded in this first pass. A calendar snapshot older
than six minutes is marked stale and cannot produce a misleading fresh summary.

For an optional daily silent card, configure `notifications.agenda_time` as
`"08:00"` and `notifications.agenda_timezone` as `"America/Los_Angeles"` (or
`"local"`). The default time is empty, disabling scheduled cards. A successful
calendar refresh in the first 15 minutes after that time queues one deduplicated
card for the local date; late startup does not announce an obsolete morning agenda.
The existing calendar reminder lead time remains independently configurable.

## AWS relay: outbound-only Mac connection

`infra/aws/` provides a small CloudFormation deployment:

`GitHub → Lambda function URL → private SQS standard queue → Mac consumer`

Lambda checks the raw-body HMAC and repository allowlist before queueing. The
Mac checks the signature again and uses the same durable local dedupe and delivery
policy as direct webhooks. Queue messages are deleted only after successful local
handling. An interrupted receive/ack can redeliver without repeating a notification.
Deployment scene updates use the existing high-level scene API. The Mac opens only
outbound AWS requests; neither the dashboard nor Home Assistant is exposed.

Prepare an AWS CLI v2 login and GitHub CLI access with webhook administration for
the explicitly allowed repositories. Configure the private secret and repository
list described above, then run from a prepared checkout/environment:

```sh
python scripts/deploy-github-relay.py --config /path/to/okabebot.local.json --region us-west-2
python scripts/connect-github-relay.py --config /path/to/okabebot.local.json
```

The first command creates or updates the `okabebot-github-relay` stack. Region,
source AWS profile and stack name are configurable. Secret parameters are NoEcho
and supplied through a private temporary file, not command arguments or output.
The second command registers or updates matching webhook URLs, backs up private
configuration, sets the queue URL/region/profile, and creates a dedicated AWS
profile that assumes a **queue-consumer-only role** from the signed-in source
profile. It refuses to overwrite a profile pointing to another role. No IAM user
or permanent access key is created. It verifies access before enabling consumption.
Restart the controller after connecting. Deployment metadata and hook IDs are in
`state/github-relay.json`; do not publish that file or copy Mac credentials to Pis.

This login-based setup still depends on a valid source AWS login. When that login
expires, run `aws login --profile SOURCE_PROFILE`; the consumer retries and the
dashboard health line reports the outage. GitHub polling runs only when
`notifications.github_polling` is true (the compatibility default). Set it false
after every desired repository has a verified hook. Calendar polling is unaffected.
Webhook-only mode receives workflow failures and deployment events; it does not
replace the old general GitHub inbox/review-request polling. The role profile renews its assumed-role credentials while the
source credentials remain valid; it does not eliminate source-login expiration.

The standard queue retains messages for 14 days. Failed messages retry after a
120-second visibility timeout and move to a private dead-letter queue after five
receives. Inspect that queue with the deployment/admin profile; the consumer has
no dead-letter queue access. Invalid signatures never reach the queue through
Lambda. The cloud body limit is 512 KiB so its base64 envelope fits SQS's 1 MiB
limit; oversized deliveries are rejected; polling is a fallback only if explicitly enabled.
CloudWatch logs retain seven days and the receiver never logs event bodies or
secrets. Lambda is 128 MB, capped at two concurrent executions; there is no EC2,
load balancer, VPC or NAT gateway. Free allowances and account-wide usage determine
the actual bill; the personal-use planning estimate is $0–$1/month, not a hard cap.

A real GitHub ping verifies the public endpoint and signature. A signed deployment
fixture through Lambda/SQS/local delivery verifies the queue-to-screen path without
rerunning or changing a real CI workflow. A ping is intentionally not queued.
To add repositories, edit the explicit local allowlist, rerun deploy/connect, and
restart. With polling disabled, repositories without hooks do not generate GitHub cards.

To disable consumption, set `notifications.github_queue_url` to `""` and restart.
To remove cloud infrastructure, remove its registered repository hooks, then delete
the named CloudFormation stack in its region. Stack deletion also removes queue
contents and the queue-only role; preserve any pending data you need first. The
local profile can then be removed. No teardown is performed automatically.

### Identity Center consumer profile

Use `infra/aws/queue-sso.json` in your **Identity Center home region**, which may
be different from the SQS region. Supply InstanceArn, PrincipalId (your Identity
Store user ID), AccountId and the exact QueueArn. The template creates and assigns
`OkabeBotQueueConsumer`, with only ReceiveMessage, DeleteMessage and
GetQueueAttributes on that queue, and a 12-hour role session. It grants no send,
queue administration, dead-letter queue or other service access.

Configure a named AWS profile using your existing SSO session:

```ini
[profile okabebot-sqs]
sso_session = YOUR_EXISTING_SESSION
sso_account_id = YOUR_ACCOUNT_ID
sso_role_name = OkabeBotQueueConsumer
region = YOUR_QUEUE_REGION
```

```sh
aws sso login --profile okabebot-sqs
python scripts/connect-github-relay.py --config /path/to/okabebot.local.json --consumer-profile okabebot-sqs
```

The connector verifies access without changing this profile and reuses the saved
consumer profile on subsequent runs. Renew the SSO login
when its session expires; role credentials refresh while the SSO login is valid.
Deploying/updating relay infrastructure still uses a separate administrator profile.
Re-deployment preserves private hook and Identity Center metadata.

### Relay sign-in recovery

On an expired or missing AWS login, the dashboard component status displays the
specific renewal command for the consumer's configured profile. Identity Center
profiles use `aws sso login --profile PROFILE`; assumed-role profiles follow
`source_profile` to the underlying login. Run that command on the controller host,
finish the AWS sign-in, and leave the controller running: queue consumption retries
automatically. Successful consumption clears the sign-in warning. Permission or
network failures keep a separate connection/permissions message. CLI stderr and
credential contents are never exposed in dashboard status. This guidance does not
make SSO unattended or renew a browser login automatically.

## Personal reminders

Dashboard and MCP reminders share the notification inbox. `create_reminder` accepts
text, a relative delay in minutes (1–525600), a unique request ID, and optional
silent/chime/default audio. Reuse the ID after a lost response; the original due
time and reminder remain unchanged. `list_reminders` returns up to 100 pending
personal reminders, and `cancel_reminder` only cancels that class of pending record.
Focus timers remain separate. Completion respects quiet hours, snooze and source
rules. The controller must be running to deliver; overdue reminders expire one day
after their due time, so this is not a safety-critical alarm.
