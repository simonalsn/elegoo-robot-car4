"""Bounded, latest-frame-only JPEG-over-UDP receiver for the local camera firmware."""
import select
import secrets
import socket
import struct
import threading
import time
import sys

import cv2 as cv
import numpy as np

HEADER = struct.Struct('!4sIIIHH')
CHUNK = 1200
MAX_FRAME = 262144
MAX_AGE = .75
STATUS = struct.Struct('!4sIIIIII')


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
        self.started = min(self.started, now)
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
        self._timestamp_option = None
        if sys.platform == 'linux':
            option = getattr(socket, 'SO_TIMESTAMPNS', 35)
            try:
                self._socket.setsockopt(socket.SOL_SOCKET, option, 1)
                self._timestamp_option = option
            except OSError:
                pass
        self._socket.connect((host, port))  # filters packets and replies through same firewall tuple
        self._token = secrets.randbits(32)
        self._assembler = FrameAssembler(self._token)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest = None
        self.error = None
        self.frames = 0
        self.stale_frames = 0
        self.sender_status = None
        self._thread = threading.Thread(target=self._run, name='udp-video', daemon=True)
        self._thread.start()

    def _receive(self):
        if self._timestamp_option is None:
            return self._socket.recv(HEADER.size+CHUNK+1), time.monotonic()
        packet, ancillary, _, _ = self._socket.recvmsg(HEADER.size+CHUNK+1, socket.CMSG_SPACE(16))
        received = time.monotonic()
        for level, kind, data in ancillary:
            if level == socket.SOL_SOCKET and kind == self._timestamp_option:
                seconds, nanoseconds = struct.unpack('@ll', data[:struct.calcsize('@ll')])
                received -= max(0, time.time()-(seconds+nanoseconds/1e9))
        return packet, received

    def _feed(self, packet, received):
        if len(packet) == STATUS.size and packet[:4] == b'EVT1':
            _, token, frames, oversized, failed, size, quality = STATUS.unpack(packet)
            if token == self._token:
                self.sender_status = dict(frames=frames, oversized=oversized,
                                          failed=failed, bytes=size, quality=quality)
            return None
        jpeg = self._assembler.feed(packet, received)
        return (jpeg, self._assembler.started) if jpeg is not None else None

    def _run(self):
        renewed = 0.0
        while not self._stop.is_set():
            try:
                now = time.monotonic()
                if now - renewed >= 0.5:
                    self._socket.send(struct.pack('!4sI', b'EVS1', self._token))
                    renewed = now
                packet, received = self._receive()
                candidate = self._feed(packet, received)
                # Drain already-arrived packets before decoding: drop superseded
                # complete frames instead of letting a decode queue build up.
                for _ in range(256):
                    if not select.select([self._socket], [], [], 0)[0]:
                        break
                    packet, received = self._receive()
                    completed = self._feed(packet, received)
                    if completed is not None:
                        candidate = completed
                if candidate is None:
                    continue
                jpeg, received = candidate
                if time.monotonic()-received > MAX_AGE:
                    self.stale_frames += 1
                    continue
                frame = cv.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv.IMREAD_COLOR)
                if time.monotonic()-received > MAX_AGE:
                    self.stale_frames += 1
                    continue
                if frame is not None:
                    with self._lock:
                        self._latest = (frame, received)
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
                    receive_buffer_bytes=self.receive_buffer_bytes,
                    stale=self.stale_frames, kernel_timestamps=self._timestamp_option is not None,
                    sender=self.sender_status)

    def close(self):
        self._stop.set()
        self._thread.join(timeout=1)
        try:
            self._socket.send(struct.pack('!4sI', b'EVX1', self._token))
        except OSError:
            pass  # firmware subscription also expires after three seconds
        finally:
            self._socket.close()
