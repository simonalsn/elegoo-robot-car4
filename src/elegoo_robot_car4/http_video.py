"""Independent HTTP capture worker for the dashboard's fallback transport."""
import threading
import time

import cv2 as cv
import numpy as np
import requests


class HttpVideo:
    def __init__(self, host):
        self.endpoint = f'http://{host}/capture'
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest = None
        self.frames = 0
        self.error = None
        self._thread = threading.Thread(target=self._run, name='http-video', daemon=True)
        self._thread.start()

    def _run(self):
        with requests.Session() as session:
            while not self._stop.is_set():
                started = time.monotonic()
                try:
                    with session.get(self.endpoint, timeout=(1, .5), stream=True) as response:
                        response.raise_for_status()
                        data = bytearray()
                        for chunk in response.iter_content(16384):
                            if self._stop.is_set():
                                return
                            if time.monotonic()-started > .75 or len(data)+len(chunk) > 2*1024*1024:
                                raise ValueError('HTTP frame exceeded freshness or size limit')
                            data.extend(chunk)
                    if not (data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9')):
                        raise ValueError('Incomplete HTTP JPEG')
                    frame = cv.imdecode(np.frombuffer(data, np.uint8), cv.IMREAD_COLOR)
                    if frame is not None and time.monotonic()-started <= .75:
                        with self._lock:
                            self._latest = (frame, started)
                            self.frames += 1
                        self.error = None
                except (requests.RequestException, ValueError, cv.error) as exc:
                    self.error = str(exc)
                    self._stop.wait(.1)
                self._stop.wait(max(0, 1/30-(time.monotonic()-started)))

    def latest(self):
        with self._lock:
            if self._latest is None:
                return None, float('inf')
            frame, started = self._latest
            return frame, time.monotonic()-started

    def diagnostics(self):
        return dict(completed=self.frames, error=self.error)

    def close(self):
        self._stop.set()
        self._thread.join(timeout=.1)
