# Active-code review fixes — 2026-09-30

Baseline before these changes: `1f604ed`, committed and pushed to the user's fork.
The fixes are separate working changes. No robot commands or firmware uploads
were used for validation.

## Control scheduling and input freshness

The dashboard samples input at up to 120 Hz and renders at up to 30 Hz. One network
worker refreshes drive commands independently at up to 30 Hz, retaining one latest
input snapshot rather than a command queue. Zero demand wakes the worker early.
It reads the current demand after a ground query and again after UART pacing,
immediately before serialization. Normal trigger release and both-trigger stop
therefore replace an unsent movement demand even while a sensor query is pending.

Input older than 150 ms forces zero wheel speeds and requires neutral recovery.
Focus/video/controller guards and manually latched Stop are preserved. A command
already on the wire cannot be recalled; the existing UNO 400 ms lease remains the
fallback. Sensor queries stay at 10 Hz. Their IDs are shortened from verbose
strings to five characters, reducing a representative request/reply from 79 to
33 bytes (about 20.6 to 8.6 ms on the 38400-baud UART). The dashboard's **Control
exchange** metric includes sensor-query and pacing time, not just the final ACK.
This is transaction duration, not physical input-to-motion latency.

Reconnect skips the 30-sample MPU offset calibration and centres the camera using
the acknowledged zero-wheel command after firmware negotiation. Default `Car()`
library initialization retains calibration for optional navigation. Cancellation
interrupts established control sockets and pacing; an OS TCP connect is bounded
by its two-second timeout. Cleanup stays serialized with control I/O.

## Video freshness and HTTP fallback

UDP frames retain their first packet's receive timestamp through assembly and
decoding. Frames older than 750 ms are dropped both before and after decoding.
Linux uses kernel receive timestamps where supported, accounting for socket
backlog. Other platforms use userspace receive timestamps, which cannot reveal
time already spent queued in the kernel. Neither is a synchronized sensor
capture timestamp; camera and network transit delay remain outside that metric.

HTTP capture uses its own background worker and persistent session. It cannot
block drive/Stop transactions. Request-start time is retained as a conservative
age; capture size and age are bounded. Pending camera-setting operations are
cancelled between requests on reconnect, so old preset sequences are not replayed.

## Adaptive quality and diagnostics

Fast, Drive and Balanced retain their chosen quality. Detail increases the JPEG
quality number by five (more compression), up to 40, when receive age exceeds two
seconds, frames approach 220 KiB, or counters indicate substantial loss. Decisions
are at least five seconds apart and require a responsive control link. Changes
use the same acknowledged-zero, fresh-video and neutral-input gates as manual
presets; they never clear a manual Stop. Selecting a preset resets its quality.
Resolution is retained. The UI reports adaptive quality in the preset message.

Older firmware works with this fallback adaptation. The updated ESP32
firmware sends `EVT1` diagnostic datagrams with oversized-frame and send-failure
counters, allowing better diagnosis when frames never reach the PC. Existing
`EVF1`, `EVS1` and `EVX1` messages remain unchanged; old receivers ignore diagnostics.
The 256 KiB frame cap and 250 ms assembly deadline remain in effect.

The diagnostic application was compiled and **flashed on 2026-09-30**:

```sh
python tools/prepare-video-diagnostics.py
arduino-cli compile --fqbn esp32:esp32:esp32:PartitionScheme=huge_app,PSRAM=enabled --build-path .cache/build/camera-video-diagnostics firmware/camera-video-diagnostics/ESP32_CameraServer_AP_20220120
```

Application: `.cache/build/camera-video-diagnostics/ESP32_CameraServer_AP_20220120.ino.bin`

SHA-256: `421da18be31f9a2218a80708367ba34559a321aa1f71de2dac8d2989fab5fe4a`

Build report: 2,613,022 program bytes, 56,720 global RAM bytes. UART remains
38400 baud; camera clock remains 10 MHz. The preparation script copies the working
ESP32 sources into a separate candidate folder, preserving rollback sources and
private router settings. Compiled images contain credentials and stay excluded.
Flashing requires the established isolated-ESP32 setup; no UNO update is needed.

Upload and subsequent independent digest verification passed at offset 0x10000.
A fresh full backup matches the previous working application and the unchanged
partition table. Backup, upload and verification logs are retained privately in
`logs/video-diagnostics-2026-09-30/`. Application-only rollback uses
`.cache/build/camera-control38400/ESP32_CameraServer_AP_20220120.ino.bin`
at 0x10000 (SHA-256 `bd96d9d0a15c8516e4f8ac6448b6fa7b61d45278b8e3c8610336d05c15744ee6`).
After reset, the video-only probe received 174 frames at 800×600 in 15 seconds,
with EVT1 diagnostics and zero incomplete/expired frames or sender oversize/send
failures. Latest receive age was 126 ms; this is not capture-to-display latency.
No motor-control connection was opened.

## X11 startup fix

The dashboard now defaults `SDL_FRAMEBUFFER_ACCELERATION=0` before creating its
window; an explicit environment override remains possible. Its Surface-based
renderer needs no OpenGL context. SDL's automatic acceleration reproduced a
fatal `X_GLXCreateContext BadValue` on this desktop. The software surface passed
a real desktop window/redraw/resize check without connecting to the robot.
See [SDL's framebuffer hint](https://wiki.libsdl.org/SDL2/SDL_HINT_FRAMEBUFFER_ACCELERATION).

## Rendering and validation

The dashboard reuses scaled destination and stale-overlay surfaces and caches up
to 256 text surfaces. Offline SDL redraw medians before/after were approximately
5.75/5.09 ms at 1200×960, 11.06/4.73 ms at 1920×1080 and 12.73/11.04 ms at
3840×2160. These are local dummy-display timings, not live camera latency.

Tests include real worker threads with delayed sensor replies while the active
dashboard releases triggers, presses both triggers or applies manual Stop;
independent control refresh and input expiry; cancellation during initialization;
delayed decoding and kernel timestamp conversion; slow HTTP capture; quality-only
updates; and active preset handling while manual Stop is latched.

Physical driving and power-cycle checks remain pending. Higher camera clocks and
UART rates were not introduced: they need separate measurements on this hardware.

Final desktop regression result: **168 passed, 2 skipped** (optional dependencies
are not installed). The ESP32 diagnostic candidate compiled successfully.
