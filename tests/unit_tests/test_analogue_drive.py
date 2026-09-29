import json
from unittest.mock import MagicMock

import pygame as pg
import pytest

from elegoo_robot_car4.analogue_drive import AnalogueDrive, deadzone, expo, mix_wheels, motor_pwm
from elegoo_robot_car4 import Car
from elegoo_robot_car4.elegoo_smartcar_control import GameEngine


@pytest.mark.parametrize('forward,reverse,steering', [(1,.1,1),(.1,1,-1),(1,1,0),(.041,.041,.5)])
def test_both_triggers_stop_even_with_steering(forward,reverse,steering):
    drive=AnalogueDrive(left=200,right=100)
    assert drive.update(forward,reverse,steering,0,10)[:2] == (0,0)


def test_noise_is_not_a_second_trigger_press():
    assert mix_wheels(1,.02,0) == (1,1)
    assert mix_wheels(.02,1,0) == (-1,-1)


def test_full_throttle_turn_keeps_outside_at_limit_and_slows_inside():
    left,right=mix_wheels(1,0,.5)
    assert left == 1 and 0 < right < left
    steer=deadzone(.5,.08)
    steer=.20+.80*steer**3
    assert right == pytest.approx((1-steer)/(1+steer))


def test_lower_throttle_can_speed_up_outside_wheels():
    straight=mix_wheels(.4,0,0)
    left,right=mix_wheels(.4,0,.2)
    assert 0 < right < straight[0] < left < 1


def test_reverse_steering_and_pivot_are_continuous():
    # Stick-right means nose-right both forwards and backwards (robot convention).
    left,right=mix_wheels(0,1,.4)
    assert -1 == right < left < 0
    left,right=mix_wheels(0,0,.4)
    assert 0 < left < 1 and right == -left
    assert mix_wheels(0,0,.079) == (0,0)
    assert max(map(abs,mix_wheels(0,0,.081))) < .001


def test_commands_stay_bounded_and_turn_monotonically():
    for throttle in [0,.1,.5,1]:
        previous=-3
        for i in range(-100,101):
            left,right=mix_wheels(throttle,0,i/100)
            assert max(abs(left),abs(right)) <= 1
            assert left-right >= previous-1e-9
            previous=left-right


def test_release_stop_bypasses_ramp():
    drive=AnalogueDrive(left=200,right=200)
    assert drive.update(0,0,0,0,0) == (0,0,0)


def test_acceleration_and_camera_rate_are_time_based():
    a=AnalogueDrive(previous_time=0)
    b=AnalogueDrive(previous_time=0)
    for i in range(1,7):
        a.update(1,0,0,1,i/30)
    for i in range(1,13):
        b.update(1,0,0,1,i/60)
    assert a.left == pytest.approx(b.left)
    assert a.left == pytest.approx(160)
    assert a.head == b.head == -80
    for i in range(7,13):
        a.update(1,0,0,0,i/30)
    assert a.head == 0 and a.left == 200


def test_long_pause_cannot_create_single_step_acceleration():
    a=AnalogueDrive(previous_time=0)
    assert a.update(1,0,0,0,10)[0] == 80


def test_camera_does_not_cancel_wheel_commands():
    a=AnalogueDrive(left=200,right=200,previous_time=0)
    left,right,head=a.update(1,0,0,1,.1)
    assert (left,right,head) == (200,200,-45)


def test_protocol_requires_handshake_and_sends_signed_wheels_and_exact_pan(car_mocks):
    sock=car_mocks['socket']
    sock.recv.side_effect=[b'{drive_v1}',b'{d1_ok}',b'{d2_ok}']
    with Car() as car:
        with pytest.raises(RuntimeError,match='handshake'):
            car.drive_analogue(0,0,0)
        assert not sock.sendall.called
        car.enable_analogue_drive()
        car.drive_analogue(-200,123,17)
        assert json.loads(sock.sendall.call_args.args[0]) == {
            'H':'d1','N':1001,'D1':-200,'D2':123,'D3':107}
        assert car.head_angle == 17
        car.drive_analogue(-200,123,17)  # identical commands renew the lease
        assert json.loads(sock.sendall.call_args.args[0])['H'] == 'd2'
        assert len(sock.sendall.call_args.args[0]) < 64
        with pytest.raises(ValueError):
            car.drive_analogue(201,0,0)


