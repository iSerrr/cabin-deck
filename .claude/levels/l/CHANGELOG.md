# Level L changelog

Versioning rules: [`../README.md`](../README.md#versioning).

## 1.0.0 — 2026-10-19

First version (replaces the "not implemented" stub).

- Wraps the existing `/spec` and `/deliver` flow instead of repeating it. Roles: conductor, optional
  scout (`Explore`) and designer, architect, parallel executors per side, reviewer.
- Prerequisite: `docs/architecture.md` and `docs/backlog.md`.
- Six steps: intake; stage plan (one spec per stage, `depends_on` chains, shown without waiting,
  `templates/stage-plan.md`); spec (gate one, risk checklist in the spec; a spec touching a risk
  area is always approved by the user); deliver; merge and ship (`ship@1`, migration notes for
  production; risk-area PRs merged by the user); next stage.
- Risk checklist for money, authorization, user data and migrations.
- Going down to M at the stage plan only when no risk area is touched.
- Stops for an architectural decision, a blocked or needs-human delivery, a wrong contract (spec
  revision), or a red ship.
- Report template for each stage and the final report.
