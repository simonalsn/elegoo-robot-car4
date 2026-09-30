#  Copyright (c) Michele De Stefano 2026.
import pickle
import socket
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from elegoo_robot_car4 import Car


@pytest.fixture(scope="function")
def socket_mock() -> MagicMock:
    return MagicMock(spec_set=socket.socket)


@pytest.fixture(scope="function")
def socket_class_mock(mocker, socket_mock: MagicMock) -> MagicMock:
    return mocker.patch(
        "elegoo_robot_car4.car.socket.socket",
        autospec=True,
        return_value=socket_mock,
    )


def mpu_data_generator() -> Iterator[dict[str, str | float | list[float]]]:
    t = 0.0  # seconds
    while True:
        # First 30 measurements are supposed to be taken while the robot is
        # still
        az = -1.0 if t >= 30.0 else 0.0
        gz = 10.0 if t >= 30.0 else 0.0
        yield {
            "id": "MPU_Request_test",
            "t": t,
            "a": [0.0, 0.0, az],  # robot is on a perfectly flat ground
            "g": [0.0, 0.0, gz],  # 10 degrees/second to the left
        }
        t += 1.0


@pytest.fixture(scope="function")
def get_mpu_data_mock(mocker) -> MagicMock:
    return mocker.patch.object(
        Car,
        "get_mpu_data",
        side_effect=mpu_data_generator(),
    )


@pytest.fixture(scope="function")
def set_head_angle_mock(mocker) -> MagicMock:
    return mocker.patch.object(
        Car,
        "set_head_angle",
    )


@pytest.fixture(scope="function")
def car_forward_mock(mocker) -> MagicMock:
    return mocker.patch.object(Car, "forward", autospec=True)


@pytest.fixture(scope="function")
def car_left_mock(mocker) -> MagicMock:
    return mocker.patch.object(Car, "left", autospec=True)


@pytest.fixture(scope="function")
def car_right_mock(mocker) -> MagicMock:
    return mocker.patch.object(Car, "right", autospec=True)


@pytest.fixture(scope="function")
def car_stop_mock(mocker) -> MagicMock:
    return mocker.patch.object(Car, "stop", autospec=True)


@pytest.fixture(scope="function")
def car_move_mock(mocker) -> MagicMock:
    return mocker.patch.object(Car, "move", autospec=True)


@pytest.fixture(scope="function")
def capture_request_mock(mocker, resources_path: Path) -> MagicMock:
    response_file = resources_path / "capture-response.pkl"
    with open(response_file, "rb") as f:
        response = pickle.load(f)
    return mocker.patch(
        "elegoo_robot_car4.car.req.get",
        autospec=True,
        return_value=response,
    )


@pytest.fixture(scope="function")
def yolo_model_mock(mocker) -> MagicMock:
    return MagicMock()


@pytest.fixture(scope="function")
def yolo_class_mock(mocker, yolo_model_mock: MagicMock) -> MagicMock:
    return mocker.patch(
        "elegoo_robot_car4.car.load_yolo",
        autospec=True,
        return_value=yolo_model_mock,
    )


@pytest.fixture(scope="function")
def car_mocks(
    socket_mock: MagicMock,
    socket_class_mock: MagicMock,
    get_mpu_data_mock: MagicMock,
    set_head_angle_mock: MagicMock,
    capture_request_mock: MagicMock,
    yolo_model_mock: MagicMock,
    yolo_class_mock: MagicMock,
) -> dict[str, MagicMock]:
    return {
        "socket": socket_mock,
        "socket_class": socket_class_mock,
        "get_mpu_data": get_mpu_data_mock,
        "set_head_angle": set_head_angle_mock,
        "capture_request": capture_request_mock,
        "yolo_model_mock": yolo_model_mock,
        "yolo_class_mock": yolo_class_mock,
    }


@pytest.fixture(scope="function")
def car_motion_mocks(
    car_mocks: dict[str, MagicMock],
    car_forward_mock: MagicMock,
    car_left_mock: MagicMock,
    car_right_mock: MagicMock,
    car_stop_mock: MagicMock,
    car_move_mock: MagicMock,
) -> dict[str, MagicMock]:
    car_mocks |= {
        "car_forward": car_forward_mock,
        "car_left": car_left_mock,
        "car_right": car_right_mock,
        "car_stop": car_stop_mock,
        "car_move": car_move_mock,
    }
    return car_mocks


@pytest.fixture(scope="function")
def frame_shape_hw() -> np.ndarray:
    return np.array([600, 800])
