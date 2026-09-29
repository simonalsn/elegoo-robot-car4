#!/usr/bin/env python3
"""Read gamepad identity and mapped inputs only; never connects to the robot."""
import argparse
import json
import os
import time
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ['SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS'] = '1'
import pygame as pg
from pygame._sdl2 import controller

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seconds', type=float, default=2)
args = parser.parse_args()
pg.init()
controller.init()
opened = {}
last = {}
try:
    end = time.monotonic() + args.seconds
    while time.monotonic() < end:
        pg.event.pump()
        for i in range(pg.joystick.get_count()):
            joy = pg.joystick.Joystick(i)
            ident = joy.get_instance_id()
            if ident not in opened:
                pad = controller.Controller(i) if controller.is_controller(i) else None
                opened[ident] = (joy, pad)
                print(json.dumps(dict(name=joy.get_name(),guid=joy.get_guid(),
                    axes=joy.get_numaxes(),buttons=joy.get_numbuttons(),hats=joy.get_numhats(),
                    mapping=pad.get_mapping() if pad else None)), flush=True)
            joy, pad = opened[ident]
            state = dict(axes=[round(joy.get_axis(a),2) for a in range(joy.get_numaxes())],
                         buttons=[b for b in range(joy.get_numbuttons()) if joy.get_button(b)],
                         hats=[joy.get_hat(h) for h in range(joy.get_numhats())])
            if pad:
                state['mapped_axes'] = [pad.get_axis(a) for a in range(6)]
                state['mapped_buttons'] = [b for b in range(15) if pad.get_button(b)]
            if state != last.get(ident):
                print(json.dumps(dict(instance=ident,**state)), flush=True)
                last[ident]=state
        time.sleep(0.1)
    if not opened:
        print('No gamepad detected by SDL.')
finally:
    controller.quit()
    pg.quit()
