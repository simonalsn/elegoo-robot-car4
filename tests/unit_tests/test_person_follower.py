#  Copyright (c) Michele De Stefano - 2026.
from unittest.mock import MagicMock

import numpy as np
import pytest
torch = pytest.importorskip("torch", reason="Requires the vision extra")
Results = pytest.importorskip("ultralytics.engine.results", reason="Requires the vision extra").Results

from elegoo_robot_car4 import Car
from elegoo_robot_car4.person_follower import PersonFollower


@pytest.fixture(scope="function")
def follower(
    car_motion_mocks: dict[str, MagicMock], frame_shape_hw: np.ndarray
) -> PersonFollower:
    car = Car()
    return PersonFollower(car, frame_shape_hw)


def test_follow_without_track_results(
    car_motion_mocks: dict[str, MagicMock],
    follower: PersonFollower,
) -> None:
    # given, when
    follower.follow(last_track_results=[])

    # then
    car_motion_mocks["car_move"].assert_not_called()


def test_follow_with_no_track_boxes(
    car_motion_mocks: dict[str, MagicMock],
    follower: PersonFollower,
) -> None:
    # given
    last_track_results = [
        Results(
            orig_img=np.array([]),
            path="",
            names={},
            boxes=torch.Tensor(size=(0, 6)),
        )
    ]

    # when
    follower.follow(last_track_results=last_track_results)

    # then
    car_motion_mocks["car_stop"].assert_called_once()
    car_motion_mocks["car_move"].assert_called_once()


def test_follow_with_detected_person_close(
    car_motion_mocks: dict[str, MagicMock],
    follower: PersonFollower,
    frame_shape_hw: np.ndarray,
) -> None:
    # given
    last_track_results = [
        Results(
            orig_img=np.ndarray(shape=frame_shape_hw),
            path="",
            names={},
            boxes=torch.Tensor([[0.0, 0.0, 800.0, 600.0, 0.9, 0.0]]),
        )
    ]

    # when
    follower.follow(last_track_results=last_track_results)

    # then
    car_motion_mocks["car_forward"].assert_not_called()
    car_motion_mocks["car_left"].assert_not_called()
    car_motion_mocks["car_right"].assert_not_called()
    car_motion_mocks["car_stop"].assert_called_once()
    car_motion_mocks["car_move"].assert_called_once()


def test_follow_with_detected_person_far_away(
    car_motion_mocks: dict[str, MagicMock],
    follower: PersonFollower,
    frame_shape_hw: np.ndarray,
) -> None:
    # given
    last_track_results = [
        Results(
            orig_img=np.ndarray(shape=frame_shape_hw),
            path="",
            names={},
            boxes=torch.Tensor([[398.0, 298.0, 402.0, 302.0, 0.9, 0.0]]),
        )
    ]

    # when
    follower.follow(last_track_results=last_track_results)

    # then
    car_motion_mocks["car_forward"].assert_called_once()
    car_motion_mocks["car_left"].assert_not_called()
    car_motion_mocks["car_right"].assert_not_called()
    car_motion_mocks["car_stop"].assert_not_called()
    car_motion_mocks["car_move"].assert_called_once()


def test_follow_with_detected_person_on_the_left(
    car_motion_mocks: dict[str, MagicMock],
    follower: PersonFollower,
    frame_shape_hw: np.ndarray,
) -> None:
    # given
    last_track_results = [
        Results(
            orig_img=np.ndarray(shape=frame_shape_hw),
            path="",
            names={},
            boxes=torch.Tensor([[0.0, 298.0, 100.0, 302.0, 0.9, 0.0]]),
        )
    ]

    # when
    follower.follow(last_track_results=last_track_results)

    # then
    car_motion_mocks["car_forward"].assert_not_called()
    car_motion_mocks["car_left"].assert_called_once()
    car_motion_mocks["car_right"].assert_not_called()
    car_motion_mocks["car_stop"].assert_not_called()
    car_motion_mocks["car_move"].assert_called_once()


def test_follow_with_detected_person_on_the_right(
    car_motion_mocks: dict[str, MagicMock],
    follower: PersonFollower,
    frame_shape_hw: np.ndarray,
) -> None:
    # given
    last_track_results = [
        Results(
            orig_img=np.ndarray(shape=frame_shape_hw),
            path="",
            names={},
            boxes=torch.Tensor([[700.0, 298.0, 800.0, 302.0, 0.9, 0.0]]),
        )
    ]

    # when
    follower.follow(last_track_results=last_track_results)

    # then
    car_motion_mocks["car_forward"].assert_not_called()
    car_motion_mocks["car_left"].assert_not_called()
    car_motion_mocks["car_right"].assert_called_once()
    car_motion_mocks["car_stop"].assert_not_called()
    car_motion_mocks["car_move"].assert_called_once()
