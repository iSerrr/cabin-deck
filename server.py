"""Cab Deck server: serves the tablet panel, presses vJoy buttons and
reports truck state from game telemetry. Two more ports serve the read-only
Alpha Gen instrument cluster: v1 dials (dash/index.html) and v2 bars (dash/v2.html).

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
from fastapi import FastAPI, Query, Request, WebSocket
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.json"
STATIC_DIR = BASE_DIR / "static"
INDEX_PATH = STATIC_DIR / "index.html"
LOG_PATH = BASE_DIR / "logs" / "cab_deck.log"
DEFAULT_PORT = 8000
DASH_INDEX_PATH = BASE_DIR / "dash" / "index.html"
DASH_V2_PATH = BASE_DIR / "dash" / "v2.html"
DEFAULT_DASH_PORT = 8701
DEFAULT_DASH_V2_PORT = 8702

BUTTON_ID_PATTERN = re.compile(r"^cab_deck_btn_(\d{3})$")
NAMED_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
CONTROL_TYPES = ("tap", "hold", "switch", "gauge")
MAX_LOGGED_TEXT = 500
MAX_LOG_LINES = 1000

# Single press used by the SETUP page to bind a vJoy button in the game menu.
BIND_PRESS_S = 0.15
TELEMETRY_POLL_S = 0.1
# The instrument cluster reads the game on its own, much faster loop so needles keep up.
DASH_POLL_S = 1 / 60
TELEMETRY_RETRY_S = 5.0
# Telemetry needs a moment to reflect a press; skip corrections right after one.
SWITCH_SETTLE_S = 1.0

# Driving pace for the "miles before rest" estimate.
PACE_WINDOW_KM = 80.47        # average over the last 50 miles
PACE_MIN_KM = 3.0             # need this much driving before giving an estimate
PACE_MIN_MINUTES = 5          # ... and this many in-game driving minutes
PACE_IDLE_MINUTES = 10        # a standstill longer than this is a break, not driving
PACE_MAX_STEP_MINUTES = 30    # a bigger clock jump means sleep, ferry or train: start over
PACE_MAX_STEP_KM = 5.0        # a bigger odometer jump means a teleport: start over
PACE_MOVING_KM = 0.01         # odometer change that counts as moving within one game minute
PACE_MAX_SAMPLES = 5000

# Delivery plan: the route is split into shifts (wake up to sleep) that fit before the deadline.
SHIFT_DEFAULT_MIN = 11 * 60   # driving window between sleeps until the game shows a real one
SLEEP_DEFAULT_MIN = 9 * 60    # until a real sleep is measured from the clock jump
SLEEP_RESET_MIN = 120         # restStop jumping up by this much means the driver slept
PLAN_MAX_DAYS = 14

MS_TO_MPH = 2.236936
KM_TO_MI = 0.621371

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
class DrivePace:
    """Average driving speed over the last PACE_WINDOW_KM, in in-game time.

    samples holds (odometer km, cumulative driving minutes), one per in-game minute
    of movement. Long standstills do not add driving minutes.
    """

    samples: deque = field(default_factory=lambda: deque(maxlen=PACE_MAX_SAMPLES))
    last_clock: int | None = None
    last_odometer: float = 0.0
    driving_minutes: int = 0
    idle_minutes: int = 0


@dataclass
class JobPlan:
    """Shift-by-shift plan of the current job. Lives in memory, like DrivePace."""

    job_key: tuple[str, int] | None = None
    job_start_km: float = 0.0
    planned_km: float = 0.0
    day: int = 0
    shift_start_km: float = 0.0
    shift_start_rest: int = 1
    shift_target_km: float = 0.0
    last_rest: int = 0
    last_clock: int = 0
    shift_min: int = SHIFT_DEFAULT_MIN
    sleep_min: int = SLEEP_DEFAULT_MIN
    view: dict[str, Any] | None = None


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
    dash_sockets: set[WebSocket] = field(default_factory=set)
    dash: dict[str, Any] = field(default_factory=lambda: {"type": "dash", "live": False})
    game: dict[str, Any] = field(default_factory=lambda: {"telemetry": False})
    indicators: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_state_message: dict[str, Any] | None = None
    pace: DrivePace = field(default_factory=DrivePace)
    plan: JobPlan = field(default_factory=JobPlan)

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


def compute_dash(data: dict[str, Any]) -> dict[str, Any]:
    """Instrument cluster values in the units ATS shows: mph, psi, °F, miles."""
    capacity = float(data.get("fuelCapacity") or 0.0)
    return {
        "type": "dash",
        "live": True,
        "mph": round(abs(float(data.get("speed") or 0.0)) * MS_TO_MPH, 2),
        "rpm": round(float(data.get("engineRpm") or 0.0)),
        "gear": int(data.get("gearDashboard") or 0),
        "air_psi": round(float(data.get("airPressure") or 0.0), 1),
        "fuel": round(float(data.get("fuel") or 0.0) / capacity, 4) if capacity > 0 else 0.0,
        "oil_psi": round(float(data.get("oilPressure") or 0.0), 1),
        "water_f": round(float(data.get("waterTemperature") or 0.0) * 9 / 5 + 32, 1),
        "cruise": bool(data.get("cruiseControl")),
        "cruise_mph": round(float(data.get("cruiseControlSpeed") or 0.0) * MS_TO_MPH),
        "blinker_left": bool(data.get("blinkerLeftOn")),
        "blinker_right": bool(data.get("blinkerRightOn")),
        "park_brake": bool(data.get("parkBrake")),
        "engine_brake": bool(data.get("motorBrake")),
        "diff_lock": bool(data.get("differentialLock")),
        "high_beam": bool(data.get("lightsBeamHigh")),
        "odometer_mi": round(float(data.get("truckOdometer") or 0.0) * KM_TO_MI, 1),
    }


def reset_pace(pace: DrivePace, clock: int, odometer: float) -> None:
    pace.samples.clear()
    pace.last_clock = clock
    pace.last_odometer = odometer
    pace.driving_minutes = 0
    pace.idle_minutes = 0
    pace.samples.append((odometer, 0))


def record_pace(pace: DrivePace, data: dict[str, Any]) -> None:
    """Add one in-game minute of driving to the pace window. Call on every poll."""
    clock = int(data.get("time_abs") or 0)
    odometer = float(data.get("truckOdometer") or 0.0)
    if data.get("paused") or clock <= 0:
        return
    if pace.last_clock is None:
        reset_pace(pace, clock, odometer)
        return
    step = clock - pace.last_clock
    moved = odometer - pace.last_odometer
    if step < 0 or step > PACE_MAX_STEP_MINUTES or abs(moved) > PACE_MAX_STEP_KM:
        log.info("Drive pace reset: clock %+d min, odometer %+.1f km.", step, moved)
        reset_pace(pace, clock, odometer)
        return
    if step == 0:
        return
    if moved >= PACE_MOVING_KM:
        # A stop that ended within PACE_IDLE_MINUTES (lights, junctions) counts as driving;
        # a longer one was a break and is left out.
        if pace.idle_minutes <= PACE_IDLE_MINUTES:
            pace.driving_minutes += pace.idle_minutes
        pace.idle_minutes = 0
        pace.driving_minutes += step
    else:
        pace.idle_minutes += step
    pace.last_clock = clock
    pace.last_odometer = odometer
    if moved >= PACE_MOVING_KM:
        pace.samples.append((odometer, pace.driving_minutes))
    while len(pace.samples) > 2 and odometer - pace.samples[1][0] >= PACE_WINDOW_KM:
        pace.samples.popleft()


def pace_estimate(pace: DrivePace) -> dict[str, Any]:
    """Average speed in km/h over the window, or None while there is too little driving."""
    if len(pace.samples) < 2:
        return {"avg_kmh": None, "window_km": 0.0}
    first_km, first_min = pace.samples[0]
    last_km, last_min = pace.samples[-1]
    distance, minutes = last_km - first_km, last_min - first_min
    if distance < PACE_MIN_KM or minutes < PACE_MIN_MINUTES:
        return {"avg_kmh": None, "window_km": round(distance, 1)}
    return {"avg_kmh": round(distance / minutes * 60, 1), "window_km": round(distance, 1)}


def plan_shifts(rest_min: int, minutes_left: int, shift_min: int, sleep_min: int) -> list[int]:
    """Driving minutes of each shift that starts before the deadline, the current one first."""
    shifts = [max(0, min(rest_min, minutes_left))]
    start = rest_min + sleep_min
    while start < minutes_left and len(shifts) < PLAN_MAX_DAYS:
        shifts.append(min(shift_min, minutes_left - start))
        start += shift_min + sleep_min
    return shifts


def remaining_km(plan: JobPlan, data: dict[str, Any]) -> float:
    """GPS distance left, or the planned job distance minus what was driven when no route is set."""
    route_km = float(data.get("routeDistance") or 0.0) / 1000
    if route_km > 0:
        return route_km
    return max(0.0, plan.planned_km - (float(data.get("truckOdometer") or 0.0) - plan.job_start_km))


def start_shift(plan: JobPlan, odometer: float, rest_min: int, remaining: float, minutes_left: int) -> None:
    """Fix today's target: today's share of the remaining distance by available driving time."""
    plan.day += 1
    plan.shift_start_km = odometer
    plan.shift_start_rest = max(rest_min, 1)
    shifts = plan_shifts(rest_min, minutes_left, plan.shift_min, plan.sleep_min)
    total = sum(shifts)
    plan.shift_target_km = remaining * shifts[0] / total if total > 0 else remaining


def update_plan(plan: JobPlan, data: dict[str, Any]) -> dict[str, Any] | None:
    """Today's target, progress against it and the split of the remaining days. Call on every poll."""
    if not data.get("onJob"):
        plan.job_key, plan.view = None, None
        return None
    clock = int(data.get("time_abs") or 0)
    deadline = int(data.get("time_abs_delivery") or 0)
    if data.get("paused") or clock <= 0 or deadline <= 0:
        return plan.view
    rest = int(data.get("restStop") or 0)
    odometer = float(data.get("truckOdometer") or 0.0)
    minutes_left = deadline - clock
    key = (str(data.get("cityDst") or ""), deadline)

    if key != plan.job_key:
        log.info("Delivery plan: new job to %s, %d min to deadline.", key[0] or "?", minutes_left)
        plan.job_key, plan.day = key, 0
        plan.job_start_km = odometer
        plan.planned_km = float(data.get("plannedDistanceKm") or 0.0)
        start_shift(plan, odometer, rest, remaining_km(plan, data), minutes_left)
    elif rest - plan.last_rest >= SLEEP_RESET_MIN:
        plan.shift_min = rest
        if clock - plan.last_clock >= SLEEP_RESET_MIN:
            plan.sleep_min = clock - plan.last_clock
        log.info("Delivery plan: slept %d min, new shift of %d min.", plan.sleep_min, plan.shift_min)
        start_shift(plan, odometer, rest, remaining_km(plan, data), minutes_left)
    plan.last_rest, plan.last_clock = rest, clock

    remaining = remaining_km(plan, data)
    shifts = plan_shifts(rest, minutes_left, plan.shift_min, plan.sleep_min)
    total = sum(shifts)
    done = odometer - plan.shift_start_km
    today_left = max(0.0, plan.shift_target_km - done)
    elapsed = min(1.0, max(0.0, (plan.shift_start_rest - rest) / plan.shift_start_rest))
    future_total = sum(shifts[1:])
    later = max(0.0, remaining - today_left)
    plan.view = {
        "day": plan.day,
        "days": plan.day + len(shifts) - 1,
        "done_km": round(done, 1),
        "target_km": round(plan.shift_target_km, 1),
        "ahead_km": round(done - plan.shift_target_km * elapsed, 1),
        "next_km": [round(later * s / future_total, 1) for s in shifts[1:]] if future_total > 0 else [],
        "required_kmh": round(remaining / total * 60, 1) if total > 0 else None,
        "late": minutes_left <= 0 or total <= 0,
    }
    return plan.view


