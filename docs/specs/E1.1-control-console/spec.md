---
id: E1.1
title: Run the server, the QR codes and the dash overlay from one console app
status: done
depends_on: []
touches: [server, overlay]
---

# E1.1 — Control console

## Context

Backlog epic E1.1 (`docs/backlog.md`): "Console app: a window that starts, stops and restarts
`server.py` as a child process, shows its health, log tail and QR codes for the tablet; the dash
overlay becomes a window of the same app; one `console.bat` launcher; the server stops gracefully on
request from this PC only, releasing every button". Level L, stage 1 of 2; stage 2 (E1.2) adds the
"Update" button.

The owner (translated): "I want one control console instead of opening things through .bat files and
launching the overlay separately. The console can be the same Electron app, opened as a big window,
where I can scan the QR code and do all the other actions: restart, re-pull right there. I never have
to leave it."

`PRD.md` sections this extends: "Етап 5: оверлей поверх гри" ("Програма: `overlay/` на Electron (Node
18+, без збирання; `overlay.bat` ставить залежності при першому запуску)") and "Архітектура"
("Сервер перевіряє ID за конфігом і сам вирішує, яку кнопку vJoy натиснути"). The hard constraint
from `CLAUDE.md` this spec must keep: "No button may stay pressed after disconnect, page hide, or
server shutdown."

What exists today:

- `server.py` `main()` parses args (`parse_args`: `--dry-run`, `--port` 8000, `--dash-port` 8701,
  `--dash2-port` 8702, `--config`), computes `local_ipv4_addresses()` once and prints the panel and
  dash URLs, binds three sockets with `bind_socket()`, then runs `uvicorn.Server(config).run(sockets=…)`
  without keeping a handle to stop it. The only way to stop it is Ctrl+C in its console window
  (`run.bat`). `create_app()`'s `lifespan` cancels the background tasks and calls `release_all(state)`
  on shutdown, logging "Server stopped, all buttons released.". `GET /api/health` and
  `GET /api/logs?lines=N` exist and answer on every port. `open_vjoy()` acquires the device but does
  not reset its buttons.
- `overlay/main.js` is a single-window Electron app: one transparent, frameless, click-through,
  always-on-top window loading `overlay.json`'s `url` (default `http://127.0.0.1:8702/?shape=1`),
  retrying every 2 s while the server is down; hotkeys Ctrl+Shift+F9 (show/hide) and Ctrl+Shift+F10
  (edit mode); placement saved by `savePlacement()` into `overlay/overlay.json`. `overlay/preload.js`
  exposes only `overlayApi.resize/move` to the dash page. `overlay/package.json` has Electron 33.2.1
  as its only dependency and one script, `start`.
- `run.bat` pulls, installs into `.venv`, starts the server in a console window. `overlay.bat`
  installs Electron on first run and starts the overlay.

## Scope

Size target: one PR per side; the server PR is small (one route, two health fields, one reset call,
a stop handle), the overlay PR is the console app. Cut line: everything that changes code on disk
(git pull, dependency install, app relaunch) is E1.2.

- Server: `POST /api/shutdown`, answered only to a local, non-browser caller, which stops uvicorn the
  normal way so the lifespan's `release_all` runs; `addresses` and `ports` added to `/api/health`;
  vJoy buttons reset when the device is opened.
- Overlay app becomes "Cab Deck Console": a large console window (local page) that starts, stops and
  restarts `server.py` as a child process or attaches to one already running, shows state, health,
  log tail and QR codes for the panel and dash v2, and controls the existing overlay window, which is
  kept unchanged as the app's second window.
- `console.bat` at the repo root as the one launcher; `run.bat` and `overlay.bat` stay as fallbacks.
- A short Ukrainian README section on the console.

The overlay window inside the console is small (two IPC calls onto existing functions), so it is not
cut to a follow-up.

## Out of scope

- "Update" (git pull, pip/npm install, server restart, app relaunch): E1.2. No Update button and no
  disabled placeholder in this spec; see "Screens" for the seam.
- Creating the venv or installing Python dependencies from the console: E1.2. The console only says
  to run `run.bat` once.
- Automatic restart after a crash: not planned (R17).
- Changing ports from the console, running several servers, managing a server on another PC: not
  planned.
- Autostart with Windows, tray icon: not planned.
- A new `PRD.md` stage section: the backlog says it comes with the first E1 spec; the main session
  writes it (the architect writes only under `docs/`).

