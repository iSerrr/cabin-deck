---
id: E1.2
title: Update the code, the dependencies and the console itself from one console button
status: done
depends_on: [E1.1]
touches: [overlay]
---

# E1.2 — Update from the console

## Context

Backlog epic E1.2 (`docs/backlog.md`): "'Update' in the console: `git pull`, dependencies when their
lockfiles changed, server restart, and an app relaunch when the console's own code changed". Level
L, stage 2 of 2 of epic E1; risk area "controls the PC" (git, processes, files).

The owner (translated): "From the console you can restart, re-pull right there. You don't have to
leave it, close the overlay, close one thing, then another. You just re-pull once and everything is
updated, and the console itself updated too."

`PRD.md` section this extends: "Етап 6: пульт керування" — "**E1.2 Оновлення:** кнопка «Оновити» —
`git pull`, залежності, рестарт сервера й перезапуск пульта." and its intro "Виходити з пульта й
закривати вікна по черзі не треба." Hard constraint from `CLAUDE.md` kept: "No button may stay
pressed after disconnect, page hide, or server shutdown."

What exists today (E1.1, merged):

- `overlay/server-control.js`: the state machine (`unavailable | stopped | starting | running |
  stopping | crashed | attached`, plus the internal `initial` reported as `starting` with
  `probing: true`); `doStart()` (probe health, attach or `spawnServer()`), `doStop()` (shutdown route,
  `stopManaged()` wait/kill, or `waitForGone()` for an attached server), `exclusive(fn)` (one
  operation at a time: a call while `busy` is ignored), exported `startServer()`, `stopServer()`,
  `restartServer()`, `init()`, `stopManagedForQuit()`, `killNow()`, `isManaged()`, `getSnapshot()`,
  `getLog()` and the `events` emitter (`change`, `log`, `child-exit`). The log ring (`logLines`, 500
  lines) is cleared by `spawnServer()` and replaced wholesale by `pollLogs()` while attached. The
  constant `NO_PYTHON` holds the R10 text "Python environment not found. Run run.bat once to create
  it, then press Start."
- `overlay/main.js`: single-instance lock (`app.requestSingleInstanceLock()`, `second-instance` →
  `showConsole()`), `createConsoleWindow()`, `createOverlayWindow()`, `registerConsoleIpc()` with
  `fromConsole(event)` checks on `console:get-snapshot|start|stop|restart|toggle-overlay|
  toggle-overlay-edit|set-address`, `fullSnapshot()`/`notifyConsole()`, and `before-quit` which stops
  a managed server (cap `QUIT_CAP_MS` 11 s) and then `app.exit(0)`. `DRY_RUN` comes from
  `process.argv`.
- `overlay/console-preload.js` exposes `consoleApi` with exactly `getSnapshot, start, stop, restart,
  toggleOverlay, toggleOverlayEdit, setAddress, onSnapshot, onLog`.
- `overlay/console.html`: header with `#state` and `#dry` badges and buttons `#start`, `#stop`,
  `#restart` enabled by the `ENABLED` table and `s.probing`; `#notice` line; `renderLog()` colours
  lines containing `ERROR` red and `WARNING` amber; the label above the tail shows `log.source`.
- `console.bat` / `overlay.bat`: `cd overlay`, check `npm`, `npm install --no-audit --no-fund` when
  `node_modules` or `node_modules\qrcode` is missing, then `call npm start`.
- `run.bat` (the current update procedure, unchanged by this spec): `git pull --ff-only`; `python -m
  venv .venv` when missing; `.venv\Scripts\python -m pip install --quiet
  --disable-pip-version-check -r requirements.txt`; start the server.
- `server.py` reads its commit once at start (`git_commit()`, `git rev-parse --short HEAD`), so
  health's `commit` changes after the restart. No server change is needed.

## Scope

Size target: one overlay PR of roughly one new module (`overlay/updater.js`, ~250 lines) plus small
changes to `server-control.js`, `main.js`, `console-preload.js`, `console.html`, `console.bat`,
`overlay.bat` and the README console section. Cut line: one button that brings code, Python packages,
console packages and the console itself up to date and leaves the server as it was; nothing about
choosing branches, rolling back, or scheduling.

