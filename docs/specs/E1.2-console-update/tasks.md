# E1.2 — Tasks

Ordered. Each task is small enough to commit on its own and names the requirement IDs it serves.
Demo mode: no test tasks; acceptance is the checklist in `spec.md`.

Allowed paths in this spec: overlay side = `overlay/` (not `node_modules/`), `overlay.bat`, plus
**`console.bat`** and **`README.md`** for this spec only. No new npm or Python dependency.

## Server

None (`touches: [overlay]`).

## Overlay

- [ ] **O1** (R2, R25, R27) — `overlay/server-control.js`: export the lock as `runExclusive(fn)` and
  unlocked start/stop for use inside it; add `appendLog(lines)`; the `update` snapshot block
  (`running, step, from, to, notice, result`) with setters that emit `change`; log `source` value
  `"update"`; `spawnServer()` and `attach()` after an update append `---- server ----` instead of
  clearing, and `pollLogs()` replaces only the lines after that marker; change `NO_PYTHON` to "Python
  environment not found. Press Update to create it."
- [ ] **O2** (R4, R8, R10, R11, R24, R28, R29) — New `overlay/updater.js`, step runner: spawn with
  an argument array, no shell, `windowsHide`, `stdio` ignore/pipe/pipe, cwd and env per the contract;
  stream stdout/stderr lines into the log ring; the `[update] $ …`, `[update] done in N s` and
  `[update] ERROR: …` lines; per-step timeout with kill (SIGTERM then SIGKILL after 2 s on macOS);
  `ENOENT` reported distinctly. Git steps: `rev-parse HEAD`, `pull --ff-only` with
  `GIT_TERMINAL_PROMPT=0`, `rev-parse HEAD`, `diff --name-only old new` (diff failure = treat
  `requirements.txt` and `overlay/package-lock.json` as changed). No other git command.
- [ ] **O3** (R5, R6, R7, R9, R12, R13, R14, R15, R16, R19, R23, R26) — `overlay/updater.js`,
  `runUpdate()` inside `runExclusive`: record "must run" from the state; stop through the E1.1 stop
  sequence (cancel on an attached server that does not stop); pull and its failure paths; venv
  creation (`py -3` then `python` on `ENOENT` on Windows, `python3` on macOS) and pip with
  `--progress-bar off`; the macOS npm step with `--no-save`; restore the server when there is no
  relaunch; set `step`, `from`, `to` as it goes and exactly one notice from the notice table at the
  end; return `{ action: "none" | "relaunch" | "handover" }` from the R17/R18/R19 rules.
- [ ] **O4** (R22) — `overlay/updater.js`: write `logs/console-update.json` (create `logs/` if
  missing; `version` 1, `writtenAt`, `from`, `to`, `result`, `notice`, last 200 update lines) before a
  relaunch or handover; `consumeResultFile()` reads it at start, applies the 10-minute and version
  rules, puts its notice into the `update` block and its lines into the log ring, and deletes it.
- [ ] **O5** (R3, R17, R18, R20, R30) — `overlay/main.js`: `ipcMain.handle("console:update")` with
  `fromConsole`; call `consumeResultFile()` before `serverControl.init()`; on `relaunch`:
  `releaseSingleInstanceLock()`, `app.relaunch({ execPath: process.execPath, args:
  [app.getAppPath(), …--dry-run] })`, `app.exit(0)`; on `handover` (Windows only): show the handover
  notice, `releaseSingleInstanceLock()`, spawn `cmd.exe /d /s /c ""<repo>\console.bat" update <pid>[
  dry]"` detached, visible, `windowsVerbatimArguments`, `unref()`, `app.exit(0)`; on spawn failure
  show the error notice and restore the server. While an update runs, prevent the console window's
  `close` and `before-quit` and set the R30 notice.
- [ ] **O6** (R1, R2, R3, R23, R26) — `overlay/console-preload.js`: add `update` to `consoleApi`
  (nothing else). `overlay/console.html`: **Update** button after Restart enabled per R1; all four
  process buttons disabled while `update.running`; the amber `Updating: <label>` badge with the
  commits; the update-notice line coloured by `result`; log label "Update output"; `[update]` lines
  dim.
- [ ] **O7** (R21, R31) — `console.bat`: the `update <pid> [dry]` mode per the contract (title, wait
  for the Electron PID with `tasklist`, 2 s grace, `npm install --no-save --no-audit --no-fund`,
  start anyway on failure, `npm run start:dry` with `dry`, `pause` on a failed start); normal mode and
  `overlay.bat` install with `--no-save`.
- [ ] **O8** (R32) — `README.md`, section "Консоль" (Ukrainian): the **Update** button — steps in
  order, never discards local changes, the console may close and reopen (on Windows a separate
  window installs the console's packages first), what to do when git pull fails (local changes,
  `index.lock`, a dirty `overlay/package-lock.json`), and that the R10 message now says to press
  Update.
