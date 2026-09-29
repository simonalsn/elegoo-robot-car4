import struct
import socket
import time

import cv2 as cv
import numpy as np

from elegoo_robot_car4.udp_video import CHUNK, HEADER, FrameAssembler, UdpVideo


def packets(data, seq=1, token=123):
    count = (len(data) + CHUNK - 1) // CHUNK
    return [HEADER.pack(b'EVF1', token, seq, len(data), i, count)
            + data[i*CHUNK:(i+1)*CHUNK] for i in range(count)]


def test_reordered_fragments_and_duplicates():
    data = b'\xff\xd8' + b'x' * 3500 + b'\xff\xd9'
    p = packets(data)
    a = FrameAssembler(123)
    assert a.feed(p[2], 0) is None
    assert a.feed(p[2], 0.01) is None
    assert a.feed(p[0], 0.02) is None
    assert a.feed(p[1], 0.03) == data
    assert a.feed(p[0], 0.04) is None


def test_lost_frame_does_not_hold_up_next_frame_or_accept_old_packets():
    data = b'\xff\xd8' + b'x' * 1300 + b'\xff\xd9'
    a = FrameAssembler(123)
    old, new = packets(data), packets(data, 2)
    assert a.feed(old[0], 0) is None
    assert a.feed(new[1], 0.1) is None
    assert a.feed(old[1], 0.11) is None
    assert a.feed(new[0], 0.12) == data


def test_expired_incomplete_frame_is_never_published():
    data = b'\xff\xd8' + b'x' * 1300 + b'\xff\xd9'
    a = FrameAssembler(123)
    p = packets(data)
    assert a.feed(p[0], 0) is None
    assert a.feed(p[1], 0.3) is None
    assert a.feed(p[0], 0.31) is None


def test_invalid_lengths_tokens_and_jpeg_rejected():
    a = FrameAssembler(123)
    for p in [b'', packets(b'\xff\xd8ok\xff\xd9', token=9)[0],
              HEADER.pack(b'EVF1', 123, 1, 999999, 0, 834),
              packets(b'notajpeg')[0], packets(b'\xff\xd8ok\xff\xd9')[0][:-1]]:
        assert a.feed(p, 0) is None


def test_sequence_wrap():
    a = FrameAssembler(123)
    data = b'\xff\xd8ok\xff\xd9'
    assert a.feed(packets(data, 0xffffffff)[0], 0) == data
    assert a.feed(packets(data, 0)[0], 0.1) == data
    assert a.feed(packets(data, 0xffffffff)[0], 0.2) is None


def test_real_udp_subscription_decode_and_unsubscribe():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(('127.0.0.1', 0))
    server.settimeout(2)
    receiver = UdpVideo('127.0.0.1', server.getsockname()[1])
    try:
        request, peer = server.recvfrom(32)
        magic, token = struct.unpack('!4sI', request)
        assert magic == b'EVS1'
        ok, jpeg = cv.imencode('.jpg', np.zeros((60, 80, 3), np.uint8))
        assert ok
        for packet in reversed(packets(jpeg.tobytes(), token=token)):
            server.sendto(packet, peer)
        deadline = time.monotonic() + 2
        frame, age = receiver.latest()
        while frame is None and time.monotonic() < deadline:
            time.sleep(0.01)
            frame, age = receiver.latest()
        assert frame.shape == (60, 80, 3)
        assert age < 0.5
    finally:
        receiver.close()
    try:
        while True:
            request, _ = server.recvfrom(32)
            if request[:4] == b'EVX1':
                assert request[4:] == struct.pack('!I', token)
                break
    finally:
        server.close()
