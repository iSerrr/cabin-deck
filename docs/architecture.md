# Architecture

What exists today and the decisions that hold it together. `PRD.md` (Ukrainian) is the product
source of truth; this file is the technical map a spec must fit. Change it only through a spec or an
ADR in `docs/decisions/`.

## Components

```
Tablet browser ──WS /ws──────────► server.py ──pyvjoy──► vJoy driver ──► ATS / ETS2
 (static/index.html, v3.html)        │   ▲
                                     │   └── truck-telemetry (SCS SDK shared memory)
Phone / tablet ──WS /ws/dash──────►  │
 (dash/index.html :8701,             │
  dash/v2.html    :8702)             ├── config.json (layout, validated at start)
                                     └── logs/cab_deck.log (rotating)
Console (Electron, overlay/) ── spawns server.py, polls /api/health, POST /api/shutdown (this PC only)
   └── overlay window ── loads http://127.0.0.1:8702/?shape=1 in a transparent window
```

| Component | Path | Runs on | Started by |
| --- | --- | --- | --- |
| Server | `server.py` | Windows gaming PC (macOS: `--dry-run`) | the console (`console.bat`), or `run.bat` as a fallback |
| Panel | `static/index.html`, `static/v3.html` | tablet browser (Android Chrome) | the server serves it on `:8000` |
| Dash | `dash/index.html` (v1), `dash/v2.html` (v2, WebGL2) | phone, tablet or the overlay | the server serves them on `:8701` / `:8702` |
| Console + overlay | `overlay/` (`main.js`, `server-control.js`, `console.html`) | Windows gaming PC | `console.bat` (npm install when needed, then the app) |

## Server

One Python process, FastAPI + uvicorn, three listening sockets (`--port` 8000, `--dash-port` 8701,
`--dash2-port` 8702) on `0.0.0.0`. Everything runs on one asyncio loop: WebSocket handlers, the
telemetry loop, the dash loop, per-client outboxes (a slow client cannot stall the others) and a
performance watchdog.

- **Input.** The panel sends `{"id": "cab_deck_btn_NNN", "event": "down" | "up"}`; the server maps
  the ID to vJoy button `NNN` through the validated config and never accepts a raw number or key.
  `tap` buttons release after `tap_ms`; `hold` buttons release on `up` or after `hold_timeout_s`;
  `switch` controls step through positions with `switch_gap_ms`. On disconnect the client's held
  buttons are released; `release_all` runs on shutdown.
- **Telemetry.** On Windows, `truck-telemetry` reads the SCS SDK shared memory; the server turns it
  into indicators, switch positions, navigation, the delivery plan and the dash state, and pushes
  them to panels and dashes.
- **Diagnostics.** `GET /api/health` (input mode, pressed buttons, clients, game state, commit,
  uptime, last error, performance) and `GET /api/logs?lines=N`. Panels report their JS errors as
  `client_error`.
- **Dry run.** `--dry-run` replaces vJoy with logging and telemetry with nothing; it is how the
  server runs on macOS and in the gates.

## Console and overlay

An Electron app without a build step ("Cab Deck Console", spec E1.1). The console window (a local
page with its own preload; process-control IPC only from that window) starts `server.py` from
`.venv` as a child process or attaches to one already running, shows health, the log tail and QR
codes, and stops the server through `POST /api/shutdown` (loopback, `X-Cab-Deck-Console: 1`, no
`Origin`), falling back to a kill after 8 s; the server resets every vJoy button when it starts.
The second window is the overlay: one transparent, frameless, always-on-top, click-through window
showing dash v2 from `127.0.0.1:8702`; it retries while the server is down. Hotkeys: Ctrl+Shift+F9
show/hide, Ctrl+Shift+F10 edit mode (drag, resize, nudge). Position and options live in
`overlay/overlay.json` (local, git-ignored).

## Decisions

- **vJoy, not keyboard emulation:** the game sees a separate controller; no conflict with the
  keyboard (PRD, "Архітектура").
- **No build step, no framework** for pages and the overlay: one HTML file per page, plain JS; three.js
  and similar libraries only from a pinned CDN URL.
- **LAN only, no auth, no HTTPS, no database** in the pilot. Consequence: any route that controls the
  PC (processes, git, files) must answer to `127.0.0.1` only.
- **Overlay over a game mod:** the game's UI cannot reproduce live dials and bloom (PRD, stage 5).
- **The gaming PC deploys itself** by pulling `main` (`run.bat`). There is no CI and no stage.

## Phases

Stages 1–5 of `PRD.md` (panel, game feedback, pneumatics and pages, the Alpha Gen dash, the overlay)
are built; open acceptance items are tracked there. New work is planned in [`backlog.md`](backlog.md).

## Marked for removal

None.