def update_from_telemetry(state: DeckState, data: dict[str, Any] | None) -> None:
    if data is None:
        state.game = {"telemetry": False}
        state.indicators = {}
        return
    active = bool(data.get("sdkActive"))
    state.game = {"telemetry": True, "active": active, "paused": bool(data.get("paused"))}
    state.indicators = compute_indicators(data) if active else {}
    if active:
        record_pace(state.pace, data)
        add_rest_range(state.indicators["nav"], pace_estimate(state.pace))
        state.indicators["nav"]["plan"] = update_plan(state.plan, data)
    correct_switches(state)


def add_rest_range(nav: dict[str, Any], pace: dict[str, Any]) -> None:
    """Miles the truck can still cover before the rest stop at the recent pace."""
    nav["avg_kmh"] = pace["avg_kmh"]
    nav["pace_window_km"] = pace["window_km"]
    rest = nav["rest_min"]
    nav["rest_range_km"] = round(pace["avg_kmh"] * rest / 60, 1) if pace["avg_kmh"] and rest > 0 else None


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


async def dash_loop(state: DeckState) -> None:
    """Read and send cluster values at 60 Hz, but only while a dash is connected."""
    loop = asyncio.get_running_loop()
    deadline = loop.time()
    while True:
        if state.dash_sockets:
            data = state.read_telemetry()
            active = data is not None and bool(data.get("sdkActive"))
            state.dash = compute_dash(data) if active else {"type": "dash", "live": False}
            await publish_dash(state)
        # Sleep to the next tick rather than a fixed pause, so the work does not slow the rate.
        deadline = max(deadline + DASH_POLL_S, loop.time())
        await asyncio.sleep(deadline - loop.time())


