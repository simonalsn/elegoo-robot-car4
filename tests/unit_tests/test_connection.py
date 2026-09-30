"""Reconnect I/O checks without connecting to hardware."""
from concurrent.futures import Future
from threading import Event
from unittest.mock import MagicMock

from elegoo_robot_car4.connection import Connection


class ImmediateExecutor:
    def submit(self, function, *args):
        result = Future()
        try:
            result.set_result(function(*args))
        except Exception as exc:
            result.set_exception(exc)
        return result

    def shutdown(self, **kwargs):
        pass


class SteppedConnection(Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.controlling = False

    def start_control(self):
        self.controlling = True

    def poll(self):
        if not self.controlling:
            return super().poll()
        if self._cancel.is_set():
            self.controlling = False
            return True, None
        try:
            return True, self.exchange(self.current_demand(), latest=self.current_demand)
        except Exception as exc:
            self.controlling = False
            return False, exc


def test_connect_replaces_socket_handshake_video_and_starts_zero():
    first, second = MagicMock(), MagicMock()
    factory = MagicMock(side_effect=[first, second])
    videos = MagicMock()
    link = Connection('test.invalid', 'udp', car_factory=factory, video_factory=videos)
    link.connect()
    video1 = link.video
    link.connect()
    first.stop.assert_called_once()
    first.disconnect.assert_called_once()
    video1.close.assert_called_once()
    second.enable_analogue_drive.assert_called_once()
    second.drive_analogue.assert_called_once_with(0, 0, 0)
    assert factory.call_args.kwargs['stop_before_init']
    link.close()
    link.executor.shutdown(wait=True)


def test_handshake_failure_closes_partial_connection():
    car = MagicMock()
    car.enable_analogue_drive.side_effect = TimeoutError('no firmware reply')
    link = Connection('test.invalid', 'udp', car_factory=MagicMock(return_value=car))
    link.submit(link.connect)
    link.executor.shutdown(wait=True)
    success, error = link.poll()
    assert not success and isinstance(error, TimeoutError)
    car.disconnect.assert_called_once()
    assert link.car is None and link.video is None


def test_slow_io_does_not_block_poll_or_queue_more_demands():
    entered, release = Event(), Event()
    def slow():
        entered.set()
        assert release.wait(5)
        return 'done'
    link = Connection('test.invalid', 'udp')
    try:
        assert link.submit(slow)
        assert entered.wait(2)
        assert link.poll() is None
        assert not link.submit(lambda: 'stale motor command')
    finally:
        release.set()
        link.executor.shutdown(wait=True)
    assert link.poll() == (True, 'done')
    assert link.poll() is None


def test_raised_car_overrides_moving_demand():
    link = Connection('test.invalid', 'udp')
    link.car = MagicMock()
    link.car.is_far_from_the_ground.return_value = True
    raised, demand, _, _, frame = link.exchange((100, -100, 20))
    assert raised and demand == (0, 0, 20) and frame is None
    link.car.drive_analogue.assert_called_once_with(0, 0, 20)
    link.close()
    link.executor.shutdown(wait=True)


def test_stop_during_sensor_query_cancels_unsent_motor_demand():
    link = Connection('test.invalid', 'udp')
    link.car = MagicMock()
    generation = link.generation
    def ground():
        link.invalidate()  # UI requests Stop while the sensor call is pending.
        return False
    link.car.is_far_from_the_ground.side_effect = ground
    link.exchange((180, 180, 0), generation)
    link.car.drive_analogue.assert_called_once_with(0, 0, 0)
    link.close()
    link.executor.shutdown(wait=True)


def test_failed_car_initialization_closes_socket_before_retry(mocker):
    from elegoo_robot_car4.car import Car
    socket = mocker.patch('elegoo_robot_car4.car.socket.socket').return_value
    stop = mocker.patch.object(Car, 'stop')
    calibration = mocker.patch.object(Car, '_Car__compute_mpu_offsets', side_effect=TimeoutError('IMU'))
    import pytest
    with pytest.raises(TimeoutError):
        Car('test.invalid', stop_before_init=True)
    stop.assert_called_once()
    calibration.assert_called_once()
    socket.close.assert_called_once()
