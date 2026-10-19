# E1.2 — Review report

## overlay

**Outcome:** approved  
**Review rounds:** 2  
**Verdict:** approve  
**Score:** 8/10

Round 1 returned `changes` (one major: update log lines lost on the server restart, plus four minors); the fix round addressed all five.

### Gates (reviewer)

- scripts/gates overlay: pass

### Remaining findings

- **minor** `overlay/server-control.js:79` — The `update` block in `console:snapshot` carries a seventh field, `closeRefused`, that is not in the spec's contract. The contract lists exactly `running, step, from, to, notice, result`. The field is internal to the R30 sticky notice, and its text already reaches the page through `notice`. Nothing breaks, but the block no longer matches the contract field by field.
  - Fix: Keep `closeRefused` in a module variable outside `update`, or strip it when building the snapshot: `const { closeRefused, ...pub } = update; ... update: pub`.
- **minor** `overlay/server-control.js:125` — `finishUpdateLog()` returns without changing anything when there is neither a child nor an attached server. After an update ends with the server stopped or unavailable (R5 'no', R9 with no venv, R14), `getLog().source` stays `"update"`, so the tail label keeps saying 'Update output' after the update is over. I reproduced this in a node run: a pull failure from `unavailable` ended with `LOGSRC update` and `running:false`. The contract says the source is `"update"` only while an update runs. The same happens after `consumeResultFile()` when the new console ends up `unavailable`.
  - Fix: In `finishUpdateLog()`, when there is no child and no attached server, append `LOG_MARKER` and set `logSource = "server"`, then `schedulePush()`. The update lines stay, and `resetServerLog` still adds the marker on the next spawn because it checks the old source.
- **minor** `overlay/updater.js:184` — On the relaunch and handover paths with a pip failure, the warning text adds ' The server was started anyway.' only when `mustRun` is true. Per R20, though, the relaunched console always starts the server. When the server was stopped before the update, the carried notice leaves out a sentence that is true after the relaunch. The effect is cosmetic.
  - Fix: In `buildNotice`, append the sentence when `f.mustRun || f.relaunch`.
- **minor** `overlay/updater.js:241` — The catch branch in `runUpdate()` does not restore the server. If `sequence()` throws after `stopUnlocked()` (an unexpected exception between the stop and `end()`), the update ends with the server stopped even when R5 recorded 'must run'. That breaks R16 on this path. I found no throw path today, so this is defensive only.
  - Fix: Record `mustRun`/`canStart` and whether the stop happened in variables visible to the catch, and call `serverControl.startUnlocked()` there when the server must run, before `finishUpdateLog()`/`setUpdate`.

### Deviations

- No new tests were added: the root CLAUDE.md Mode section is Demo mode (no new tests, no test framework).
- Finding 4 on a stopped or unavailable server with no child: the label stays "update", as the finding allowed.

### Reviewer summary

I reviewed feat/E1.2-overlay (round 2) against main on the overlay paths, plus console.bat and README.md, which this spec allows. `scripts/gates overlay` passes (node --check, exit 0). All overlay requirements R1–R32 are implemented.

**What I checked:**
- **Button and lock (R1–R3):** the Update button follows the ENABLED rule and is disabled while probing or while an update runs. The update runs inside the shared `exclusive()` lock, and the main process also ignores start, stop and restart while `update.running` is set. `console:update` is gated by `fromConsole`, and `preload.js` is unchanged.
- **Commands (R4–R16, R24, R28, R29):** git commands are limited to `rev-parse HEAD`, `pull --ff-only` and `diff --name-only`, with `GIT_TERMINAL_PROMPT=0`. Every command is spawned without a shell, with `windowsHide` and the ignore/pipe/pipe stdio. Timeouts use SIGTERM then SIGKILL on macOS and `kill()` on Windows. On Windows venv creation falls back from `py` to `python` on ENOENT. pip and npm use the exact arguments from the contract.
- **Notices:** every notice-table text matches the spec exactly.
- **Relaunch, handover and result file (R17–R22):**
  - The relaunch and handover follow the contract order.
  - The handover spawns cmd with `/d /s /c` and the verbatim quoted line; the command is built only from the repo path and the PID.
  - When the handover spawn fails, the console takes the single-instance lock again and starts the server.
  - The result file is written, then read and validated (version, age, result) before `init()`.
- **R25:** the `---- server ----` marker is added on spawn and on attach after an update, and `pollLogs` keeps the lines above it.
- **R30:** closing the window and quitting are refused while an update runs, with a sticky notice.
- **console.bat (R21):** the update mode waits for the old PID with tasklist, adds the 2 s grace, runs npm install with `--no-save` and starts the console even when the install failed. Both launchers now install with `--no-save` (R31).
- **README (R32):** the Ukrainian Console section covers the Update button.

**Dry run:** I ran `server-control` plus `updater` in plain Node against the detached worktree, which has no `.venv`, so the state was `unavailable`. The steps were checking → pulling → starting. The log tail showed the `[update] $` line, git's output and `[update] ERROR: git failed (exit 1)`. The notice was the exact red pull-failed text, the state ended `unavailable`, and the server was never touched before the pull.

**What only the Windows PC can confirm:** the cmd.exe handover window and its quoting, tasklist matching `electron.exe`, the `py -3` venv, killing a timed-out git with TerminateProcess, horn release during an update (AC15), and AC14–AC18 in general. The full macOS Electron relaunch flows (AC5, AC6, AC10–AC13) also need the click-through on the bench clone.

**Findings:** none are blockers or majors. There are four minors:
- an extra internal `closeRefused` field in the snapshot's `update` block;
- the log label stays 'Update output' when an update ends with no server running;
- the pip-warning wording on the relaunch path;
- the catch path in `runUpdate()` does not start the server again.
