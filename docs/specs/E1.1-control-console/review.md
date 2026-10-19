# E1.1 — Review report

## server

**Outcome:** approved  
**Review rounds:** 1  
**Verdict:** approve  
**Score:** 9/10

### Gates (reviewer)

- scripts/gates server: pass

### Findings

None.

### Deviations

None.

### Reviewer summary

I reviewed feat/E1.1-server at commit 003da57 against main for E1.1 tasks S1–S4 (R1–R6). There is one Conventional commit. On the server side's paths it changes only server.py. It also adds one entry to the side's state log at docs/specs/E1.1-control-console/state-server.md. No dependency was added and no other side's files were touched.

The contract matches the spec field by field:
- POST /api/shutdown is allowed only when the client is 127.0.0.1 or ::1, the X-Cab-Deck-Console header is exactly "1", and there is no Origin header.
- An allowed call answers 202 {"status":"stopping"} and schedules state.request_shutdown with loop.call_later(0.2, ...).
- Anything else answers 403 with the exact detail text and logs a warning with the client address.
- /api/health keeps every existing field and adds `addresses` (empty list instead of the "<this-pc-ip>" placeholder, primary address first, no 127.*) and `ports` {panel, dash, dash2}.
- uvicorn.Config sets proxy_headers=False and timeout_graceful_shutdown=3, and main() keeps the Server handle.
- open_vjoy() calls device.reset_buttons() after the device opens and before any client connects. It logs "vJoy device N: all buttons reset." and, on vJoyException, logs a warning and continues.

I re-ran `scripts/gates server` myself and it passed. In --dry-run on spare ports (18000/18701/18702) I checked the route and the shutdown path:
- The new health fields are present and correct.
- 403 when the header is missing, when it is "2", when Origin is present, and when called from the LAN IP. The LAN-IP call was still 403 when spoofed with X-Forwarded-For: 127.0.0.1, which confirms proxy_headers=False works.
- 202 on a dash port (route served on every port) and 202 again on a second request (idempotent).
- Both 202 calls logged "Shutdown requested by the console."; the stop then logged "Server stopped, all buttons released." and the process exited with code 0 (R6).
- With a panel WebSocket holding HORN (button 7), the shutdown request released button 7 about 0.2 s later. The socket closed with code 1012 and the lifespan ran release_all.

The installed uvicorn is 0.54.0, which supports timeout_graceful_shutdown. requirements.txt leaves uvicorn unpinned, and any version from 0.24 on has this parameter.

Only the Windows PC can confirm these:
- R5 / AC14: pyvjoy's reset_buttons() really clears the device and the log line appears.
- AC15: holding the horn and pressing Stop releases it in ATS, and Monitor vJoy shows no button lit.
- R3 bounding with a real stuck client on Windows.
- AC16 / AC17: restart and attach behaviour with run.bat.

## overlay

**Outcome:** approved  
**Review rounds:** 1  
**Verdict:** approve  
**Score:** 8/10

### Gates (reviewer)

- scripts/gates overlay: pass

### Findings

- **minor** `overlay/server-control.js:314` — On macOS the last-resort `proc.kill()` sends SIGTERM again (the Node default), not SIGKILL. A server that ignored the first SIGTERM is therefore never killed. `stopManaged` then returns false after waiting 2 s, while `child` still points at the live process. `doStop` reports `stopped` with the warning, but `isManaged()` stays true. A later Start probes and then spawns over the old `child` reference, and the old process's exit is ignored. This matters on macOS only. On Windows, `child.kill()` is TerminateProcess and behaves as the spec says.
  - Fix: On non-Windows, call `proc.kill("SIGKILL")` in the final step (keep plain `proc.kill()` on Windows). If `waitForExit` still fails, leave the state as `stopping`/`crashed` instead of `stopped`, or clear `child` explicitly, so the snapshot never says `stopped` while `managed` is true.