## Requirements

### Server

- **R1** — When `POST /api/shutdown` arrives from a loopback client (`127.0.0.1` or `::1`) with the
  header `X-Cab-Deck-Console: 1` and no `Origin` header, the server shall answer `202` and then stop
  uvicorn through its normal shutdown, so the lifespan cancels its tasks and calls `release_all`.
- **R2** — If `POST /api/shutdown` arrives from any other client address, or without the header, or
  with an `Origin` header, then the server shall answer `403`, log a warning with the client address,
  and keep running.
- **R3** — The server shall bound its graceful shutdown: open connections get at most 3 s
  (`timeout_graceful_shutdown=3`) before uvicorn cancels them and runs the lifespan shutdown, so a
  stuck client cannot keep buttons pressed or stall the stop.
- **R4** — The server shall add `addresses` (the LAN IPv4 addresses from `local_ipv4_addresses()`,
  computed once at startup) and `ports` (`panel`, `dash`, `dash2`) to the `GET /api/health` body,
  without changing any existing field.
- **R5** — When the server opens the vJoy device (not in `--dry-run`), it shall set every button of
  that device to up before accepting clients, and log it.
- **R6** — The server shall exit with code `0` after a graceful shutdown requested through R1, and
  keep its existing non-zero exit on startup failure.

### Console process control (overlay side)

- **R7** — When the console starts and `GET http://127.0.0.1:8000/api/health` answers `status: "ok"`
  within 1.5 s, the console shall attach to that server (state `attached`): show its health and log
  tail and say it did not start it, and not spawn a second server.
- **R8** — When the console starts and no server answers, the console shall start `server.py` as its
  child process (state `starting`, then `running` once health answers ok).
- **R9** — The console shall spawn the server as `<repo>/.venv/Scripts/python.exe` (Windows) or
  `<repo>/.venv/bin/python` (macOS) with arguments `-u server.py` plus `--dry-run` when the console
  was started with `--dry-run`, working directory = repo root (parent of `overlay/`), without a shell,
  with `windowsHide: true`, and with `PYTHONUNBUFFERED=1` and `PYTHONIOENCODING=utf-8` added to the
  inherited environment.
- **R10** — If the venv python does not exist, then the console shall show state `unavailable` with
  the message "Python environment not found. Run run.bat once to create it, then press Start." and
  disable Start/Restart until the file appears (checked on each Start press).
- **R11** — When the owner presses Stop, the console shall send `POST /api/shutdown` (with the R1
  header), wait up to 8 s for the server to go away (child exit when managed, health no longer
  answering when attached), and show `stopped`.
- **R12** — If a managed child has not exited 8 s after the shutdown request (or the request failed),
  then the console shall on macOS send SIGTERM and wait 3 s more, and then kill the process
  (`child.kill()`, which is TerminateProcess on Windows), log "Server did not stop in time and was
  killed; vJoy buttons may stay down until the server starts again" into the log tail, and show
  `stopped` with that warning.
- **R13** — If an attached server does not stop within 8 s, then the console shall not try to kill it
  (it has no handle to it) and shall show "The server did not stop. Close its window (run.bat)."
- **R14** — When the owner presses Restart, the console shall run Stop (R11, R12 or R13) and, once the
  server is gone, Start (R8, R9); after a restart of an attached server the new server is managed.
- **R15** — When the owner presses Start while state is `stopped` or `crashed`, the console shall
  first probe health; if a server answers it shall attach (R7), otherwise spawn (R9).
- **R16** — While a server is managed or attached, the console shall poll `GET /api/health` every
  1 s (request timeout 800 ms) and show the latest result; while a managed child is alive but health
  fails, it shall show "not answering for N s" instead of clearing the panel.
- **R17** — If a managed child exits without a Stop/Restart/quit request, then the console shall show
  state `crashed` with the exit code (or signal) and keep the last log lines visible; it shall not
  restart the server automatically.
- **R18** — If an attached server stops answering health for 3 consecutive polls, then the console
  shall show `stopped` with "The server that was already running has stopped." and stop polling.
- **R19** — While a server is managed, the console shall read the child's stdout and stderr
  continuously (never letting the pipes fill), split them into lines and keep the last 500 lines for
  the log tail; while attached, it shall fill the log tail from `GET /api/logs?lines=200` every 2 s.
