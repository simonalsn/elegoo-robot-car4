#  Copyright (c) Michele De Stefano - 2026.
from unittest.mock import MagicMock

import numpy as np
import pytest

from elegoo_robot_car4.car import Car


def test_use_car_in_with_context(car_mocks: dict[str, MagicMock]) -> None:
    # given
    socket_mock = car_mocks["socket"]
    socket_class_mock = car_mocks["socket_class"]
    get_mpu_data_mock = car_mocks["get_mpu_data"]
    set_head_angle_mock = car_mocks["set_head_angle"]

    # when
    with Car() as car:
        pass

    # then
    assert car.state == "stop"
    socket_class_mock.assert_called_once()
    socket_mock.close.assert_called_once()
    set_head_angle_mock.assert_called_once()
    assert get_mpu_data_mock.call_count == 30


def test_constructor_with_dry_run(car_mocks: dict[str, MagicMock]) -> None:
    # given
    socket_mock = car_mocks["socket"]
    socket_class_mock = car_mocks["socket_class"]
    get_mpu_data_mock = car_mocks["get_mpu_data"]
    set_head_angle_mock = car_mocks["set_head_angle"]

    # when
    with Car(dry_run=True):
        pass

    # then
    socket_class_mock.assert_not_called()
    socket_mock.settimeout.assert_not_called()
    socket_mock.connect.assert_not_called()
    get_mpu_data_mock.assert_not_called()
    set_head_angle_mock.assert_not_called()


def test_setting_head_scan_step(car_mocks: dict[str, MagicMock]) -> None:
    # given
    new_head_scan_step = 27

    # when
    with Car() as car:
        car.head_angle_scan_step = new_head_scan_step

    # then
    expected_step_angle = 20
    assert expected_step_angle == car.head_angle_scan_step


def test_capture(car_mocks: dict[str, MagicMock]) -> None:
    # given
    with Car() as car:
        # when
        frame = car.capture()

    # then
    assert isinstance(frame, np.ndarray), "Correct frame type"
    assert len(frame.shape) == 3, "Correct frame shape size"
    assert frame.shape[0] < frame.shape[1], "Correct image rotation"
    assert frame.shape[-1] == 3, "Correct number of frame channels"


def test_capture_with_dry_run() -> None:
    # given
    with Car(dry_run=True) as car:
        # when
        frame = car.capture()

    # then
    assert frame.size == 0


def test_turn_by(car_mocks: dict[str, MagicMock]) -> None:
    pytest.importorskip("scipy", reason="Requires the navigation extra")
    # given
    angle: int = 30  # turn by 30 degrees, counterclockwise
    get_mpu_data_mock = car_mocks["get_mpu_data"]

    # when
    with Car() as car:
        initial_get_mpu_calls = get_mpu_data_mock.call_count
        car.turn_by(angle=angle)

    # then
    assert car.state == "stop"
    expected_get_mpu_calls = 4
    actual_get_mpu_calls = get_mpu_data_mock.call_count - initial_get_mpu_calls
    assert expected_get_mpu_calls == actual_get_mpu_calls


def test_move_no_command_received(car_mocks: dict[str, MagicMock]) -> None:
    # given
    socket_mock = car_mocks["socket"]

    # when
    with Car() as car:
        car.move()

    # then
    assert car.state == "stop"
    expected_call_arg = b'{"H": "stop", "N": 100}'
    socket_mock.sendall.assert_called_with(expected_call_arg)


def test_move_one_command_received(car_mocks: dict[str, MagicMock]) -> None:
    # given
    socket_mock = car_mocks["socket"]

    # when
    with Car() as car:
        car.forward(speed=40, lazy=True)
        car.move()

    # then
    expected_call_arg = b'{"H": "fw_40", "N": 102, "D1": 1, "D2": 40}'
    socket_mock.sendall.assert_called_with(expected_call_arg)
    assert car.state == "fw_40"


