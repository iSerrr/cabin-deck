# CLAUDE.md — Cab Deck

> This file overrides the parent `sandbox/CLAUDE.md` (transcription tool) for
> everything inside `cabin_deck/`. AssemblyAI rules do not apply here.
> For **what** to build, read `PRD.md`. If the two conflict, ask first.

## Project in one line
A tablet web panel that presses vJoy virtual joystick buttons on a Windows PC
so American Truck Simulator (or ETS2) sees them as a separate game controller.

## How to behave
- `PRD.md` is the source of truth for scope. Build the smallest thing that
  satisfies it. No features, dependencies, or modules outside `PRD.md`
  without asking first.
- When `PRD.md` is ambiguous, ask one focused question instead of guessing.
- Keep the project runnable at every step.
- After changes, explain in plain language what changed and how to run it.

## Hard constraints
- The client sends only a button ID and `down`/`up`. The server never accepts
  a raw button number or key from the client.
- Button IDs are `cab_deck_btn_NNN`; `NNN` is the vJoy button number.
- No button may stay pressed after disconnect, page hide, or server shutdown.
- LAN only. No auth, HTTPS, database, or build step in the pilot.

## Environment
- Development happens on macOS: always support `--dry-run` (no vJoy, logs only).
- Real input is tested on the Windows gaming PC with vJoy installed.

## Tech stack
- Python 3.10+, FastAPI + uvicorn, `pyvjoy` (Windows only, imported lazily).
- Panel: a single `static/index.html` with plain HTML/CSS/JS.
- Dash: `dash/index.html` (v1) and `dash/v2.html` (v2, WebGL2) on ports 8701/8702.
- Overlay: `overlay/` is an Electron app (Node 18+) that shows dash v2 over the game.

## Code conventions
- Small single-purpose functions with type hints.
- Explicit error handling with helpful messages. No bare `except`.
- Plain functions over classes until the pilot works.
- Comments and identifiers in English.

## Commands
- Install: `pip install -r requirements.txt`
- Run: `python server.py` (Windows) or `python server.py --dry-run` (macOS)
- Spike: `python spike_vjoy.py 1` (Windows, ATS or ETS2 running)
- Gates: `scripts/gates [server|overlay]` (see "Sides and gates")
- Worktree bootstrap: `scripts/worktree-init [server|overlay]`

## Documents

| Path | What |
| --- | --- |
| `PRD.md` | Product source of truth (Ukrainian). Specs extend it; it wins on scope |
| `docs/architecture.md` | Components, processes, ports, decisions. **Read before planning anything** |
| `docs/backlog.md` | Epics with IDs (`E1.1`) and `depends_on`. Every spec starts from one |
| `docs/specs/` | One folder per unit of work (level L) |
| `docs/decisions/` | ADRs, when a spec needs an architectural decision |
| `docs/status.md` | What is done, in flight, next, and known failures |
| [`docs/templates/`](docs/templates/) | Spec, tasks and state templates |

## Sides and gates

A side is a set of paths one developer agent owns in a delivery. Docs (`PRD.md`, `README.md`,
`docs/`) belong to the main session and the architect.

| Side | Paths | Gates |
| --- | --- | --- |
| `server` | `server.py`, `config.json`, `requirements.txt`, `static/`, `dash/`, `spike_*.py`, `run.bat` | `scripts/gates server`: py_compile, then a `--dry-run` start whose `/api/health` must answer ok |
| `overlay` | `overlay/` (not `node_modules/`), `overlay.bat` | `scripts/gates overlay`: `node --check` of every `overlay/*.js`, `package.json` parses |

There is no test suite and no CI in the pilot: the gates are the check, and whatever needs vJoy, the
game or Windows is checked by the owner on the gaming PC from steps written in the PR.

## Levels

Every development task enters through the level router
([`.claude/levels/router.md`](.claude/levels/router.md)) before anything is touched: the main session
says the level and follows its protocol.

- `level-s@1` ([`.claude/levels/s/protocol.md`](.claude/levels/s/protocol.md)): the main session
  alone, 1–3 files.
- `level-m@1` ([`.claude/levels/m/protocol.md`](.claude/levels/m/protocol.md)): one side, one
  `executor` in a worktree, the main session checks.