- **R20** — When the console app quits (console window closed, or app quit), it shall stop a managed
  server through R11/R12 before exiting, waiting at most 11 s in total, and shall leave an attached
  server running.
- **R21** — The console shall hold a single-instance lock: a second start of the app shall exit at
  once and the first instance shall show, restore and focus its console window.

### Console window and overlay window (overlay side)

- **R22** — The console window shall be a local page (`overlay/console.html`) with its own preload
  (`overlay/console-preload.js`); process-control and overlay-control IPC shall be exposed only by
  that preload, and the main process shall ignore those IPC messages unless they come from the
  console window's `webContents`.
- **R23** — The dash overlay window shall keep its current behaviour, URL, preload (`overlay/preload.js`,
  only `resize`/`move`), hotkeys and `overlay.json` placement, and be created at app start as today.
- **R24** — The console shall show QR codes for `http://<address>:<ports.panel>` (panel) and
  `http://<address>:<ports.dash2>` (dash v2) for the address chosen from health's `addresses` (first by
  default; a chooser when there are several), generated in the main process with the npm package
  `qrcode` 1.5.4 as PNG data URLs, with the URL as text under each code.
- **R25** — If the server is not `running`/`attached`, or `addresses` is empty, then the QR area shall
  show "Start the server to see the QR codes" or "No LAN address found. Is the PC on the network?"
  instead of codes.
- **R26** — When the owner presses "Show overlay"/"Hide overlay" or "Edit overlay"/"Done editing",
  the console shall do exactly what Ctrl+Shift+F9 / Ctrl+Shift+F10 do, and the buttons shall reflect
  the overlay's current visibility and edit mode, also when changed by hotkey.
- **R27** — The console shall show the health summary: input mode (`vjoy`/`dry-run`), game telemetry
  (connected / paused / not connected), panel clients, dash clients, pressed buttons (numbers, or
  "none"), uptime, commit and last error.
- **R28** — The console app shall accept `--dry-run` on its command line (`npm run start:dry`), show a
  "DRY RUN" badge while it is set, and pass it to the server it spawns (R9).
- **R29** — `console.bat` at the repo root shall check for npm, run `npm install` in `overlay/` when
  `node_modules` or `node_modules/qrcode` is missing, and start the console; `overlay.bat` shall get
  the same install check (it starts the same app).
- **R30** — If `qrcode` cannot be loaded, then the console shall still run and show "QR codes need
  `npm install`: run console.bat again." in the QR area.

## Config and files

- `overlay/package.json`: `name` → `cab-deck-console`, `productName` → `Cab Deck Console`,
  `description` updated; `dependencies: { "qrcode": "1.5.4" }` (exact pin, runtime dependency);
  scripts `start: "electron ."` (unchanged) and `start:dry: "electron . --dry-run"`.
  `overlay/package-lock.json` updated by `npm install`.
- `overlay/overlay.json`: no new keys. Existing files keep working unchanged.
- `console.bat` (new, repo root, side `overlay` for this spec).
- `README.md`: new section, written by the overlay side in this spec.
- `config.json`: no change.

## API contract

### `POST /api/shutdown`