def test_move_many_commands_received(car_mocks: dict[str, MagicMock]) -> None:
    # given
    socket_mock = car_mocks["socket"]

    # when
    with Car() as car:
        car.forward(speed=100, lazy=True)
        car.backward_left(speed=30, lazy=True)
        car.forward_left(speed=70, lazy=True)
        car.move()

    # then
    socket_mock.sendall.assert_not_called()
    assert car.state == "stop"


def test_no_state_change_when_receiving_consecutive_identical_commands(
    car_mocks: dict[str, MagicMock],
) -> None:
    # given
    socket_mock = car_mocks["socket"]

    # when
    with Car() as car:
        car.forward(speed=40, lazy=True)
        car.move()
        car.forward(speed=40, lazy=True)
        car.move()

    # then
    expected_call_arg = b'{"H": "fw_40", "N": 102, "D1": 1, "D2": 40}'
    socket_mock.sendall.assert_called_once_with(expected_call_arg)
    assert car.state == "fw_40"


def test_lazy_change_state_to_stop(car_mocks: dict[str, MagicMock]) -> None:
    # given
    socket_mock = car_mocks["socket"]

    # when
    with Car() as car:
        car.forward(speed=40, lazy=True)
        car.move()
        car.stop(lazy=True)
        car.move()

    # then
    expected_call_arg = b'{"H": "stop", "N": 100}'
    socket_mock.sendall.assert_called_with(expected_call_arg)
    assert car.state == "stop"


def test_find_best_front_direction(
    mocker, car_mocks: dict[str, MagicMock]
) -> None:
    # given
    scan_range = (-100, -30)
    mocker.patch.object(
        Car,
        "get_ultrasonic_value",
        side_effect=[30.0, 25.0, 8.0, 150.0, 20.0, 25.0],
    )

    # when
    with Car() as car:
        best_angle, best_distance = car.find_best_front_direction(scan_range)

    # then
    expected_best_angle = -50
    expected_best_distance = 150.0
    assert expected_best_angle == best_angle
    assert expected_best_distance == best_distance


def test_set_head_angle_with_dry_run(car_mocks: dict[str, MagicMock]) -> None:
    # given
    socket_mock = car_mocks["socket"]

    # when
    with Car(dry_run=True) as car:
        car.set_head_angle(angle=90)

    # then
    socket_mock.recv.assert_not_called()


def test_clear_all_states_with_dry_run(car_mocks: dict[str, MagicMock]) -> None:
    # given
    socket_mock = car_mocks["socket"]

    # when
    with Car(dry_run=True) as car:
        car.clear_all_states()

    # then
    socket_mock.recv.assert_not_called()


def test_toggle_vision_tracking_mode(car_mocks: dict[str, MagicMock]) -> None:
    # given
    yolo_class_mock = car_mocks["yolo_class_mock"]
    car = Car()

    # then
    assert not car.vision_tracking_is_on

    # when
    car.toggle_vision_tracking()

    # then
    assert car.vision_tracking_is_on
    yolo_class_mock.assert_called_once()

    # when
    car.toggle_vision_tracking()

    # then
    assert not car.vision_tracking_is_on
    yolo_class_mock.assert_called_once()


def test_vision_tracking_when_it_is_enabled(
    car_mocks: dict[str, MagicMock],
) -> None:
    # given
    car = Car()
    car.toggle_vision_tracking()
    test_frame = np.array([])
    yolo_model_mock = car_mocks["yolo_model_mock"]

    # when
    car.track(test_frame)

    # then
    yolo_model_mock.track.assert_called_once()


def test_vision_tracking_when_it_is_disabled(
    car_mocks: dict[str, MagicMock],
) -> None:
    # given
    car = Car()
    test_frame = np.array([])
    yolo_model_mock = car_mocks["yolo_model_mock"]

    # when
    car.track(test_frame)

    # then
    yolo_model_mock.track.assert_not_called()
