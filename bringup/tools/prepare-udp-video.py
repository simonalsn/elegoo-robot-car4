#!/usr/bin/env python3
"""Apply the local UDP overlay to the already-configured router firmware."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
firmware = root / 'firmware/camera-router/ESP32_CameraServer_AP_20220120'
source = firmware / 'CameraWebServer_AP.cpp'
data = source.read_bytes()
newline = b'\r\n' if b'\r\n' in data else b'\n'
if b'void startUdpVideo();' not in data:
    assert data.count(b'void startCameraServer();') == 1
    assert data.count(b'  startCameraServer();') == 1
    data = data.replace(b'void startCameraServer();', b'void startUdpVideo();' + newline + b'void startCameraServer();')
    data = data.replace(b'  startCameraServer();', b'  startCameraServer();' + newline + b'  startUdpVideo();')
    source.write_bytes(data)
shutil.copyfile(root / 'firmware-overlays/udp-video/udp_video.cpp', firmware / 'udp_video.cpp')
print('UDP overlay prepared; router credentials unchanged. No flashing performed.')
