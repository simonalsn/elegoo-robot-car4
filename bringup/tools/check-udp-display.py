#!/usr/bin/env python3
"""Exercise the real UDP display with mocked motor/sensor control, off-screen."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pygame as pg
from elegoo_robot_car4.elegoo_smartcar_control import GameEngine

car = MagicMock()
car.is_far_from_the_ground.return_value = True
car.vision_tracking_is_on = False
car.capture.side_effect = AssertionError('UDP display attempted HTTP capture')
car.move.side_effect = AssertionError('Motor movement attempted')
pg.init()
try:
    with patch('elegoo_robot_car4.elegoo_smartcar_control.Car', return_value=car):
        with GameEngine('192.168.0.213', video='udp') as engine:
            pg.time.set_timer(pg.QUIT, 5000, loops=1)
            engine.run()
            frames = engine._GameEngine__video.frames
            size = engine._GameEngine__display.get_size()
            assert frames > 0 and size == (800, 600)
    car.move.assert_not_called()
    car.capture.assert_not_called()
    car.disconnect.assert_called_once()
    result = dict(decoded_frames=frames,display_size=size,real_control_connection=False,
                  http_capture_calls=0,motor_move_calls=0,normal_exit=True)
    Path('logs/udp-video/display.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
finally:
    pg.quit()
