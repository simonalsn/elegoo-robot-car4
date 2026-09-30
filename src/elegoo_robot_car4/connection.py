"""Serialized dashboard I/O. No command queue survives a reconnect."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
import time

from .car import Car
from .udp_video import UdpVideo


class Connection:
    def __init__(self, ip, transport, log=False, car_factory=Car, video_factory=UdpVideo):
        self.ip, self.transport, self.log = ip, transport, log
        self.car_factory, self.video_factory = car_factory, video_factory
        self.car = self.video = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='car-link')
        self.pending = None
        self.closed = False
        self.generation = 0
        self.ground_checked = -float("inf")
        self.raised = True

    def submit(self, operation, *args):
        if self.pending is not None or self.closed:
            return False
        self.pending = self.executor.submit(operation, *args)
        return True

    def poll(self):
        if self.pending is None or not self.pending.done():
            return None
        future, self.pending = self.pending, None
        try:
            return True, future.result()
        except Exception as exc:
            return False, exc

    def disconnect(self):
        if self.car is not None:
            with suppress(Exception):
                self.car.stop()
            self.car.disconnect()
            self.car = None
        if self.video is not None:
            self.video.close()
            self.video = None

    def connect(self):
        self.disconnect()
        self.ground_checked = -float("inf")
        self.raised = True
        try:
            self.car = self.car_factory(ip=self.ip, log=self.log, stop_before_init=True)
            self.car.enable_analogue_drive()
            self.car.drive_analogue(0, 0, 0)
            if self.transport == 'udp':
                self.video = self.video_factory(self.ip)
        except Exception:
            self.disconnect()
            raise

    def invalidate(self):
        self.generation += 1

    def exchange(self, demand, generation=None):
        # Keep the original 10 Hz sensor budget on the 38400-baud serial link.
        if time.monotonic()-self.ground_checked >= .1:
            self.raised = self.car.is_far_from_the_ground()
            self.ground_checked = time.monotonic()
        raised = self.raised
        left, right, head = demand
        if raised or self.closed or (generation is not None and generation != self.generation):
            left = right = 0
        started = time.monotonic()
        self.car.drive_analogue(left, right, head)
        ack = time.monotonic()
        frame = self.car.capture() if self.transport == 'http' else None
        return raised, (left, right, head), (ack-started)*1000, ack, frame

    def close(self):
        self.closed = True
        self.invalidate()
        # Cleanup is serialized behind any in-flight call, never concurrent with recv.
        self.executor.submit(self.disconnect)
        self.executor.shutdown(wait=False)
