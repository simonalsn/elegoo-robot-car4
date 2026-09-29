"""Bring-up checks using the unchanged upstream Car client.

--motors requires an attended, secured robot with every wheel off the surface.
"""
import argparse
import json
from pathlib import Path
import signal
import time

import cv2
from elegoo_robot_car4 import Car

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--ip", default="192.168.0.213")
parser.add_argument("--motors", action="store_true")
args = parser.parse_args()
out = Path("logs/assembled-wifi")
out.mkdir(parents=True, exist_ok=True)


def timeout(signum, frame):
    raise TimeoutError("Bring-up check exceeded 45 seconds")


signal.signal(signal.SIGALRM, timeout)
signal.alarm(45)
car = None
try:
    print("Connecting; keep robot still during upstream MPU calibration.", flush=True)
    car = Car(ip=args.ip)
    car.stop()
    time.sleep(0.3)
    result = {"mpu": car.get_mpu_data()}
    time.sleep(0.2)
    result["ultrasonic_cm_upstream_calibration"] = car.get_ultrasonic_value()
    time.sleep(0.2)
    result["ir"] = car.get_ir_all()
    time.sleep(0.2)
    result["ground_status_upstream"] = car.is_far_from_the_ground()
    image = car.capture()
    assert image is not None and image.size > 0
    result["camera_shape"] = list(image.shape)
    assert cv2.imwrite(str(out / "capture.jpg"), image)
    print(json.dumps(result, indent=2), flush=True)
    (out / "sensors.json").write_text(json.dumps(result, indent=2) + "\n")
    if args.motors:
        actions = []
        for name in ("forward", "backward", "left", "right"):
            print(f"{name.upper()} — 0.35 seconds at speed 80", flush=True)
            try:
                getattr(car, name)(speed=80)
                time.sleep(0.35)
            finally:
                car.stop()
            print("STOP", flush=True)
            time.sleep(2)
            # A responding UNO shows the bridge is still alive, not wheel motion.
            sample = car.get_mpu_data()
            actions.append({"command": name, "duration_s": 0.35, "speed": 80,
                            "stop_sent": True, "mpu_after_stop": sample})
        (out / "motor-commands.json").write_text(json.dumps(actions, indent=2) + "\n")
        print("Commands completed; actual wheel directions/stops require observer confirmation.", flush=True)
finally:
    signal.alarm(0)
    if car is not None:
        try:
            car.stop()
        finally:
            car.disconnect()
