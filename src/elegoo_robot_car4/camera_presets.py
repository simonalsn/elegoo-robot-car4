"""Runtime presets for the installed Arduino-ESP32 1.0.6 camera firmware."""
from dataclasses import dataclass
from queue import Queue, Empty
from threading import Thread, Lock, Event
import requests


@dataclass(frozen=True)
class CameraPreset:
    name: str
    size: tuple[int, int]
    quality: int
    framesize: int


# Enum IDs from the installed 1.0.6 sensor.h, not the current ESP-IDF driver.
PRESETS = {
    'fast': CameraPreset('Fast', (320, 240), 20, 5),
    'drive': CameraPreset('Drive', (640, 480), 15, 8),
    'balanced': CameraPreset('Balanced', (800, 600), 10, 9),
    'detail': CameraPreset('Detail', (1024, 768), 10, 10),
}


def apply_preset(host, key, get=None, cancelled=None):
    """Use one HTTP connection for the transaction; failures may be partial."""
    if get is None:
        with requests.Session() as session:
            return apply_preset(host, key, session.get, cancelled)
    quality_only = key.startswith('quality:')
    if quality_only:
        quality = int(key.split(':')[1])
        if not 10 <= quality <= 40:
            raise ValueError('Adaptive JPEG quality outside supported range')
        settings = [('quality', quality)]
    else:
        preset = PRESETS[key]
        quality = preset.quality
        settings = [('quality', quality), ('framesize', preset.framesize)]
    for variable, value in settings:
        if cancelled is not None and cancelled.is_set():
            raise ValueError('Camera setting cancelled')
        response = get(f'http://{host}/control', params={'var': variable, 'val': value}, timeout=(2, 3))
        try:
            response.raise_for_status()
        finally:
            response.close()
    if cancelled is not None and cancelled.is_set():
        raise ValueError('Camera setting cancelled')
    response = get(f'http://{host}/status', timeout=(2, 3))
    try:
        response.raise_for_status()
        status = response.json()
    finally:
        response.close()
    if not isinstance(status, dict):
        raise ValueError('Invalid camera status response')
    if status.get('quality') != quality or (not quality_only and status.get('framesize') != preset.framesize):
        raise ValueError('Camera settings did not match the requested preset')


class CameraSettings:
    """Single background request; no pygame calls or shared control socket."""
    def __init__(self, host):
        self.host = host
        self.results = Queue()
        self.busy = False
        # The legacy ESP32 has a small socket pool. Keep a single HTTP connection
        # across writes, readback AND later preset selections, instead of opening
        # a fresh connection for every requests.get().
        self._session = requests.Session()
        self._lock = Lock()
        self._working = False
        self._closed = False
        self._cancel = Event()
        self.quality = None

    def close(self):
        with self._lock:
            self._closed = True
            self._cancel.set()
            if not self._working:
                self._session.close()

    def start(self, key):
        with self._lock:
            quality_only = key.startswith('quality:') and key.split(':')[1].isdigit() and 10 <= int(key.split(':')[1]) <= 40
            if (key not in PRESETS and not quality_only) or self.busy or self._closed:
                return False
            self.busy = self._working = True
        def work():
            try:
                apply_preset(self.host, key, self._session.get, self._cancel)
                result = (key, None)
            except (requests.RequestException, ValueError) as exc:
                result = (key, f'{type(exc).__name__}: {exc}')
            finally:
                with self._lock:
                    self._working = False
                    if self._closed:
                        self._session.close()
            self.results.put(result)
        Thread(target=work, name='camera-settings', daemon=True).start()
        return True

    def poll(self):
        try:
            result = self.results.get_nowait()
        except Empty:
            return None
        self.busy = False
        key, error = result
        if error is None:
            self.quality = int(key.split(':')[1]) if key.startswith('quality:') else PRESETS[key].quality
        return result
