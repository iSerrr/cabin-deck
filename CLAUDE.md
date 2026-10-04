# CLAUDE.md — Cab Deck

> This file overrides the parent `sandbox/CLAUDE.md` (transcription tool) for
> everything inside `cabin_deck/`. AssemblyAI rules do not apply here.
> For **what** to build, read `PRD.md`. If the two conflict, ask first.

## Project in one line
A tablet web panel that presses vJoy virtual joystick buttons on a Windows PC
so Euro Truck Simulator 2 sees them as a separate game controller.

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

## Code conventions
- Small single-purpose functions with type hints.
- Explicit error handling with helpful messages. No bare `except`.
- Plain functions over classes until the pilot works.
- Comments and identifiers in English.

## Commands
- Install: `pip install -r requirements.txt`
- Run: `python server.py` (Windows) or `python server.py --dry-run` (macOS)
- Spike: `python spike_vjoy.py 1` (Windows, ETS2 running)
