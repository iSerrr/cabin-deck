# E1.2 — State (overlay)

Append-only log kept by the developer agent of this side, in English. Newest entry last. One entry
per notable event: a task done, a decision the spec left open, a deviation, a contract problem, a
blocker, or a pre-existing failure found on `main`.

| Date | Task | Entry |
| --- | --- | --- |
| 2026-10-19 | O1-O8 | All overlay tasks built. Decisions: (1) if the second `git rev-parse` after a successful pull fails, the pull-failed error notice is used and the server is restored (spec silent). (2) The R30 "Wait for the update…" text is set on the E1.1 notice line and may be overwritten by the next server state change during the update. (3) After a failed handover spawn the single-instance lock is requested again. (4) On a relaunch the update block keeps `running: true` until the process exits, so close/quit stay refused. (5) Handover waits 600 ms so the notice can be painted. Not run: Electron/Windows paths (no GUI in this environment). |
