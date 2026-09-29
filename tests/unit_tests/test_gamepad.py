from unittest.mock import MagicMock
import pygame as pg
import pytest
from elegoo_robot_car4.elegoo_smartcar_control import GameEngine


def pad(axes=None, buttons=()):
    result = MagicMock()
    result.attached.return_value = True
    result.get_axis.side_effect = lambda axis: (axes or {}).get(axis, 0)
    result.get_button.side_effect = lambda button: button in buttons
    return result


def engine(*pads):
    result = GameEngine.__new__(GameEngine)
    result._GameEngine__car = MagicMock()
    result._GameEngine__joysticks = dict(enumerate(pads))
    result._GameEngine__delta_speed = 150
    return result


@pytest.mark.parametrize('x,y,action', [
    (0,-32768,'forward'), (0,32767,'backward'),
    (-32768,0,'left'), (32767,0,'right'),
    (-32768,-32768,'forward_left'), (32767,-32768,'forward_right'),
    (-32768,32767,'backward_left'), (32767,32767,'backward_right')])
def test_stick_directions(x,y,action):
    e=engine(pad({pg.CONTROLLER_AXIS_LEFTX:x,pg.CONTROLLER_AXIS_LEFTY:y}))
    assert e._GameEngine__handle_controller_player_actions()
    getattr(e._GameEngine__car,action).assert_called_once_with(speed=50,lazy=True)


def test_neutral_and_deadzone_return_no_drive():
    e=engine(pad({pg.CONTROLLER_AXIS_LEFTX:4000,pg.CONTROLLER_AXIS_LEFTY:-1000}))
    assert not e._GameEngine__handle_controller_player_actions()
    assert not e._GameEngine__car.mock_calls


def test_trigger_and_stick_scale_speed():
    p=pad({pg.CONTROLLER_AXIS_LEFTY:-32768,pg.CONTROLLER_AXIS_TRIGGERRIGHT:32767})
    e=engine(p)
    e._GameEngine__handle_controller_player_actions()
    e._GameEngine__car.forward.assert_called_once_with(speed=200,lazy=True)
    e=engine(pad({pg.CONTROLLER_AXIS_LEFTY:-19661,pg.CONTROLLER_AXIS_TRIGGERRIGHT:32767}))
    e._GameEngine__handle_controller_player_actions()
    e._GameEngine__car.forward.assert_called_once_with(speed=125,lazy=True)


def test_idle_pad_does_not_hide_active_pad():
    e=engine(pad(),pad(buttons=[pg.CONTROLLER_BUTTON_DPAD_UP]))
    assert e._GameEngine__handle_controller_player_actions()
    e._GameEngine__car.forward.assert_called_once_with(speed=50,lazy=True)


def test_pan_stops_previous_drive_before_queuing_head_command():
    e=engine(pad({pg.CONTROLLER_AXIS_RIGHTX:32767,pg.CONTROLLER_AXIS_LEFTY:-32768}))
    assert e._GameEngine__handle_controller_player_actions()
    assert [c[0] for c in e._GameEngine__car.mock_calls] == ['stop','turn_head']
    e._GameEngine__car.turn_head.assert_called_once_with(-10,lazy=True)


def test_x_centres_camera():
    e=engine(pad(buttons=[pg.CONTROLLER_BUTTON_X]))
    e._GameEngine__handle_controller_player_actions()
    e._GameEngine__car.stop.assert_called_once()
    e._GameEngine__car.set_head_angle.assert_called_once_with(lazy=True)


def test_hotplug_processed_while_raised(mocker):
    e=engine()
    p=pad()
    p.as_joystick.return_value.get_instance_id.return_value=42
    mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.gamecontroller.is_controller',return_value=True)
    mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.gamecontroller.Controller',return_value=p)
    e._GameEngine__dry_run=False
    e._GameEngine__car.is_far_from_the_ground.return_value=True
    mocker.patch.object(e,'_GameEngine__display_new_frame')
    mocker.patch('pygame.time.Clock')
    mocker.patch('pygame.display.set_caption')
    mocker.patch('pygame.event.get',side_effect=[
        [pg.event.Event(pg.JOYDEVICEADDED,device_index=0)], [pg.event.Event(pg.QUIT)]])
    e.run()
    assert e._GameEngine__joysticks[42] is p
    e._GameEngine__car.move.assert_not_called()


def test_disconnect_and_unknown_disconnect_are_safe():
    p=pad();e=engine(p)
    e._GameEngine__detect_relevant_events([pg.event.Event(pg.JOYDEVICEREMOVED,instance_id=0),
                                        pg.event.Event(pg.JOYDEVICEREMOVED,instance_id=999)])
    assert not e._GameEngine__handle_controller_player_actions()
    p.quit.assert_called_once()
