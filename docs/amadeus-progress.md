# Amadeus capability and engineering log

This is a declarative public log of software improvements and known regressions.
It is not a trial journal, evaluation report or anonymized participant dataset.
Private outcomes and detailed measurements remain local and are not exported here.
Entries describe what the implementation supports, where it is limited, and the
next general engineering improvement. No participant quotes, routines, health
information, behavioral counts or personal trial success/failure rates belong here.

## Offline foundation

- Improved: private event persistence, explicit preferences, source allowlisting,
  duplicate handling, recent recall, retention and subject deletion.
- Limited: no authenticated live collectors, semantic recall or routine learning.
- Next: source/privacy onboarding and bounded authenticated observations.

## Supportive coaching and publication boundaries

- Improved: an offline opt-in coaching policy supports chosen topics, quiet-card
  planning, explicit feedback, durable snooze/stop, and conservative delivery limits.
- Improved: known private artifact paths are excluded and checked at commit, CI
  and release boundaries. Declarative documentation and synthetic tests remain public.
- Limited: coaching is not connected to an onboarding UI or live notification
  delivery. Audio sentiment is not an input. Path checks cannot detect personal
  information pasted into an otherwise allowed source/documentation file.
- Next: render the invitation and controls in authenticated onboarding, then test
  policy enforcement through the shared suggestion/delivery interfaces.

Do not derive entries by uploading or summarizing participant records into the
repository, issues or PRs. Document general fixes/regressions, with synthetic
reproduction when useful. Publication of actual trial results needs a separate
explicit policy change; aggregation alone does not authorize it.

## Private onboarding and explicit memory controls

- Improved: owner-only setup supports profile/source permissions, retention,
  quiet hours and coaching choices, with setup hidden after confirmation.
- Improved: explicit memory editing, private export/forgetting and persistent
  pause/guest/coaching controls share the existing dashboard authority boundary.
- Improved: unrelated saves preserve stop/snooze; private content clears on logout,
  revoked access and late responses. Export filenames receive publication guards.
- Limited: no observation adapters, scheduled retention, inferred memory, semantic
  recall or live nudges. Recent observations are a bounded view, not a full timeline.
- Next: complete private setup review, then bind authenticated metadata adapters
  and exercise shadow context learning without unsolicited output.
