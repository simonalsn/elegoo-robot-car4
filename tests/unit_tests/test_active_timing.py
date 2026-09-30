from threading import Event, Lock
from unittest.mock import MagicMock
import json
import socket
import struct
import time

import numpy as np
import pytest

from elegoo_robot_car4.car import Car
from elegoo_robot_car4.connection import Connection
from elegoo_robot_car4.udp_video import UdpVideo, FrameAssembler, HEADER, STATUS
from elegoo_robot_car4.video_adaptation import VideoAdaptation
from elegoo_robot_car4.camera_presets import apply_preset


class RecordingCar:
    vision_tracking_is_on = False

    def __init__(self):
        self.commands = []
        self.updated = Event()
        self.stopped_after_motion = Event()

    def is_far_from_the_ground(self):
        return False

    def drive_analogue(self, left, right, head, latest=None):
        demand = latest() if latest is not None else (left, right, head)
        if demand[:2] == (0, 0) and any(command[0] for command in self.commands):
            self.stopped_after_motion.set()
        self.commands.append(demand)
        if len(self.commands) >= 3:
            self.updated.set()

    def stop(self):
        pass

    def enable_analogue_drive(self):
        pass

    def cancel(self):
        pass

    def disconnect(self):
        pass


def cleanup(link):
    link.close()
    link.executor.shutdown(wait=True)


def test_neutral_replaces_movement_during_delayed_ground_reply():
    entered, release = Event(), Event()
    link = Connection('unused', 'udp')
    car = link.car = RecordingCar()
    def ground():
        entered.set()
        assert release.wait(2)
        return False
    car.is_far_from_the_ground = ground
    link.update_demand((150, 150, 0))
    link.submit(lambda: link.exchange((150, 150, 0), latest=link.current_demand))
    try:
        assert entered.wait(2)
        link.update_demand((0, 0, 0))
        release.set()
        link.pending.result(timeout=2)
        assert car.commands == [(0, 0, 0)]
    finally:
        release.set()
        cleanup(link)


def test_control_refresh_is_independent_of_gui_and_expires_without_input():
    link = Connection('unused', 'udp')
    car = link.car = RecordingCar()
    link.update_demand((100, 100, 0))
    try:
        link.start_control()
        assert car.updated.wait(2)
        assert len(car.commands) >= 3
        assert car.stopped_after_motion.wait(2)
        assert link.input_expired
        link.update_demand((100, 100, 0))
        assert link.current_demand() == (0, 0, 0)
        link.update_demand((0, 0, 0))
        link.update_demand((100, 100, 0))
        assert link.current_demand() == (100, 100, 0)
    finally:
        cleanup(link)


def test_latest_input_is_checked_after_uart_pacing(mocker):
    car = Car(dry_run=True)
    car._Car__dry_run = False
    car._Car__analogue_ready = True
    car._Car__socket = MagicMock()
    car._Car__socket.recv.return_value = b'{d1_ok}'
    current = [(100, 100, 0)]
    def wait(_):
        current[0] = (0, 0, 0)
        return False
    car._Car__cancel_event = MagicMock()
    car._Car__cancel_event.wait.side_effect = wait
    car._Car__cancel_event.is_set.return_value = False
    car.drive_analogue(100, 100, 0, latest=lambda: current[0])
    packet = json.loads(car._Car__socket.sendall.call_args.args[0])
    assert packet['D1'] == packet['D2'] == 0
    car.disconnect()


def test_close_cancels_connection_initialization():
    entered = Event()
    def factory(**kwargs):
        assert kwargs['initialize'] is False
        entered.set()
        assert kwargs['cancel_event'].wait(2)
        raise ConnectionAbortedError('cancelled')
    link = Connection('unused', 'udp', car_factory=factory)
    link.submit(link.connect)
    assert entered.wait(2)
    link.close()
    with pytest.raises(ConnectionAbortedError):
        link.pending.result(timeout=1)
    link.executor.shutdown(wait=True)