- An **Update** button in the console header that runs: check git → stop the server (graceful,
  E1.1's sequence) → `git pull --ff-only` → create `.venv` if missing → `pip install` when
  `requirements.txt` changed or the venv was just created → relaunch the console when its own code
  changed (with a `console.bat` handover on Windows when its npm packages changed) → otherwise start
  the server again if it was running.
- Live progress: the header shows the step and `old → new` commit; every command's output streams
  into the log tail and survives the server restart and the console relaunch.
- Safe failure: nothing in the working tree is ever reset, stashed or forced; a failed pull leaves the
  code as it was and restarts the server.
- "Python environment not found" now points to Update, which creates the venv.
- `console.bat` gains an `update` mode for the handover; both launchers stop rewriting the tracked
  lockfile. README console section (Ukrainian) gets the Update button.

This spec allows `README.md` and `console.bat` as overlay-side paths (as E1.1 did).

## Out of scope

- Choosing a branch, showing what is new (changelog), rolling back to an older commit: not planned.
- Fixing a dirty or diverged working tree from the console (stash, reset, discard): not planned on
  purpose; the console reports the git error and the owner fixes it by hand.
- Automatic or scheduled updates, update-available badges (`git fetch` in the background): not
  planned.
- Updating Node.js, Python, Git or vJoy themselves: not planned.
- Changing `run.bat`: it keeps its own pull/install procedure (server side; unchanged).
- Any server change (`server.py`): none needed; the server is stopped and started through E1.1's
  interface.
- The three minor E1.1 review notes: already addressed by `fix/console-review-notes` (merged).
- Updating `docs/architecture.md` for the new file and launcher mode: the main session after delivery
  (see the summary note).

## Requirements

### Button and exclusivity

- **R1** — The console header shall show an **Update** button after Restart, enabled while the state
  is `running`, `attached`, `stopped`, `crashed` or `unavailable`, and disabled while `starting`,
  `stopping`, probing (`probing: true`) or while an update runs.
- **R2** — While an update runs, the console shall disable Start, Stop, Restart and Update, and the
  main process shall ignore start, stop, restart and update requests, using the same one-operation
  lock as E1.1 (`exclusive()` in `server-control.js`) for the whole update.
- **R3** — The update request shall be exposed only by `overlay/console-preload.js` as
  `consoleApi.update()` (IPC channel `console:update`), and the main process shall ignore it unless
  it comes from the console window's `webContents` (E1.1 R22).

### Sequence

- **R4** — When the owner presses Update, the console shall first run `git rev-parse HEAD` in the repo
  root; if that fails (git not on PATH, not a repository, timeout), then it shall show the failure
  notice from the notice table and end the update without stopping the server.
- **R5** — When the update starts, the console shall record whether the server must run afterwards:
  yes when the state was `running`, `attached` or `unavailable`; no when it was `stopped` or
  `crashed`.
- **R6** — When the server is managed or attached, the console shall stop it through E1.1's stop
  sequence (`doStop()`: shutdown route, R11/R12 for managed, R13 for attached) before running any
  command that changes files.
- **R7** — If an attached server does not stop (E1.1 R13), then the console shall end the update
  without pulling, keep the state `attached`, and show the "update cancelled" notice.
- **R8** — After the server is stopped, the console shall run `git pull --ff-only` in the repo root
  with `GIT_TERMINAL_PROMPT=0`.
- **R9** — If `git pull` exits non-zero, cannot be spawned, or times out, then the console shall show
  the matching failure notice, skip every later step except restoring the server (R16), and not
  relaunch.
- **R10** — The console shall run only these git commands: `rev-parse HEAD`, `pull --ff-only`, `diff
  --name-only <old> <new>`. It shall never run `git reset`, `git stash`, `git checkout`, `git clean`,
  `git merge`, `git rebase`, or any command with `--force`/`-f`.
- **R11** — When `git pull` succeeds, the console shall read `git rev-parse HEAD` again; if it equals
  the old commit, the result is "already up to date"; otherwise it shall run `git diff --name-only
  <old> <new>` and use that file list for R13, R17, R18 and R19. If that `diff` fails, the console
  shall treat the update as if `requirements.txt` and `overlay/package-lock.json` changed.
- **R12** — When the venv python (`<repo>/.venv/Scripts/python.exe` on Windows,
  `<repo>/.venv/bin/python` on macOS) does not exist after a successful pull, the console shall create
  the venv with the system Python — Windows: `py -3 -m venv .venv`, and only if `py` cannot be spawned
  (`ENOENT`), `python -m venv .venv`; macOS: `python3 -m venv .venv` — whether or not the pull
  brought new commits.
- **R13** — When the venv was created by R12, or `requirements.txt` is in the R11 file list, the
  console shall run `<venv python> -m pip install --disable-pip-version-check --progress-bar off -r
  requirements.txt` in the repo root.
- **R14** — If venv creation fails, then the console shall skip pip, show the "cannot create the
  Python environment" notice, and leave the server in state `unavailable` without a start attempt
  (R16 does not start it; R17, R18 and R19 still apply).
- **R15** — If pip exits non-zero or times out, then the console shall show the "pip failed" notice
  and still continue with R16, R17 or R18 (the server may still run with the old packages).
- **R16** — When the update does not relaunch the console (R17, R18 and R19 do not apply or were
  skipped), the console shall end by starting the server through E1.1's start sequence (`doStart()`:
  probe, attach or spawn managed) if R5 recorded "must run", and leave it stopped otherwise.
- **R17** — When the R11 file list has any path under `overlay/` other than `overlay/overlay.json`,
  and neither `overlay/package.json` nor `overlay/package-lock.json`, the console shall (server
  already stopped) write the result file (R22), call `app.releaseSingleInstanceLock()`, then
  `app.relaunch({ execPath: process.execPath, args: [app.getAppPath(), ...(dryRun ? ["--dry-run"] :
  [])] })` and `app.exit(0)`.