def test_unsupported_firmware_cannot_enable_fast_drive(car_mocks):
    car_mocks['socket'].recv.side_effect=TimeoutError()
    with Car() as car:
        with pytest.raises(RuntimeError,match='paired'):
            car.enable_analogue_drive()
        with pytest.raises(RuntimeError,match='handshake'):
            car.drive_analogue(100,100,0)


def analogue_engine(mocker,axes):
    engine=GameEngine.__new__(GameEngine)
    engine._GameEngine__analogue=AnalogueDrive()
    engine._GameEngine__car=MagicMock()
    pad=MagicMock()
    pad.attached.return_value=True
    pad.get_button.return_value=False
    pad.get_axis.side_effect=lambda axis: axes.get(axis,0)
    engine._GameEngine__joysticks={1:pad}
    mocker.patch('pygame.key.get_focused',return_value=True)
    return engine


def test_new_layout_ignores_left_stick_vertical(mocker):
    e=analogue_engine(mocker,{pg.CONTROLLER_AXIS_LEFTY:-32768})
    e._GameEngine__handle_analogue_actions()
    e._GameEngine__car.drive_analogue.assert_called_once_with(0,0,0)


def test_trigger_stop_wins_over_steering_in_actual_handler(mocker):
    e=analogue_engine(mocker,{pg.CONTROLLER_AXIS_TRIGGERRIGHT:32767,
                             pg.CONTROLLER_AXIS_TRIGGERLEFT:10000,
                             pg.CONTROLLER_AXIS_LEFTX:32767})
    e._GameEngine__analogue.left=200
    e._GameEngine__handle_analogue_actions()
    e._GameEngine__car.drive_analogue.assert_called_once_with(0,0,0)


def test_focus_loss_stops_and_resets_ramp(mocker):
    e=analogue_engine(mocker,{pg.CONTROLLER_AXIS_TRIGGERRIGHT:32767})
    mocker.patch('pygame.key.get_focused',return_value=False)
    e._GameEngine__analogue.left=200
    e._GameEngine__handle_analogue_actions()
    e._GameEngine__car.stop.assert_called_once()
    e._GameEngine__car.drive_analogue.assert_not_called()
    assert e._GameEngine__analogue.left == 0


def test_drive_error_requests_stop_and_resets_state(mocker):
    e=analogue_engine(mocker,{pg.CONTROLLER_AXIS_TRIGGERRIGHT:32767})
    e._GameEngine__car.drive_analogue.side_effect=TimeoutError()
    with pytest.raises(TimeoutError):
        e._GameEngine__handle_analogue_actions()
    e._GameEngine__car.stop.assert_called_once()
    assert e._GameEngine__analogue.left == 0


def test_analogue_loop_never_falls_through_to_legacy_keyboard_or_queue(mocker):
    e=analogue_engine(mocker,{pg.CONTROLLER_AXIS_TRIGGERRIGHT:32767,
                             pg.CONTROLLER_AXIS_TRIGGERLEFT:32767,
                             pg.CONTROLLER_AXIS_LEFTX:32767})
    e._GameEngine__dry_run=False
    e._GameEngine__car.is_far_from_the_ground.return_value=False
    mocker.patch.object(e,'_GameEngine__display_new_frame',return_value=True)
    old_keyboard=mocker.patch.object(e,'_GameEngine__handle_keyboard_player_actions')
    mocker.patch('pygame.time.Clock')
    mocker.patch('pygame.display.set_caption')
    mocker.patch('pygame.event.get',side_effect=[[],[pg.event.Event(pg.QUIT)]])
    e.run()
    old_keyboard.assert_not_called()
    e._GameEngine__car.move.assert_not_called()
    e._GameEngine__car.drive_analogue.assert_called_once_with(0,0,0)


