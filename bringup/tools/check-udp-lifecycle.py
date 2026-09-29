#!/usr/bin/env python3
"""Camera-only hardware check: subscription expiry, restart, stop and HTTP fallback."""
import json
import socket
import struct
import time
import urllib.request
from pathlib import Path

ip = '192.168.0.213'
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect((ip, 5000))
s.settimeout(0.3)
start = time.monotonic()
s.send(struct.pack('!4sI', b'EVS1', 901))
packets = 0
last = None
while time.monotonic() - start < 4.5:
    try:
        packet = s.recv(1500)
        if packet.startswith(b'EVF1'):
            packets += 1
            last = time.monotonic() - start
    except socket.timeout:
        pass
assert packets and last is not None and 2 < last < 3.8, (packets, last)
s.send(struct.pack('!4sI', b'EVS1', 902))
s.settimeout(2)
packet = s.recv(1500)
assert packet[:8] == struct.pack('!4sI', b'EVF1', 902)
s.send(struct.pack('!4sI', b'EVX1', 902))
# Drain in-flight datagrams; no new packets should arrive after a settling period.
s.settimeout(0.2)
end = time.monotonic() + 0.5
while time.monotonic() < end:
    try:
        s.recv(1500)
    except socket.timeout:
        pass
try:
    s.recv(1500)
    raise AssertionError('Video continued after unsubscribe')
except socket.timeout:
    pass
s.close()
with urllib.request.urlopen(f'http://{ip}/capture', timeout=5) as response:
    jpeg = response.read()
assert jpeg.startswith(b'\xff\xd8') and jpeg.endswith(b'\xff\xd9')
result = dict(packets=packets,last_packet_seconds_after_subscription=last,
              expiry_passed=True,resubscribe_passed=True,unsubscribe_passed=True,
              http_fallback_jpeg_bytes=len(jpeg))
Path('logs/udp-video/lifecycle.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
