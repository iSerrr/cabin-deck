"""Spike: check which truck states ATS/ETS2 telemetry exposes.

Requires the RenCloud scs-sdk-plugin (V.1.12.1) installed in the game:
copy scs-telemetry.dll to <game folder>\\bin\\win_x64\\plugins\\

Run on the Windows gaming PC while ATS/ETS2 is running (in the cab, not in menus):
    .venv\\Scripts\\python spike_telemetry.py

Prints every watched field once, then only the fields that change.
Press panel buttons and watch which fields react.
"""

import sys
import time
from typing import Any

POLL_SECONDS = 0.1
TIMING_SAMPLES = 50

WATCHED_FIELDS = (
    "sdkActive",
    "paused",
    "electricEnabled",
    "engineEnabled",
    "lightsParking",
    "lightsBeamLow",
    "lightsBeamHigh",
    "lightsBeacon",
    "lightsHazards",
    "lightsAuxFront",
    "lightsAuxRoof",
    "lightsDashboard",
    "blinkerLeftActive",
    "blinkerRightActive",
    "blinkerLeftOn",
    "blinkerRightOn",
    "wipers",
    "parkBrake",
    "motorBrake",
    "retarderBrake",
    "retarderStepCount",
    "cruiseControl",
)


def open_telemetry() -> Any:
    try:
        import truck_telemetry
    except ImportError:
        sys.exit("truck-telemetry is not installed. Run run.bat once or: pip install truck-telemetry")

    try:
        truck_telemetry.init()
    except FileNotFoundError:
        sys.exit(
            "Telemetry shared memory not found. Start ATS/ETS2 with scs-telemetry.dll in "
            "bin\\win_x64\\plugins and confirm the 'advanced SDK features' dialog."
        )
    # The library raises a bare Exception for an unsupported plugin version.
    except Exception as error:  # noqa: BLE001
        sys.exit(f"Cannot read telemetry: {error}. Use scs-sdk-plugin V.1.12.1.")
    return truck_telemetry


def snapshot(data: dict[str, Any]) -> dict[str, Any]:
    values = {field: data.get(field, "<missing>") for field in WATCHED_FIELDS}
    trailers = data.get("trailer") or []
    values["trailer[0].attached"] = trailers[0].get("attached", "<missing>") if trailers else "<missing>"
    if isinstance(values["lightsDashboard"], float):
        values["lightsDashboard"] = round(values["lightsDashboard"], 2)
    return values


def measure_read_ms(telemetry: Any) -> float:
    started = time.perf_counter()
    for _ in range(TIMING_SAMPLES):
        telemetry.get_data()
    return (time.perf_counter() - started) * 1000 / TIMING_SAMPLES


def main() -> None:
    telemetry = open_telemetry()
    data = telemetry.get_data()
    print(
        f"Plugin revision {data.get('telemetry_plugin_revision')}, "
        f"game telemetry {data.get('telemetry_version_game_major')}.{data.get('telemetry_version_game_minor')}, "
        f"one read takes {measure_read_ms(telemetry):.2f} ms"
    )

    previous = snapshot(data)
    for field, value in previous.items():
        print(f"  {field:<22} {value}")
    print("\nWatching for changes. Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(POLL_SECONDS)
            current = snapshot(telemetry.get_data())
            changes = [f"{field}: {previous[field]} -> {value}" for field, value in current.items() if value != previous[field]]
            if changes:
                print(time.strftime("%H:%M:%S"), " | ".join(changes))
            previous = current
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        telemetry.deinit()


if __name__ == "__main__":
    main()
