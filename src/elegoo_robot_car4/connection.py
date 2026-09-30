"""Serialized dashboard I/O. No command queue survives a reconnect."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
import time
from queue import Queue, Empty, Full
from threading import Event, Lock

from .car import Car
from .udp_video import UdpVideo
from .http_video import HttpVideo


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
        self._cancel = Event()
        self._wake = Event()
        self._lock = Lock()
        self._demand = ((0, 0, 0), 0, 0.0)
        self._results = Queue(maxsize=1)
        self.input_expired = False

    def submit(self, operation, *args):
        if self.pending is not None or self.closed:
            return False
        self.pending = self.executor.submit(operation, *args)
        return True

    def poll(self):
        if self.pending is None or not self.pending.done():
            try:
                return True, self._results.get_nowait()
            except Empty:
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
        if self._cancel.is_set() or self.closed:
            raise ConnectionAbortedError('Connection cancelled')
        self.ground_checked = -float("inf")
        self.raised = True
        try:
            self.car = self.car_factory(ip=self.ip, log=self.log, stop_before_init=True,
                                        initialize=False, cancel_event=self._cancel)
            self.car.enable_analogue_drive()
            self.car.drive_analogue(0, 0, 0)
            if self.transport == 'udp':
                self.video = self.video_factory(self.ip)
            else:
                self.video = HttpVideo(self.ip)
        except Exception:
            self.disconnect()
            raise

    def invalidate(self):
        with self._lock:
            previous = self._demand[0]
            self.generation += 1
            self._demand = ((0, 0, previous[2]), self.generation, time.monotonic())
        if previous[:2] != (0, 0):
            self._wake.set()

    def prepare_connect(self):
        self._cancel = Event()
        while not self._results.empty():
            with suppress(Empty):
                self._results.get_nowait()

    def interrupt(self):
        self.invalidate()
        self._cancel.set()
        self._wake.set()
        if self.car is not None:
            self.car.cancel()

    def update_demand(self, demand):
        with self._lock:
            previous = self._demand[0]
            self._demand = (demand, self.generation, time.monotonic())
            if demand[:2] == (0, 0):
                self.input_expired = False
        if demand[:2] == (0, 0) and previous[:2] != (0, 0):
            self._wake.set()

    def current_demand(self):
        with self._lock:
            demand, generation, sampled = self._demand
            expired = time.monotonic()-sampled > .15
            if expired and demand[:2] != (0, 0):
                self.input_expired = True
            if (expired or self.input_expired or generation != self.generation or self.raised
                    or self.closed or self._cancel.is_set()):
                return 0, 0, demand[2]
            return demand

    def start_control(self):
        return self.submit(self._control_loop)

    def _control_loop(self):
        while not self._cancel.is_set() and not self.closed:
            started = time.monotonic()
            result = self.exchange(self.current_demand(), latest=self.current_demand)
            with suppress(Empty):
                self._results.get_nowait()
            with suppress(Full):
                self._results.put_nowait(result)
            self._wake.wait(max(0, 1/30-(time.monotonic()-started)))
            self._wake.clear()

    def exchange(self, demand, generation=None, latest=None):
        started = time.monotonic()
        # Keep the original 10 Hz sensor budget on the 38400-baud serial link.
        if time.monotonic()-self.ground_checked >= .1:
            self.raised = self.car.is_far_from_the_ground()
            self.ground_checked = time.monotonic()
        raised = self.raised
        left, right, head = demand
        if raised or self.closed or (generation is not None and generation != self.generation):
            left = right = 0
        sent = [(left, right, head)]
        if latest is None:
            self.car.drive_analogue(left, right, head)
        else:
            def refresh():
                sent[0] = latest()
                return sent[0]
            self.car.drive_analogue(*refresh(), latest=refresh)
        ack = time.monotonic()
        return raised, sent[0], (ack-started)*1000, ack, None

    def close(self):
        self.closed = True
        self.interrupt()
        # Cleanup is serialized behind any in-flight call, never concurrent with recv.
        self.executor.submit(self.disconnect)
        self.executor.shutdown(wait=False)
