#!/usr/bin/env python3
"""Prepare a separate ESP32 diagnostic candidate; never flash or replace installed sources."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
source = root / 'firmware/camera-control38400/ESP32_CameraServer_AP_20220120'
target = root / 'firmware/camera-video-diagnostics/ESP32_CameraServer_AP_20220120'
shutil.copytree(source, target, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('*.bin', '*.elf', '*.map'))
shutil.copyfile(root / 'firmware-overlays/udp-video/udp_video.cpp', target / 'udp_video.cpp')
print('Prepared ESP32 video diagnostics candidate; no flashing performed.')
