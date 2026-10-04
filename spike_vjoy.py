"""Spike: check that ETS2 sees vJoy buttons pressed from Python.

Run on the Windows gaming PC with vJoy installed:
    pip install pyvjoy
    python spike_vjoy.py 1

The script pulses the given vJoy button every few seconds. While it runs,
open ETS2 controls, start binding an action and wait for the pulse.
"""

import argparse
import sys
import time

DEVICE_ID = 1
PRESS_SECONDS = 0.1
INTERVAL_SECONDS = 3.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pulse a vJoy button for ETS2 testing.")
    parser.add_argument("button", type=int, help="vJoy button number, 1-based")
    parser.add_argument("--count", type=int, default=20, help="number of pulses")
    return parser.parse_args()


def open_device(device_id: int):
    try:
        import pyvjoy
        from pyvjoy.exceptions import vJoyException
    except ImportError:
        sys.exit("pyvjoy is not installed. Run: pip install pyvjoy (Windows only).")

    try:
        return pyvjoy.VJoyDevice(device_id)
    except vJoyException as error:
        sys.exit(
            f"Cannot open vJoy device {device_id}: {error!r}\n"
            "Check that vJoy is installed, device 1 is enabled in 'Configure vJoy', "
            "and vJoyInterface.dll matches the driver version."
        )


def pulse(device, button: int, count: int) -> None:
    for index in range(1, count + 1):
        print(f"[{index}/{count}] press button {button}")
        device.set_button(button, 1)
        time.sleep(PRESS_SECONDS)
        device.set_button(button, 0)
        time.sleep(INTERVAL_SECONDS)


def main() -> None:
    args = parse_args()
    device = open_device(DEVICE_ID)
    print(f"Pulsing vJoy button {args.button} {args.count} times. Ctrl+C to stop.")
    try:
        pulse(device, args.button, args.count)
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        device.set_button(args.button, 0)


if __name__ == "__main__":
    main()
