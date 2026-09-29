#!/usr/bin/env python3
"""Paired-firmware check: zero wheel speeds, centred camera, UDP and sensors.

Run with the assembled car stationary and all other clients closed.
"""
import argparse
import json
import time
from pathlib import Path
from elegoo_robot_car4 import Car
from elegoo_robot_car4.udp_video import UdpVideo

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--updates',type=int,default=300)
parser.add_argument('--output',type=Path,default=Path('logs/analogue-drive-2026-09-29/wifi-probe.json'))
args=parser.parse_args()
video=None
car=None
try:
    car=Car(ip='192.168.0.213')
    car.stop()
    car.enable_analogue_drive()
    video=UdpVideo('192.168.0.213')
    delays=[]
    started=time.monotonic()
    for i in range(args.updates):
        start=time.monotonic()
        car.drive_analogue(0,0,0)
        delays.append(time.monotonic()-start)
        if i%10==0:car.is_far_from_the_ground()
        time.sleep(max(0,1/30-(time.monotonic()-start)))
    frame,age=video.latest()
    assert frame is not None and age < .75, 'No recent UDP frame'
    mpu=car.get_mpu_data()
    car.stop()
    result=dict(passed=True,zero_speed_updates=len(delays),elapsed_seconds=time.monotonic()-started,
                mean_ack_ms=1000*sum(delays)/len(delays),max_ack_ms=1000*max(delays),
                udp_frames=video.frames,frame_shape=list(frame.shape),latest_receive_age_seconds=age,
                mpu=mpu,movement_tested=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
finally:
    if car is not None:
        try:car.stop()
        finally:car.disconnect()
    if video is not None:video.close()