def test_dashboard_connect_skips_calibration_and_head_command(mocker):
    mocker.patch('elegoo_robot_car4.car.socket.socket')
    calibration = mocker.patch.object(Car, '_Car__compute_mpu_offsets')
    head = mocker.patch.object(Car, 'set_head_angle')
    car = Car('unused', initialize=False, stop_before_init=True)
    calibration.assert_not_called()
    head.assert_not_called()
    car.disconnect()


def receiver():
    video = UdpVideo.__new__(UdpVideo)
    video._stop = Event()
    video._lock = Lock()
    video._socket = MagicMock()
    video._token = 123
    video._assembler = FrameAssembler(123)
    video._latest = None
    video.frames = video.stale_frames = 0
    video.sender_status = None
    return video


def test_decode_delay_cannot_refresh_an_old_frame(mocker):
    video = receiver()
    now = [10.0]
    packet = HEADER.pack(b'EVF1', 123, 1, 6, 0, 1)+b'\xff\xd8ok\xff\xd9'
    mocker.patch.object(video, '_receive', return_value=(packet, 10.0))
    mocker.patch('elegoo_robot_car4.udp_video.select.select', return_value=([], [], []))
    mocker.patch('elegoo_robot_car4.udp_video.time.monotonic', side_effect=lambda: now[0])
    def decode(*args):
        now[0] = 11.0
        video._stop.set()
        return np.zeros((2, 2, 3), np.uint8)
    mocker.patch('elegoo_robot_car4.udp_video.cv.imdecode', side_effect=decode)
    video._run()
    assert video.frames == 0 and video.stale_frames == 1
    assert video.latest() == (None, float('inf'))


def test_kernel_receive_timestamp_includes_socket_backlog(mocker):
    video = receiver()
    video._timestamp_option = 35
    video._socket.recvmsg.return_value = (b'packet', [(socket.SOL_SOCKET, 35, struct.pack('@ll', 100, 0))], 0, None)
    mocker.patch('elegoo_robot_car4.udp_video.time.time', return_value=101.0)
    mocker.patch('elegoo_robot_car4.udp_video.time.monotonic', return_value=50.0)
    assert video._receive() == (b'packet', 49.0)


def test_sender_counters_require_matching_subscription():
    video = receiver()
    video._feed(STATUS.pack(b'EVT1', 456, 10, 2, 3, 280000, 10), 0)
    assert video.sender_status is None
    video._feed(STATUS.pack(b'EVT1', 123, 10, 2, 3, 280000, 10), 0)
    assert video.sender_status['oversized'] == 2
    assert video.sender_status['failed'] == 3


def test_adaptation_is_bounded_and_keeps_driving_presets():
    adaptation = VideoAdaptation()
    assert adaptation.recommend({}, 3, 'fast', 20, 10) is None
    assert adaptation.recommend({}, 3, 'drive', 15, 10) is None
    assert adaptation.recommend({}, 3, 'balanced', 10, 10) is None
    assert adaptation.recommend({}, 3, 'detail', 10, 10) == 15
    assert adaptation.recommend({}, 3, 'detail', 15, 11) is None
    assert adaptation.recommend({}, .1, 'detail', 15, 15) is None
    assert adaptation.recommend({'last_jpeg_bytes': 240000}, .1, 'detail', 35, 20) == 40
    assert adaptation.recommend({}, 3, 'detail', 40, 30) is None


def test_quality_adaptation_does_not_change_resolution():
    get = MagicMock()
    get.return_value.json.return_value = dict(quality=20, framesize=13)
    apply_preset('unused', 'quality:20', get)
    assert get.call_count == 2
    assert get.call_args_list[0].kwargs['params'] == {'var': 'quality', 'val': 20}


def test_cancelled_preset_does_not_send_remaining_camera_writes():
    cancel = Event()
    get = MagicMock()
    def first(*args, **kwargs):
        cancel.set()
        return MagicMock()
    get.side_effect = first
    with pytest.raises(ValueError, match='cancelled'):
        apply_preset('unused', 'detail', get, cancel)
    assert get.call_count == 1


