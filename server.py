"""Cab Deck server: serves the tablet panel and presses vJoy buttons.

Run on Windows:  python server.py
Run on macOS:    python server.py --dry-run
"""

import argparse
import asyncio
import json
import logging
import re
import socket
import subprocess
import sys
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, AsyncIterator, Callable

import uvicorn
from fastapi import FastAPI, Query, WebSocket
from fastapi.responses import FileResponse, PlainTextResponse

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.json"
INDEX_PATH = BASE_DIR / "static" / "index.html"
LOG_PATH = BASE_DIR / "logs" / "cab_deck.log"
DEFAULT_PORT = 8000

BUTTON_ID_PATTERN = re.compile(r"^cab_deck_btn_(\d{3})$")
BUTTON_TYPES = ("tap", "hold")
MAX_LOGGED_TEXT = 500
MAX_LOG_LINES = 1000

log = logging.getLogger("cab_deck")

SetButton = Callable[[int, bool], None]


class ConfigError(Exception):
    """Raised when config.json is missing or invalid."""


class InputError(Exception):
    """Raised when the vJoy device cannot be opened."""


class LastErrorHandler(logging.Handler):
    """Remembers the most recent ERROR record for /api/health."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.last: str | None = None

    def emit(self, record: logging.LogRecord) -> None:
        self.last = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {record.getMessage()}"[:MAX_LOGGED_TEXT]


@dataclass
class DeckState:
    config: dict[str, Any]
    set_button: SetButton
    input_mode: str
    vjoy_buttons: int | None
    commit: str
    errors: LastErrorHandler
    started_at: float = field(default_factory=time.monotonic)
    pressed: set[int] = field(default_factory=set)
    release_tasks: dict[int, asyncio.Task] = field(default_factory=dict)
    clients: int = 0

    @property
    def buttons_by_id(self) -> dict[str, dict[str, Any]]:
        return self.config["buttons_by_id"]


# --- Logging -----------------------------------------------------------------


def setup_logging() -> LastErrorHandler:
    LOG_PATH.parent.mkdir(exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    errors = LastErrorHandler()

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in (file_handler, console_handler, errors):
        root.addHandler(handler)
    return errors


def tail_log(count: int) -> str:
    try:
        with LOG_PATH.open(encoding="utf-8", errors="replace") as log_file:
            return "".join(deque(log_file, maxlen=count))
    except FileNotFoundError:
        return ""


# --- Config ------------------------------------------------------------------


def load_config(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"Config file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path.name} is not valid JSON: {error}") from error
    return validate_config(raw)


def validate_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a JSON object.")

    problems: list[str] = []
    config: dict[str, Any] = {
        "vjoy_device": raw.get("vjoy_device", 1),
        "tap_ms": raw.get("tap_ms", 80),
        "hold_timeout_s": raw.get("hold_timeout_s", 10),
        "grid": raw.get("grid", {}),
    }

    if not _is_int_in(config["vjoy_device"], 1, 16):
        problems.append("vjoy_device must be an integer from 1 to 16.")
    if not _is_int_in(config["tap_ms"], 10, 1000):
        problems.append("tap_ms must be an integer from 10 to 1000.")
    if not isinstance(config["hold_timeout_s"], (int, float)) or not 0 < config["hold_timeout_s"] <= 120:
        problems.append("hold_timeout_s must be a number from 0 to 120.")

    grid = config["grid"]
    if not isinstance(grid, dict) or not _is_int_in(grid.get("cols"), 1, 12) or not _is_int_in(grid.get("rows"), 1, 12):
        problems.append('grid must look like {"cols": 4, "rows": 3}.')

    buttons = raw.get("buttons")
    if not isinstance(buttons, list) or not buttons:
        problems.append("buttons must be a non-empty list.")
        buttons = []

    buttons_by_id: dict[str, dict[str, Any]] = {}
    for index, button in enumerate(buttons, start=1):
        where = f"buttons[{index}]"
        if not isinstance(button, dict):
            problems.append(f"{where} must be an object.")
            continue
        button_id = button.get("id")
        match = BUTTON_ID_PATTERN.match(button_id) if isinstance(button_id, str) else None
        if match is None:
            problems.append(f"{where}: id {button_id!r} must look like cab_deck_btn_001.")
            continue
        number = int(match.group(1))
        if number < 1:
            problems.append(f"{where}: {button_id} maps to vJoy button 0, numbering starts at 001.")
        if button_id in buttons_by_id:
            problems.append(f"{where}: duplicate id {button_id}.")
        if button.get("type") not in BUTTON_TYPES:
            problems.append(f"{where}: type must be one of {BUTTON_TYPES}.")
        if not isinstance(button.get("label"), str) or not button["label"].strip():
            problems.append(f"{where}: label must be a non-empty string.")
        buttons_by_id[button_id] = {
            "id": button_id,
            "number": number,
            "type": button.get("type"),
            "label": button.get("label", ""),
            "icon": button.get("icon", ""),
            "color": button.get("color", "#8b949e"),
        }

    if isinstance(grid, dict) and _is_int_in(grid.get("cols"), 1, 12) and _is_int_in(grid.get("rows"), 1, 12):
        if len(buttons_by_id) > grid["cols"] * grid["rows"]:
            problems.append(f"{len(buttons_by_id)} buttons do not fit into a {grid['cols']}x{grid['rows']} grid.")

    if problems:
        raise ConfigError("Invalid config.json:\n  - " + "\n  - ".join(problems))

    config["buttons_by_id"] = buttons_by_id
    return config


def check_button_range(config: dict[str, Any], vjoy_buttons: int | None) -> None:
    if vjoy_buttons is None:
        return
    too_high = [b["id"] for b in config["buttons_by_id"].values() if b["number"] > vjoy_buttons]
    if too_high:
        raise ConfigError(
            f"vJoy device has only {vjoy_buttons} buttons, but config uses {', '.join(too_high)}. "
            "Raise 'Number of Buttons' in Configure vJoy."
        )


def _is_int_in(value: Any, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


# --- Input backends ----------------------------------------------------------


def open_dry_run() -> tuple[SetButton, int | None]:
    def set_button(number: int, pressed: bool) -> None:
        log.info("[dry-run] vJoy button %d %s", number, "DOWN" if pressed else "UP")

    return set_button, None


def open_vjoy(device_id: int) -> tuple[SetButton, int | None]:
    try:
        import pyvjoy
        from pyvjoy.exceptions import vJoyException
    except ImportError as error:
        raise InputError("pyvjoy is not available. It works only on Windows; use --dry-run elsewhere.") from error

    try:
        device = pyvjoy.VJoyDevice(device_id)
    except vJoyException as error:
        raise InputError(
            f"Cannot open vJoy device {device_id}: {error!r}. Check that vJoy is installed, the device is "
            "enabled in 'Configure vJoy', and vJoyInterface.dll matches the driver version."
        ) from error

    def set_button(number: int, pressed: bool) -> None:
        try:
            device.set_button(number, 1 if pressed else 0)
        except vJoyException as error:
            log.error("vJoy failed to set button %d to %s: %r", number, pressed, error)

    return set_button, read_vjoy_button_count(device_id)


def read_vjoy_button_count(device_id: int) -> int | None:
    try:
        from pyvjoy import _sdk

        count = _sdk._vj.GetVJDButtonNumber(device_id)
    except (ImportError, AttributeError, OSError) as error:
        log.warning("Cannot read vJoy button count, skipping range check: %r", error)
        return None
    return int(count) if count > 0 else None


# --- Button state ------------------------------------------------------------


def press(state: DeckState, number: int) -> None:
    if number not in state.pressed:
        state.set_button(number, True)
        state.pressed.add(number)


def release(state: DeckState, number: int) -> None:
    task = state.release_tasks.pop(number, None)
    if task is not None and task is not asyncio.current_task():
        task.cancel()
    if number in state.pressed:
        state.set_button(number, False)
        state.pressed.discard(number)


def release_all(state: DeckState) -> None:
    for number in list(state.pressed):
        release(state, number)


def schedule_release(state: DeckState, number: int, delay_s: float, warn: str | None = None) -> None:
    previous = state.release_tasks.pop(number, None)
    if previous is not None:
        previous.cancel()
    state.release_tasks[number] = asyncio.create_task(_release_later(state, number, delay_s, warn))


async def _release_later(state: DeckState, number: int, delay_s: float, warn: str | None) -> None:
    await asyncio.sleep(delay_s)
    state.release_tasks.pop(number, None)
    if warn and number in state.pressed:
        log.warning(warn)
    release(state, number)


# --- Protocol ----------------------------------------------------------------


def layout_message(config: dict[str, Any]) -> dict[str, Any]:
    buttons = [
        {key: button[key] for key in ("id", "label", "icon", "color", "type")}
        for button in config["buttons_by_id"].values()
    ]
    return {"type": "layout", "grid": config["grid"], "buttons": buttons}


def handle_message(state: DeckState, text: str, held: set[int]) -> dict[str, Any] | None:
    """Apply one client message. Returns a reply to send back, if any."""
    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Ignored non-JSON message: %s", text[:MAX_LOGGED_TEXT])
        return None
    if not isinstance(message, dict):
        log.warning("Ignored message that is not an object: %s", text[:MAX_LOGGED_TEXT])
        return None

    message_type = message.get("type")
    if message_type == "ping":
        return {"type": "pong"}
    if message_type == "client_error":
        log.error("Panel error: %s", str(message.get("message", ""))[:MAX_LOGGED_TEXT])
        return None

    button = state.buttons_by_id.get(message.get("id"))
    event = message.get("event")
    if button is None or event not in ("down", "up"):
        log.warning("Ignored unknown command: %s", text[:MAX_LOGGED_TEXT])
        return None

    log.info("%s %s (%s, %s)", button["id"], event, button["label"], button["type"])
    number = button["number"]

    if button["type"] == "tap":
        if event == "down":
            press(state, number)
            schedule_release(state, number, state.config["tap_ms"] / 1000)
    elif event == "down":
        press(state, number)
        held.add(number)
        timeout = state.config["hold_timeout_s"]
        schedule_release(state, number, timeout, f"{button['id']} released by hold timeout ({timeout}s)")
    else:
        release(state, number)
        held.discard(number)
    return None


# --- Web app -----------------------------------------------------------------


def create_app(state: DeckState) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        release_all(state)
        log.info("Server stopped, all buttons released.")

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(INDEX_PATH, headers={"Cache-Control": "no-store"})

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "input": state.input_mode,
            "vjoy_device": state.config["vjoy_device"],
            "vjoy_buttons": state.vjoy_buttons,
            "config_buttons": len(state.buttons_by_id),
            "pressed": sorted(state.pressed),
            "clients": state.clients,
            "commit": state.commit,
            "uptime_s": round(time.monotonic() - state.started_at),
            "last_error": state.errors.last,
        }

    @app.get("/api/logs")
    async def logs(lines: int = Query(200, ge=1, le=MAX_LOG_LINES)) -> PlainTextResponse:
        return PlainTextResponse(tail_log(lines))

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        client = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
        state.clients += 1
        held: set[int] = set()
        log.info("Panel connected: %s (clients: %d)", client, state.clients)
        try:
            await websocket.send_json(layout_message(state.config))
            while True:
                incoming = await websocket.receive()
                if incoming["type"] == "websocket.disconnect":
                    break
                text = incoming.get("text")
                if text is None:
                    log.warning("Ignored binary message from %s", client)
                    continue
                reply = handle_message(state, text, held)
                if reply is not None:
                    await websocket.send_json(reply)
        finally:
            state.clients -= 1
            still_pressed = sorted(number for number in held if number in state.pressed)
            for number in still_pressed:
                release(state, number)
            log.info("Panel disconnected: %s, released %s (clients: %d)", client, still_pressed or "nothing", state.clients)

    return app


# --- Startup -----------------------------------------------------------------


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=BASE_DIR, capture_output=True, text=True, timeout=5, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def local_ipv4_addresses() -> list[str]:
    addresses: list[str] = []
    primary = _primary_ipv4()
    if primary:
        addresses.append(primary)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in addresses and not address.startswith("127."):
                addresses.append(address)
    except socket.gaierror as error:
        log.warning("Cannot list local addresses: %r", error)
    return addresses


def _primary_ipv4() -> str | None:
    # Connecting a UDP socket sends nothing; it only picks the outgoing interface.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("10.255.255.255", 1))
            return probe.getsockname()[0]
        except OSError:
            return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cab Deck tablet panel server.")
    parser.add_argument("--dry-run", action="store_true", help="log button presses instead of using vJoy")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    errors = setup_logging()
    commit = git_commit()
    log.info("Starting Cab Deck (commit %s, %s)", commit, "dry-run" if args.dry_run else "vJoy")

    try:
        config = load_config(args.config)
        if args.dry_run:
            set_button, vjoy_buttons = open_dry_run()
        else:
            set_button, vjoy_buttons = open_vjoy(config["vjoy_device"])
        check_button_range(config, vjoy_buttons)
    except (ConfigError, InputError) as error:
        log.error("Startup failed: %s", error)
        sys.exit(1)

    state = DeckState(
        config=config,
        set_button=set_button,
        input_mode="dry-run" if args.dry_run else "vjoy",
        vjoy_buttons=vjoy_buttons,
        commit=commit,
        errors=errors,
    )

    log.info("Loaded %d buttons. vJoy buttons available: %s", len(state.buttons_by_id), vjoy_buttons or "unknown")
    addresses = local_ipv4_addresses() or ["<this-pc-ip>"]
    print("\nOpen the panel on the tablet:")
    for address in addresses:
        print(f"  http://{address}:{args.port}")
    print("Press Ctrl+C to stop.\n", flush=True)

    uvicorn.run(create_app(state), host="0.0.0.0", port=args.port, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
