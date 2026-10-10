"""Cab Deck server: serves the tablet panel, presses vJoy buttons and
reports truck state from game telemetry.

Run on Windows:  python server.py
Run on macOS:    python server.py --dry-run
"""

import argparse
import asyncio
import json
import logging
import re
import socket
import struct
import subprocess
import sys
import time
from collections import deque
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, AsyncIterator, Callable

import uvicorn
from fastapi import FastAPI, Query, WebSocket
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.json"
STATIC_DIR = BASE_DIR / "static"
INDEX_PATH = STATIC_DIR / "index.html"
LOG_PATH = BASE_DIR / "logs" / "cab_deck.log"
DEFAULT_PORT = 8000

BUTTON_ID_PATTERN = re.compile(r"^cab_deck_btn_(\d{3})$")
NAMED_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
CONTROL_TYPES = ("tap", "hold", "switch", "gauge")
MAX_LOGGED_TEXT = 500
MAX_LOG_LINES = 1000

# Single press used by the SETUP page to bind a vJoy button in the game menu.
BIND_PRESS_S = 0.15
TELEMETRY_POLL_S = 0.1
TELEMETRY_RETRY_S = 5.0
# Telemetry needs a moment to reflect a press; skip corrections right after one.
SWITCH_SETTLE_S = 1.0

INDICATORS = (
    "engine",
    "lights",
    "high_beam",
    "blinker_left",
    "blinker_right",
    "hazards",
    "park_brake",
    "wipers",
    "trailer",
    "engine_brake",
    "diff_lock",
    "lift_axle",
    "trailer_lift_axle",
    "beacon",
    "aux_front",
    "aux_roof",
    "air_pressure",
    "fuel",
    "nav",
)
GAUGE_INDICATORS = ("air_pressure", "fuel", "nav")
# Switches whose position the game reports exactly (instead of on/off only).
POSITION_SOURCES = ("lights",)

log = logging.getLogger("cab_deck")

SetButton = Callable[[int, bool], None]
TelemetryReader = Callable[[], dict[str, Any] | None]


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
class SwitchState:
    position: int = 0
    target: int = 0
    last_press: float = 0.0
    task: asyncio.Task | None = None

    @property
    def moving(self) -> bool:
        return self.task is not None and not self.task.done()


@dataclass
class DeckState:
    config: dict[str, Any]
    set_button: SetButton
    read_telemetry: TelemetryReader
    input_mode: str
    vjoy_buttons: int | None
    commit: str
    errors: LastErrorHandler
    started_at: float = field(default_factory=time.monotonic)
    pressed: set[int] = field(default_factory=set)
    release_tasks: dict[int, asyncio.Task] = field(default_factory=dict)
    switches: dict[str, SwitchState] = field(default_factory=dict)
    sockets: set[WebSocket] = field(default_factory=set)
    game: dict[str, Any] = field(default_factory=lambda: {"telemetry": False})
    indicators: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_state_message: dict[str, Any] | None = None

    @property
    def controls_by_id(self) -> dict[str, dict[str, Any]]:
        return self.config["controls_by_id"]


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
        "switch_gap_ms": raw.get("switch_gap_ms", 150),
        "hold_timeout_s": raw.get("hold_timeout_s", 10),
    }

    if not _is_int_in(config["vjoy_device"], 1, 16):
        problems.append("vjoy_device must be an integer from 1 to 16.")
    if not _is_int_in(config["tap_ms"], 10, 1000):
        problems.append("tap_ms must be an integer from 10 to 1000.")
    if not _is_int_in(config["switch_gap_ms"], 10, 2000):
        problems.append("switch_gap_ms must be an integer from 10 to 2000.")
    if not isinstance(config["hold_timeout_s"], (int, float)) or not 0 < config["hold_timeout_s"] <= 120:
        problems.append("hold_timeout_s must be a number from 0 to 120.")

    entries = raw.get("controls")
    if not isinstance(entries, list) or not entries:
        problems.append("controls must be a non-empty list.")
        entries = []

    controls_by_id: dict[str, dict[str, Any]] = {}
    used_numbers: dict[int, str] = {}
    for index, entry in enumerate(entries, start=1):
        where = f"controls[{index}]"
        control = _validate_control(entry, where, problems)
        if control is None:
            continue
        if control["id"] in controls_by_id:
            problems.append(f"{where}: duplicate id {control['id']}.")
            continue
        for number in _vjoy_numbers(control):
            if number in used_numbers:
                problems.append(f"{where}: vJoy button {number} is already used by {used_numbers[number]}.")
            used_numbers[number] = control["id"]
        controls_by_id[control["id"]] = control

    if problems:
        raise ConfigError("Invalid config.json:\n  - " + "\n  - ".join(problems))

    config["controls_by_id"] = controls_by_id
    config["bindings"] = build_bindings(controls_by_id)
    return config


