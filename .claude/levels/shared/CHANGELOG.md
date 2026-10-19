# Shared modules changelog

Versioning rules: [`../README.md`](../README.md#versioning). One section per module.

## ship

### 1.0.0 — 2026-10-19

First version.

- Starts after the merge (at once in Autonomy B; on the merge in owner-gated mode).
- Steps: wait in the background for CI on `main` and the deploy run; read the post-deploy smoke
  (success, smoke passed, no rollback); report with the stage URL and smoke steps against it; on
  red, stop and report (failed step, log, rollback), no fixing or re-running inside the task.
- Never deploys to production or by hand; without a pipeline ends at the merge.
- Batches: ship the last merge and check it contains every merged PR.