- **Who may call:** this PC only, and only a non-browser caller (the console's main process).
  Enforced in the route: `request.client.host` in `{"127.0.0.1", "::1"}`, header
  `X-Cab-Deck-Console: 1` present, header `Origin` absent. The `Origin`/custom-header rule stops a web
  page open in a browser on the gaming PC (which would also come from `127.0.0.1`) from stopping the
  server: browsers always send `Origin` on a cross-origin or same-origin `fetch` POST, and a custom
  header forces a CORS preflight that the server never approves. uvicorn must run with
  `proxy_headers=False` so `X-Forwarded-For` cannot change `request.client.host`.
- **Change:** new. Served on every port (8000, 8701, 8702) like every other route; the console calls
  it on `127.0.0.1:8000`.
- **Request:** no query, no body (any body is ignored). Header `X-Cab-Deck-Console: 1` required.
- **Responses:**

  `202` — accepted; the server stops about 0.2 s later (after the response is sent).
  ```json
  { "status": "stopping" }
  ```

  `403` — not loopback, header missing or wrong, or `Origin` present.
  ```json
  { "detail": "Shutdown is allowed only from the Cab Deck console on this PC." }
  ```

  A second request while already stopping also gets `202` (idempotent). The server logs
  "Shutdown requested by the console." at INFO, then the existing "Server stopped, all buttons
  released." from the lifespan.

### `GET /api/health` (additive change)

Two new top-level fields; every existing field unchanged:

```json
{
  "status": "ok",
  "input": "vjoy",
  "...": "existing fields unchanged",
  "addresses": ["192.168.2.112"],
  "ports": { "panel": 8000, "dash": 8701, "dash2": 8702 }
}
```

- `addresses`: `list[str]`, IPv4 dotted strings, primary interface first, no `127.*`; empty list when
  none is found (never the `"<this-pc-ip>"` placeholder `main()` prints). Computed once at startup.
- `ports`: integers, the ports this server actually listens on (from `--port`, `--dash-port`,
  `--dash2-port`).
- Fields the console reads (all existing): `status`, `input` (`"vjoy"` | `"dry-run"`), `pressed`
  (`list[int]`), `clients` (int), `dash_clients` (int), `game` (`{"telemetry": false}` or
  `{"telemetry": true, "active": bool, "paused": bool}`), `commit` (str), `uptime_s` (int, seconds),
  `last_error` (str or null).

### `GET /api/logs?lines=200` (unchanged)

Plain text, last N lines of `logs/cab_deck.log`. Used only for an attached server.

### Process interface: console → `server.py`

- **Command:** `<python> -u server.py` or `<python> -u server.py --dry-run`, where `<python>` is
  `<repo>\.venv\Scripts\python.exe` (Windows) or `<repo>/.venv/bin/python` (macOS), `<repo>` =
  `path.resolve(__dirname, "..")`. Passed as an argument array to `child_process.spawn` (no shell),
  so paths with spaces need no quoting. No port arguments: the console relies on the defaults
  8000/8701/8702.
- **Options:** `cwd: <repo>`, `windowsHide: true`, `stdio: ["ignore", "pipe", "pipe"]`,
  `env: { ...process.env, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8" }`.
- **Output:** UTF-8 text lines on stdout (the URL banner from `main()`) and stderr (log records,
  tracebacks). The console displays them; it parses nothing from them. Health and addresses come
  only from `/api/health`.
- **Exit codes:** `0` after a graceful stop (R1, R6) or Ctrl+C; `1` on startup failure (config
  error, vJoy not available, port taken: the last log line says "Startup failed: …"); any other code
  or a signal is a crash. The console shows the code as is.
- **Stopping:** always `POST /api/shutdown` first. Fallback: macOS SIGTERM (uvicorn handles it
  gracefully), then `child.kill()`; Windows goes straight from the shutdown request to `child.kill()`
  (TerminateProcess: no cleanup runs; see Risks).
- **Timeouts (ms):** health probe at start 1500; health poll interval 1000, request timeout 800;
  stop wait 8000; SIGTERM wait 3000 (macOS only); quit cap 11000.

## Server

- `DeckState`: new fields `addresses: list[str]` and `ports: dict[str, int]`, and
  `request_shutdown: Callable[[], None] | None = None`.
- `main()`: store `local_ipv4_addresses()` (without the placeholder) and the three ports in `state`;
  build `uvicorn.Config(..., log_config=None, access_log=False, proxy_headers=False,
  timeout_graceful_shutdown=3)`, keep the `uvicorn.Server` instance and set
  `state.request_shutdown = lambda: setattr(server, "should_exit", True)` before `run()`.
- `create_app()`: new route `POST /api/shutdown` (contract above). After the guard passes it logs,
  answers `202`, and schedules `state.request_shutdown` with `loop.call_later(0.2, …)` so the
  response is sent first. `health()` adds `addresses` and `ports`.
- `open_vjoy()`: after `pyvjoy.VJoyDevice(device_id)` succeeds, call `device.reset_buttons()`; on
  `vJoyException` log a warning and continue. Log "vJoy device N: all buttons reset." on success.
- `run.bat`: unchanged.

## Screens

### Console window (`overlay/console.html`)

A normal framed, resizable window, title "Cab Deck Console", 1100×760 at start, minimum 900×600,
shown in the taskbar, centred on the primary screen. Dark look following the panel
(`static/index.html`): background `#08090B`, panel cards slightly lighter, system UI font, state
colours green (running), amber (starting, stopping, attached), red (crashed, unavailable), grey
(stopped). Plain HTML/CSS/JS, no build, no external network requests; a CSP that allows `self` and
`data:` images only.

Layout, top to bottom:

1. **Header bar.** "Cab Deck Console" · state badge (`Starting…`, `Running`, `Stopping…`, `Stopped`,
   `Crashed (exit 1)`, `Attached (started outside the console)`, `Python environment not found`) ·
   "DRY RUN" badge when `--dry-run` · buttons **Start**, **Stop**, **Restart**. Enabled by state:
   Start in `stopped`/`crashed`/`unavailable`; Stop in `starting`/`running`/`attached`; Restart in
   `running`/`attached`/`crashed`; none while `stopping`. A message line under the bar shows the last
   notice (R10, R12, R13, R18 texts).
2. **Main row, two columns.**
   - Left, **"Open on the tablet"**: two cards side by side, "Panel" and "Dash v2", each a QR code
     about 220 px square on a white quiet zone with the URL in monospace under it. An address chooser
     (small buttons, one per address) above the cards when health lists more than one. Empty states
     per R25 and R30.
   - Right, **"Server"** health grid (R27): Input, Game, Panels, Dashes, Pressed, Uptime (h:mm:ss),
     Commit, Last error (red when set, wraps). Greyed with "—" when no health; "not answering for
     N s" per R16.
     Under it, **"Overlay"**: **Show overlay / Hide overlay** and **Edit overlay / Done editing**
     buttons with the hotkey hints "Ctrl+Shift+F9" and "Ctrl+Shift+F10" next to them.
3. **Log tail.** Fills the rest of the height: monospace, dark, last 500 lines, auto-scrolls to the
   bottom unless the owner scrolled up; lines containing `ERROR` in red and `WARNING` in amber. A
   label above says "Server output" (managed) or "logs/cab_deck.log" (attached). After a crash the
   lines stay.

The header's button row is where E1.2 adds **Update**; nothing is rendered for it in E1.1 (no
disabled placeholder, so the owner never sees a dead button). The seam is in the main process: the
process-control module exports promise-returning `startServer()`, `stopServer()` and
`restartServer()` that E1.2 calls around `git pull`.