async def publish_dash(state: DeckState) -> None:
    await asyncio.gather(*(ws.send_json(state.dash) for ws in list(state.dash_sockets)), return_exceptions=True)


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


def create_app(state: DeckState, dash_pages: dict[int, Path]) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        tasks = [asyncio.create_task(telemetry_loop(state)), asyncio.create_task(dash_loop(state))]
        yield
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        release_all(state)
        log.info("Server stopped, all buttons released.")

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    # Manifest and icons for running the panel as a fullscreen home-screen app.
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index(request: Request) -> FileResponse:
        # The same app listens on every port; a dash port serves its instrument cluster.
        server = request.scope.get("server")
        page = dash_pages.get(server[1], INDEX_PATH) if server else INDEX_PATH
        return FileResponse(page, headers={"Cache-Control": "no-store"})

    @app.get("/dash")
    async def dash_index() -> FileResponse:
        return FileResponse(DASH_INDEX_PATH, headers={"Cache-Control": "no-store"})

    @app.get("/dash2")
    async def dash_v2() -> FileResponse:
        return FileResponse(DASH_V2_PATH, headers={"Cache-Control": "no-store"})

    @app.websocket("/ws/dash")
    async def dash_websocket(websocket: WebSocket) -> None:
        # Read-only stream: the cluster never sends commands, so nothing can be pressed from here.
        await websocket.accept()
        client = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
        state.dash_sockets.add(websocket)
        log.info("Dash connected: %s (dash clients: %d)", client, len(state.dash_sockets))
        try:
            await websocket.send_json(state.dash)
            while (await websocket.receive())["type"] != "websocket.disconnect":
                pass
        finally:
            state.dash_sockets.discard(websocket)
            log.info("Dash disconnected: %s (dash clients: %d)", client, len(state.dash_sockets))

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
            "dash_clients": len(state.dash_sockets),
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


