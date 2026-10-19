# Level S changelog

Versioning rules: [`../README.md`](../README.md#versioning).

## 1.0.0 — 2026-10-19

First version.

- Five steps: intake (one sentence + "Level S", no questions), locate, minimal edit, verify
  (logic change → small test; copy/styles/config → no new test), deliver (commit on a branch + report).
- Escalation triggers: more than 3 files; place not found or cause not obvious; first edit breaks
  tests for an unclear reason; payments/authorization/user data/migrations → at least L.
- Deliver: PR, merge per mode, then `ship@1` (stage deploy, smoke, stage link in the report).
- On escalation: continue at once under the M or L protocol (L's gate is the spec approval).
- Batch mode: tasks one by one, one commit each; escalated M, then L tasks run after the S tasks;
  one report with a smoke checklist.
- Report template: `templates/report.md` (single task and batch).
