# E1.1 — State (overlay)

Append-only log kept by the developer agent of this side, in English. Newest entry last. One entry
per notable event: a task done, a decision the spec left open, a deviation, a contract problem, a
blocker, or a pre-existing failure found on `main`.

| Date | Task | Entry |
| --- | --- | --- |
| 2026-10-19 | O1-O7 | Built the console. Decisions the spec left open: (1) an internal `initial` state while probing at start is reported to the page as `starting`; (2) `startServer`/`restartServer` resolve when the child is spawned or attached, not when health turns ok; (3) an attached stop that fails goes back to `attached` with the R13 notice; (4) the page decides the R25/R30 empty states from `health.addresses` and `qrError`, `qr` is `null` then; (5) the overlay `resize`/`move` IPC now also checks the sender is the overlay window. Not run here: a real server stop (the server side is a separate branch with `/api/shutdown`) and anything on Windows. |
