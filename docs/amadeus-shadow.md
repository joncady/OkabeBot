# Private shadow trial

The optional `ShadowTrial` runs the existing habit and contextual planners every
five minutes on the controller. It has no notification dispatcher, speech callback,
model worker, delivery acknowledgement or device interface. An eligible candidate
means **would offer**, never delivered. The current planners are deterministic
rules/templates; this trial does not pretend to be a generative autonomous agent.
Existing morning briefings, arrivals and optional conversations are separate flows.

Enable or pause **Amadeus shadow trial (private log only)** in Dev. Repository
default: disabled. Enabling preserves existing preferences and goals, adds missing
morning/departure/media shadow goals, and enables planner previews without changing
observation consent, coaching choices or allowing unverified media discovery. The
habit learner retains its minimum-history/support thresholds. No invented input
or catalogue is inserted into the real profile. Disable stops planner evaluations;
pausing Amadeus or enabling guest mode stops new shadow records as well.

## Private decision trail

`shadow_decisions` lives in the existing private `amadeus.sqlite3`, accessible only
on the controller host. Each record captures evaluation time, planner states,
bounded routine summaries, candidate text/eligibility/reason, input recency and
possible data gaps. Empty evaluations are logged as `no_candidate`; ineligible
candidates are `withheld`; eligible candidates are `would_offer`. Diagnostic gaps
are prerequisites to inspect, not proof that every gap caused that evaluation's
outcome. Current owner summaries appear in dashboard state, without publishing
candidate contents to other surfaces.

The log contains participant-derived trial data. Never commit, quote in public
issues/PRs, or export it into `docs/amadeus-progress.md`. Retention is at most seven
days, capped at 2,500 evaluations, and respects shorter configured retention.
Pruning also runs during ordinary private-store maintenance. Full Amadeus forget
removes the log; forgetting preferences clears derived profile decisions; source
revocation clears prior profile decisions and invalidates contextual evaluation
until explicitly re-enabled. Trial feedback is separate private owner input; no
helpfulness score is invented from silence.

## Initial interpretation

Until enough complete observation days exist, the habit learner may have no
supported routine. Contextual candidates can still be evaluated from alarm/wake,
weather and calendar evidence, subject to goals and availability requirements.
Verified media recommendations require a catalogue and provider/preferences data.
The dashboard DND policy is shared with contextual attention checks; disabling it
does not disable focus, media, calendar, home or consent checks. Do not silently
expand consent to make a candidate eligible.

Review several ordinary days before deciding which candidates deserve live
delivery. These are collection/evaluation checkpoints, not scheduled notifications.
