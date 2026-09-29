#!/usr/bin/env python3
"""Check UDP video only: no TCP control connection or movement commands."""
import argparse
import json
import time
from pathlib import Path
import cv2 as cv
from elegoo_robot_car4.udp_video import UdpVideo

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--robot-ip', default='192.168.0.213')
parser.add_argument('--seconds', type=float, default=15)
parser.add_argument('--output', type=Path, default=Path('logs/udp-video'))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
video = UdpVideo(args.robot_ip)
start = time.monotonic()
try:
    while time.monotonic() - start < args.seconds:
        time.sleep(0.1)
    frame, age = video.latest()
    result = dict(frames=video.frames, elapsed_seconds=time.monotonic()-start,
                  latest_frame_age_seconds=age if frame is not None else None,
                  shape=list(frame.shape) if frame is not None else None,
                  error=video.error)
    if frame is not None:
        cv.imwrite(str(args.output / 'latest.jpg'), frame)
    (args.output / 'probe.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if frame is None or age > 0.75:
        raise SystemExit('FAIL: no recent UDP image; check firmware, USB power, Wi-Fi and firewall.')
finally:
    video.close()
