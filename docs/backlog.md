# Backlog

Epics with IDs and `depends_on`. Every spec (`/spec <id>`) starts from an entry here. Work done
before this backlog existed is stages 1–5 of `PRD.md`.

Status: `todo` → `spec` (spec PR open) → `approved` → `done`.

## E1 — Control console

One Electron app on the gaming PC replaces `run.bat` + `overlay.bat`: a large console window that
runs the server, updates everything with one button, shows the QR codes for the tablet, and hosts the
dash overlay. Level L: it controls the PC (processes, git) and touches the button release guarantee.
`PRD.md` gets a new stage section with the first spec.

| ID | Scope | Sides | depends_on | Risk areas | Status |
| --- | --- | --- | --- | --- | --- |
| E1.1 | Console app: a window that starts, stops and restarts `server.py` as a child process, shows its health, log tail and QR codes for the tablet; the dash overlay becomes a window of the same app; one `console.bat` launcher; the server stops gracefully on request from this PC only, releasing every button | server, overlay | — | controls the PC, button release | approved |
| E1.2 | "Update" in the console: `git pull`, dependencies when their lockfiles changed, server restart, and an app relaunch when the console's own code changed | overlay | E1.1 | controls the PC | todo |