def bind_socket(port: int) -> socket.socket:
    """Listening socket on all interfaces, the way uvicorn binds its own."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", port))
    except OSError as error:
        sock.close()
        raise OSError(f"Cannot listen on port {port}: {error}. Is another server already running?") from error
    sock.set_inheritable(True)
    return sock


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cab Deck tablet panel server.")
    parser.add_argument("--dry-run", action="store_true", help="log button presses instead of using vJoy")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--dash-port", type=int, default=DEFAULT_DASH_PORT, help="port of the Alpha Gen dials (v1)")
    parser.add_argument("--dash2-port", type=int, default=DEFAULT_DASH_V2_PORT, help="port of the Alpha Gen bars (v2)")
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
    try:
        sockets = [bind_socket(port) for port in (args.port, args.dash_port, args.dash2_port)]
    except OSError as error:
        log.error("Startup failed: %s", error)
        sys.exit(1)

    print("\nOpen the panel on the tablet:")
    for address in addresses:
        print(f"  http://{address}:{args.port}")
    print("Open the Alpha Gen dash on the phone (v1 dials, v2 bars):")
    for address in addresses:
        print(f"  http://{address}:{args.dash_port}   http://{address}:{args.dash2_port}")
    print("Press Ctrl+C to stop.\n", flush=True)

    dash_pages = {args.dash_port: DASH_INDEX_PATH, args.dash2_port: DASH_V2_PATH}
    config = uvicorn.Config(create_app(state, dash_pages), log_config=None, access_log=False)
    uvicorn.Server(config).run(sockets=sockets)


if __name__ == "__main__":
    main()