def test_slow_http_capture_does_not_block_control(mocker):
    from elegoo_robot_car4.http_video import HttpVideo
    entered, release = Event(), Event()
    session = mocker.patch('elegoo_robot_car4.http_video.requests.Session').return_value.__enter__.return_value
    def get(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        raise ValueError('delayed capture')
    session.get.side_effect = get
    video = HttpVideo('unused')
    link = Connection('unused', 'http')
    car = link.car = RecordingCar()
    try:
        assert entered.wait(2)
        link.update_demand((0, 0, 0))
        link.start_control()
        assert car.updated.wait(1)
        assert len(car.commands) >= 3
    finally:
        video.close()
        release.set()
        video._thread.join(2)
        cleanup(link)


@pytest.mark.parametrize('stop_action', ['neutral', 'both', 'stop'])
def test_active_dashboard_replaces_pending_drive_before_sensor_reply(monkeypatch, mocker, stop_action):
    import pygame as pg
    from elegoo_robot_car4.elegoo_smartcar_control import GameEngine
    monkeypatch.setenv('SDL_VIDEODRIVER', 'dummy')
    monkeypatch.setenv('SDL_AUDIODRIVER', 'dummy')
    pg.init()
    car = RecordingCar()
    entered, release = Event(), Event()
    blocked = [False]
    sent_before_release = [None]
    def ground():
        if any(command[0] for command in car.commands) and not blocked[0]:
            blocked[0] = True
            entered.set()
            assert release.wait(2)
            sent_before_release[0] = len(car.commands)
        return False
    car.is_far_from_the_ground = ground
    mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.Car', return_value=car)
    video = mocker.patch('elegoo_robot_car4.elegoo_smartcar_control.UdpVideo').return_value
    video.latest.side_effect = lambda: (np.zeros((600, 800, 3), np.uint8), .02)
    video.frames = 1
    apply = mocker.patch('elegoo_robot_car4.camera_presets.apply_preset')
    mocker.patch('pygame.key.get_focused', return_value=True)
    mocker.patch.object(GameEngine, '_GameEngine__render_dashboard')
    axes = {}
    pad = MagicMock()
    pad.attached.return_value = True
    pad.get_button.return_value = False
    pad.get_axis.side_effect = lambda axis: axes.get(axis, 0)
    phase = ['ready']
    started = time.monotonic()
    try:
        with GameEngine('unused', video='udp', analogue_drive=True) as engine:
            engine._GameEngine__joysticks = {1: pad}
            def events():
                assert time.monotonic()-started < 3
                if phase[0] == 'ready' and engine._GameEngine__ui.status == 'Ready':
                    assert engine._GameEngine__ui.preset == 'balanced'
                    assert not engine._GameEngine__ui.preset_pending
                    assert apply.call_args.args[1] == 'balanced'
                    axes[pg.CONTROLLER_AXIS_TRIGGERRIGHT] = 32767
                    phase[0] = 'driving'
                if phase[0] == 'driving' and entered.is_set():
                    phase[0] = 'stopping'
                    if stop_action == 'both':
                        axes[pg.CONTROLLER_AXIS_TRIGGERLEFT] = 32767
                    else:
                        axes.clear()
                    if stop_action == 'stop':
                        return [pg.event.Event(pg.KEYDOWN, key=pg.K_SPACE)]
                elif phase[0] == 'stopping':
                    phase[0] = 'released'
                    release.set()
                if sent_before_release[0] is not None and len(car.commands) > sent_before_release[0]:
                    return [pg.event.Event(pg.QUIT)]
                return []
            mocker.patch('pygame.event.get', side_effect=events)
            engine.run()
            assert any(command[0] for command in car.commands)
            assert all(command[:2] == (0, 0) for command in car.commands[sent_before_release[0]:])
    finally:
        release.set()
        pg.quit()
