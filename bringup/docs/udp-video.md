# Dedicated UDP camera video

Status: implemented and compiled for ESP32-WROVER Camera V1.5 using the verified
M5STACK_WIDE pin mapping and ESP32 Arduino core 1.0.6. Flashed at application offset 0x10000; esptool verified its hash.
Isolated hardware tests passed. No measured improvement in end-to-end latency is claimed yet. No new
baseline measurement was performed. YOLO and UNO firmware are unchanged.

## Build and run

From the project directory, in `nix-shell`:

```sh
python3 tools/prepare-udp-video.py
arduino-cli compile --fqbn esp32:esp32:esp32:PartitionScheme=huge_app,PSRAM=enabled --build-path .cache/build/camera-udp firmware/camera-router/ESP32_CameraServer_AP_20220120
```

The overlay script is idempotent, does not read or print credentials, and copies
`firmware-overlays/udp-video/udp_video.cpp` into the configured private firmware
folder. It adds a declaration and startup call in `CameraWebServer_AP.cpp`.
The generated application contains Wi-Fi credentials: keep it private.

After flashing and reconnecting Wi-Fi, test camera-only while the ESP32 remains
isolated from the car:

```sh
python3 tools/probe-udp-video.py --robot-ip 192.168.0.213
```

After reassembly, use one video client at a time:

```sh
elegoo-smartcar-control --robot-ip 192.168.0.213 --video udp
```

HTTP remains the default for compatibility; explicitly select `--video udp`. Existing
`--video http`, `/capture` and `:81/stream` remain available. Do not open an HTTP
camera feed while using UDP: they compete for camera buffers and Wi-Fi airtime.

## Transport

Custom JPEG-over-UDP, not RTP/H.264: it uses the camera's existing JPEG output.
Camera configuration remains 800x600, JPEG quality 10 with PSRAM, XCLK 10 MHz,
two frame buffers. Wi-Fi sleep is disabled to reduce power-save delays.
A FreeRTOS task at priority 1 sends video independently of TCP control/serial.
No retransmission, FEC or adaptive bitrate is implemented.

The PC uses a connected UDP socket to camera port 5000. Subscribe/renew every
500 ms with `EVS1` plus a random uint32 session token. Stop with `EVX1` plus the
same token. Integers are big-endian. The camera leases the stream to the source
IP/port/token for three seconds; a second client cannot take an active lease.
The token distinguishes sessions; it is not authentication. LAN-only use.
Responses use the same UDP tuple, so a stateful firewall normally permits them
without opening an unsolicited inbound port. Verify on this PC before changing
firewall configuration.

Frame datagrams use Python struct `!4sIIIHH` (20-byte header):
`EVF1`, session token, frame sequence, total JPEG byte length, zero-based chunk
index, chunk count. Payloads are 1200 bytes except the final chunk. Total UDP
payload is at most 1220 bytes, below a typical LAN MTU. JPEGs are capped at
256 KiB. Sender yields after each eight packets and after each frame.

Receiver validates packet lengths and JPEG boundaries, accepts within-frame
reordering and duplicates, abandons incomplete frames after 250 ms or when a
newer frame arrives, handles sequence wraparound, and rejects old sessions.
It drains received datagrams before decoding, retains only the newest decoded
frame, and runs outside the pygame/control loop. UDP loss drops frames instead
of waiting for retransmission. It is not a guarantee of higher image quality
or a particular latency on congested Wi-Fi.

If no decoded frame has arrived for 750 ms, the controller blanks the image,
requests stop and blocks driving; Escape still works. This is local receive
age, not a synchronized capture-to-display latency measurement. Sensor queries
still block the control loop, and its existing 10 Hz cap remains. Those are
separate future responsiveness work. Client-side stop is best-effort; firmware
still lacks a reliable motor command lease on link loss.

## Flash and rollback

Do not flash until the ESP32 is USB-connected, car cable unplugged and car
battery disconnected. Confirm chip/MAC matches the known WROVER (MAC
40:91:51:bb:d6:08). Only write the app at 0x10000, then verify. No UNO upload,
partition change, erase-flash, bootloader or NVS overwrite is needed.

The new partition binary has been compared byte-for-byte with the known-working
router partition table. Build hashes/status are in `firmware-artifacts.json`.
The previous working router application is preserved separately at:
`.cache/build/camera-router/ESP32_CameraServer_AP_20220120.ino.bin`
(SHA-256 f0e3f98dbe4da41bbb0b05112acc342753da1fb8f5d86c15907e7eb37b60d190).
Rewriting that image at 0x10000 rolls back just this change. Full factory flash
backups and restore instructions remain in `backups/esp32-2026-09-28/`.

## Validation

ESP32 build: 2,612,690 program bytes; 56,720 global RAM bytes. Protocol tests
cover loss, reordering, duplicates, malformed packets, session isolation,
expiration and sequence wraparound. A real localhost UDP test checks subscription,
JPEG reconstruction/decoding and unsubscribe. Controller tests cover stale-video
stop and cleanup. Physical validation on the isolated ESP32: 178 decoded 800x600 frames in
15.02 seconds (~11.9 fps); latest receive age at completion 52 ms. This age
is not end-to-end latency. The saved image was visually inspected. Subscription
expiry passed (last packet ~3.09 s after the only renewal); resubscription,
explicit unsubscribe and HTTP JPEG fallback also passed. Logs and image:
`logs/udp-video/`. Assembled-car coexistence with actual control and subjective
driving responsiveness remain untested. No movement commands were sent.

The actual pygame UDP display loop also passed a five-second off-screen check:
57 decoded frames, 800x600 display, normal quit and cleanup. Car control was
mocked: zero HTTP captures and zero movement calls. See `logs/udp-video/display.json`.
