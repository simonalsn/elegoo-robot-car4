#  Copyright (c) Michele De Stefano - 2026.
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ultralytics.engine.results import Results

from elegoo_robot_car4 import Car


class PersonFollower:
    """
    A simmple AI that is able to follow a person.
    """

    __car: Car
    __frame_shape: np.ndarray
    __center: np.ndarray
    __horizontal_threshold: float
    __distance_threshold: float

    def __init__(self, car: Car, frame_shape_hw: np.ndarray) -> None:
        """
        Constructor.

        Args:
            car:            The car instance.

            frame_shape_hw: The shape of the captured frames (height, width),
                            which is the format returned by the camera (OpenCV
                            format).
        """
        self.__car = car
        self.__frame_center = frame_shape_hw[::-1] * 0.5
        self.__horizontal_threshold = frame_shape_hw[1] * 0.15
        self.__distance_threshold = 0.4

    def follow(self, last_track_results: list[Results]) -> None:
        """
        The action to call at every time step.

        Args:
            last_track_results: Last track results coming from a YOLO model
                                track call.
        """
        if not last_track_results:
            return
        result = last_track_results[0]
        if result.boxes.xywh.numel() > 0:
            box_xywh = result.boxes.xywh[0].cpu().numpy()
            box_center = box_xywh[:2]
            displacement = box_center - self.__frame_center
            norm_box_area = np.prod(result.boxes.xywhn[0].cpu().numpy()[2:])
            if abs(displacement[0]) < self.__horizontal_threshold:
                if norm_box_area < self.__distance_threshold:
                    self.__car.forward(speed=150, lazy=True)
                else:
                    self.__car.stop(lazy=True)
            elif displacement[0] > 0:
                self.__car.right(lazy=True)
            else:
                self.__car.left(lazy=True)
        else:
            self.__car.stop(lazy=True)
        self.__car.move()
