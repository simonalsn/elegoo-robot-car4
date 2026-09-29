"""Exercise the camera/ground/stop loop without any movement commands."""
import argparse
import signal
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--original", action="store_true")
args = parser.parse_args()
if args.original:
    sys.path.insert(0, "/tmp/elegoo-original-client")
from elegoo_robot_car4 import Car


def expired(signum, frame):
    raise TimeoutError("Loop check exceeded 60 seconds")


signal.signal(signal.SIGALRM, expired)
signal.alarm(60)
car = None
try:
    car = Car(ip="192.168.0.213")
    for i in range(30):
        started = time.monotonic()
        frame = car.capture()
        raised = car.is_far_from_the_ground()
        car.stop()
        print(i, frame.shape, "raised:", raised,
              "seconds:", round(time.monotonic() - started, 3), flush=True)
    print("PASS: 30 camera/ground/stop iterations", flush=True)
finally:
    signal.alarm(0)
    if car is not None:
        try:
            car.stop()
        finally:
            car.disconnect()
