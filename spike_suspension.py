"""Spike: does telemetry show air suspension height?

Run on the Windows gaming PC while ATS is running, in the cab, truck standing still:
    .venv\\Scripts\\python spike_suspension.py

Then hold Front / Rear / Trailer Suspension Up and Down and watch the numbers.
Prints average suspension deflection per group in millimetres:
front axle (steerable wheels), rear axles (the rest), trailer.
"""

import sys
import time
from typing import Any

POLL_SECONDS = 0.2
CHANGE_MM = 1.0


def open_telemetry() -> Any:
    try:
        import truck_telemetry
    except ImportError:
        sys.exit("truck-telemetry is not installed. Run run.bat once.")
    try:
        truck_telemetry.init()
    except FileNotFoundError:
        sys.exit("Telemetry shared memory not found. Start ATS with scs-telemetry.dll installed.")
    # The library raises a bare Exception for an unsupported plugin version.
    except Exception as error:  # noqa: BLE001
        sys.exit(f"Cannot read telemetry: {error}")
    return truck_telemetry


def average_mm(values: list[float]) -> float | None:
    return round(sum(values) / len(values) * 1000, 1) if values else None


def groups(data: dict[str, Any]) -> dict[str, float | None]:
    count = int(data.get("truckWheelCount") or 0)
    deflection = data.get("truck_wheelSuspDeflection") or []
    steerable = data.get("truckWheelSteerable") or []
    front = [deflection[i] for i in range(count) if steerable[i]]
    rear = [deflection[i] for i in range(count) if not steerable[i]]
    trailer = (data.get("trailer") or [{}])[0]
    trailer_count = int(trailer.get("wheelCount") or 0)
    trailer_values = list((trailer.get("wheelSuspDeflection") or [])[:trailer_count])
    return {
        "front": average_mm(front),
        "rear": average_mm(rear),
        "trailer": average_mm(trailer_values) if trailer.get("attached") else None,
        "bodyY": round(float(data.get("coordinateY") or 0.0) * 1000, 1),
    }


def main() -> None:
    telemetry = open_telemetry()
    data = telemetry.get_data()
    count = int(data.get("truckWheelCount") or 0)
    print(f"Truck wheels: {count}, steerable: {list(data.get('truckWheelSteerable') or [])[:count]}")
    print("Values in mm. Hold suspension up/down keys and watch. Ctrl+C to stop.\n")

    previous: dict[str, float | None] = {}
    try:
        while True:
            current = groups(telemetry.get_data())
            changed = any(
                current[key] is not None and (previous.get(key) is None or abs(current[key] - previous[key]) >= CHANGE_MM)
                for key in current
            )
            if changed:
                print(time.strftime("%H:%M:%S"), "  ".join(f"{key}={value}" for key, value in current.items()))
                previous = current
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        telemetry.deinit()


if __name__ == "__main__":
    main()