### Main-process modules (overlay side, internal)

- `overlay/main.js`: app lifecycle, single-instance lock, both windows, hotkeys, IPC registration,
  `before-quit` handling (R20: `event.preventDefault()`, await `stopServer()`, then `app.exit(0)`).
  The existing overlay functions (`createWindow`, `setEditing`, `resizeBy`, `moveBy`, `onEditKey`,
  `registerKeys`, config load/save) stay; `createWindow` may be renamed `createOverlayWindow`.
  `window-all-closed` quits; closing the console window quits the app (the overlay window cannot be
  closed by the user).
- `overlay/server-control.js` (new): spawn, health probe and poll, log ring buffer, `/api/logs` poll
  for attached, shutdown/kill sequence, state machine, change events to `main.js`.
- `overlay/console-preload.js` (new): `contextBridge.exposeInMainWorld("consoleApi", { getSnapshot,
  start, stop, restart, toggleOverlay, toggleOverlayEdit, setAddress, onSnapshot, onLog })`; nothing
  else. The console window uses `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`,
  blocks navigation (`will-navigate` prevented) and new windows (`setWindowOpenHandler` → deny).
- Snapshot sent to the page: `{ state, managed, dryRun, exitCode, notice, health, healthAgeS,
  overlay: { visible, editing }, qr: { address, addresses, panel: { url, dataUrl }, dash2: { url,
  dataUrl } } | null, qrError }`. `state` ∈ `unavailable | stopped | starting | running | stopping |
  crashed | attached`.

### Overlay window

Unchanged (R23). Its visibility and edit mode are now also driven from the console (R26).

## Acceptance criteria

Demo mode: a click-through checklist. `[mac]` = macOS with `npm run start:dry` in `overlay/` (venv
present); `[pc]` = the Windows gaming PC with vJoy and ATS.

- [ ] **AC1** (R8, R9, R16, R27, R28) `[mac]` — With no server running, run `npm run start:dry` in
  `overlay/`: the console opens, shows `Starting…` then `Running` and "DRY RUN"; Input shows
  `dry-run`; the log tail shows the server's startup lines.
- [ ] **AC2** (R4, R24) `[mac]` — In the running console, two QR codes show `http://<mac-ip>:8000`
  and `http://<mac-ip>:8702`; scanning the panel code with a phone on the same Wi-Fi opens the panel.
- [ ] **AC3** (R11, R1, R6) `[mac]` — Press Stop: the log tail shows "Shutdown requested by the
  console." and "Server stopped, all buttons released."; state `Stopped`; the QR area shows "Start the
  server to see the QR codes".
