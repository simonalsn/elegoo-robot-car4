from unittest.mock import MagicMock

import pygame as pg
import pytest

from elegoo_robot_car4 import Car
from elegoo_robot_car4.elegoo_smartcar_control import GameEngine


def test_closed_control_socket_fails_instead_of_spinning(car_mocks):
    car_mocks["socket"].recv.return_value = b""
    with Car() as car, pytest.raises(ConnectionError, match="closed"):
        car.is_far_from_the_ground()


def test_heartbeats_do_not_extend_command_deadline(car_mocks, mocker):
    car_mocks["socket"].recv.return_value = b"{Heartbeat}"
    with Car() as car:
        clock = iter([0.0, 0.0, 0.0, 0.5, 1.0, 2.1])
        mocker.patch("elegoo_robot_car4.car.time.monotonic", side_effect=clock)
        with pytest.raises(TimeoutError, match="timed out"):
            car.is_far_from_the_ground()
    assert car_mocks["socket"].recv.call_count == 2


def test_truncated_jpeg_is_rejected(car_mocks):
    response = car_mocks["capture_request"].return_value
    response._content = b"\xff\xd8truncated"
    with Car() as car, pytest.raises(ValueError, match="Incomplete"):
        car.capture()


def engine_for_loop(mocker):
    engine = GameEngine.__new__(GameEngine)
    engine._GameEngine__car = MagicMock()
    engine._GameEngine__dry_run = False
    engine._GameEngine__car.is_far_from_the_ground.return_value = True
    mocker.patch.object(engine, "_GameEngine__display_new_frame")
    mocker.patch("pygame.time.Clock")
    caption = mocker.patch("pygame.display.set_caption")
    return engine, caption


def test_escape_works_while_ground_guard_blocks_driving(mocker):
    engine, caption = engine_for_loop(mocker)
    mocker.patch("pygame.event.get", side_effect=[[], [pg.event.Event(pg.KEYDOWN, key=pg.K_ESCAPE)]])
    engine.run()
    engine._GameEngine__car.stop.assert_called_once()
    engine._GameEngine__car.move.assert_not_called()
    assert "Car raised" in caption.call_args.args[0]


def test_bad_camera_frame_stops_then_recovers_without_driving(mocker):
    engine, caption = engine_for_loop(mocker)
    engine._GameEngine__display_new_frame.side_effect = [ValueError("Incomplete camera JPEG"), None]
    mocker.patch("pygame.event.get", side_effect=[[], [], [pg.event.Event(pg.QUIT)]])
    engine.run()
    assert engine._GameEngine__car.stop.call_count == 2
    engine._GameEngine__car.move.assert_not_called()
    assert "Car raised" in caption.call_args.args[0]


def test_cleanup_requests_stop_even_after_loop_error(mocker):
    engine, _ = engine_for_loop(mocker)
    engine._GameEngine__car.stop.side_effect = OSError("disconnected")
    engine.release_resources()
    engine._GameEngine__car.disconnect.assert_called_once()


def test_stale_udp_video_blocks_driving_but_quit_still_works(mocker):
    engine, caption = engine_for_loop(mocker)
    engine._GameEngine__display_new_frame.return_value = False
    mocker.patch("pygame.event.get", side_effect=[[], [pg.event.Event(pg.QUIT)]])
    engine.run()
    engine._GameEngine__car.stop.assert_called_once()
    engine._GameEngine__car.move.assert_not_called()
    engine._GameEngine__car.is_far_from_the_ground.assert_not_called()
    assert "stale" in caption.call_args.args[0]


def test_cleanup_unsubscribes_udp_video(mocker):
    engine, _ = engine_for_loop(mocker)
    engine._GameEngine__video = MagicMock()
    engine.release_resources()
    engine._GameEngine__video.close.assert_called_once()