def test_corrupt_bytes_are_rejected_not_removed_to_forge_an_ack(car_mocks):
    from elegoo_robot_car4.car import ControlProtocolError
    sock=car_mocks['socket']
    sock.recv.side_effect=[b'{drive_v1}', b'{d1_o\xffk}', b'{d2_ok}']
    with Car() as car:
        car.enable_analogue_drive()
        with pytest.raises(ControlProtocolError,match='ff'):
            car.drive_analogue(10,10,0)
        car.drive_analogue(0,0,0)
        assert json.loads(sock.sendall.call_args.args[0])['H']=='d2'


def test_split_ascii_ack_still_works(car_mocks):
    sock=car_mocks['socket']
    sock.recv.side_effect=[b'{drive_v2_38400}',b'{d1_',b'ok}']
    with Car() as car:
        car.enable_analogue_drive()
        car.drive_analogue(0,0,0)
        assert car._Car__serial_baud == 38400


def test_error_latch_sends_only_zero_until_released_and_acknowledged(mocker):
    axes={pg.CONTROLLER_AXIS_TRIGGERRIGHT:32767}
    e=analogue_engine(mocker,axes)
    e._GameEngine__neutral_required=True
    e._GameEngine__analogue.left=200
    mocker.patch('pygame.display.set_caption')
    e._GameEngine__handle_analogue_actions()
    e._GameEngine__car.drive_analogue.assert_called_with(0,0,0)
    assert e._GameEngine__neutral_required
    axes.clear()
    e._GameEngine__car.drive_analogue.side_effect=TimeoutError()
    with pytest.raises(TimeoutError):
        e._GameEngine__handle_analogue_actions()
    assert e._GameEngine__neutral_required
    e._GameEngine__car.stop.assert_called_once()
    e._GameEngine__car.drive_analogue.side_effect=None
    e._GameEngine__handle_analogue_actions()
    assert not e._GameEngine__neutral_required


def test_corrupt_drive_reply_does_not_crash_loop_or_replay_throttle(mocker):
    from elegoo_robot_car4.car import ControlProtocolError
    e=analogue_engine(mocker,{pg.CONTROLLER_AXIS_TRIGGERRIGHT:32767})
    e._GameEngine__dry_run=False
    e._GameEngine__car.is_far_from_the_ground.return_value=False
    e._GameEngine__car.drive_analogue.side_effect=[ControlProtocolError('bad bytes'),None]
    mocker.patch.object(e,'_GameEngine__display_new_frame',return_value=True)
    mocker.patch('pygame.time.Clock')
    mocker.patch('pygame.display.set_caption')
    mocker.patch('pygame.event.get',side_effect=[[],[],[pg.event.Event(pg.QUIT)]])
    e.run()
    assert e._GameEngine__neutral_required
    assert e._GameEngine__car.drive_analogue.call_args_list[-1].args==(0,0,0)
    e._GameEngine__car.stop.assert_called_once()


@pytest.mark.parametrize('travel,expected',[(0,0),(.25,.015625),(.5,.125),(.75,.421875),(1,1)])
def test_expo_gives_fine_control_and_preserves_endpoints(travel,expected):
    forward=.04+.96*travel
    assert mix_wheels(forward,0,0)==pytest.approx((expected,expected))
    assert mix_wheels(0,forward,0)==pytest.approx((-expected,-expected))
    steering=.08+.92*travel
    assert mix_wheels(0,0,steering)==pytest.approx((expected,-expected))
    assert expo(-travel)==pytest.approx(-expected)