def build_bindings(controls_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Every vJoy button the config uses, for the SETUP page. Keyed by button id, never by raw number."""
    bindings: list[dict[str, Any]] = []
    for control in controls_by_id.values():
        if control["type"] == "switch":
            bindings.append(_binding(control["forward"], control["label"], "forward", control["forward_action"]))
            if control["back"] is not None:
                bindings.append(_binding(control["back"], control["label"], "back", control["back_action"]))
        elif control["type"] in ("tap", "hold"):
            bindings.append(_binding(control["number"], control["label"], None, control["action"]))
    return sorted(bindings, key=lambda binding: binding["number"])


def _binding(number: int, label: str, part: str | None, action: str | None) -> dict[str, Any]:
    return {"key": f"cab_deck_btn_{number:03d}", "number": number, "label": label, "part": part, "action": action}


def _validate_control(entry: Any, where: str, problems: list[str]) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        problems.append(f"{where} must be an object.")
        return None

    control_type = entry.get("type")
    if control_type not in CONTROL_TYPES:
        problems.append(f"{where}: type must be one of {CONTROL_TYPES}.")
        return None
    if not isinstance(entry.get("label"), str) or not entry["label"].strip():
        problems.append(f"{where}: label must be a non-empty string.")
    indicator = entry.get("indicator")
    if indicator is not None and indicator not in INDICATORS:
        problems.append(f"{where}: indicator must be one of {INDICATORS}.")

    control: dict[str, Any] = {
        "id": entry.get("id"),
        "type": control_type,
        "label": entry.get("label", ""),
        "indicator": indicator,
    }

    if control_type in ("switch", "gauge"):
        if not isinstance(control["id"], str) or not NAMED_ID_PATTERN.match(control["id"]):
            problems.append(f"{where}: {control_type} id {control['id']!r} must be lowercase letters, digits and _.")
            return None

    if control_type == "gauge":
        low, high = entry.get("min", 0), entry.get("max")
        if indicator not in GAUGE_INDICATORS:
            problems.append(f"{where}: gauge indicator must be one of {GAUGE_INDICATORS}.")
        if not isinstance(low, (int, float)) or not isinstance(high, (int, float)) or low >= high:
            problems.append(f"{where}: gauge needs numeric min < max.")
            return None
        control.update(min=low, max=high)
        return control

    if control_type == "switch":
        position_source = entry.get("position_source")
        if position_source is not None and position_source not in POSITION_SOURCES:
            problems.append(f"{where}: position_source must be one of {POSITION_SOURCES}.")
        control["position_source"] = position_source
        positions = entry.get("positions")
        if (
            not isinstance(positions, list)
            or not 2 <= len(positions) <= 8
            or not all(isinstance(p, str) and p.strip() for p in positions)
        ):
            problems.append(f"{where}: positions must be a list of 2 to 8 non-empty strings.")
            return None
        # A cyclic switch wraps from the last position to the first and only needs "forward".
        cyclic = entry.get("cyclic", False) is True
        forward = _button_number(entry.get("forward"))
        back = None if cyclic else _button_number(entry.get("back"))
        if forward is None or (back is None and not cyclic):
            problems.append(f"{where}: forward (and back, unless cyclic) must be button ids like cab_deck_btn_013.")
            return None
        control.update(
            positions=positions,
            cyclic=cyclic,
            forward=forward,
            back=back,
            forward_action=_optional_text(entry, "forward_action", where, problems),
            back_action=_optional_text(entry, "back_action", where, problems),
        )
        return control

    number = _button_number(control["id"])
    if number is None:
        problems.append(f"{where}: id {control['id']!r} must look like cab_deck_btn_001.")
        return None
    control["number"] = number
    control["action"] = _optional_text(entry, "action", where, problems)
    return control


def _optional_text(entry: dict[str, Any], key: str, where: str, problems: list[str]) -> str | None:
    value = entry.get(key)
    if value is not None and (not isinstance(value, str) or not value.strip()):
        problems.append(f"{where}: {key} must be a non-empty string.")
        return None
    return value


def _button_number(button_id: Any) -> int | None:
    match = BUTTON_ID_PATTERN.match(button_id) if isinstance(button_id, str) else None
    if match is None or int(match.group(1)) < 1:
        return None
    return int(match.group(1))


def _vjoy_numbers(control: dict[str, Any]) -> list[int]:
    if control["type"] == "switch":
        return [n for n in (control["forward"], control["back"]) if n is not None]
    if control["type"] == "gauge":
        return []
    return [control["number"]]


def check_button_range(config: dict[str, Any], vjoy_buttons: int | None) -> None:
    if vjoy_buttons is None:
        return
    too_high = [
        f"{control['id']} (button {number})"
        for control in config["controls_by_id"].values()
        for number in _vjoy_numbers(control)
        if number > vjoy_buttons
    ]
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


# --- Telemetry ---------------------------------------------------------------


def no_telemetry() -> dict[str, Any] | None:
    return None


def open_telemetry() -> TelemetryReader:
    """Return a reader that connects lazily and retries while the game is not running."""
    try:
        import truck_telemetry
    except ImportError:
        log.warning("truck-telemetry is not installed; panel will show no game state.")
        return no_telemetry

    status = {"ready": False, "next_try": 0.0, "reported": None}

    def report(message: str) -> None:
        if status["reported"] != message:
            status["reported"] = message
            log.info(message)

    def read() -> dict[str, Any] | None:
        now = time.monotonic()
        if not status["ready"]:
            if now < status["next_try"]:
                return None
            status["next_try"] = now + TELEMETRY_RETRY_S
            try:
                truck_telemetry.init()
            except FileNotFoundError:
                report("Telemetry not available: start the game with scs-telemetry.dll installed.")
                return None
            # The library raises a bare Exception for an unsupported plugin version.
            except Exception as error:  # noqa: BLE001
                report(f"Telemetry not available: {error}. Use scs-sdk-plugin V.1.12.1.")
                return None
            status["ready"] = True
            report("Telemetry connected.")
        try:
            return truck_telemetry.get_data()
        except (OSError, ValueError, struct.error) as error:
            log.warning("Telemetry read failed, reconnecting: %r", error)
            truck_telemetry.deinit()
            status["ready"] = False
            return None

    return read


def compute_indicators(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map raw telemetry to panel indicators with level off / dim / on."""

    def flag(value: Any, text: str | None = None) -> dict[str, Any]:
        if value and text:
            return {"level": "on", "text": text}
        return {"level": "on" if value else "off"}

    def blinking(active: Any, phase: Any) -> dict[str, str]:
        if not active:
            return {"level": "off"}
        return {"level": "on" if phase else "dim"}

    def three_state(value: Any) -> dict[str, str]:
        # Aux lights report 0 = off, 1 = dimmed, 2 = full.
        return {"level": {1: "dim", 2: "on"}.get(value, "off")}

    if data.get("engineEnabled"):
        engine = {"level": "on", "text": "RUNNING"}
    elif data.get("electricEnabled"):
        engine = {"level": "dim", "text": "IGNITION"}
    else:
        engine = {"level": "off"}

    # value is the light switch position: 0 off, 1 parking, 2 low beam.
    if data.get("lightsBeamLow"):
        lights = {"level": "on", "text": "LOW", "value": 2}
    elif data.get("lightsParking"):
        lights = {"level": "dim", "text": "PARK", "value": 1}
    else:
        lights = {"level": "off", "value": 0}


    # truck-telemetry overwrites the float warning threshold with the bool flag of the same name.
    if data.get("airPressureEmergency"):
        air_state = "emergency"
    elif data.get("airPressureWarning") is True:
        air_state = "warning"
    else:
        air_state = "ok"
    air_pressure = {
        "level": "on" if air_state != "ok" else "off",
        "value": round(float(data.get("airPressure") or 0.0), 1),
        "unit": "psi",
        "state": air_state,
    }

    # SDK units: litres, km and litres per km.
    fuel = {
        "level": "on" if data.get("fuelWarning") else "off",
        "value": round(float(data.get("fuel") or 0.0), 1),
        "capacity": round(float(data.get("fuelCapacity") or 0.0), 1),
        "range_km": round(float(data.get("fuelRange") or 0.0), 1),
        "avg_l_per_km": round(float(data.get("fuelAvgConsumption") or 0.0), 4),
        "state": "warning" if data.get("fuelWarning") else "ok",
    }

    nav = compute_nav(data)

    trailers = data.get("trailer") or [{}]
    hazard_phase = data.get("blinkerLeftOn") or data.get("blinkerRightOn")
    return {
        "engine": engine,
        "lights": lights,
        "high_beam": flag(data.get("lightsBeamHigh")),
        "blinker_left": blinking(data.get("blinkerLeftActive"), data.get("blinkerLeftOn")),
        "blinker_right": blinking(data.get("blinkerRightActive"), data.get("blinkerRightOn")),
        "hazards": blinking(data.get("lightsHazards"), hazard_phase),
        "park_brake": flag(data.get("parkBrake")),
        "wipers": flag(data.get("wipers")),
        "trailer": flag(trailers[0].get("attached"), "CONNECTED"),
        "engine_brake": flag(data.get("motorBrake")),
        "diff_lock": flag(data.get("differentialLock"), "LOCKED"),
        "lift_axle": flag(data.get("liftAxleIndicator"), "RAISED"),
        "trailer_lift_axle": flag(data.get("trailerLiftAxleIndicator"), "RAISED"),
        "beacon": flag(data.get("lightsBeacon")),
        "aux_front": three_state(data.get("lightsAuxFront")),
        "aux_roof": three_state(data.get("lightsAuxRoof")),
        "air_pressure": air_pressure,
        "fuel": fuel,
        "nav": nav,
    }


def compute_nav(data: dict[str, Any]) -> dict[str, Any]:
    """Route and job timing. Times are in-game: route in seconds, the rest in minutes."""
    clock = int(data.get("time_abs") or 0)
    on_job = bool(data.get("onJob"))
    rest_min = int(data.get("restStop") or 0)
    deadline = int(data.get("time_abs_delivery") or 0)
    return {
        "level": "on" if rest_min <= 60 else "off",
        "distance_m": round(float(data.get("routeDistance") or 0.0)),
        "time_s": round(float(data.get("routeTime") or 0.0)),
        "rest_min": rest_min,
        "clock_min": clock,
        "on_job": on_job,
        "deadline_min": deadline - clock if on_job and deadline else None,
        "planned_km": int(data.get("plannedDistanceKm") or 0) if on_job else 0,
        "destination": str(data.get("cityDst") or "") if on_job else "",
        "speed_limit_ms": round(float(data.get("speedLimit") or 0.0), 2),
    }


def update_from_telemetry(state: DeckState, data: dict[str, Any] | None) -> None:
    if data is None:
        state.game = {"telemetry": False}
        state.indicators = {}
        return
    active = bool(data.get("sdkActive"))
    state.game = {"telemetry": True, "active": active, "paused": bool(data.get("paused"))}
    state.indicators = compute_indicators(data) if active else {}
    correct_switches(state)


def correct_switches(state: DeckState) -> None:
    """Keep switch positions honest against telemetry.

    Switches with a position_source take the exact position from the game.
    Others only know on/off: position 0 must match a stopped indicator.
    """
    now = time.monotonic()
    for control in state.controls_by_id.values():
        if control["type"] != "switch" or control["indicator"] not in state.indicators:
            continue
        switch = state.switches[control["id"]]
        if switch.moving or now - switch.last_press < SWITCH_SETTLE_S:
            continue
        indicator = state.indicators[control["indicator"]]
        if control["position_source"]:
            exact = min(indicator["value"], len(control["positions"]) - 1)
            if exact != switch.position:
                log.info("%s: game reports position %d (panel had %d)", control["id"], exact, switch.position)
                switch.position = switch.target = exact
            continue
        running = indicator["level"] != "off"
        if not running and switch.position != 0:
            log.info("%s: game shows it off, correcting position %d -> 0", control["id"], switch.position)
            switch.position = switch.target = 0
        elif running and switch.position == 0:
            log.info("%s: game shows it on, correcting position 0 -> 1", control["id"])
            switch.position = switch.target = 1


async def telemetry_loop(state: DeckState) -> None:
    while True:
        update_from_telemetry(state, state.read_telemetry())
        await publish_state(state)
        await asyncio.sleep(TELEMETRY_POLL_S)


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


# --- Switches ----------------------------------------------------------------


def switch_limit(state: DeckState, control: dict[str, Any]) -> int:
    """Highest reachable position; the game may report fewer steps than configured."""
    highest = len(control["positions"]) - 1
    indicator = state.indicators.get(control["indicator"] or "")
    if control["position_source"] and indicator and indicator.get("max"):
        return min(highest, indicator["max"])
    return highest


def set_switch(state: DeckState, control: dict[str, Any], target: int) -> None:
    switch = state.switches[control["id"]]
    switch.target = min(target, switch_limit(state, control))
    if not switch.moving:
        switch.task = asyncio.create_task(move_switch(state, control))


async def move_switch(state: DeckState, control: dict[str, Any]) -> None:
    """Step forward/back one press at a time until the switch reaches its target.

    The target is re-read every step, so a new tap mid-move just changes direction.
    A cyclic switch only steps forward and wraps from the last position to the first.
    """
    switch = state.switches[control["id"]]
    count = len(control["positions"])
    tap_s = state.config["tap_ms"] / 1000
    gap_s = state.config["switch_gap_ms"] / 1000
    while switch.position != switch.target:
        forward = control["cyclic"] or switch.target > switch.position
        number = control["forward"] if forward else control["back"]
        press(state, number)
        try:
            await asyncio.sleep(tap_s)
        finally:
            release(state, number)
        if control["cyclic"]:
            switch.position = (switch.position + 1) % count
        else:
            switch.position += 1 if forward else -1
        switch.last_press = time.monotonic()
        log.info("%s -> %s", control["id"], control["positions"][switch.position])
        await publish_state(state)
        await asyncio.sleep(gap_s)


# --- Protocol ----------------------------------------------------------------


def layout_message(config: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "type", "label", "indicator", "positions", "min", "max")
    controls = [
        {key: control[key] for key in keys if key in control}
        for control in config["controls_by_id"].values()
    ]
    return {"type": "layout", "controls": controls, "bindings": config["bindings"]}


def state_message(state: DeckState) -> dict[str, Any]:
    return {
        "type": "state",
        "game": state.game,
        "indicators": state.indicators,
        "switches": {switch_id: switch.position for switch_id, switch in state.switches.items()},
    }


async def publish_state(state: DeckState) -> None:
    message = state_message(state)
    if message == state.last_state_message:
        return
    state.last_state_message = message
    await asyncio.gather(*(ws.send_json(message) for ws in list(state.sockets)), return_exceptions=True)


def bind_press(state: DeckState, key: Any, text: str) -> None:
    """One plain press of a configured vJoy button, for binding it in the game's controls menu."""
    binding = next((b for b in state.config["bindings"] if b["key"] == key), None)
    if binding is None:
        log.warning("Ignored unknown bind key: %s", text[:MAX_LOGGED_TEXT])
        return
    number = binding["number"]
    if number in state.pressed:
        return
    log.info("SETUP press vJoy %d (game Button %d, %s %s)", number, number - 1, binding["label"], binding["part"] or "")
    press(state, number)
    schedule_release(state, number, BIND_PRESS_S)


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
    if message_type == "bind":
        bind_press(state, message.get("key"), text)
        return None
    if message_type == "client_error":
        log.error("Panel error: %s", str(message.get("message", ""))[:MAX_LOGGED_TEXT])
        return None

    control = state.controls_by_id.get(message.get("id"))
    event = message.get("event")
    if control is None or control["type"] == "gauge":
        log.warning("Ignored unknown command: %s", text[:MAX_LOGGED_TEXT])
        return None

    if control["type"] == "switch":
        position = message.get("position")
        if event != "set" or not _is_int_in(position, 0, len(control["positions"]) - 1):
            log.warning("Ignored invalid switch command: %s", text[:MAX_LOGGED_TEXT])
            return None
        log.info("%s set %s (%s)", control["id"], control["positions"][position], control["label"])
        set_switch(state, control, position)
        return None

    if event not in ("down", "up"):
        log.warning("Ignored unknown command: %s", text[:MAX_LOGGED_TEXT])
        return None

    log.info("%s %s (%s, %s)", control["id"], event, control["label"], control["type"])
    number = control["number"]

    if control["type"] == "tap":
        if event == "down":
            press(state, number)
            schedule_release(state, number, state.config["tap_ms"] / 1000)
    elif event == "down":
        press(state, number)
        held.add(number)
        timeout = state.config["hold_timeout_s"]
        schedule_release(state, number, timeout, f"{control['id']} released by hold timeout ({timeout}s)")
    else:
        release(state, number)
        held.discard(number)
    return None


# --- Web app -----------------------------------------------------------------


def create_app(state: DeckState) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        telemetry_task = asyncio.create_task(telemetry_loop(state))
        yield
        telemetry_task.cancel()
        with suppress(asyncio.CancelledError):
            await telemetry_task
        release_all(state)
        log.info("Server stopped, all buttons released.")

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    # Manifest and icons for running the panel as a fullscreen home-screen app.
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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
            "controls": len(state.controls_by_id),
            "pressed": sorted(state.pressed),
            "clients": len(state.sockets),
            "game": state.game,
            "indicators": state.indicators,
            "switches": {switch_id: switch.position for switch_id, switch in state.switches.items()},
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
        held: set[int] = set()
        state.sockets.add(websocket)
        log.info("Panel connected: %s (clients: %d)", client, len(state.sockets))
        try:
            await websocket.send_json(layout_message(state.config))
            await websocket.send_json(state_message(state))
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
            state.sockets.discard(websocket)
            still_pressed = sorted(number for number in held if number in state.pressed)
            for number in still_pressed:
                release(state, number)
            log.info(
                "Panel disconnected: %s, released %s (clients: %d)",
                client, still_pressed or "nothing", len(state.sockets),
            )

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
            read_telemetry = no_telemetry
        else:
            set_button, vjoy_buttons = open_vjoy(config["vjoy_device"])
            read_telemetry = open_telemetry()
        check_button_range(config, vjoy_buttons)
    except (ConfigError, InputError) as error:
        log.error("Startup failed: %s", error)
        sys.exit(1)

    state = DeckState(
        config=config,
        set_button=set_button,
        read_telemetry=read_telemetry,
        input_mode="dry-run" if args.dry_run else "vjoy",
        vjoy_buttons=vjoy_buttons,
        commit=commit,
        errors=errors,
    )
    for control in config["controls_by_id"].values():
        if control["type"] == "switch":
            state.switches[control["id"]] = SwitchState()

    log.info("Loaded %d controls. vJoy buttons available: %s", len(state.controls_by_id), vjoy_buttons or "unknown")
    addresses = local_ipv4_addresses() or ["<this-pc-ip>"]
    print("\nOpen the panel on the tablet:")
    for address in addresses:
        print(f"  http://{address}:{args.port}")
    print("Press Ctrl+C to stop.\n", flush=True)

    uvicorn.run(create_app(state), host="0.0.0.0", port=args.port, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
