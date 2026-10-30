# Roadmap maintenance

[Repository issues](https://github.com/joncady/OkabeBot/issues) are the source of
truth for backlog scope, acceptance criteria and remaining work. The
[OkabeBot roadmap project](https://github.com/users/joncady/projects/4) is the Kanban
view of those same issues. Local documentation explains contracts and deployment;
it is not a second independent status tracker.

## Workflow

- Create an issue for actionable follow-up work and add it to the project. Avoid
  new project-only draft cards or duplicate issues for the same acceptance scope.
- **Todo:** planned, deferred or waiting for an owner/account/hardware prerequisite.
  State the prerequisite in the issue; do not imply work is actively running.
- **In Progress:** implementation or required review/acceptance remains active.
  An open PR with passing tests is still in progress until accepted/merged.
- **Done:** acceptance scope is complete and the issue is closed. Close through
  `Closes #N` in the merged PR when that PR fully satisfies the issue. Use `Refs #N`
  for partial work. Do not close an umbrella because one subtask shipped.
- Each checkpoint PR should list completed scope, remaining issues and automatic
  versus physical validation. Keep source, installed capability and planned work
  distinct; use `docs/deployment.md` for actual hosting and runtime ownership.

## Reconciliation

Legacy draft cards were converted to repository issues in place, preserving their
project identity and existing completion state. Their descriptions were rewritten
as declarative engineering scope rather than copied historical activity notes.
Already-Done baseline cards remain closed; this is not a fresh physical acceptance
claim. Active/partial capabilities retain explicit remaining work. New source
onboarding, Trakt coverage and storage/pagination issues are included on the board.

Amadeus A0–A8 remain work-package issues. `docs/amadeus-todo.md` provides detailed
acceptance breakdown; reconcile its checkboxes when implementation lands rather
than treating an unchecked historical checklist as proof that code is absent.
Private trial evaluations, household data, account identifiers, recordings and
personal metrics must never be used to populate issue bodies or PR descriptions.
