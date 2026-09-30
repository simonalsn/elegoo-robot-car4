"""Bounded, latest-frame-only JPEG-over-UDP receiver for the local camera firmware."""
import select
import secrets
import socket
import struct
import threading
import time

import cv2 as cv
import numpy as np

HEADER = struct.Struct('!4sIIIHH')
CHUNK = 1200
MAX_FRAME = 262144


class FrameAssembler:
    """Accept reordered fragments within one frame; never wait for a lost fragment."""

    def __init__(self, token):
        self.token = token
        self.sequence = None
        self.parts = {}
        self.started = 0.0
        self.total = 0
        self.count = 0
        self.finished = False
        self.incomplete_frames = 0
        self.expired_frames = 0
        self.completed_frames = 0
        self.last_frame_bytes = 0

    def feed(self, packet, now):
        if len(packet) < HEADER.size:
            return None
        magic, token, sequence, total, index, count = HEADER.unpack_from(packet)
        if (magic != b'EVF1' or token != self.token or not 4 <= total <= MAX_FRAME
                or count != (total + CHUNK - 1) // CHUNK or index >= count):
            return None
        payload = packet[HEADER.size:]
        if len(payload) != min(CHUNK, total - index * CHUNK):
            return None
        if self.sequence is None or 0 < ((sequence - self.sequence) & 0xffffffff) < 0x80000000:
            if self.sequence is not None and not self.finished:
                self.incomplete_frames += 1
            self.sequence, self.total, self.count = sequence, total, count
            self.started, self.finished, self.parts = now, False, {}
        if (sequence != self.sequence or self.finished or total != self.total
                or count != self.count):
            return None
        if now - self.started > 0.25:
            self.expired_frames += 1
            self.parts.clear()
            self.finished = True
            return None
        self.parts[index] = payload
        if len(self.parts) != count:
            return None
        jpeg = b''.join(self.parts[i] for i in range(count))
        self.parts.clear()
        self.finished = True
        if jpeg.startswith(b'\xff\xd8') and jpeg.endswith(b'\xff\xd9'):
            self.completed_frames += 1
            self.last_frame_bytes = len(jpeg)
            return jpeg
        return None


class UdpVideo:
    def __init__(self, host, port=5000):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Extra datagram headroom for large JPEG bursts; frame cap, deadline and
        # latest-frame-only decoding remain unchanged. The OS may clamp this.
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024*1024)
        self.receive_buffer_bytes = self._socket.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        self._socket.settimeout(0.05)
        self._socket.connect((host, port))  # filters packets and replies through same firewall tuple
        self._token = secrets.randbits(32)
        self._assembler = FrameAssembler(self._token)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest = None
        self.error = None
        self.frames = 0
        self._thread = threading.Thread(target=self._run, name='udp-video', daemon=True)
        self._thread.start()

    def _run(self):
        renewed = 0.0
        while not self._stop.is_set():
            try:
                now = time.monotonic()
                if now - renewed >= 0.5:
                    self._socket.send(struct.pack('!4sI', b'EVS1', self._token))
                    renewed = now
                packet = self._socket.recv(HEADER.size + CHUNK + 1)
                jpeg = self._assembler.feed(packet, time.monotonic())
                # Drain already-arrived packets before decoding: drop superseded
                # complete frames instead of letting a decode queue build up.
                for _ in range(256):
                    if not select.select([self._socket], [], [], 0)[0]:
                        break
                    packet = self._socket.recv(HEADER.size + CHUNK + 1)
                    completed = self._assembler.feed(packet, time.monotonic())
                    if completed is not None:
                        jpeg = completed
                if jpeg is None:
                    continue
                frame = cv.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv.IMREAD_COLOR)
                if frame is not None:
                    with self._lock:
                        self._latest = (frame, time.monotonic())
                        self.frames += 1
                    self.error = None
            except socket.timeout:
                pass
            except (OSError, cv.error) as exc:
                self.error = str(exc)
                self._stop.wait(0.05)

    def latest(self):
        """Return (frame, local receive age), without waiting for network input."""
        with self._lock:
            if self._latest is None:
                return None, float('inf')
            frame, received = self._latest
            return frame, time.monotonic() - received

    def diagnostics(self):
        """Approximate counters for troubleshooting, never a connection verdict."""
        a = self._assembler
        return dict(completed=a.completed_frames, incomplete=a.incomplete_frames,
                    expired=a.expired_frames, last_jpeg_bytes=a.last_frame_bytes,
                    receive_buffer_bytes=self.receive_buffer_bytes)

    def close(self):
        self._stop.set()
        self._thread.join(timeout=1)
        try:
            self._socket.send(struct.pack('!4sI', b'EVX1', self._token))
        except OSError:
            pass  # firmware subscription also expires after three seconds
        finally:
            self._socket.close()
