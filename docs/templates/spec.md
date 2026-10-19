---
id: E0.0
title: Short imperative title
status: draft          # draft | approved | done | blocked — only a human (or the mode in CLAUDE.md) sets approved
depends_on: []         # spec IDs that must be done first
touches: [server, overlay]   # sides, paths in the root CLAUDE.md (section "Sides")
---

# E0.0 — Title

## Context

Why this exists: the backlog epic, the `PRD.md` lines it serves (quote them, with the section), and
what exists in the code today. Name the files and functions.

## Scope

What this spec delivers, in two to five bullets. State the cut line: what was deliberately left for a
follow-up spec.

## Out of scope

What a reader might expect here but is not included, and where it goes instead (spec ID or "not
planned").

## Requirements

EARS form. One behaviour per requirement. Each requirement has an ID.

- **R1** — When <trigger>, the system shall <response>.
- **R2** — While <state>, when <trigger>, the system shall <response>.
- **R3** — If <unwanted condition>, then the system shall <response>.
- **R4** — The system shall <always-true property>.

## Config and files

New and changed keys in `config.json`, `overlay/overlay.json` and any other file a side reads or
writes: type, default, validation, and what happens to an existing file without the key. Write
"None" if nothing changes.

## API contract

The single source of truth between the sides: HTTP routes, WebSocket messages, the process interface
between the Electron app and `server.py` (arguments, exit codes, signals, output it parses). Write it
precisely enough to build the other side against a fake from it alone. Write "None" with a reason if
there is no surface between the sides.

### `METHOD /api/path` (or a WebSocket message, or a process interface)

- **Who may call:** LAN | this PC only (`127.0.0.1`) — anything that controls the PC is this PC only
- **Change:** new | additive change to existing | breaking change to existing (justify)
- **Request:** query/body fields with type, required, validation rule
- **Responses:**

  `200`
  ```json
  { "success": true, "data": { } }
  ```

  Every error status with its body and when it happens (e.g. `403` from a LAN address).

## Server

New and changed routes, WebSocket handlers, background tasks and startup/shutdown behaviour in
`server.py`. Write "None" if nothing changes.

## Screens

Pages (`static/`, `dash/`) and Electron windows (`overlay/`): layout in words, every state (server
down, starting, error), what each control does, hotkeys. Write "None" if nothing changes.

## Acceptance criteria

Each criterion is checkable and traces to requirement IDs. Outside Demo mode each becomes at least
one test. In Demo mode write them as a click-through checklist; mark each `[mac]` (checkable in
`--dry-run`) or `[pc]` (only on the Windows gaming PC with vJoy and the game).

- [ ] **AC1** (R1) — Given …, when …, then ….

## Risks and edge cases

Answer each: can a vJoy button stay pressed (disconnect, page hide, crash, restart, update)? What
happens on Windows, where killing a process skips its cleanup? Who on the LAN can reach the new
surface? What if the server is not running, or a port is taken? Concurrency on the asyncio loop.

## Open questions

Each with the architect's recommended default. A spec cannot be approved with an open question that
changes the contract.

- **Q1** — … *Default:* …
