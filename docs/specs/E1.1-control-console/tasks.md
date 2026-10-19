# E1.1 — Tasks

Ordered. Each task is small enough to commit on its own and names the requirement IDs it serves.
Demo mode: no test tasks; acceptance is the checklist in `spec.md`.

Allowed paths in this spec: server side as in the root `CLAUDE.md`; overlay side = `overlay/` (not
`node_modules/`), `overlay.bat`, plus **`console.bat`** and **`README.md`** for this spec only.

## Server

- [ ] **S1** (R4) — In `server.py`, add `addresses: list[str]` and `ports: dict[str, int]` to
  `DeckState`; in `main()` store `local_ipv4_addresses()` (without the `"<this-pc-ip>"` placeholder)
  and `{"panel": args.port, "dash": args.dash_port, "dash2": args.dash2_port}`; add both fields to
  `health()` in `create_app()`. Existing fields unchanged.
- [ ] **S2** (R3, R6) — In `main()`, build `uvicorn.Config` with `proxy_headers=False` and
  `timeout_graceful_shutdown=3`, keep the `uvicorn.Server` instance, and set
  `state.request_shutdown` (new `DeckState` field, `Callable[[], None] | None`) to set its
  `should_exit`. A graceful stop exits with code 0.
- [ ] **S3** (R1, R2) — In `create_app()`, add `POST /api/shutdown` per the contract: loopback client,
  `X-Cab-Deck-Console: 1`, no `Origin`; `403` with the exact `detail` and a warning log otherwise;
  `202 {"status": "stopping"}` and `loop.call_later(0.2, state.request_shutdown)` when allowed;
  idempotent; logs "Shutdown requested by the console.".
- [ ] **S4** (R5) — In `open_vjoy()`, call `device.reset_buttons()` after the device opens; log
  "vJoy device N: all buttons reset."; on `vJoyException` log a warning and continue.

## Overlay

- [ ] **O1** (R24, R28, R29) — `overlay/package.json`: name `cab-deck-console`, productName
  `Cab Deck Console`, description, `dependencies: {"qrcode": "1.5.4"}`, script
  `start:dry: "electron . --dry-run"`; update `package-lock.json` with `npm install`.
- [ ] **O2** (R7, R8, R9, R10, R11, R12, R13, R14, R15, R16, R17, R18, R19) — New
  `overlay/server-control.js`: venv path, spawn per the process interface, start-up health probe and
  attach, 1 s health poll, 500-line log ring from stdout/stderr, `/api/logs` poll when attached,
  shutdown → wait → (SIGTERM on macOS) → kill sequence with the warning, crash detection without
  restart, the state machine and one operation at a time; exports `startServer()`, `stopServer()`,
  `restartServer()`, snapshot and change events.
- [ ] **O3** (R20, R21, R22, R23, R26, R28) — `overlay/main.js`: single-instance lock and focus;
  create the console window (local page, `console-preload.js`, sandboxed, navigation blocked) and the
  existing overlay window unchanged; IPC handlers accepting only the console window's
  `webContents`; overlay show/hide and edit from IPC and hotkeys share one code path and notify the
  console; `--dry-run` flag; `before-quit` awaits `stopServer()` for a managed server (cap 11 s);
  closing the console window quits.
- [ ] **O4** (R24, R25, R30) — QR generation in the main process with `qrcode` (`toDataURL`, PNG),
  for the panel and dash v2 URLs of the chosen address; lazy `require` with the R30 message when it
  fails; empty states per R25.
- [ ] **O5** (R22, R25, R26, R27) — New `overlay/console-preload.js` (`consoleApi` only) and
  `overlay/console.html`: header with state and DRY RUN badges and Start/Stop/Restart enabled by
  state, notice line, QR cards with address chooser, health grid, overlay buttons with hotkey hints,
  log tail with auto-scroll and colouring; every state (unavailable, stopped, starting, running,
  stopping, crashed, attached). Strict CSP, no network.
- [ ] **O6** (R29) — New `console.bat` at the repo root (npm check, install when `node_modules` or
  `node_modules\qrcode` is missing, `npm start` in `overlay/`); same install check in `overlay.bat`.
- [ ] **O7** (R29) — `README.md`: a short Ukrainian section "Консоль" before "Запуск": what it does,
  `console.bat` as the main way to start, `run.bat`/`overlay.bat` as fallbacks, attach behaviour,
  Stop releases every button, `npm run start:dry` on the Mac; update step 2 of "Оверлей поверх гри".
