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
