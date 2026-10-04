"""Spike: find which telemetry fields change between game states.

Run on the Windows gaming PC while ATS is running:
    .venv\\Scripts\\python spike_diff.py

Bring the game into a state, switch to this window, type a short label and
press Enter to take a snapshot. Repeat for each state, then type "q".
The script prints every field that differs between consecutive snapshots.

Example for advanced trailer coupling:
    1. "free"      - truck in front of the trailer, not coupled
    2. "locked"    - backed in, fifth wheel locked, lines not connected yet
    3. "connected" - after pressing the connect button
Keep the truck still between snapshots so moving values stay quiet.
"""

import sys
from typing import Any

MAX_FLOAT_CHANGES = 40
FLOAT_EPSILON = 1e-3
# Values that change on their own every frame and only add noise.
NOISY_PARTS = ("time", "Time", "coordinate", "rotation", "Rotation", "AV", "AA", "LV", "LA", "Velocity", "Acc", "rpm", "Rpm")


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


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        flat: dict[str, Any] = {}
        for key, item in value.items():
            flat.update(flatten(item, f"{prefix}.{key}" if prefix else str(key)))
        return flat
    if isinstance(value, (list, tuple)):
        flat = {}
        for index, item in enumerate(value):
            flat.update(flatten(item, f"{prefix}[{index}]"))
        return flat
    return {prefix: value}


def is_noisy(key: str) -> bool:
    return any(part in key for part in NOISY_PARTS)


def diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[list[str], list[str]]:
    exact, floats = [], []
    for key, new in after.items():
        old = before.get(key)
        if old == new or is_noisy(key):
            continue
        if isinstance(new, float) and isinstance(old, float):
            if abs(new - old) >= FLOAT_EPSILON:
                floats.append((abs(new - old), f"  {key}: {old:.4f} -> {new:.4f}"))
        else:
            exact.append(f"  {key}: {old!r} -> {new!r}")
    floats.sort(reverse=True)
    return exact, [line for _, line in floats[:MAX_FLOAT_CHANGES]]


def main() -> None:
    telemetry = open_telemetry()
    snapshots: list[tuple[str, dict[str, Any]]] = []
    print("Type a label and press Enter to take a snapshot, or q to finish.")
    try:
        while True:
            label = input(f"snapshot {len(snapshots) + 1} label> ").strip()
            if label.lower() == "q":
                break
            snapshots.append((label or f"#{len(snapshots) + 1}", flatten(telemetry.get_data())))
            print(f"  saved '{snapshots[-1][0]}' ({len(snapshots[-1][1])} fields)")
    finally:
        telemetry.deinit()

    for (name_a, a), (name_b, b) in zip(snapshots, snapshots[1:]):
        exact, floats = diff(a, b)
        print(f"\n=== {name_a} -> {name_b} ===")
        print("Flags, numbers, text:" if exact else "Flags, numbers, text: no changes")
        print("\n".join(exact))
        if floats:
            print(f"Largest float changes (top {MAX_FLOAT_CHANGES}):")
            print("\n".join(floats))


if __name__ == "__main__":
    main()
