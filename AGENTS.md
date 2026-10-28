# Repository maintenance

## Deployment documentation

- Treat `docs/deployment.md` as the maintained inventory of actual hosting, devices,
  model workers, configuration ownership, ports and integration routes. The main
  Mermaid topology is in `README.md` under Current deployment map.
- When changing those responsibilities or deployment settings, update both the
  inventory and any affected README diagram nodes/edges in the same change. Update
  setup guides/examples where needed. Review them even for an internal change to
  a topology-sensitive file; explain unchanged topology with the commit trailer
  described below rather than inventing an update.
- Keep repository defaults, the active installed deployment, experimental source
  changes and planned/backlog features distinct. Source edits are not evidence of
  deployment. Verify live state before updating observed status or verification
  dates; identify physical tests that still require the user.
- Never copy tokens, private reference audio, secret calendar feeds, account IDs,
  SSH keys or token-bearing dashboard URLs into public documentation. Use roles
  and configuration keys instead of hardcoded private host addresses.
- Existing per-commit README review remains required. The commit-msg hook also
  requires `docs/deployment.md` staged for topology-sensitive changes, or an
  explanatory `Topology-Reviewed: ...` trailer. These checks verify review evidence
  and do not prove that the documentation is correct.
- Enable the checked-in hook with `git config core.hooksPath .githooks` in a new
  checkout. Do not weaken the review requirement just to make a commit pass.

Hardware/account tests can have physical effects. Use isolated regressions for
routine verification and preserve the user's current volume and state during
read-only documentation audits.

## Amadeus privacy and public reporting

- Never commit participant trial results, transcripts/audio, observations,
  health/coaching preferences, personal schedules, history, or derived user metrics.
  Keep them in ignored private local state. This includes ostensibly anonymized
  personal trial aggregates and excerpts; do not put them in PRs/issues either.
- Commit core code improvements, synthetic regressions, declarative specifications
  and deployment capability state. Use invented fixtures, never edited real data.
- Maintain `docs/amadeus-progress.md` as a high-level capability/improvement and
  regression log. Describe general engineering wins/losses without participant
  details, measurements of personal behavior, dates of personal activity or quotes.
- Do not export private results to create the public log. Review prose manually;
  path guards and ignored folders do not prove that content is safe to publish.