- **R18** — When the R11 file list has `overlay/package.json` or `overlay/package-lock.json` and the
  platform is Windows, the console shall not run npm itself; it shall write the result file (R22),
  call `app.releaseSingleInstanceLock()`, spawn `console.bat update <pid> [dry]` detached in its own
  visible console window (process interface below), and then `app.exit(0)`.
- **R19** — When the R11 file list has `overlay/package.json` or `overlay/package-lock.json` and the
  platform is macOS, the console shall run `npm install --no-save --no-audit --no-fund` in `overlay/`
  and then relaunch as in R17; if npm fails or times out, it shall show the "console packages failed"
  notice, not relaunch, and restore the server (R16).
- **R20** — After a relaunch (R17, R18, R19), the new console instance shall start like any start
  (E1.1 R7/R8: attach or spawn), so the server runs afterwards even if it was stopped before the
  update.
- **R21** — `console.bat update <pid> [dry]` shall wait until no `electron.exe` with that PID exists
  (checking every 1 s, at most 30 s, then 2 s more), run `npm install --no-save --no-audit --no-fund`
  in `overlay/`, and start the console with `npm start` (or `npm run start:dry` when `dry` is given);
  if the wait runs out it shall say so and stop without installing; if npm install fails it shall say
  so and still try to start the console; if the start fails it shall `pause` so the window stays
  open with the error.
- **R22** — Before a relaunch or handover, the console shall write `<repo>/logs/console-update.json`
  (format below); when the console starts and that file exists, is valid and is at most 10 minutes
  old, it shall show its notice as the update notice, put its lines at the top of the log tail, and
  delete the file; an invalid or older file is deleted and ignored.

### Progress, output, notices

- **R23** — While an update runs, the header shall show a badge "Updating: <step label>" (labels in
  "Screens") and, once known, the commits as `abc1234 → def5678` (7-character short hashes; only
  `abc1234` before the pull finishes).
- **R24** — For every command it runs, the console shall add to the log tail a line `[update] $
  <program> <args…>` before it, every stdout and stderr line of it as it arrives, and after it either
  `[update] done in N s` or `[update] ERROR: <program> failed (exit N | signal S | timed out after N s
  | <spawn error message>)`.
- **R25** — The update's log lines shall stay in the log tail when the server is started again: the
  spawn after an update (and an attach after an update) appends a line `---- server ----` instead of
  clearing the tail, and while attached `/api/logs` lines replace only the lines after that marker.
- **R26** — When an update ends, the console shall show exactly one notice from the notice table
  (below) in an update-notice line under the header, coloured by its result (`ok` green, `warning`
  amber, `error` red), kept until the next update starts.
- **R27** — The E1.1 R10 message shall become "Python environment not found. Press Update to create
  it." (state `unavailable`; Start stays enabled to attach to a server started elsewhere).

### Commands and lifecycle

- **R28** — The console shall run every update command with `child_process.spawn` and an argument
  array (no shell), `windowsHide: true`, `stdio: ["ignore", "pipe", "pipe"]`, cwd = repo root (git,
  python, pip) or `<repo>/overlay` (npm on macOS), the inherited environment plus the variables in
  the contract, and a per-command timeout; the only exception is the R18 handover, which must start
  `cmd.exe` to run a `.bat`.
- **R29** — If a command runs past its timeout, then the console shall kill it (`child.kill()`:
  TerminateProcess on Windows; SIGTERM on macOS, then SIGKILL after 2 s) and treat the step as
  failed with "timed out after N s".
- **R30** — While an update runs, closing the console window or quitting the app shall be refused:
  the window stays open and the notice line says "Wait for the update to finish; every step stops by
  itself within its time limit." The update ends within the sum of its step timeouts.
- **R31** — `console.bat` and `overlay.bat` in their normal mode shall install with `npm install
  --no-save --no-audit --no-fund`, so the tracked `overlay/package-lock.json` is never rewritten on
  the PC (a rewritten lockfile would make the next `git pull --ff-only` fail).