- `level-l@1` ([`.claude/levels/l/protocol.md`](.claude/levels/l/protocol.md)): one spec per stage
  through `/spec` and `/deliver`, `executor` per side, `reviewer` per side.

For the router, Cab Deck's risk areas (question 2, always L) are: anything that **controls the PC**
(starting or stopping processes, `git`, writing files outside `logs/`), anything reachable **from the
LAN** that was not before, and the **button release guarantees** in "Hard constraints". `/spec` and
`/deliver` invoked directly run as before. How levels are versioned and extended:
[`.claude/levels/README.md`](.claude/levels/README.md).

### Ship

After a merge, levels run the ship module ([`.claude/levels/shared/ship.md`](.claude/levels/shared/ship.md)).

- Deploy workflow: `none`
- Stage URL: `none`

There is no pipeline: the gaming PC takes `main` itself (today `run.bat`, which runs `git pull`). Ship
ends at the merge, and the report gives the owner the steps to run on the PC.

## How work flows

1. **Spec.** `/spec <id>`: the `architect` turns a backlog epic into `docs/specs/<id>-<slug>/` and
   opens a spec PR (`spec/<id>-<slug>`) with `status: draft`.
2. **Approval (gate one).** The owner sets `status: approved` and merges.
3. **Delivery.** `/deliver <id>` runs [`.claude/workflows/deliver.js`](.claude/workflows/deliver.js):
   one `executor` per side, each in its own worktree, against the spec's contract; each side passes
   its gates, then the `reviewer` reviews it, with fix rounds.
4. **Pull request (gate two).** One PR per spec (`feat/<id>-<slug>`) with `review.md` and the owner's
   steps for the PC. The owner merges.

A **change** (bug fix, copy, small contained fix) skips the spec but still goes through a branch, its
side's gates and a PR. The **main session** is the conductor: outside level S it never writes product
code itself. It never ends a turn "waiting" without something that will wake it.

### Agent roles and boundaries

| Agent | Writes to | Never |
| --- | --- | --- |
| `architect` | `docs/` | code |
| `executor` | its side's paths, its spec's `state-<side>.md`; at level M, the places its brief lists | another side, the spec itself, new dependencies unless the spec names them |
| `reviewer` | nothing (returns its report) | any file |

Agents never change a spec's requirements or contract. They record disagreement in `state-*.md` and
stop.

## Git

- `main` only moves through merged PRs. Agents never push to `main`, merge, rebase shared branches
  or force-push.
- Branches: `feat/<id>-<slug>` for a spec (sides on `feat/<id>-server` and `feat/<id>-overlay`),
  `spec/<id>-<slug>`, `fix/<slug>`, `chore/<slug>`.
- Commits are Conventional: imperative, lowercase subject, no trailing period, max 100 characters,
  scoped by side when useful (`feat(server): …`). End every commit message with the
  `Co-Authored-By` line from the session's attribution.
- Never commit secrets: the `block-secrets` hook ([`.claude/settings.json`](.claude/settings.json))
  refuses a commit or push that looks like it holds one.

## Mode

- **Owner-gated** (2026-10-19): the owner approves specs and merges PRs.
- **Demo mode** (pilot, until the owner lifts it): no new tests and no test framework; gates run once
  before reporting done; one review round is the norm (`maxFixRounds: 1`); acceptance is a checklist
  marked `[mac]` (dry-run) or `[pc]` (gaming PC).

## Orchestration canon

This project's agent setup comes from the canon repository
`https://github.com/iSerrr/agent-orchestration`, at the version pinned in
[`.claude/orchestration-version`](.claude/orchestration-version). Adapted here: one `executor` for
both sides instead of `backend-dev` / `frontend-dev`, sides `server` / `overlay`, `scripts/gates`,
no CI, no stage, no design tool, no usage report. The level protocols under `.claude/levels/` are
kept verbatim.

- `/orchestration-sync pull` shows what changed in the canon since the pinned version and applies it
  on a `chore/orchestration-sync-<version>` branch with a PR.
- A lesson about the approach (not product code) goes back to the canon with
  `/orchestration-sync push`.

## Language

The owner reads chat in **Ukrainian**. Everything in the repository is **English** (code, comments,
specs, state files, reviews, commits, PRs), except `PRD.md` and `README.md`, which stay Ukrainian.
Agents return their reports in English; only the main session speaks Ukrainian.