- [ ] **AC4** (R14) `[mac]` — Press Start, then Restart: the state goes `Stopping…` → `Starting…` →
  `Running`; Uptime restarts from 0.
- [ ] **AC5** (R2) `[mac]` — From another device on the LAN, `curl -X POST -H "X-Cab-Deck-Console: 1"
  http://<mac-ip>:8000/api/shutdown` answers 403 and the server keeps running; on the Mac,
  `curl -X POST http://127.0.0.1:8000/api/shutdown` (no header) also answers 403.
- [ ] **AC6** (R7, R13, R18) `[mac]` — Start `python server.py --dry-run` in a terminal, then the
  console: it shows `Attached`, the log tail labelled "logs/cab_deck.log". Ctrl+C the terminal
  server: within ~3 s the console shows `Stopped` with "The server that was already running has
  stopped."
- [ ] **AC7** (R17) `[mac]` — With a managed server running, kill its python process from Activity
  Monitor: the console shows `Crashed` with the exit signal/code and the last log lines; it does not
  restart it.
- [ ] **AC8** (R20) `[mac]` — With a managed server running, close the console window: the app exits
  within a few seconds and `curl http://127.0.0.1:8000/api/health` then fails; with an attached
  server, closing the console leaves that server running.
- [ ] **AC9** (R21) `[mac]` — Run `npm run start:dry` a second time while the console is open: no
  second window appears; the first console comes to the front.
- [ ] **AC10** (R10) `[mac]` — Temporarily rename `.venv`, start the console: it shows "Python
  environment not found. Run run.bat once…"; rename it back, press Start: it starts.
- [ ] **AC11** (R26, R23) `[mac]` — Press Hide overlay / Show overlay and Edit overlay / Done
  editing: the overlay window behaves exactly like with Ctrl+Shift+F9 / F10; pressing the hotkeys
  updates the console buttons.
- [ ] **AC12** (R22) `[mac]` — In the overlay window's devtools (or by reading `preload.js`),
  `window.consoleApi` is undefined; only `overlayApi.resize/move` exist.
- [ ] **AC13** (R29, R30) `[pc]` — On the gaming PC with an `overlay/node_modules` from the old
  overlay (no `qrcode`), double-click `console.bat`: it installs, the console opens and starts the
  server in vJoy mode (Input `vjoy`), QR codes for `http://192.168.2.112:8000` and `:8702`; the
  overlay shows over ATS; no Python console window appears.
- [ ] **AC14** (R5) `[pc]` — The console's log tail shows "vJoy device 1: all buttons reset." at
  start.
- [ ] **AC15** (R1, R3, R11) `[pc]` — On the tablet, hold a `hold` button (e.g. horn) and press Stop
  in the console while holding: the horn stops in the game, and the log shows "Server stopped, all
  buttons released.". In "Configure vJoy"/"Monitor vJoy", no button is lit.
- [ ] **AC16** (R14) `[pc]` — Press Restart while ATS is running: the tablet reconnects by itself
  within a few seconds and buttons work again.
- [ ] **AC17** (R7, R11) `[pc]` — Start `run.bat`, then `console.bat`: the console shows `Attached`;
  press Stop: the `run.bat` window shows the server stopped (then "Press any key").
- [ ] **AC18** (R20) `[pc]` — Close the console window with a managed server: the app exits; in
  Task Manager no `python.exe` of Cab Deck remains; the tablet panel shows disconnected.
- [ ] **AC19** (R24) `[pc]` — Scan both QR codes with the Android tablet: the panel and dash v2 open.

## Risks and edge cases