- **R32** — `README.md`, section "Консоль" (Ukrainian), shall describe the Update button: what it does
  in order, that it never discards local changes, that the console may close and reopen itself (and
  on Windows a window installs the console's packages), and what to do when git pull fails.

## Notice table

`<old>`/`<new>` are 7-character short hashes. "Python packages installed." is appended (after a
space) to the ok texts when R13 ran and succeeded; "Python environment created." is prepended when
R12 ran and succeeded.

| Case | Result | Exact text |
| --- | --- | --- |
| Up to date | ok | `Already up to date (commit <old>).` |
| Updated, no relaunch | ok | `Updated <old> → <new>.` |
| Updated, relaunch (shown by the new instance) | ok | `Updated <old> → <new>. The console was relaunched with its new code.` |
| git not found (R4) | error | `Update failed: git is not installed or not on PATH. Nothing was changed.` |
| rev-parse failed otherwise (R4) | error | `Update failed: cannot read the current commit (see the log). Nothing was changed.` |
| Attached server did not stop (R7) | error | `Update cancelled: the server did not stop. Close its window (run.bat), then press Update again.` |
| git pull failed (R9) | error | `Update failed: git pull did not succeed (see the log). Nothing was changed.` |
| git pull timed out (R9) | error | `Update failed: git pull did not finish in 60 s and was stopped (see the log).` |
| venv creation failed (R14) | error | `Cannot create the Python environment. Is Python 3.10+ installed and on PATH? (see the log)` |
| pip failed or timed out (R15) | warning | `Updated <old> → <new>, but installing Python packages failed (see the log). The server was started anyway.` (when the update was "already up to date": `Already up to date (commit <old>), but installing Python packages failed (see the log). The server was started anyway.`; when R5 said "no", "The server was started anyway." is left out) |
| npm failed on macOS (R19) | warning | `Updated <old> → <new>, but installing the console's packages failed (see the log). Run npm install in overlay/ and restart the console.` |
| Handover (R18), shown while closing | ok | `Console packages changed: the console closes, installs them in a separate window and opens again.` |

For the relaunch and handover paths the final notice is carried by the result file (R22); when R15
also failed, the pip warning text is used instead of the "relaunched" text.

## Config and files

- `overlay/overlay.json`: no change.
- `config.json`, `requirements.txt`: no change.
- New, written and read only by the console: `<repo>/logs/console-update.json` (in the git-ignored
  `logs/`; the console creates `logs/` if missing). Format:

  ```json
  {
    "version": 1,
    "writtenAt": "2026-10-19T18:04:05.123Z",
    "from": "abc1234",
    "to": "def5678",
    "result": "ok",
    "notice": "Updated abc1234 → def5678. The console was relaunched with its new code.",
    "lines": ["[update] $ git pull --ff-only", "..."]
  }
  ```

  `version` int, must be `1`; `writtenAt` ISO 8601 UTC; `from`/`to` 7-character strings; `result`
  `"ok" | "warning" | "error"`; `notice` string; `lines` the update's log lines (at most the last 200).
  Read once at console start; deleted after reading; ignored and deleted when it does not parse, has
  another `version`, or `writtenAt` is more than 600 000 ms (10 minutes) before now.
- `.venv/`: created by Update when missing (R12), git-ignored as today.
- `console.bat`: new `update` mode (contract below); normal mode adds `--no-save` (R31).
- `overlay.bat`: `--no-save` (R31); no update mode.
- `overlay/package.json`, `overlay/package-lock.json`: no change (no new dependency).

## API contract

No HTTP route or WebSocket message changes: the server side is untouched, and Update stops and starts
the server only through E1.1's existing interface (`POST /api/shutdown`, `GET /api/health`, `GET
/api/logs`, the `server.py` process interface). What crosses process boundaries in this spec is
listed below; it is all on the overlay side, so no other developer builds against it, but the
reviewer checks it field by field.

### IPC: console page → main process (additive)

- **Who may call:** the console window only (E1.1 R22): `console-preload.js` exposes
  `consoleApi.update(): Promise<void>` = `ipcRenderer.invoke("console:update")`; the main process's
  `ipcMain.handle("console:update", …)` returns without doing anything unless `fromConsole(event)`.
  The overlay window's `preload.js` is unchanged (only `overlayApi.resize/move`).
- **Change:** additive. The promise resolves when the update ends (or at once when another operation
  runs; it is ignored then). No arguments; the page never sends a command, path or flag.
- **Snapshot (additive):** `console:snapshot` gains

  ```json
  "update": {
    "running": false,
    "step": null,
    "from": null,
    "to": null,
    "notice": "",
    "result": null
  }
  ```

  `running` bool; `step` one of `checking | stopping | pulling | venv | pip | npm | starting |
  relaunching | handover` or `null` when not running; `from`/`to` 7-character short hash or `null`;
  `notice` the last R26 text or `""`; `result` `"ok" | "warning" | "error" | null`. Every existing
  snapshot field is unchanged; `state` keeps its seven values (the server state keeps moving
  `stopping → stopped → starting → running` during an update). `getLog().source` gains the value
  `"update"` (label "Update output") while an update runs.

### Process interface: console → git

All with `cwd: <repo>`, `windowsHide: true`, `stdio: ["ignore", "pipe", "pipe"]`, `env: {
...process.env, GIT_TERMINAL_PROMPT: "0" }`, program `git` resolved from `PATH` (libuv finds
`git.exe` on Windows without a shell).

| Step | Arguments | Timeout | Success | Output used |
| --- | --- | --- | --- | --- |
| checking | `["rev-parse", "HEAD"]` | 10 000 ms | exit 0 | stdout first line, 40 hex chars → old commit |
| pulling | `["pull", "--ff-only"]` | 60 000 ms | exit 0 | displayed only |
| pulling | `["rev-parse", "HEAD"]` | 10 000 ms | exit 0 | new commit |
| pulling | `["diff", "--name-only", "<old>", "<new>"]` | 10 000 ms | exit 0 | one repo-relative path per line, `/` separators |

`ENOENT` on spawn → "git is not installed" notice. A failing `diff` after a successful pull is treated
as if `requirements.txt` and `overlay/package-lock.json` changed (R11): pip runs and the R18/R19
package path is taken.

### Process interface: console → Python

| Step | Program | Arguments | Timeout |
| --- | --- | --- | --- |
| venv (Windows) | `py` | `["-3", "-m", "venv", ".venv"]` | 120 000 ms |
| venv (Windows, only on `ENOENT` for `py`) | `python` | `["-m", "venv", ".venv"]` | 120 000 ms |
| venv (macOS) | `python3` | `["-m", "venv", ".venv"]` | 120 000 ms |
| pip | `<repo>\.venv\Scripts\python.exe` / `<repo>/.venv/bin/python` | `["-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off", "-r", "requirements.txt"]` | 300 000 ms |

`cwd: <repo>`, `windowsHide: true`, `stdio: ["ignore", "pipe", "pipe"]`, `env: { ...process.env,
PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8" }`. Success = exit 0 and, for venv, the venv python
file exists afterwards. A Windows `python` that is the Microsoft Store alias exits non-zero (9009);
that is a venv failure (R14).

### Process interface: console → npm (macOS only)

`npm` with `["install", "--no-save", "--no-audit", "--no-fund"]`, `cwd: <repo>/overlay`,
`windowsHide: true`, `stdio: ["ignore", "pipe", "pipe"]`, inherited env, timeout 300 000 ms. Never
run on Windows (R18).

### Process interface: console → `console.bat` handover (Windows only)

- **Spawn:** `spawn(process.env.ComSpec || "cmd.exe", ["/d", "/s", "/c", "\"\"<repo>\\console.bat\"
  update <pid>[ dry]\""], { cwd: <repo>, detached: true, stdio: "ignore", windowsHide: false,
  windowsVerbatimArguments: true })`, then `child.unref()`. `<pid>` = `process.pid` of the Electron
  main process (decimal integer); ` dry` is appended when the console runs with `--dry-run`. The
  command string is built only from the repo path and that integer; nothing comes from the page.
- **Order in the console:** server already stopped → write the result file → show the handover
  notice → `app.releaseSingleInstanceLock()` → spawn → `app.exit(0)`. If the spawn throws, the
  console does not exit: it shows "Cannot start console.bat for the update: <message>. Close the
  console and run console.bat." (result `error`) and restores the server (R16).
- **`console.bat update <pid> [dry]` behaviour (R21):**
  1. `title Cab Deck Console update`, `cd /d "%~dp0overlay"`, the existing `where npm` check.
  2. Echo `Waiting for the old console to close...`; loop up to 30 times: `tasklist /FI "PID eq
     <pid>" /FI "IMAGENAME eq electron.exe" /NH | find /I "electron.exe" >nul`; if found, `timeout /t
     1 /nobreak >nul` and repeat. If still found after 30 tries: echo `The old console did not close.
     Close it, then run console.bat.`, `pause`, `exit /b 1`. Then `timeout /t 2 /nobreak >nul` (lets
     Electron's helper processes release their files).
  3. Echo `Installing the console's packages...`; `call npm install --no-save --no-audit --no-fund`;
     on errorlevel ≠ 0 echo `npm install failed (see above). Trying to start the console anyway...`.
  4. `call npm start` (or `call npm run start:dry` when `%3` is `dry`); on errorlevel ≠ 0 echo `The
     console did not start. Run console.bat again; if it fails again, delete overlay\node_modules
     and run console.bat.` and `pause`.
  The window stays open while the new console runs (as after a double-click on `console.bat`) and
  closes when it exits.
- **Exit codes:** `0` after the console exits normally; `1` when npm is missing or the old console did
  not close. Nobody reads them; the window shows the text.
- **Normal mode** (no arguments): unchanged except `--no-save` (R31).

### Process interface: relaunch (R17, R19)

`app.releaseSingleInstanceLock()`; `app.relaunch({ execPath: process.execPath, args:
[app.getAppPath(), "--dry-run"?] })` (absolute app path, so the working directory of the new process
does not matter); `app.exit(0)`. Electron starts the new process after the old one has exited, so
the single-instance lock is free; `before-quit`/`will-quit` do not run, which is fine because the
server is already stopped and no update command is running.

### Step timeouts (ms)

rev-parse 10 000; pull 60 000; diff 10 000; venv 120 000; pip 300 000; npm (macOS) 300 000; kill
grace on macOS 2 000; handover PID wait 30 000 + 2 000 (in `console.bat`); result file max age
600 000. Stop and start keep E1.1's timeouts (stop wait 8 000, SIGTERM 3 000, probe 1 500).

## Server

None. Update uses only E1.1's server interface; `server.py` and `run.bat` are unchanged.

## Screens

### Console window (`overlay/console.html`)

Same look as E1.1. Changes:

1. **Header bar.** After **Restart**, a fourth button **Update**, same style. Enabled per R1.
   While an update runs, a second badge (amber) after the state badge reads `Updating: <label>` and,
   after it in monospace, `abc1234` or `abc1234 → def5678`. Step labels:

   | `step` | Label |
   | --- | --- |
   | `checking` | `Checking the repository` |
   | `stopping` | `Stopping the server` |
   | `pulling` | `Pulling code` |
   | `venv` | `Creating the Python environment` |
   | `pip` | `Installing Python packages` |
   | `npm` | `Installing console packages` |
   | `starting` | `Starting the server` |
   | `relaunching` | `Relaunching the console` |
   | `handover` | `Closing for the package install` |

   The state badge keeps showing the server state (`Stopping…`, `Stopped`, `Starting…`, `Running`).
   All four process buttons are disabled while `update.running` (R2).
2. **Update-notice line** (new, under the existing `#notice` line): `update.notice`, green/amber/red
   by `update.result`, empty when there is none. The existing `#notice` keeps the E1.1 notices and
   the R30 "Wait for the update to finish…" text.
3. **Log tail.** Label "Update output" while `source` is `"update"`. Lines starting `[update]` use the
   dim text colour, except `[update] ERROR:` lines, which are red by the existing `ERROR` rule.
   After the update the `---- server ----` marker separates update and server lines (R25).

Unavailable state text per R27. Nothing else in the window changes; the overlay window is unchanged.

### Main-process modules (overlay side, internal)

- `overlay/updater.js` (new): the step runner (spawn with timeout and line streaming into the log
  ring), the git/Python/npm steps, the decisions of R11–R19, the notice texts, writing and reading
  the result file. Exposes `runUpdate()` (resolves to `{ action: "none" | "relaunch" | "handover" }`)
  and `consumeResultFile()`.
- `overlay/server-control.js`: export the lock (`runExclusive(fn)`, the existing `exclusive`), the
  unlocked `doStart`/`doStop` for use inside it, an `appendLog(lines)`, the `update` snapshot block
  and setters, the R25 marker behaviour, and the R27 text. Exclusivity stays here.
- `overlay/main.js`: `console:update` handler with `fromConsole`; acts on `runUpdate()`'s result
  (R17/R18/R19 relaunch or handover, since it owns `app`); calls `consumeResultFile()` before
  `serverControl.init()`; refuses close/quit while an update runs (R30: `close` on the console
  window and `before-quit` are prevented and the notice set).

## Acceptance criteria

Demo mode: a click-through checklist. `[mac]` = macOS with `npm run start:dry` in `overlay/`; `[pc]` =
the Windows gaming PC with vJoy and ATS.

**Mac test bench** (once; the console updates the clone it runs from, so never point it at your
working repo). With the E1.2 overlay branch pushed as `<branch>`:

```
git clone --bare --single-branch --branch <branch> https://github.com/iSerrr/cabin-deck.git /tmp/cd-origin.git
git clone /tmp/cd-origin.git /tmp/cd-a        # the console runs here
git clone /tmp/cd-origin.git /tmp/cd-b        # you make "new commits" here and git push them
cd /tmp/cd-a && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd /tmp/cd-a/overlay && npm install --no-save && npm run start:dry
```

- [ ] **AC1** (R1, R4, R5, R6, R8, R11, R16, R23, R26) `[mac]` — With the server Running, press
  Update: the badge goes `Updating: Checking the repository` → `Stopping the server` → `Pulling code`
  → `Starting the server`; the update-notice line says `Already up to date (commit abc1234).` in
  green; the state ends `Running`.
- [ ] **AC2** (R11, R16, R23, R24, R25) `[mac]` — In `/tmp/cd-b`, change `docs/status.md`, commit,
  `git push`. Press Update: the header shows `abc1234 → def5678`; the log tail shows `[update] $ git
  pull --ff-only`, git's output, `[update] done in N s`, then `---- server ----` and the server's
  startup lines; notice `Updated abc1234 → def5678.`; health Commit shows `def5678`; no relaunch
  (the window does not close).
- [ ] **AC3** (R13) `[mac]` — In `/tmp/cd-b`, add a comment line `# test` to `requirements.txt`,
  commit, push; press Update: the step `Installing Python packages` appears and pip's output streams;
  notice ends with `Python packages installed.`
- [ ] **AC4** (R15) `[mac]` — In `/tmp/cd-b`, add `cab-deck-no-such-package==0.0.1` to
  `requirements.txt`, push; press Update: pip fails with an `[update] ERROR:` line in red, the notice
  is the amber pip warning, and the server is Running anyway. Revert the line in `/tmp/cd-b`, push,
  Update again: green.
- [ ] **AC5** (R17, R20, R22, R25) `[mac]` — In `/tmp/cd-b`, change the heading text
  `Open on the tablet` in `overlay/console.html` to `Open on the tablet (new)`, push; press Update: the
  badge shows `Relaunching the console`, the window closes and one new console window opens within a
  few seconds showing `Open on the tablet (new)`, the update-notice line `Updated … The console was
  relaunched with its new code.`, the update lines at the top of the log tail, and the server
  Running. `ls /tmp/cd-a/logs/console-update.json` → no such file. Only one console window exists.
- [ ] **AC6** (R19, R20) `[mac]` — In `/tmp/cd-b`, change `"version"` in `overlay/package.json` to
  `0.1.1`, push; press Update: the step `Installing console packages` runs `npm install --no-save`
  with output, then the console relaunches as in AC5. `git -C /tmp/cd-a status` shows a clean tree
  (the lockfile was not rewritten).
- [ ] **AC7** (R9, R10, R16) `[mac]` — Make a local commit in `/tmp/cd-a` (any file) and a different
  one in `/tmp/cd-b`, push from `/tmp/cd-b`; press Update: git's "Not possible to fast-forward" text
  shows in the tail, the notice is the red `Update failed: git pull did not succeed…`, the server is
  Running again on the old commit, the window does not close, and `git -C /tmp/cd-a log -1` still
  shows your local commit (nothing reset). Then `git -C /tmp/cd-a reset --hard origin/<branch>` by
  hand to continue.
- [ ] **AC8** (R27, R12, R13, R5, R16) `[mac]` — Quit the console, `mv /tmp/cd-a/.venv
  /tmp/cd-venv-backup`, start it again: the state is `Python environment not found` with `Press Update
  to create it.`; press Update: steps `Creating the Python environment` (`python3 -m venv .venv`) and
  `Installing Python packages` run, the notice starts with `Python environment created.`, and the
  server ends Running.
- [ ] **AC9** (R5, R16) `[mac]` — Press Stop, then Update: the update runs and the server stays
  `Stopped` at the end.
- [ ] **AC10** (R2, R30) `[mac]` — Push a commit that adds a slow step (e.g. AC3's requirements
  change) and press Update; while it runs, Start/Stop/Restart/Update are disabled; close the console
  window: it stays open and the notice says `Wait for the update to finish…`; after the update the
  window closes normally.
- [ ] **AC11** (R6, R7, R16) `[mac]` — Quit the console; in `/tmp/cd-a` run `.venv/bin/python
  server.py --dry-run` in a terminal; start the console (Attached); press Update: the terminal server
  stops ("Server stopped, all buttons released."), the update runs, and the console ends `Running`
  (managed, log label "Server output").
- [ ] **AC12** (R3) `[mac]` — In the overlay window's devtools, `window.consoleApi` is undefined;
  `overlay/preload.js` is unchanged.
- [ ] **AC13** (R4) `[mac]` — Start the console with git hidden from PATH (`PATH=$(dirname $(which
  node)) npm run start:dry` in `/tmp/cd-a/overlay`; the venv python is used by full path); press
  Update: the red `Update failed: git is not installed or not on PATH. Nothing was changed.` and the
  server was never stopped (Uptime keeps counting). Skip this check when `node` and `git` live in the
  same folder (e.g. both in Homebrew's `bin`).
- [ ] **AC14** (R31) `[pc]` — First install of E1.2 on the PC (the E1.1 console has no Update
  button): close the console, run `git pull` (or `run.bat` once, then close it), double-click
  `console.bat`. Then press **Update**: `Already up to date (commit …)`, Input `vjoy`, the log shows
  "vJoy device 1: all buttons reset." after `---- server ----`; no Python console window appears;
  `git status` in `C:\cab-deck` is clean.
- [ ] **AC15** (R6, R16) `[pc]` — On the tablet, hold the horn and press Update in the console while
  holding: the horn stops in the game, the log shows "Server stopped, all buttons released.", the
  tablet reconnects by itself after the update, and buttons work again; "Monitor vJoy" shows no
  button lit during the update.
- [ ] **AC16** (R17, R20) `[pc]` — After the next merge that changes `overlay/` JS or HTML (not the
  packages), press Update with ATS running: the console window closes and one console reopens within
  a few seconds with the new code; the overlay reappears over ATS; the server is Running; Task
  Manager shows one Cab Deck Console (Electron) and one `python.exe` of Cab Deck.
- [ ] **AC17** (R18, R21, R22) `[pc]` — After the next merge that changes `overlay/package.json` (the
  conductor bumps its `version` in a small follow-up for exactly this check), press Update: the
  console closes, a window "Cab Deck Console update" shows `Waiting for the old console to close...`,
  `Installing the console's packages...` and npm's output, then the console opens with the update
  notice and the update lines; the server is Running; exactly one console exists; `git status` is
  clean.
- [ ] **AC18** (R12) `[pc]` — Rename `C:\cab-deck\.venv` to `.venv-old`, start the console, press
  Update: the venv is created with `py -3` (the log shows `[update] $ py -3 -m venv .venv`), pip
  installs, the server starts in vJoy mode. Delete `.venv-old` afterwards.

## Risks and edge cases

- **Can a vJoy button stay pressed?**
  - *During an update:* the first step that touches anything is E1.1's graceful stop (R6): the
    shutdown route, WebSocket disconnects release held buttons, the lifespan's `release_all` runs. The
    server stays stopped while git/pip/npm run, so nothing can be pressed then.
  - *Stop needed a kill (E1.1 R12):* on Windows TerminateProcess skips cleanup, so a button pressed at
    that instant can stay down in the vJoy driver. The update continues; the E1.1 warning is in the
    tail; the next server start resets every button (E1.1 R5) — on every path: R16 starts it, R17/R18/R19
    relaunch a console that starts it (R20). The only path where the server does not start again is
    "venv creation failed" (R14) and "was stopped before" (R5 "no"); in the first, a stuck button
    stays until the owner fixes Python and presses Start; the R14 notice and the E1.1 kill warning
    are both visible.
  - *Relaunch / handover:* the server is already stopped gracefully before the old console exits;
    during the handover's npm install (one or two minutes) the panel shows disconnected and nothing is
    pressed. The new console's server start resets the buttons.
  - *Console crash in the middle of an update:* the server is stopped (or was never stopped, if the
    crash is in `checking`); nothing is pressed. On the next console start the server is started.
  - *Disconnect / page hide:* unchanged.
- **Windows kill skips cleanup (for the update's own commands):** a timed-out `git pull` killed with
  TerminateProcess can leave `.git/index.lock` (and orphan `git-remote-https`); the next update then
  fails with git's "index.lock exists" text in the tail. The console never deletes it (R10 spirit:
  no forced repair); the README tells the owner to delete it when no git runs. A killed pip can leave
  a half-installed package; the next pip run repairs it; if the server cannot start, the state shows
  `Crashed (exit 1)` with the traceback. 60 s for a pull is generous on home broadband.
- **Two consoles or none:** R17/R19 relaunch only after `releaseSingleInstanceLock()` and Electron
  starts the new process after the old one exits. R18: `console.bat` installs only after the old PID
  is gone and starts the console after the install; if the owner double-clicks `console.bat` while
  the update window installs, a second npm/Electron may start: the update window says what it is
  doing; worst case, the single-instance lock keeps one console. "None": if the new code does not
  start (a bug in a merged `main.js`), R17 leaves no window; the owner runs `console.bat`, whose
  window shows Electron's error. R18/R21 keep the window open on any failure.
- **Electron files locked on Windows:** the reason for R18. Electron's GPU/renderer helpers exit with
  the main process; the 2 s extra wait covers their teardown. If the wait still is not enough, npm
  reports `EBUSY`/`EPERM`, R21 still tries to start the console (old files may still be complete),
  and the message says to run `console.bat` again.
- **Lockfile rewritten on the PC:** `npm install` without `--no-save` can rewrite
  `overlay/package-lock.json`, which then blocks `git pull --ff-only` when upstream changes it. R31
  and the R19/R21 commands use `--no-save`. An existing dirty lockfile from an earlier E1.1 install
  makes the pull fail with git's message; the owner restores it with `git checkout --
  overlay/package-lock.json` by hand (the console never does).
- **Local changes or diverged branch:** `--ff-only` refuses; R9 restarts the server on the unchanged
  code; R10 forbids any automatic repair.
- **Wrong Python on Windows:** `py -3` picks the newest installed Python 3; if it is older than 3.10,
  pip or the server fails and the tail shows why. A Store-alias `python` fails venv creation (R14).
- **Who on the LAN can reach the new surface?** Nobody: Update is an IPC call from the local console
  page only (R3), which has a strict CSP and no network access; no HTTP route was added. What Update
  runs is the code of the tracked branch on GitHub, the same trust as `run.bat` today.
- **Server not running / port taken:** Update from `stopped`/`crashed` does not start it (R5); a port
  taken after the update gives `Crashed (exit 1)` as in E1.1.
- **Concurrency:** one operation at a time (R2); the health poll keeps running and only reports. No
  change on the server's asyncio loop. The page cannot start a second update while one runs.
- **Gaming-PC check, step by step:** AC14 (first install, then Update with nothing new), AC15 (horn
  held during Update), AC18 (venv from scratch), then AC16 and AC17 when the next console-code and
  package changes are merged. After each: Task Manager shows one console and one `python.exe`, and
  `git status` is clean.

## Open questions

Resolved 2026-10-19 by the main session (Autonomy B): Q1–Q5 take their defaults.

- **Q1** — The sequence stops the server before `git pull` even when nothing is new, so "Already up
  to date" costs a server restart (the tablet reconnects; a held button is released). An alternative
  is `git fetch` first and stop only when `HEAD` differs from `@{u}` or the venv is missing.
  *Default:* keep the conductor's sequence (simpler, one code path, and pip never runs against a live
  server); revisit if the owner presses Update while driving.
- **Q2** — After a relaunch the new console always starts the server (R20), even if it was stopped
  before the update. *Default:* accept; it matches "the console starts the server when it opens" and
  avoids a new command-line flag.
- **Q3** — From `unavailable`, Update ends by starting the server (R5) although it was not running.
  *Default:* yes; `unavailable` means the owner wanted it running and could not.
- **Q4** — Closing the console is refused during an update (R30), at worst for the pip limit (5 min).
  *Default:* refuse; killing git or pip mid-way is worse (index.lock, half-installed packages).
- **Q5** — No confirmation dialog before Update, even with the game running. *Default:* none; the
  owner presses it on purpose, and the stop is graceful.
