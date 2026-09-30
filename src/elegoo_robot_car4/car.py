#  Copyright (c) Michele De Stefano - 2026.
from __future__ import annotations

import json
import re
import socket
import time
import threading
from collections import deque
from collections.abc import Callable
from contextlib import AbstractContextManager, suppress
from typing import TYPE_CHECKING

import cv2 as cv
import numpy as np
import requests as req
from .optional_features import load_yolo, navigation_integrator

if TYPE_CHECKING:
    from ultralytics.engine.model import Model
    from ultralytics.engine.results import Results


class ControlProtocolError(OSError):
    """A control reply was corrupted; its acknowledgement cannot be trusted."""


class Car(AbstractContextManager):
    """
    Controller of the Elegoo Smart Robot Car v4.0.

    Author:
        Michele De Stefano
    """

    # WARNING: Sometimes it is needed to sleep between different method calls,
    # otherwise the robot starts not responding on the socket.

    TRACKING_MODE: int = 1
    OBSTACLE_AVOIDANCE_MODE: int = 2
    FOLLOW_MODE: int = 3

    IR_LEFT: int = 0
    IR_MIDDLE: int = 1
    IR_RIGHT: int = 2

    __no_response_cmds: list[str] = [
        "stop",
        "fw",
        "bw",
        "l",
        "r",
        "fl",
        "fr",
        "bl",
        "br",
    ]
    __heartbeat_re: re.Pattern = re.compile(r"\{Heartbeat\}")
    __ok_re: re.Pattern = re.compile(r"\{ok\}")

    __num_quant_steps: int = 1 << 16

    # +/- 2g, quantized with 16 bit (it is 1 / 16384)
    __accel_quantum: float = 4.0 / __num_quant_steps

    # +/- 250 deg/s quantized with 16 bit (it is about 1 / 131)
    __gyro_quantum: float = 500.0 / __num_quant_steps

    __yolo_model: str = "yolo26n.pt"
    __vision_tracking_on: bool

    log: bool
    __state: str
    __dry_run: bool
    __cmd_queue: deque
    __recv_msg_queue: str
    __head_servo_angle: int
    __head_angle_scan_step: int = 10
    __a_offsets: np.ndarray
    __g_offsets: np.ndarray
    __capture_endpoint: str
    __socket: socket.socket
    __tracking_model: Model | None

    # Ultrasonic regression coefficients for sensor -> real measurement
    # conversion
    __ultrasonic_q: float = -0.37779223
    __ultrasonic_m: float = 1.26030353

    def __init__(
        self,
        ip: str = "192.168.4.1",
        port: int = 100,
        log: bool = False,
        dry_run: bool = False,
        stop_before_init: bool = False,
        initialize: bool = True,
        cancel_event: threading.Event | None = None,
    ):
        """
        Initializes the connection with the car.

        Args:
            ip:      IP address (numeric or symbolic) of the car.
            port:    Listening port on the car.
            log:     Put this to True if you want to see logging information.
            dry_run: Put this to True if you want to simulate commands without
                     execution.
        """
        super().__init__()
        self.__state = "stop"
        self.log = log
        self.__dry_run = dry_run
        self.__cancel_event = cancel_event or threading.Event()
        self.__cmd_queue = deque()
        self.__recv_msg_queue = ""
        self.__command_ready_at = 0.0
        self.__serial_baud = 9600
        self.__drive_sequence = 0
        self.__analogue_ready = False
        self.__head_servo_angle = 90
        self.__a_offsets = np.zeros(3)
        self.__g_offsets = np.zeros(3)
        self.__capture_endpoint = f"http://{ip}/capture"
        self.__tracking_model = None
        self.__vision_tracking_on = False
        if not dry_run:
            self.__socket = socket.socket()
            # Set a timeout of 2 seconds for all the blocking operations on
            # this socket
            self.__socket.settimeout(2)
            try:
                self.__socket.connect((ip, port))
                self.__socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                if stop_before_init:
                    self.stop()
                if initialize:
                    self.__compute_mpu_offsets()
                    self.set_head_angle()
            except Exception:
                self.__socket.close()
                raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    @property
    def state(self) -> str:
        return self.__state

    @property
    def head_angle_scan_step(self) -> int:
        """
        Retrieves the currently set scan step for head angles.

        Returns:
            The currently set scan step (degrees) for head angles.
        """
        return self.__head_angle_scan_step

    @head_angle_scan_step.setter
    def head_angle_scan_step(self, step: int) -> None:
        """
        Sets the current scan step for head angles.

        Args:
            step:   The new step (in degrees). The value is clipped between
                    10 and 80 degrees because this is the maximum range of
                    the servo. Furthermore, the step is rounded down to the
                    nearest ten, because the servo mounted on the robot is not
                    able to move with a step that is less than 10 degrees.
        """
        rounded_step = int(step * 0.1) * 10
        self.__head_angle_scan_step = np.clip(rounded_step, 10, 80)

    @property
    def vision_tracking_is_on(self) -> bool:
        return self.__vision_tracking_on

    def toggle_vision_tracking(self) -> None:
        """
        Toggles the vision-tracking mode.

        Args:
            on: If True, switches the vision-tracking mode on. Otherwise it
                switches it off.
        """
        enabled = not self.__vision_tracking_on
        model = load_yolo(self.__yolo_model) if enabled else None
        self.__tracking_model = model
        self.__vision_tracking_on = enabled

    def disconnect(self) -> None:
        """
        Closes the connection with the robot car.
        """
        with suppress(BaseException):
            self.__socket.close()

    def cancel(self):
        self.__cancel_event.set()
        with suppress(OSError, AttributeError):
            self.__socket.shutdown(socket.SHUT_RDWR)

    def capture(self) -> np.ndarray:
        """
        Takes a snapshot from the robot's camera.

        Returns:
            A snapshot from the robot's camera. The frame is in BGR format
            with (height, width, 3) shape (OpenCV format).
        """
        if self.__dry_run:
            return np.array([])
        r = req.get(self.__capture_endpoint, timeout=(2, 3))
        r.raise_for_status()
        if not (r.content.startswith(b"\xff\xd8") and r.content.endswith(b"\xff\xd9")):
            raise ValueError("Incomplete camera JPEG")
        frame = np.frombuffer(r.content, dtype=np.uint8)
        decoded = cv.imdecode(frame, cv.IMREAD_UNCHANGED)
        if decoded is None:
            raise ValueError("Camera JPEG could not be decoded")
        return decoded

    def track(self, frame: np.ndarray, **kwargs) -> list[Results]:
        """
        Tracks detected items on a frame.

        Args:
            frame:  Frame returned by the capture method.

            kwargs: Keyword arguments to be passed to YOLO model's track
                    method (look at YOLO documentation), further to the
                    frame argument.

        Returns:
            List of results obtained from a YOLO model.
        """
        results = (
            self.__tracking_model.track(frame, **kwargs)
            if self.__tracking_model
            else []
        )
        return results

    def request_mpu_data(self) -> str:
        """
        Sends the request for MPU data.

        Returns:
            The ID of the command that was sent.
        """
        cmd_id = f"MPU_Request_{np.random.randint(0, 1 << 32)}"
        cmd = {"H": cmd_id, "N": 1000}
        self.__send_cmd(cmd)
        return cmd_id

    def receive_mpu_data(self, id_str: str) -> dict:
        """
        Waits for MPU data returned by the robot car (this is a blocking
        operation).
        Call this only if you have previously called request_mpu_data.

        Args:
            id_str: The string ID of the request command (value returned by
                    request_mpu_data).

        Returns:
            A dictionary with the MPU data. The dictionary is composed as
            follows:

            {
                "id": <the string ID of the request>,
                "t": <the acquisition time in seconds>,
                "a": [ax, ay, az], # The three components of the acceleration
                                   # (as fraction of g)
                "g": [wx, wy, wz] # The three angular velocities (in degrees
                                  # per second) around the three axes
            }

            The reference system is right handed, with x pointing to the right,
            y pointing to the front, and z pointing upwards. The angular
            velocities are positive when the rotation is counter-clockwise
            around the corresponding axis.
        """
        expected_pattern = f'{{"id":"{id_str}",.+]}}'
        data = json.loads(self.__recv_until_confirmation(expected_pattern))
        data["t"] *= 0.001  # Convert to seconds
        # NOTE: The readings for the accelerations arrive with the
        # wrong sign, so I have to change it
        data["a"] = [-x * self.__accel_quantum for x in data["a"]]
        data["g"] = [x * self.__gyro_quantum for x in data["g"]]
        if self.log:  # pragma: no cover
            print(f"Retrieved MPU data: {data}")
        return data

    def get_mpu_data(self) -> dict:
        """
        Convenience method that combines a call to request_mpu_data and
        receive_mpu_data.

        Returns:
            The dictionary with MPU data (see documentation of
            receive_mpu_data).
        """
        return self.receive_mpu_data(self.request_mpu_data())

    def __compute_mpu_offsets(self):
        if self.log:  # pragma: no cover
            print("Computing MPU offsets ...")
        accelerations = []
        omegas = []
        for _ in range(30):  # Acquire 30 measurements
            d = self.get_mpu_data()
            accelerations += [d["a"]]
            omegas += [d["g"]]
        self.__a_offsets = np.mean(accelerations, axis=0)
        self.__g_offsets = np.mean(omegas, axis=0)
        if self.log:  # pragma: no cover
            print(f"acceleration offsets: {self.__a_offsets}")
            print(f"gyro offsets: {self.__g_offsets}")

    def get_ultrasonic_value(self) -> float:
        """
        Returns the reading of the ultrasonic sensor.

        Returns:
            The reading (in cm) of the ultrasonic sensor. The reading is clipped
            to 150cm directly by the onboard software.
        """
        cmd_id = f"Ultrasonic_Value_Request_{np.random.randint(0, 1 << 32)}"
        cmd = {"H": cmd_id, "N": 21, "D1": 2}
        self.__send_cmd(cmd)
        pattern = rf"{{{cmd_id}_(\d+)}}"
        recv_message = self.__recv_until_confirmation(pattern)
        m = re.search(pattern, recv_message)
        sensor_value = float(m.group(1))
        real_distance = self.__ultrasonic_q + self.__ultrasonic_m * sensor_value
        if self.log:  # pragma: no cover
            print(f"Ultrasonic distance: {real_distance}")
        return real_distance

    def check_obstacle(self) -> bool:
        """
        Check if there is an obstacle in front of the ultrasonic sensor.

        Returns:
            True if there is an obstacle. False otherwise.
        """
        cmd_id = f"Check_Obstacle_{np.random.randint(0, 1 << 32)}"
        cmd = {"H": cmd_id, "N": 21, "D1": 1}
        self.__send_cmd(cmd)
        pattern = f"{{{cmd_id}_(true|false)}}"
        recv_message = self.__recv_until_confirmation(pattern)
        m = re.search(pattern, recv_message)
        return m.group(1) == "true"

    def get_ir_value(self, sensor: int) -> int:
        """
        Retrieves the reading of one of the IR sensors placed under the car.

        Returns:
            The value read by the requested IR sensor.
        """
        cmd_id = f"IR_{sensor}_{np.random.randint(0, 1 << 32)}"
        cmd = {"H": cmd_id, "N": 22, "D1": sensor}
        self.__send_cmd(cmd)
        pattern = rf"{{{cmd_id}_(\d+)}}"
        recv_message = self.__recv_until_confirmation(pattern)
        m = re.search(pattern, recv_message)
        return int(m.group(1))

    def get_ir_all(self) -> dict:
        """
        Convenience method for retrieving the readings of the three IR sensors
        placed under the car.

        Returns:
            A dictionary with the following structure:

        {
            Car.IR_LEFT: <left reading>,
            Car.IR_MIDDLE: <middle reading>,
            Car.IR_RIGHT: <right reading>
        }
        """
        sensors = [self.IR_LEFT, self.IR_MIDDLE, self.IR_RIGHT]
        return {sensor: self.get_ir_value(sensor) for sensor in sensors}

    def is_far_from_the_ground(self) -> bool:
        """
        Checks if the car is far from the ground.

        Returns:
            True if the car is far from the ground. False otherwise.
            The result is deduced from the IR sensor readings.
        """
        cmd_id = f"g{np.random.randint(0, 1 << 16):04x}"
        cmd = {"H": cmd_id, "N": 23}
        self.__send_cmd(cmd)
        pattern = f"{{{cmd_id}_(true|false)}}"
        recv_message = self.__recv_until_confirmation(pattern)
        m = re.search(pattern, recv_message)
        return m.group(1) == "true"

    def set_mode(self, mode: int) -> None:
        """
        Changes the operation mode of the car.

        Args:
            mode:   An integer flag for switching the operation mode. See the
                    available public constants in this class.
        """
        cmd = {"N": 101, "D1": mode}
        self.__send_cmd(cmd)

    def clear_all_states(self) -> None:
        """
        Clears all states in execution.
        """
        cmd_id = f"clear_all_states_{np.random.randint(0, 1 << 32)}"
        cmd = {"H": cmd_id, "N": 110}
        self.__send_cmd(cmd)
        expected_pattern = f"{{{cmd_id}_ok}}"
        self.__recv_until_confirmation(expected_pattern)

    def enable_analogue_drive(self):
        """Require the new firmware before sending any signed-wheel commands."""
        self.__send_cmd({"H": "cap", "N": 1002})
        try:
            reply = self.__recv_until_confirmation(r"\{drive_v(?:1|2_38400)\}")
        except (OSError, ValueError) as exc:
            raise RuntimeError("Analogue drive requires paired analogue-drive UNO/ESP32 firmware") from exc
        if not self.__dry_run:
            self.__socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.__serial_baud = 38400 if "2_38400" in reply else 115200
        self.__analogue_ready = True

    def drive_analogue(self, left: int, right: int, head: int, *, latest=None):
        """One acknowledged wheel/pan update; firmware expires it after 400 ms."""
        if not self.__analogue_ready:
            raise RuntimeError("Analogue drive firmware handshake has not succeeded")
        if not (-200 <= left <= 200 and -200 <= right <= 200 and -80 <= head <= 80):
            raise ValueError("Wheel or camera command outside supported range")
        self.__drive_sequence = (self.__drive_sequence + 1) & 0xffff
        command = {"H": f"d{self.__drive_sequence}", "N": 1001,
                   "D1": int(left), "D2": int(right), "D3": int(head)+90}
        self.__process_cmd(command, False, latest=latest)
        self.__head_servo_angle = command['D3']

    def forward(self, speed: int = 50, lazy: bool = False) -> None:
        """
        Moves forward.

        Args:
            speed:  Speed [0,255] of the car.
            lazy:   If True, you need to call the move method for performing the
                    action.
        """
        cmd = {"H": "fw", "N": 102, "D1": 1, "D2": speed}
        self.__process_cmd(cmd, lazy)

    def backward(self, speed: int = 50, lazy: bool = False) -> None:
        """
        Moves backward.

        Args:
            speed:  Speed [0,255] of the car.
            lazy:   If True, you need to call the move method for performing the
                    action.
        """
        cmd = {"H": "bw", "N": 102, "D1": 2, "D2": speed}
        self.__process_cmd(cmd, lazy)

    def left(self, speed: int = 50, lazy: bool = False) -> None:
        """
        Turns left on-the-spot.

        Args:
            speed:  Speed [0,255] of the car.
            lazy:   If True, you need to call the move method for performing the
                    action.
        """
        cmd = {"H": "l", "N": 102, "D1": 3, "D2": speed}
        self.__process_cmd(cmd, lazy)

    def right(self, speed: int = 50, lazy: bool = False) -> None:
        """
        Turns right on-the-spot.

        Args:
            speed:  Speed [0,255] of the car.
            lazy:   If True, you need to call the move method for performing the
                    action.
        """
        cmd = {"H": "r", "N": 102, "D1": 4, "D2": speed}
        self.__process_cmd(cmd, lazy)

    def turn_by(self, angle: int) -> None:
        """
        Turns on-the-spot by a specified angle. Speed is hardcoded to a value
        that allows the most accurate rotation control.

        Args:
            angle:  The rotation angle in degrees. Positive angle is
                    counterclockwise.
        """
        integrate = navigation_integrator()
        if self.log:  # pragma: no cover
            print("====== TURNING ======")
        # NOTE: I experimentally found that speed = 50 grants an accurate
        # rotation control
        speed = 50
        direction_flag = "l" if angle > 0 else "r"
        direction = 3 if angle > 0 else 4
        turn_cmd = {"H": direction_flag, "N": 102, "D1": direction, "D2": speed}
        mpu_data = self.get_mpu_data()
        t0 = mpu_data["t"]
        wz0 = mpu_data["g"][-1] - self.__g_offsets[-1]
        alpha = 0
        angle = abs(angle)
        self.__process_cmd(turn_cmd, lazy=False)
        while abs(alpha) < angle:
            mpu_data = self.get_mpu_data()
            t = mpu_data["t"]
            delta_t = t - t0
            wz = mpu_data["g"][-1] - self.__g_offsets[-1]
            delta_angle = integrate([wz0, wz], dx=delta_t)
            alpha += delta_angle
            if self.log:  # pragma: no cover
                print(f"delta_t = {delta_t}")
                print(f"wz0 = {wz0}")
                print(f"wz = {wz}")
                print(f"delta angle = {delta_angle}")
                print(f"alpha = {alpha}")
            t0 = t
            wz0 = wz
        self.stop(lazy=False)
        if self.log:  # pragma: no cover
            print("====== END TURNING ======")

    def forward_left(self, speed: int = 50, lazy: bool = False) -> None:
        """
        Turns left while moving forward.

        Args:
            speed:  Speed [0,255] of the car.
            lazy:   If True, you need to call the move method for performing the
                    action.
        """
        cmd = {"H": "fl", "N": 102, "D1": 5, "D2": speed}
        self.__process_cmd(cmd, lazy)

    def backward_left(self, speed: int = 50, lazy: bool = False) -> None:
        """
        Turns left while moving backward.

        Args:
            speed:  Speed [0,255] of the car.
            lazy:   If True, you need to call the move method for performing the
                    action.
        """
        cmd = {"H": "bl", "N": 102, "D1": 6, "D2": speed}
        self.__process_cmd(cmd, lazy)

    def forward_right(self, speed: int = 50, lazy: bool = False) -> None:
        """
        Turns right while moving forward.

        Args:
            speed:  Speed [0,255] of the car.
            lazy:   If True, you need to call the move method for performing the
                    action.
        """
        cmd = {"H": "fr", "N": 102, "D1": 7, "D2": speed}
        self.__process_cmd(cmd, lazy)

    def backward_right(self, speed: int = 50, lazy: bool = False) -> None:
        """
        Turns right while moving backward.

        Args:
            speed:  Speed [0,255] of the car.
            lazy:   If True, you need to call the move method for performing the
                    action.
        """
        cmd = {"H": "br", "N": 102, "D1": 8, "D2": speed}
        self.__process_cmd(cmd, lazy)

    def stop(self, lazy: bool = False) -> None:
        """
        Stops car's wheels.

        Args:
            lazy:   If True, you need to call the move method for performing the
                    action.
        """
        cmd = {"H": "stop", "N": 100}
        self.__process_cmd(cmd, lazy)

    def forward_until(
        self, has_to_stop: Callable[[], bool], speed: int = 50
    ) -> None:
        """
        Moves forward until a stopping condition is met.

        Args:
            has_to_stop:    A callable that returns True when the robot has to
                            stop.

            speed:          Speed [0,255] of the car.
        """
        self.forward(speed)
        while not has_to_stop():
            ...
        self.stop()

    def turn_head(self, delta: int, lazy: bool = False) -> None:
        """
        Moves head by a delta-angle.

        Args:
            delta:  The delta-angle. Positive is counterclockwise.
            lazy:   If True, you need to call the move method for performing the
                    action.
        """
        self.set_head_angle(self.head_angle + delta, lazy)

    def set_head_angle(self, angle: int = 0, lazy: bool = False) -> None:
        """
        Set head angle to what specified.

        Args:
            angle:  The desired head rotation angle, in [-80,80]. 0 = front,
                    80 = left, -80 = right.

            lazy:   If True, you need to call the move method for performing the
                    action.
        """
        angle = int(np.clip(angle, -80, 80))
        # For the robot, 0 = right, 90 = front, 180 = left.
        self.__head_servo_angle = angle + 90
        cmd = {"H": "set_head", "N": 5, "D1": 1, "D2": self.__head_servo_angle}
        self.__process_cmd(cmd, lazy)

    @property
    def head_angle(self) -> int:
        """
        Retrieves the current head rotation angle.

        Returns:
            The head rotation angle, in [-80,80]. 0 = front, -80 = right,
            80 = left.
        """
        return self.__head_servo_angle - 90

    def move(self) -> None:
        """
        Applies all the lazy movement commands previously issued.
        Lazy commands are stacked into a queue and then the queue is
        progressively depleted.
        This behavior is handy for interactive remote control (video-game
        style).

        Warning:
            If more than one movement command is in the queue then the car
            is stopped and the queue is cleared. This is because the car is not
            able to deal with more than one command at the same time.
        """
        num_cmd_received = len(self.__cmd_queue)
        if num_cmd_received == 0:
            self.stop()
        elif num_cmd_received > 1:
            # TODO: This action should be removed because it is not the
            # TODO: correct behavior. At present I did not manage to properly
            # TODO: manage the command queue.
            self.__cmd_queue.clear()
        while len(self.__cmd_queue) > 0:
            new_state_cmd = self.__cmd_queue.popleft()
            self.__change_state_to(new_state_cmd)

    def find_best_front_direction(
        self, scan_range: tuple[int, int] = (-80, 80)
    ) -> tuple[int, float]:
        """
        Scans the surroundings in front of the robot and returns the best
        movement direction angle.

        Warnings:
            The current algorithm is not robust because it blindly exploits
            the ultrasonic sensor measurements. When there is an obstacle in
            front of the sensor, but the sensor is squinted with
            respect to the obstacle surface, then the reflected sound wave
            does not directly return to the sensor. What the sensor detects then
            is a secondary arrival, that could have traveled a lot more than
            the first hit. In such a situation, the measured distance from the
            obstacle is wrong, because it is actually the distance traveled
            by the multiply-reflected wave.

        Args:
            scan_range: The front angles to scan. They are going to be scanned
                        with the degrees step set into the
                        Car.head_angle_scan_step attribute. The widest allowed
                        range is (-80,80) (the default).
                        If you specify a range outside this one, it will
                        be clipped to the maximum allowed. Furthermore, if you
                        specify a max angle less than the min angle, the max
                        angle will be forcedly set equal to the min angle and
                        only one direction will be scanned (so pay attention
                        to the numbers you pass!)

        Returns:
            A pair (best_angle, best_distance). The best angle is the best
            movement angle with respect to robot front. The returned angle is
            in the [-80,80] range, where positive angle is counterclockwise.
            0 is robot front.
        """
        min_angle = np.clip(scan_range[0], -80, 80)
        max_angle = max(np.clip(scan_range[1], -80, 80), min_angle)
        scan_angles = range(
            min_angle,
            max_angle + self.__head_angle_scan_step,
            self.__head_angle_scan_step,
        )
        distances = []
        for cur_angle in scan_angles:
            self.set_head_angle(cur_angle)
            try_getting_obstacle_dist = True
            obstacle_dist = None
            while try_getting_obstacle_dist:
                try:
                    obstacle_dist = self.get_ultrasonic_value()
                    try_getting_obstacle_dist = False
                except TimeoutError:  # pragma: no cover
                    # try_getting_obstacle_dist stays True
                    # so we will retry at the next loop
                    pass
            distances += [obstacle_dist]
        distances = np.array(distances)
        ind_best_dir = round(
            np.argwhere(distances == distances.max()).ravel().mean()
        )
        self.set_head_angle(0)
        return scan_angles[ind_best_dir], distances[ind_best_dir]

    def turn_to_best_direction(
        self, angle: int | None = None
    ) -> None:  # pragma: no cover
        """
        Turns the car to the best direction. The best direction is the one with
        maximum obstacle distance.

        Warnings:
            This algorithm is not robust at all because the current search for
            the best direction is not robust.

        Args:
            The best direction angle. None means that the angle must be found.
        """
        dist = np.inf
        if angle is None:
            angle, dist = self.find_best_front_direction()
        num_trials = 0
        # The external cycle potentially scans 4 main directions, separated
        # by 90 degrees each
        while abs(angle) > self.__head_angle_scan_step and num_trials < 4:
            num_front_trials = 0
            # For each main direction, turn to the best angle found up to
            # now. After that, perform a head scan into a restricted angle range
            # to verify that, after having turned, the best angle is within the
            # minimum angle detection range in front of the car. If not, we
            # turn to the best angle (we try turning again up to a limited
            # number of trials.
            while (
                abs(angle) > self.__head_angle_scan_step
                and num_front_trials < 3  # Empirically set threshold
            ):
                self.turn_by(angle)
                num_front_trials += 1
                angle, dist = self.find_best_front_direction(
                    scan_range=(-50, 50)
                )
            if dist < 30:
                # If after previous restricted turning trials ther is still
                # an obstacle in front (less than 30 cm distant), retry
                # everything along a perpendicular direction
                self.turn_by(90)
            num_trials += 1
        if self.log:  # pragma: no cover
            print(f"Best distance up to now: {dist}")
            print(f"Best angle found: {angle}")

    def __change_state_to(self, state_cmd: dict):
        new_state = state_cmd["H"]
        wait_for_confirmation = new_state not in self.__no_response_cmds
        set_head_cmd = new_state == "set_head"
        if "D2" in state_cmd:
            new_state += f"_{str(state_cmd['D2'])}"
        state_cmd["H"] = new_state
        if new_state == self.__state:
            return
        self.__send_cmd(state_cmd)
        if wait_for_confirmation:
            self.__recv_until_confirmation("{" + new_state + "_ok}")
        if set_head_cmd:
            self.__head_servo_angle = state_cmd["D2"]
        self.__state = new_state

    def __send_cmd(self, cmd_data: dict, latest=None) -> None:
        if not self.__dry_run:
            # Use the negotiated UART speed; legacy firmware remains at 9600.
            # In particular, leave room after commands with no response.
            if self.__cancel_event.wait(max(0.0, self.__command_ready_at - time.monotonic())):
                raise ConnectionAbortedError('Control operation cancelled')
        if latest is not None:
            left, right, head = latest()
            if not (-200 <= left <= 200 and -200 <= right <= 200 and -80 <= head <= 80):
                raise ValueError('Wheel or camera command outside supported range')
            cmd_data.update(D1=int(left), D2=int(right), D3=int(head)+90)
        json_cmd = (json.dumps(cmd_data, separators=(",", ":")) if self.__analogue_ready
                    else json.dumps(cmd_data)).encode()
        if not self.__dry_run:
            self.__socket.sendall(json_cmd)
            self.__command_ready_at = time.monotonic() + len(json_cmd) * 10 / self.__serial_baud + (0.002 if self.__analogue_ready else 0.03)
        if self.log:  # pragma: no cover
            print(f"Sent command: {json_cmd}")

    def __recv_until_confirmation(self, expected_confirmation: str) -> str:
        if self.__dry_run:
            return ""
        pattern = re.compile(expected_confirmation)
        m = pattern.search(self.__recv_msg_queue)
        deadline = time.monotonic() + 2.0
        while not m:
            if self.__cancel_event.is_set():
                raise ConnectionAbortedError('Control operation cancelled')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Robot command response timed out")
            self.__socket.settimeout(min(remaining, .1))
            try:
                received = self.__socket.recv(4096)
            except socket.timeout:
                continue
            finally:
                self.__socket.settimeout(2)
            if not received:
                raise ConnectionError("Robot closed the control connection")
            try:
                decoded = received.decode("ascii")
                if any(ord(c) < 32 and c not in "\r\n\t" for c in decoded):
                    raise ValueError("non-text control bytes")
            except (UnicodeDecodeError, ValueError) as exc:
                self.__recv_msg_queue = ""
                raise ControlProtocolError(
                    f"Corrupt serial control reply (hex: {received[:96].hex()})") from exc
            self.__recv_msg_queue += decoded
            if len(self.__recv_msg_queue) > 16384:
                self.__recv_msg_queue = ""
                raise ControlProtocolError("Control reply buffer exceeded its limit")
            # Remove all received {Heartbeat} messages
            self.__recv_msg_queue = self.__heartbeat_re.sub(
                "", self.__recv_msg_queue
            )
            # Remove all received {ok} messages
            self.__recv_msg_queue = self.__ok_re.sub("", self.__recv_msg_queue)
            m = pattern.search(self.__recv_msg_queue)
            if self.log:  # pragma: no cover
                print(f"Received message: {self.__recv_msg_queue}")
        self.__recv_msg_queue = pattern.sub("", self.__recv_msg_queue)
        return m.group(0)

    def __process_cmd(self, cmd: dict, lazy: bool, latest=None) -> None:
        if lazy:
            self.__cmd_queue += [cmd]
            return
        if latest is None:
            self.__send_cmd(cmd)
        else:
            self.__send_cmd(cmd, latest=latest)
        new_state = cmd["H"]
        wait_for_confirmation = new_state not in self.__no_response_cmds
        if wait_for_confirmation:
            self.__recv_until_confirmation("{" + new_state + "_ok}")