- **Can a vJoy button stay pressed?**
  - *Stop / Restart / quit from the console:* no. `POST /api/shutdown` goes through uvicorn's normal
    shutdown: WebSocket handlers get disconnects and release their held buttons, then the lifespan's
    `release_all` runs (R1). R3 bounds the wait so a stuck client cannot block it.
  - *Kill after the 8 s timeout (R12):* on Windows `child.kill()` is TerminateProcess; no Python code
    runs, so the lifespan does not release. A button pressed at that instant stays down in the vJoy
    driver (the driver keeps the last state after the feeder dies) until a feeder sets it again.
    Minimised by: (1) the graceful path first with a generous timeout (8 s against a 3 s uvicorn
    bound), so a kill means the server is already wedged; (2) R5: the next server start resets every
    button, and Restart starts it immediately after a kill; (3) the console writes a visible warning
    (R12) telling the owner that buttons may stay down until the server starts again.
  - *Server crash (R17):* same as a kill for a hard crash (no cleanup); an uncaught exception in a
    handler does not kill the process. No auto-restart, so the owner sees it; the next Start resets
    the buttons (R5).
  - *Console crash or force-quit (Electron killed):* the child keeps running on Windows (it is not a
    job-object child) and keeps working; buttons behave as with `run.bat`. A new console attaches
    to it (R7). On macOS the child also survives. Acceptable.
  - *Disconnect / page hide:* unchanged (existing per-client release and `hold_timeout_s`).
  - *Update:* E1.2; it will reuse `stopServer()`, which is graceful.
- **Windows kill skips cleanup:** covered above; the spec never uses `taskkill /F` or signals on
  Windows, only the shutdown route and, as last resort, `child.kill()`.
- **Who on the LAN can reach the new surface?** `POST /api/shutdown` answers on all three ports on
  `0.0.0.0`, but only to loopback with the header and no `Origin` (R1, R2). A LAN device gets 403. A
  web page in a browser on the gaming PC gets 403 (Origin sent; custom header blocked by preflight).
  Worst case if bypassed: the server stops and releases every button, which is safe.
  `addresses` in `/api/health` exposes the PC's LAN IPs to the LAN, which already reach it by IP.
- **Spoofed client address:** uvicorn's `proxy_headers` defaults to trusting `X-Forwarded-For` from
  `127.0.0.1` only; R1 requires `proxy_headers=False` anyway so the guard reads the socket peer.
- **Server not running / port taken:** console start probes health (R7). If 8000 is taken by
  something that is not Cab Deck, the child exits 1 with "Cannot listen on port 8000…" and the
  console shows `Crashed (exit 1)` with that line (R17). If 8702 is taken but 8000 free, same.
- **Two servers:** the attach probe and the Start probe (R15) prevent the console from spawning over
  a running server; `bind_socket()` refusing the port is the backstop.
- **Pipe backpressure:** a child whose stdout pipe is not read blocks on write; R19 requires
  continuous reading. Unbuffered output (`-u`) keeps lines live; `PYTHONIOENCODING=utf-8` avoids
  `UnicodeEncodeError` on the Windows code page.
- **Concurrency on the asyncio loop:** the shutdown route only sets a flag via `call_later`; nothing
  blocks the loop. `local_ipv4_addresses()` (which calls `getaddrinfo`, possibly slow on Windows) runs
  once at startup, never per health request.
- **Concurrent console actions:** Start/Stop/Restart are ignored while `stopping` or `starting` is in
  progress (buttons disabled, and the main process rejects a second operation while one runs).
- **Quit during start:** `before-quit` waits for the stop sequence; if the child has not bound yet,
  the shutdown request fails and the kill path runs (no buttons can be pressed before the server
  accepts clients, and R5 resets on the next start).
- **Existing installs:** `overlay/node_modules` without `qrcode` → R29 installs; if the owner starts
  with `npm start` directly, R30 keeps the app running without QR codes.
- **Gaming-PC check, step by step:** AC13–AC19 in order: pull `main` (`git pull` or `run.bat` once,
  then close it), double-click `console.bat`, check vJoy mode and the reset line, scan both QR codes,
  start ATS and see the overlay, hold the horn and press Stop, press Start and Restart with the game
  running, start `run.bat` + `console.bat` for attach, close the console and check Task Manager.

## Open questions

Resolved 2026-10-19 by the main session (Autonomy B): Q1, Q2 and Q3 take their defaults.

- **Q1** — Closing the console window quits the whole app (overlay included) and stops a managed
  server. Should it minimise to the taskbar instead, keeping the overlay and the server while
  driving? *Default:* close = quit (simplest, safe: buttons are released); the owner minimises the
  window to keep driving. Does not change the contract.
- **Q2** — `overlay.bat` now starts the full console (same app) rather than an overlay-only app.
  *Default:* accept it; with `run.bat` running first the console just attaches, so the old two-step
  flow still works. An `--overlay-only` flag can come later if the owner misses it.
- **Q3** — The `Origin`/`X-Cab-Deck-Console` guard goes beyond "403 unless loopback". *Default:* keep
  it; it costs two header checks and stops any local browser page from stopping the server.
