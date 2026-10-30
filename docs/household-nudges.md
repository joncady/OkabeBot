# Household nudges

**Amadeus setup → Boundaries → Household nudges** controls one optional planner.
Repository defaults keep it off. Each suggestion type, timing window, comfort
threshold and cooldown is owner editable; selected devices remain in Context feeds.
This is household assistance, not a new health-coaching permission or device-control
policy. Saving it does not resume paused collection, add sources or alter volume,
quiet hours, speaker routing, health preferences or the existing daily speech budget.

## Initial behavior

- **Away lights:** after sustained fresh away-estimate and selected light-on
  evidence, **Today → Household notes** shows a readable private note. It never
  speaks into an empty house, arms an arrival greeting or treats a light as identity
  evidence. It clears when no longer supported. There is no remote push or automatic
  switch-off in this version; viewing Today requires access to the controller.
- **Bedtime:** within the configured local window, fresh selected light-on or
  garage-open readings can create a gentle optional check-in. It says what devices
  report, not that the owner forgot them or must go to bed. Missing garage data is
  not a claim that the garage is closed. Cross-midnight windows are supported.
- **Comfort:** repeated fresh thermostat **current room temperature** samples
  outside the owner's Celsius thresholds can create an optional comfort check.
  Fahrenheit readings are converted only with explicit units. Floor temperatures
  are retained as selected context but never compared to room thresholds; unknown
  units, non-finite readings and unavailable devices do not produce advice. This
  is not medical, freeze protection, HVAC diagnostics or an energy-savings claim.

The main dashboard notes panel is hidden when no suggestions exist. It refreshes
only while Today is visible and foregrounded; errors/owner-access loss clear its
contents. It never interprets device labels or candidate text as markup or commands.
The setup preview is also read-only: repeatedly refreshing it cannot fabricate a
sustained observation window.

## Gates and delivery

The existing live proactive evaluation maintains private sustained-evidence windows
when live check-ins and this planner are enabled. It uses selected source freshness,
reported sample times and the configured home-estimate anchors. New source reads
must advance sustained comfort evidence; repeatedly reading one cached sample does
not do so. Gaps, unknown presence, pause/profile/config/source-rebind revisions
reset eligibility rather than implying unobserved continuity.

Bedtime and comfort speech use the existing proactive offer → claim → last-minute
revalidation → successful-delivery acknowledgment path. They share daily attempt
and minimum-spacing limits with interests and chores. Existing quiet-hours,
focus/DND, calendar, room-media, destination and fresh-home gates remain decisive.
The planner does not bypass the current live pipeline's destination restrictions.
Successful speech starts a per-topic cooldown; failed or uncertain attempts still
consume the existing invitation allowance and are not automatically replayed.

Departure notes are dashboard-only and need a fresh healthy configured away
estimate; `probably_away` remains an estimate, never proof of departure or identity.
All configured anchors must be healthy. A degraded scanner, a lamp being on or a
speaker playing cannot establish where a person is. No stale departure message is
queued for speech after returning home.

## Private state and API

Settings, sustained-evidence cursors and latest delivery cooldowns are stored in
existing per-profile private preferences, covered by exports and whole-store
forgetting. Source state remains in the existing consented, stable-ID context
store. No new database, service, port, provider credential or capture permission is
added. No participant observations, advice transcripts or personal behavior metrics
belong in source control or public issues.

Owner-only `GET /amadeus/api/household-nudges` returns `{config, preview, state}`.
POST accepts the complete typed config. It uses the existing owner/Host/Origin
boundary; paired surfaces and HA publish-only tokens cannot change the settings.
Optional climate normalization reads only HA `config.unit_system.temperature`
when a thermostat omits its unit attribute; other HA configuration fields are
never retained by this adapter.

Initial generic defaults: away delay 10 minutes, bedtime 21:00–23:00 local,
room comfort below 18 °C or above 27 °C sustained over 15 minutes of observed
samples, and 12-hour per-topic cooldown. These are editable suggestions, not claims
about any household's preferences. Physical acceptance and active owner choices
are separate from synthetic regression coverage and source implementation.