def test_idle_camera_noise_cannot_change_commanded_angle():
    drive=AnalogueDrive()
    for i in range(300):
        noise=[-.079,.02,0,.079][i%4]
        assert drive.update(0,0,0,noise,i/30)[2]==0


@pytest.mark.parametrize('sign', [-1, 1])
def test_motor_floor_preserves_zero_direction_and_full_output(sign):
    assert motor_pwm(0) == 0
    assert motor_pwm(sign*1e-9) == pytest.approx(sign*30, abs=1e-6)
    assert motor_pwm(sign) == sign*200
    assert motor_pwm(sign*.125) == pytest.approx(sign*(30+170*.125))


def test_small_inputs_start_above_floor_and_neutral_stops():
    drive=AnalogueDrive(previous_time=-.1)
    assert drive.update(.041,0,0,0,0)[:2] == (30,30)
    assert drive.update(0,0,0,0,.1)[:2] == (0,0)
    assert drive.update(0,.041,0,0,.2)[:2] == (-30,-30)
    assert drive.update(.1,.1,1,0,.3)[:2] == (0,0)
    assert drive.update(0,0,.081,0,.4)[:2] == (30,-30)


def test_motor_floor_keeps_cancelled_inside_wheel_stopped():
    # Full throttle and steering cancel the inside wheel exactly.
    left,right=mix_wheels(1,0,1)
    assert motor_pwm(left)>30
    assert motor_pwm(right)==0


def test_camera_trace_reports_changes_and_periodic_unchanged_target(mocker,capsys):
    engine=GameEngine.__new__(GameEngine)
    engine._GameEngine__trace_camera=True
    mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.time.monotonic',side_effect=[0,.1,.2,1.2])
    engine._GameEngine__trace_camera_command(0,0)
    engine._GameEngine__trace_camera_command(.01,0)
    engine._GameEngine__trace_camera_command(1,-80)
    engine._GameEngine__trace_camera_command(1,-80)
    lines=capsys.readouterr().out.splitlines()
    assert len(lines)==3
    assert 'acknowledged_target=90deg' in lines[0]
    assert 'stick=+1.0000 acknowledged_target=10deg' in lines[1]
    assert 'acknowledged_target=10deg' in lines[2]


def test_camera_trace_is_opt_in(capsys):
    engine=GameEngine.__new__(GameEngine)
    engine._GameEngine__trace_camera_command(0,0)
    assert capsys.readouterr().out==''


@pytest.mark.parametrize('reverse', [False, True])
def test_moving_steering_has_strong_initial_differential(reverse):
    forward,backward=(0,1) if reverse else (1,0)
    left,right=mix_wheels(forward,backward,.081)
    assert motor_pwm(left)-motor_pwm(right)==pytest.approx(170/3,abs=.001)
    assert max(abs(motor_pwm(left)),abs(motor_pwm(right)))==200
    assert mix_wheels(forward,backward,-.081)==pytest.approx((right,left))
    assert mix_wheels(forward,backward,.079)==((-1,-1) if reverse else (1,1))


def test_moving_boost_blends_out_at_zero_throttle():
    pivot=mix_wheels(0,0,.4)
    assert mix_wheels(.040001,0,.4)==pytest.approx(pivot,abs=1e-12)
    # At low throttle a small steer still leaves both wheels moving forward.
    left,right=mix_wheels(.2,0,.081)
    assert left>right>0
    # Crossing the end of the throttle blend has no command discontinuity.
    trigger=.04+.96*(.25**(1/3))
    assert mix_wheels(trigger-1e-7,0,.2)==pytest.approx(
        mix_wheels(trigger+1e-7,0,.2),abs=1e-6)


def test_moving_steering_boost_obeys_acceleration_limit_and_immediate_stop():
    drive=AnalogueDrive(left=200,right=200,previous_time=0)
    left,right,_=drive.update(1,0,.081,0,1/30)
    assert left==200 and right==173
    assert drive.update(1,1,1,0,2/30)[:2]==(0,0)