- **minor** `overlay/server-control.js:69` — While the start-up probe runs, the internal `initial` state is reported as `starting`, so console.html enables Stop. `exclusive()` silently ignores a Stop press during that time (up to 1.5 s). The button looks active but does nothing.
  - Fix: Either report `initial` with Stop disabled (for example a flag in the snapshot that the page uses to disable all three buttons), or let `doStop` handle `initial` by setting a flag that makes `doStart` skip the spawn.
- **minor** `overlay/console.html:192` — When the console is attached to a server whose health has no `addresses` or `ports` field (for example a pre-E1.1 server still running from `run.bat`), `buildQr` returns null and the page shows "Start the server to see the QR codes" even though the state is `Attached`. That message is misleading.
  - Fix: In `renderQr`, when running/attached and `health.addresses` is not an array, show a specific message such as "This server is too old to report its addresses; restart it from the console.", or treat a missing field like an empty list (the R25 'No LAN address' text).

### Deviations

- The overlay resize/move IPC now also checks that the sender is the overlay window. This is not required by the spec, but it fits R22.
- startServer and restartServer resolve once the child is spawned or attached, not when health turns ok.
- An internal `initial` state while probing at start is shown to the page as `starting`.
- A failed Stop on an attached server returns it to `attached` with the R13 notice.
- The server-side /api/shutdown is on a separate branch, so Stop and Restart paths were not exercised against a real server here.

### Reviewer summary

I reviewed the overlay side of E1.1 (feat/E1.1-overlay against main): overlay/server-control.js, overlay/main.js, overlay/console-preload.js, overlay/console.html, overlay/package.json and the lock file, console.bat, overlay.bat and the README section. Requirements R7–R30 are all implemented. The process interface matches the spec: venv python, `-u server.py [--dry-run]`, cwd at the repo root, no shell, `windowsHide`, `stdio` ignore/pipe/pipe, and the PYTHONUNBUFFERED/PYTHONIOENCODING env. The shutdown call sends `X-Cab-Deck-Console: 1` and no Origin. Node's fetch does not add one: the server answered 202. All timeouts match the spec. The preload exposes exactly `consoleApi` with the specified methods. Every console IPC handler checks that the sender is the console window's webContents. The console window is sandboxed, with navigation and new windows blocked. The overlay window and its preload are unchanged; the only addition is a sender check on resize/move.

The gate passes (`scripts/gates overlay`, exit 0). For a dry-run check on macOS, I combined the server branch and this branch in a scratchpad copy and ran server-control.js against a real `server.py --dry-run`:
- **Start, restart, stop:** start went `starting` → `running`, and health showed `addresses` and `ports`. Restart went `stopping` → `stopped` → `starting` → `running`. Stop was graceful in about 0.5 s, with "Server stopped, all buttons released." in the log tail.
- **Server not answering and crash (R16, R17):** a SIGSTOPped child showed "not answering for N s". A SIGKILL then gave `crashed` with "signal SIGKILL", the last log lines stayed, and nothing restarted.
- **Attach (R15, R7, R18, R14):** Start while an external server ran attached, with the "logs/cab_deck.log" tail. Ctrl+C on that server gave `stopped` with the R18 notice. Stop on an attached server stopped it. A restart then spawned a managed server.
- **No venv (R10):** gives `unavailable` with the exact message.
- **Electron app:** I launched the full app with `--dry-run`. A second instance exited 0 (R21). Quitting the app stopped the managed server it had started, and health then failed (R20).

The findings are three minor notes, all about macOS or edge-case UX. None can leave a button pressed.

Only the Windows PC can confirm the rest: that `console.bat`/`overlay.bat` install `qrcode` over an old node_modules (AC13); that no Python console window appears; vJoy mode and the reset line (AC14); the horn being released on Stop (AC15); the tablet reconnecting after Restart (AC16); attaching to `run.bat` and stopping it (AC17); no `python.exe` left after closing the console (AC18); and scanning both QR codes with the Android tablet (AC19).
