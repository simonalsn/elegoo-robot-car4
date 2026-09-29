# Control reply corruption follow-up (2026-09-29)

User reported two crashes during analogue driving: a non-UTF-8 byte 0xff in
control replies at offsets 7/8. The earlier zero-speed test did not establish
reliability under motor/servo load. Root cause is not yet confirmed.

Installed PC changes:
- Validate control replies as ASCII. Reject the entire received chunk containing
  invalid bytes, clear the partial reply, and report bounded hex diagnostics.
  Never strip bad bytes to manufacture an acknowledgement.
- Catch drive transaction failures in the main loop, request stop, reset the
  acceleration ramp and keep the window responsive.
- Latch driving off until a fresh zero-speed command is acknowledged AND triggers
  and steering are neutral. Failed driving commands are never automatically retried.
- Repeated sensor failures in analogue mode also keep driving blocked instead of
  raising an unhandled loop error. Focus loss requires neutral before resuming.
- Accept both existing drive_v1 (115200) and candidate drive_v2_38400 capability
  replies, selecting compact-command pacing to match the firmware.

Firmware status: both 38400-baud applications flashed and verified. UNO USB
checks and isolated ESP32 UDP video passed; longer paired zero-speed validation passed; loaded validation pending.

Changes:
- UNO + ESP32 control UART at 38400, retaining ESP32 USB debug UART at 115200.
  At 16 MHz, AVR's selected divisor gives about +0.16% error at 38400 versus
  +2.12% at 115200. Nominal wire time for 60 bytes is 15.625 ms, still compatible
  with the intended 30 Hz update loop. This is a reliability candidate, not proof
  that baud mismatch caused the reports.
- ESP32 TCP/UART bridge checks integer read results before narrowing to char.
  The original code could forward read() == -1 as 0xff. The installed ESP32
  core's availability check sums queue length and FIFO count separately while
  its ISR transfers bytes between them, so a transient false-empty result is
  plausible. This is a code-based hypothesis, not a reproduced cause.
- Existing 400 ms UNO drive lease and UDP video are retained.

Build inside nix-shell:

```sh
python3 tools/prepare-analogue-drive.py --baud 38400
arduino-cli compile --fqbn arduino:avr:uno --build-property compiler.c.extra_flags=-mcall-prologues --build-property compiler.cpp.extra_flags=-mcall-prologues --build-property compiler.c.elf.extra_flags=-mcall-prologues --build-path .cache/build/uno-control38400 firmware/uno-control38400/SmartRobotCarV4.0_V1_20230201
arduino-cli compile --fqbn esp32:esp32:esp32:PartitionScheme=huge_app,PSRAM=enabled --build-path .cache/build/camera-control38400 firmware/camera-control38400/ESP32_CameraServer_AP_20220120
```

The 115200 sources/builds remain separate. This is a paired rate change: update
both boards while individually isolated before reconnecting. Do not mix UART
rates. Original and pre-analogue rollback images remain untouched.

Validation: 88 Python tests pass, including corrupted-ACK rejection, split valid
ACKs, both firmware versions, neutral-release recovery and loop-level no-crash/
no-replayed-throttle behaviour. The final zero-speed-recovery stop refinement
passed all 24 analogue tests. UNO builds at 31,900 flash / 1,227 global RAM bytes;
ESP32 at 2,612,742 program / 56,720 global RAM bytes. UNO hardware validation passed: 31,900 bytes uploaded and verified, all 512
bootloader bytes preserved, 150 zero-speed updates plus sensors at 38400 baud.
Mean acknowledgement 16.1 ms, maximum 20.1 ms. ESP32 application uploaded at 0x10000 and esptool hash verified. Its partition
table is unchanged. Isolated UDP check: 96 decoded 800x600 frames in 8.01 seconds,
no receiver error. The paired run passed all 1,800 zero-speed transactions in
65.36 seconds, with ground queries and MPU data while decoding 780 UDP frames
at 800x600. No corrupt-reply exception or timeout occurred. Acknowledgements
averaged 27.1 ms and peaked at 263.1 ms; this is not motor-response latency.
Final stop sent and clients disconnected. An attended loaded test remains pending. If faults persist, investigate power/noise and physical
connections as well as serial handling; do not claim success from zero-speed
traffic alone.

User subsequently reported that the revised link works really well while using
the car; the next reported issues were input sensitivity and idle camera twitch,
not reply corruption. This is user feedback, not a controlled endurance test.
