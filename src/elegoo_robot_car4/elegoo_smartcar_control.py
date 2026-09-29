#  Copyright (c) Michele De Stefano - 2023.

import argparse
import functools as fun
import time
from contextlib import suppress
from collections.abc import Callable
from typing import Any

import cv2 as cv
import numpy as np
import pygame as pg
from pygame._sdl2 import controller as gamecontroller
import requests
from ultralytics.engine.results import Results

from .__init__ import __version__
from .car import Car
from .person_follower import PersonFollower
from .udp_video import UdpVideo
from .analogue_drive import AnalogueDrive
from .dashboard import Dashboard, DashboardState


class GameEngine:
    __joysticks: dict[int, gamecontroller.Controller]
    __head_delta: int = 10
    __min_speed: int = 50
    __max_speed: int = 200
    __dry_run: bool
    __dry_run_size: tuple[int, int] = (400, 200)
    __autonomous_mode: bool

    __key_to_move_cmd: dict[int, Callable[[Car], Any]] = {
        pg.K_UP: fun.partial(Car.forward, speed=__min_speed, lazy=True),
        pg.K_DOWN: fun.partial(Car.backward, speed=__min_speed, lazy=True),
        pg.K_LEFT: fun.partial(Car.left, speed=__min_speed, lazy=True),
        pg.K_RIGHT: fun.partial(Car.right, speed=__min_speed, lazy=True),
        pg.K_a: fun.partial(Car.turn_head, delta=__head_delta, lazy=True),
        pg.K_d: fun.partial(Car.turn_head, delta=-__head_delta, lazy=True),
        pg.K_s: fun.partial(Car.set_head_angle, lazy=True),
    }

    __axis_thr: float = 0.5
    __small_axis_thr: float = 0.1

    __car: Car

    __last_track_results: list[Results]

    __person_follower: PersonFollower
    __run_person_follower: bool

    def __init__(self, robot_ip: str, log: bool = False, dry_run: bool = False, video: str = "http", analogue_drive: bool = False, trace_camera: bool = False):
        """
        Constructor.

        Args:
            robot_ip:   IP address of the robot.

            log:        Set this to True if you want to activate logging.

            dry_run:    Set this to True for debugging purpose (no socket call
                        will be actually made).
        """
        gamecontroller.init()
        self.__joysticks = {}
        self.__dry_run = dry_run
        self.__autonomous_mode = False
        self.__run_person_follower = False
        self.__car = Car(ip=robot_ip, log=log, dry_run=dry_run)
        self.__analogue = AnalogueDrive() if analogue_drive else None
        self.__neutral_required = analogue_drive
        self.__stop_held = False
        self.__resume_requested = False
        self.__ui = DashboardState() if analogue_drive else None
        self.__dashboard = None
        self.__last_raw_frame = None
        self.__fps_sample = (time.monotonic(), 0)
        self.__http_frames = 0
        self.__trace_camera = trace_camera
        if analogue_drive:
            try:
                self.__car.enable_analogue_drive()
            except Exception:
                self.__car.disconnect()
                raise
        self.__last_track_results = []
        self.__video = UdpVideo(robot_ip) if video == "udp" and not dry_run else None
        # UDP starts asynchronously; no HTTP capture before the window opens.
        # capture shape (height, width), OpenCV format
        capture_shape = np.array(
            self.__dry_run_size if dry_run else ((600, 800) if self.__video else self.__car.capture().shape[:2])
        )
        # pygame requires frames in (width, height) format
        display_size = self.__dry_run_size if dry_run else capture_shape[::-1]
        self.__person_follower = PersonFollower(
            car=self.__car, frame_shape_hw=capture_shape
        )
        if analogue_drive:
            self.__dashboard = Dashboard(robot_ip, 'preview' if dry_run else video, preview=dry_run)
            self.__display = self.__dashboard.screen
        else:
            self.__display = pg.display.set_mode(display_size)
        pg.display.set_caption("Elegoo Smart Robot Car v4.0 controller")

        self.__delta_speed = self.__max_speed - self.__min_speed

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release_resources()

    def __display_new_frame(self) -> bool | None:
        ui = getattr(self, "_GameEngine__ui", None)
        dashboard = getattr(self, "_GameEngine__dashboard", None)
        if self.__dry_run:
            return
        if self.__video is not None:
            frame, age = self.__video.latest()
            if ui is not None:
                ui.frame_age = age
                self.__update_video_rate(self.__video.frames)
            if frame is None or age > 0.75:
                # Never drive using a frozen image. Keep the window responsive
                # while waiting for the subscription or recovering packet loss.
                if dashboard is None:
                    self.__display.fill((25, 25, 25))
                    pg.display.update()
                else:
                    ui.video_stale = True
                return False
        else:
            frame = self.__car.capture()
            if ui is not None:
                self.__http_frames += 1
                self.__update_video_rate(self.__http_frames)
                ui.frame_age = 0.0  # HTTP image has just been received, not capture latency.
        if dashboard is not None:
            ui.video_stale = False
            if frame is not self.__last_raw_frame:
                self.__last_raw_frame = frame
                dashboard.set_frame(pg.surfarray.make_surface(self.__process_frame(frame)))
            return True
        frame = self.__process_frame(frame)
        if self.__display.get_size() != frame.shape[:2]:
            self.__display = pg.display.set_mode(frame.shape[:2])
            self.__person_follower = PersonFollower(self.__car, np.array(frame.shape[:2][::-1]))
        # blit it to the display surface.  simple!
        pg.surfarray.blit_array(self.__display, frame)
        pg.display.update()
        return True

    def __process_frame(self, frame: np.ndarray) -> np.ndarray:
        if self.__car.vision_tracking_is_on:
            self.__last_track_results = self.__car.track(
                frame,
                classes=[0],
                conf=0.5,
                max_det=2,
                verbose=False,
                persist=True,
            )
            for result in self.__last_track_results:
                frame = result.plot(img=frame)
        else:
            self.__last_track_results = []
        # Returned frame must be ready to be consumed by pygame
        frame = cv.transpose(cv.cvtColor(frame, cv.COLOR_BGR2RGB))
        return frame

    def run(self) -> None:
        """
        Runs the game loop, translating player commands to the robot.
        """

        clock = pg.time.Clock()
        failures = 0
        ground_checked = 0.0
        raised = True
        while True:
            analogue = getattr(self, "_GameEngine__analogue", None)
            clock.tick(30 if analogue else 10)
            events = pg.event.get()
            if any(e.type == pg.QUIT or (e.type == pg.KEYDOWN and e.key == pg.K_ESCAPE)
                   for e in events):
                break
            try:
                self.__detect_relevant_events(events)
                self.__handle_dashboard_events(events)
                try:
                    if self.__display_new_frame() is False:
                        self.__car.stop()
                        if analogue:
                            analogue.stop()
                            self.__neutral_required = True
                        self.__dashboard_status('Driving blocked', 'Video is stale. Wait for fresh frames, then release driving controls.')
                        pg.display.set_caption("UDP video unavailable/stale — driving blocked; Esc exits")
                        continue
                    if not analogue or time.monotonic() - ground_checked >= 0.1:
                        raised = not self.__dry_run and self.__car.is_far_from_the_ground()
                        ground_checked = time.monotonic()
                except (OSError, ValueError, requests.RequestException, cv.error) as exc:
                    with suppress(OSError):
                        self.__car.stop()
                    if analogue:
                        analogue.stop()
                        self.__neutral_required = True
                    self.__dashboard_status('Connection error', 'Stop requested. Waiting for a valid reply and neutral controls.', 'error')
                    failures += 1
                    pg.display.set_caption("Connection/camera error — stop requested")
                    print(f"Connection/camera error; stop requested: {exc}", flush=True)
                    if failures >= 3 and not analogue:
                        raise RuntimeError("Repeated robot connection/camera failures") from exc
                    continue
                failures = 0
                if raised:
                    if analogue:
                        analogue.stop()
                        self.__neutral_required = True
                    try:
                        self.__car.stop()
                    except OSError:
                        self.__dashboard_status('Stop unconfirmed', 'Car is raised; Stop reply failed. Driving remains blocked.', 'error')
                    else:
                        self.__dashboard_status('Driving blocked', 'Car is raised. Place it on the ground, then release driving controls.')
                    pg.display.set_caption("Car raised: driving blocked — place on floor; Esc exits")
                    continue
                pg.display.set_caption(
                    "RT forward | LT reverse | both stop | left stick steer | right stick camera | Esc exits"
                    if analogue else "Elegoo Smart Robot Car v4.0 controller — arrow keys drive")

                if analogue:
                    # This mode sends one combined, leased drive/pan command. Do not
                    # mix legacy keyboard/autonomous commands into that transaction.
                    try:
                        self.__handle_analogue_actions()
                    except (OSError, ValueError) as exc:
                        analogue.stop()
                        self.__neutral_required = True
                        self.__dashboard_status('Control reply failed', 'Stop requested. Release triggers and steering to recover.', 'error')
                        pg.display.set_caption("Control reply failed — stopped; release triggers and steering")
                        print(f"Control reply failed; stop requested. Release triggers and steering. {exc}", flush=True)
                        # __handle_analogue_actions has already requested stop.
                        # Never replay the failed drive demand; recover with zero only.
                    continue

                keyboard_player_actions = self.__handle_keyboard_player_actions()
                if keyboard_player_actions["command_received"] == "finish":
                    break

                move_command_received = keyboard_player_actions[
                    "command_received"
                ] == "movement" or self.__handle_controller_player_actions()

                if not self.__autonomous_mode:
                    if not move_command_received:
                        self.__car.stop(lazy=True)
                    self.__car.move()

                if keyboard_player_actions["command_received"] == "terminal":
                    self.__handle_terminal_input()

                if self.__run_person_follower:
                    self.__person_follower.follow(self.__last_track_results)
            finally:
                self.__render_dashboard()

    def __detect_relevant_events(self, events: list[pg.Event]) -> None:
        # Process hotplug even while raised or waiting for video. Otherwise the
        # initial connection event is consumed and the pad is never registered.
        for e in events:
            if e.type == pg.JOYDEVICEADDED:
                if not gamecontroller.is_controller(e.device_index):
                    print("Gamepad has no SDL mapping; ignoring it instead of guessing axes.")
                    continue
                pad = gamecontroller.Controller(e.device_index)
                ident = pad.as_joystick().get_instance_id()
                self.__joysticks[ident] = pad
                controls = ("RT forward; LT reverse; both stop; left stick steers; right stick aims camera."
                            if getattr(self, "_GameEngine__analogue", None) else
                            "Left stick/D-pad drive; RT adds speed; right stick pans; X centres camera.")
                print(f"Gamepad connected: {pad.name}. {controls}", flush=True)
            elif e.type == pg.JOYDEVICEREMOVED:
                pad = self.__joysticks.pop(e.instance_id, None)
                if pad is not None:
                    pad.quit()

    def __handle_keyboard_player_actions(self) -> dict[str, int | str | None]:
        retval: dict[str, int | str | None] = {
            "command_received": None,
            "key": None,
        }
        was_pressed = pg.key.get_pressed()
        if was_pressed[pg.K_ESCAPE]:
            retval["key"] = pg.K_ESCAPE
            retval["command_received"] = "finish"
        elif was_pressed[pg.K_t]:
            retval["key"] = pg.K_t
            retval["command_received"] = "terminal"
        else:
            for key_cmd in self.__key_to_move_cmd:
                if was_pressed[key_cmd]:
                    self.__key_to_move_cmd[key_cmd](self.__car)
                    retval["command_received"] = "movement"
                    retval["key"] = key_cmd
                    break
        return retval

    def __handle_analogue_actions(self):
        analogue = self.__analogue
        pad = next((p for p in self.__joysticks.values() if p.attached()), None)
        if pad is None or not pg.key.get_focused():
            self.__neutral_required = True
            analogue.stop()
            self.__car.stop()
            self.__dashboard_status('Driving blocked', 'Controller disconnected.' if pad is None else 'Window lost focus. Focus it and release driving controls.')
            return
        def axis(name):
            return pad.get_axis(name) / 32768.0
        ui = getattr(self, "_GameEngine__ui", None)
        forward = max(0, axis(pg.CONTROLLER_AXIS_TRIGGERRIGHT))
        reverse = max(0, axis(pg.CONTROLLER_AXIS_TRIGGERLEFT))
        steering = axis(pg.CONTROLLER_AXIS_LEFTX)
        neutral = forward <= .04 and reverse <= .04 and abs(steering) <= .08
        if ui is not None:
            ui.throttle = 0 if forward > .04 and reverse > .04 else forward-reverse
            ui.steering = steering
        if getattr(self, "_GameEngine__neutral_required", False) or getattr(self, "_GameEngine__stop_held", False):
            analogue.stop()
            try:
                self.__send_analogue(0, 0, round(analogue.head))
            except (OSError, ValueError):
                with suppress(OSError):
                    self.__car.stop()
                raise
            if getattr(self, "_GameEngine__stop_held", False):
                self.__dashboard_status('Stopped by you', 'Release driving controls, then click Resume.', 'error')
                if ui is not None:
                    ui.can_resume = neutral
                    ui.left = ui.right = 0
                if neutral and getattr(self, "_GameEngine__resume_requested", False):
                    self.__stop_held = False
                    self.__neutral_required = False
                    if ui is not None:
                        ui.stopped = ui.can_resume = False
                    self.__dashboard_status('Ready', 'Controls neutral. Use the triggers to drive.', 'good')
            elif neutral:
                self.__neutral_required = False
                self.__dashboard_status('Ready', 'Controls neutral. Use the triggers to drive.', 'good')
            else:
                self.__dashboard_status('Release controls', 'Release both triggers and steering before driving can resume.')
                pg.display.set_caption("Stopped after control error — release triggers and steering")
            return
        camera = 0 if pad.get_button(pg.CONTROLLER_BUTTON_X) else axis(pg.CONTROLLER_AXIS_RIGHTX)
        left, right, head = analogue.update(
            forward, reverse, steering,
            camera,
            time.monotonic())
        try:
            self.__send_analogue(left, right, head)
            self.__dashboard_status('Driving' if left or right else 'Ready',
                                    'Manual input active. You have control.' if left or right else
                                    ('Both triggers pressed - wheels stopped.' if forward>.04 and reverse>.04 else 'Controls neutral. Use the triggers to drive.'), 'good')
            self.__trace_camera_command(camera, head)
        except Exception:
            analogue.stop()
            with suppress(OSError):
                self.__car.stop()
            raise

    def __send_analogue(self, left, right, head):
        started = time.perf_counter()
        self.__car.drive_analogue(left, right, head)
        ui = getattr(self, "_GameEngine__ui", None)
        if ui is not None:
            ui.left, ui.right, ui.head = left, right, head
            if not self.__dry_run:
                ui.ack_ms = (time.perf_counter()-started)*1000
                ui.ack_at = time.monotonic()

    def __dashboard_status(self, status, reason, level='warning'):
        ui = getattr(self, "_GameEngine__ui", None)
        if ui is not None:
            ui.status, ui.reason, ui.level = status, reason, level
            if level != 'good':
                ui.left = ui.right = None
                ui.can_resume = False

    def __handle_dashboard_events(self, events):
        dashboard = getattr(self, "_GameEngine__dashboard", None)
        self.__resume_requested = False
        if dashboard is None:
            return
        # Stop wins over Resume when both appear in the same event batch.
        actions = [dashboard.action(event) for event in events]
        if 'stop' in actions:
            self.__stop_held = self.__neutral_required = True
            self.__ui.stopped = True
            self.__analogue.stop()
            self.__dashboard_status('Stopped by you', 'Release driving controls, then click Resume.', 'error')
            try:
                self.__car.stop()
            except OSError:
                self.__dashboard_status('Stop unconfirmed', 'Control link did not confirm Stop. Driving remains blocked.', 'error')
        elif 'resume' in actions and self.__stop_held and self.__ui.can_resume:
            self.__resume_requested = True

    def __update_video_rate(self, count):
        now = time.monotonic()
        previous, frames = self.__fps_sample
        if now-previous >= 1:
            self.__ui.fps = (count-frames)/(now-previous)
            self.__fps_sample = (now, count)

    def __render_dashboard(self):
        dashboard = getattr(self, "_GameEngine__dashboard", None)
        if dashboard is None:
            return
        ui = self.__ui
        pad = next((p for p in self.__joysticks.values() if p.attached()), None)
        ui.controller = pad.name if pad else 'No controller connected'
        if pad is None:
            ui.throttle = ui.steering = 0
        ui.focused = bool(pg.key.get_focused())
        if self.__video is not None:
            _, ui.frame_age = self.__video.latest()
            ui.video_stale = ui.frame_age > .75
        dashboard.draw(ui, time.monotonic())

    def __trace_camera_command(self, stick, head):
        if not getattr(self, "_GameEngine__trace_camera", False):
            return
        now = time.monotonic()
        last_time, last_head = getattr(self, "_GameEngine__last_camera_trace", (-float("inf"), None))
        if head != last_head or now-last_time >= 1:
            print(f"Camera {time.strftime('%H:%M:%S')} stick={stick:+.4f} "
                  f"acknowledged_target={head+90}deg", flush=True)
            self.__last_camera_trace = (now, head)

    def __handle_controller_player_actions(self) -> bool:
        for pad in self.__joysticks.values():
            if not pad.attached():
                continue
            # SDL's named axes normalize USB/receiver/Bluetooth mappings.
            lr = pad.get_axis(pg.CONTROLLER_AXIS_LEFTX) / 32768.0
            fb = pad.get_axis(pg.CONTROLLER_AXIS_LEFTY) / 32768.0
            head = pad.get_axis(pg.CONTROLLER_AXIS_RIGHTX) / 32768.0
            trigger = max(0.0, min(1.0,
                pad.get_axis(pg.CONTROLLER_AXIS_TRIGGERRIGHT) / 32767.0))
            centre = pad.get_button(pg.CONTROLLER_BUTTON_X)
            if centre or abs(head) > self.__axis_thr:
                # The upstream command queue accepts one action per iteration.
                # Stop before panning so a previous drive command cannot persist.
                self.__car.stop()
                if centre:
                    self.__car.set_head_angle(lazy=True)
                else:
                    self.__car.turn_head(self.__head_delta if head < 0
                                         else -self.__head_delta, lazy=True)
                return True

            dx = int(pad.get_button(pg.CONTROLLER_BUTTON_DPAD_RIGHT)) - int(
                pad.get_button(pg.CONTROLLER_BUTTON_DPAD_LEFT))
            dy = int(pad.get_button(pg.CONTROLLER_BUTTON_DPAD_DOWN)) - int(
                pad.get_button(pg.CONTROLLER_BUTTON_DPAD_UP))
            if dx or dy:
                magnitude = 1.0
            else:
                deadzone = 0.2
                dx = (1 if lr > deadzone else -1 if lr < -deadzone else 0)
                dy = (1 if fb > deadzone else -1 if fb < -deadzone else 0)
                if not (dx or dy):
                    continue  # An idle pad must not hide another active pad.
                magnitude = min(1.0, (max(abs(lr), abs(fb)) - deadzone) / (1-deadzone))
            ceiling = self.__min_speed + trigger * self.__delta_speed
            speed = round(self.__min_speed + magnitude * (ceiling-self.__min_speed))
            action = {
                (0, -1): self.__car.forward, (0, 1): self.__car.backward,
                (-1, 0): self.__car.left, (1, 0): self.__car.right,
                (-1, -1): self.__car.forward_left, (1, -1): self.__car.forward_right,
                (-1, 1): self.__car.backward_left, (1, 1): self.__car.backward_right,
            }[dx, dy]
            action(speed=speed, lazy=True)
            return True
        return False

    def __handle_terminal_input(self) -> None:
        print("Options:")
        print("========\n")
        print("0 - Clear all states")
        print(f"{Car.TRACKING_MODE} - Activate line tracking mode")
        print(
            f"{Car.OBSTACLE_AVOIDANCE_MODE} - Activate obstacle avoidance mode"
        )
        print(f"{Car.FOLLOW_MODE} - Activate (ultrasonic) follow mode")
        print("4 - Toggle person tracking mode")
        print("5 - Toggle person tracking and following mode")
        print()

        retry_input = True
        user_choice = -1
        while retry_input:
            try:
                user_choice = int(input("Enter your choice: "))
                retry_input = not (0 <= user_choice <= 5)
                if retry_input:
                    print("Please enter a number between 0 and 5")
            except Exception:
                print("Please enter a number between 0 and 5")

        if user_choice == 0:
            self.__autonomous_mode = False
            self.__run_person_follower = False
            self.__car.clear_all_states()
            if self.__car.vision_tracking_is_on:
                self.__car.toggle_vision_tracking()
        elif user_choice == 4:
            self.__autonomous_mode = False
            self.__run_person_follower = False
            self.__car.toggle_vision_tracking()
        elif user_choice == 5:
            self.__autonomous_mode = not self.__autonomous_mode
            self.__run_person_follower = not self.__run_person_follower
            toggle_vision_tracking = (
                not self.__car.vision_tracking_is_on
                and self.__run_person_follower
            ) or (
                not self.__run_person_follower
                and self.__car.vision_tracking_is_on
            )
            if toggle_vision_tracking:
                self.__car.toggle_vision_tracking()
        else:
            self.__autonomous_mode = True
            self.__car.set_mode(user_choice)

    def release_resources(self):
        try:
            with suppress(OSError):
                self.__car.stop()
        finally:
            self.__car.disconnect()
            for pad in getattr(self, "_GameEngine__joysticks", {}).values():
                pad.quit()
            video = getattr(self, "_GameEngine__video", None)
            if video is not None:
                video.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Program for remotely controlling Elegoo Smart "
        "Robot Car v4.0"
    )
    parser.add_argument(
        "--robot-ip",
        dest="robot_ip",
        type=str,
        default=None,
        help="Robot IP address.",
    )
    parser.add_argument(
        "--log",
        dest="log",
        action="store_true",
        help="Acquired commands are printed to the console. "
        "Default: %(default)s.",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Run without sending any command to the car. "
        "Default: %(default)s.",
    )
    parser.add_argument(
        "-v",
        "--version",
        dest="version_requested",
        action="store_true",
        help="Print the version and exit.",
    )
    parser.add_argument("--video", choices=("udp", "http"), default="http",
                        help="Video transport (default: http; udp requires local UDP camera firmware).")
    parser.add_argument("--analogue-drive", action="store_true",
                        help="Trigger throttle + proportional steering/pan; requires new paired firmware.")
    parser.add_argument("--trace-camera", action="store_true",
                        help="Log acknowledged analogue camera targets on change and once per second.")
    parser.add_argument("--dashboard-preview", action="store_true",
                        help="Open the offline dashboard preview without connecting to a robot.")
    args = parser.parse_args()

    if args.version_requested:
        print(f"Version: {__version__}")
        return

    if args.dashboard_preview:
        from .dashboard import preview
        preview()
        return

    if not args.robot_ip:
        print("Specify a robot IP address!")
        exit(1)

    pg.init()

    with GameEngine(
        args.robot_ip, log=args.log, dry_run=args.dry_run, video=args.video, analogue_drive=args.analogue_drive, trace_camera=args.trace_camera
    ) as engine:
        engine.run()

    pg.quit()
