# Level M changelog

Versioning rules: [`../README.md`](../README.md#versioning).

## 1.0.0 — 2026-10-19

First version (replaces the "not implemented" stub).

- Roles: conductor (main session), optional scout (built-in `Explore`, `haiku`), executor
  (`backend-dev` / `frontend-dev` for the brief's side, `sonnet` set in the call; the `executor`
  agent only in projects without side agents).
- Scope: one stage, one side, no contract change, nothing from the router's veto list.
- Five steps: intake (one round of questions allowed), plan (a brief from `templates/brief.md`,
  shown to the user without waiting for approval, in every mode), execute (one executor sub-agent in a worktree), check (the
  conductor re-runs gates and checks scope and criteria; at most 2 fix rounds, then a draft PR),
  deliver (PR, CI, merge per mode, `ship@1`, report from `templates/report.md`).
- Tests: a test per acceptance criterion with logic, outside Demo mode.
- Escalation triggers to L: money/auth/user data/migrations; both sides or a contract change;
  several stages or an architectural decision; executor blocked or the diff outgrowing the brief.
  Going down to S is allowed once, at the plan step.
- Escalation: keep the executor's branch, report the trigger, continue at once under the L protocol.
- Several M tasks: one at a time, each with its own branch and PR.
