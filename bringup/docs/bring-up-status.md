# ELEGOO V4 bring-up status

## Scope and current state

UNO upstream-patched firmware was uploaded on 2026-09-28; AVRDUDE verified
all 31,830 programmed bytes. The entire 512-byte bootloader was read back and
matches its original backup. USB sensor checks passed without movement commands.
ESP32 router firmware was uploaded at 0x10000 on 2026-09-28 and its flash hash
verified. The compiled partition table exactly matched the existing one, so
only the application was written; bootloader, partition table and other
partitions were preserved. Camera capture and streaming now pass on this V1.5
board with the unchanged M5STACK_WIDE mapping. The close-up `car pictures/20260927_221837.jpg`
identifies an ESP32-WROVER module on an ESP32-WROVER Camera V1.5 PCB,
with a CH340C USB bridge. The supplied schematic is V1.2; successful live
capture and streaming confirm the selected camera mapping works on this V1.5.
The other photos show SmartCar-Shield-V1.1 and a readable TB6612FNG marking.
Reassembled Wi-Fi sensor/camera checks now pass through the unchanged upstream
Car class. Four 0.35-second motor commands at speed 80, each followed by stop,
were sent. A second test used one-second pulses at speed 80 with three-second
stop intervals; the user explicitly observed forward, backward, left and right.
The final command was stop. Requested basic bring-up is complete. Physical
direction observation is human evidence; command logs separately record stops
and continued sensor responses. No floor-driving/endurance test was performed.
USB checks returned expected MPU device ID 52
(the library's six-bit WHO_AM_I extraction), five plausible acceleration/gyro
samples, ultrasonic 150, IR 246/53/47, ground false, and stop acknowledgment.
These are single-session functional readings, not sensor calibration or proof
of ground-status semantics. Logs are in `logs/uno-2026-09-28/`.
The ESP32 backup is complete and verified
in `backups/esp32-2026-09-28/`. UNO flash is also backed up twice in
`backups/uno-2026-09-28/`; both 32 KiB reads match. Its EEPROM readback is
UNSUPPORTED by the matched Optiboot bootloader: returned data aliases flash.
Those files are explicitly named INVALID and must not be restored to EEPROM.
New photos confirm TB6612FNG and an ELEGOO UNO R3 with an Atmel-marked MCU.
The full CPU engraving and IMU model remain too faint for confident optical
transcription; see `docs/hardware-photo-review.md` for evidence and confidence.
No restore test has been performed.

## Preserved sources

- `upstream/`: clone with local desktop reliability fixes (see below), based on https://github.com/micdestefano/elegoo-robot-car4
  at `f223111f4d5016834936112022f0ce9f80291cff`.
- Official archive: `stock/elegoo-v4-2023.02.01.zip`.
  SHA-256: `7cfdd6e0cd39c48bf070a758519497ed1b1da92a5312f4255460a6e95ca61055`.
- Official download page:
  https://www.elegoo.com/blogs/arduino-projects/elegoo-smart-robot-car-kit-v4-0-tutorial
- Stock contents are preserved in `stock/extracted/`.
- `firmware/uno/` and `firmware/camera-ap/` contain separate working copies
  with upstream's TB6612/MPU6050 and AP camera patches applied without fuzz.
  These compile successfully. The UNO application has been uploaded. Included `.bin`/`.hex`
  files remain STOCK binaries; patching sources does not rebuild them.

## Compatibility findings and open questions

Upstream explicitly targets TB6612, MPU6050, ESP32-WROVER and an
ELEGOO UNO R3 Car v2.0. The official archive has the corresponding UNO
and WROVER source directories. SmartCar-Shield-V1.1 alone does not prove
the camera PCB model, camera wiring, or UNO revision. Confirm the actual
module and PCB markings and compare the official WROVER V1.2 schematic
and camera pin definitions before any flash operation.

Upstream recommends Espressif Arduino core 1.0.4 (also reports 1.0.6 works),
ESP32 Dev Module, Huge APP partition scheme, PSRAM enabled. Do not silently
substitute a current core. Its UNO target is Arduino UNO with Servo library.

TCP control is port 100; camera endpoints include `/capture` and
port 81 `/stream`. Stock commands used by upstream include N=100 stop,
N=102 direction (D1=1/2/3/4 forward/back/left/right, D2 speed),
N=21 ultrasonic, N=22 tracking IR, and N=23 ground detection.
The UNO patch adds N=1000 for timestamp and six raw MPU6050 channels.
The Python Car constructor requests 30 MPU samples immediately, so stock
UNO firmware is not sufficient for this client even just to connect.

The camera patch removes heartbeat timeout checking. The router variant
also removes the AP station-count stop check. Do not assume connection
loss guarantees a prompt stop. Initial motor tests need wheels clear,
short movements, explicit stop, and the power switch within reach.

## Rollback prerequisites before flashing

1. Identify both boards and USB ports. Record current stock behavior.
2. Disconnect motor power for programming/backup and follow the official
   board connection instructions. Isolate the ESP32 from the robot.
3. Use esptool identification and `flash-id` to record chip and flash size.
   With current esptool, `read-flash 0 ALL <backup.bin>` reads the full chip.
   Capture twice, compare sizes and SHA-256 hashes, and retain logs.
   See https://docs.espressif.com/projects/esptool/en/latest/esp32/esptool/basic-commands.html
4. For the confirmed ATmega328P UNO, use avrdude read operations to preserve
   flash and EEPROM. Determine programmer/baud from the confirmed board;
   do not write fuses or burn a bootloader. Check whether the bootloader
   actually permits complete readback before claiming an exact backup.
5. Retain the matching official UNO HEX and source as stock recovery assets.
   The camera `.ino.bin` is not proof of a complete full-flash recovery image;
   preserve the full device dump including bootloader, partitions and NVS.
6. Verify recovery tooling and the appropriate image layout before upload.
   Restore a full ESP32 dump at offset zero only to its original identified
   board; never treat an application-only BIN as a full dump. Never force
   past encryption, security, or chip-mismatch errors.

## Host preparation and differences from upstream

The host uses NixOS. Tools were added to `/home/simon/nixos-config`
(the requested `~/nix-config` did not exist), tagged `ELEGOO V4 bring-up`:
uv, just, arduino-cli, esptool, avrdude, poppler-utils, unzip, gnumake,
patch, and an explicit python3.12 launcher preserving default Python.
The user was added to dialout for serial access. Dry-build and diff checks
passed. The user subsequently rebuilt the system, and tool availability and
configured dialout membership have been verified. Python dependency
installation is complete: the client imports and all 35 existing upstream tests
pass (including mock integration tests, not physical hardware).
`shell.nix` now supplies a project environment
with native wheel libraries and a `car-setup` command; see the root README.
The shell startup, Python 3.12, uv and Arduino CLI have been checked.
Arduino directories and uv cache are kept inside this workspace.

Firmware builds pass with Arduino AVR core 1.8.6, ESP32 core 1.0.6,
Servo 1.2.2, and ELEGOO's bundled FastLED 3.2.10. Unlike the upstream README's
experience, this clean environment required extracting `FastLED-master.zip`
from the official UNO `addLibrary` directory into
`.cache/arduino/user/libraries/`. No source changes were needed.

| Build | Program bytes | Static RAM bytes |
| --- | ---: | ---: |
| UNO stock | 30988 / 32256 | 1169 / 2048 |
| UNO patched | 31830 / 32256 | 1218 / 2048 |
| ESP32 stock | 2609130 / 3145728 | 56392 / 327680 |
| ESP32 AP patched | 2609102 / 3145728 | 56392 / 327680 |

The UNO's remaining 830 bytes of RAM must also accommodate stack and dynamic
allocations; compilation alone does not verify runtime stability.
Build outputs are under `.cache/build/`. Stock build outputs are also preserved
under `backups/compiled-stock/` with a SHA-256 manifest. Vendor binary hashes
are in `backups/stock-assets.json`. Neither set is a backup of the actual boards.

The official V1.2 schematic agrees with the stock M5STACK_WIDE camera mapping:
data D0–D7 GPIO 32,35,34,5,39,18,36,19; XCLK 27, SDA 22, SCL 23,
VSYNC 25, HREF 26, PCLK 21, RESET 15; PWDN is tied low. Car UART uses
RX 33 / TX 4 at 9600 baud. This does not prove V1.5 wiring is identical.

No upstream application code was changed. `tools/probe-uno.py` and
`tools/probe-wifi.py` are bring-up checks, not a new control application;
the Wi-Fi probe uses upstream's existing Car class. Local CLI instructions
use `--robot-ip` as required by the current parser, correcting the upstream
README's positional-IP example. Stock and patched firmware are
kept outside the upstream checkout to preserve recovery assets. The user selected
router mode. `firmware/camera-router/` contains an independent stock copy with
upstream's router patch applied without fuzz. `tools/configure-router.py` prompts
locally for credentials and generates the template header with escaped strings
and mode 0600; this avoids upstream's unescaped sed substitution and visible
password entry. No firmware behavior is changed by this configuration helper.
Credentials must never be copied into these notes or printed in tool logs.
No new application or architecture has been introduced.

## Bring-up results and retained limitations

- Hardware identification, accepted assumptions and rollback limitations are
  recorded above; original stock runtime behavior was not exhaustively tested.
- The official V1.2 schematic's mapping works on the physical V1.5 camera PCB.
  Protocol PDF text is extracted in `docs/protocol.txt`; its N=100, 102,
  21, 22 and 23 commands agree with the upstream client. The stock camera
  source selects CAMERA_MODEL_M5STACK_WIDE even for ELEGOO WROVER hardware;
  do not change that to CAMERA_MODEL_WROVER_KIT based on the module name.
- ESP32 backup completed: two full 4,194,304-byte reads match exactly.
  SHA-256: `625ec0c59372b410f849b2e155ed287ec05ec1a7821f8fb0701e5c9f2155fadc`.
  Electronic ID: ESP32-D0WDQ6 rev 1.0, MAC 40:91:51:bb:d6:08,
  4 MiB flash. Flash encryption and secure boot disabled according to
  read-only eFuse status register checks. The original application differs
  from the official archive's application binary, making this full backup
  the preferred exact rollback image. Restore instructions and logs are
  in its backup directory. The board was reset to original firmware after backup,
  before the later verified application-only upload.
- UNO flash backup completed: two identical 32,768-byte reads, SHA-256
  `7501f89280e07d79a7a8ebac01aec3451c839feb25025077df27a9c6f4b573dd`.
  The bootloader's populated bytes exactly match Arduino's ATmega328 Optiboot
  4.4 image; the application differs from the official 2023 HEX. A separate
  32,256-byte application rollback image excludes the bootloader. EEPROM/fuses
  remain uncaptured; full capture would require suitable ISP access. Serial
  flash-only application upload preserved EEPROM/bootloader; no EEPROM or fuse
  writes occurred. Post-upload readback confirmed the bootloader was unchanged.
  See the UNO backup README for limitations and unexecuted rollback commands.
- User accepted ATmega328P and MPU6050 as educated working assumptions after
  the markings remained too faint to read. No additional photos are required.
  TB6612FNG and ESP32-WROVER Camera V1.5 are confirmed. Revisit the assumptions
  if programming/verification or MPU readings fail. Begin with application-only
  UNO upload and USB-powered sensor checks, keeping motor battery disconnected.
  Those steps now pass; MPU data supports the assumed sensor compatibility.
- Router configuration, build and upload are complete. ESP32 MAC
  40:91:51:bb:d6:08 joined the local router at 192.168.0.213 (DHCP; may change).
  `/capture` returns HTTP 200 JPEG; port 81 `/stream` returns HTTP 200 MJPEG.
  Three stream frames and one still image were saved and visually decoded at
  800×600. TCP port 100 accepts a connection and returns `{Heartbeat}`.
  Results/logs are in `logs/esp32-2026-09-28/`. No movement commands were sent.
- User completed reassembly, cam switch selection and battery power with
  wheels clear. Upstream Car connected, completed its MPU calibration, read
  MPU samples (~1 g at rest), ultrasonic, all three IR channels and ground
  status, and decoded an 800×600 camera image. Results: `logs/assembled-wifi/`.
  The ultrasonic result applies upstream's fitted calibration to the raw
  firmware reading; a raw maximum of 150 becomes ~188.7 cm. Treat that value
  as saturated/out-of-range, not a measured 188.7 cm. Calibration was not changed.
- Forward, backward, left and right were initially commanded at speed 80 for
  0.35 seconds, with explicit stops, two-second pauses and a successful MPU
  query after each. The client sent a final stop and disconnected. The user
  missed the initial sequence, so it was repeated at speed 80 for one second
  per direction with three-second stop intervals. The user reported:
  "Forwards - backwards - left - right, observed."
  Retest evidence: `logs/assembled-wifi/motor-retest.json`. Each command was
  followed by stop and a successful MPU query; a final stop preceded disconnect.
- Scope completed: PC-to-robot router Wi-Fi, upstream movement commands,
  explicit stop, camera stream and available sensor queries. Firmware uses the
  upstream patches. Subsequent desktop reliability changes are recorded below.
  No new application or architecture was introduced.
  Exact physical MCU/IMU markings, a destructive restore test, EEPROM/fuse
  backup, sensor calibration, floor driving and link-loss stopping remain
  unverified and are not claimed as completed tests.

## Desktop reliability follow-up

The desktop controller was not covered by the initial command-level bring-up.
The user subsequently reported a sensor-response timeout and corrupt JPEGs.
Lifting the car also activates the controller's IR-based ground interlock.

Local changes in `upstream/src/elegoo_robot_car4/car.py` and
`elegoo_smartcar_control.py` add bounded response/capture waits, EOF handling,
complete-JPEG validation, conservative command spacing for the 9600-baud
bridge, stop requests on camera/connection errors, limited recovery attempts,
clearer raised/error window captions, early Escape/quit handling and best-effort
stop/disconnect cleanup. These do not provide a firmware link-loss stop guarantee.
The original timeout's exact cause has not been established.

Validation: 41 tests passed (35 existing plus six regression tests). A 15-second
headless run of the actual desktop loop against the raised robot recovered
from four incomplete JPEGs and exited normally. Movement was prohibited in
that test. An original-client probe completed 30 capture/ground/stop cycles;
cycle durations were approximately 0.18–0.66 seconds. These are loop timings,
not measured camera end-to-end latency. No firmware was changed in this follow-up.

The local source diff is saved in `patches/local-desktop-bringup.patch`; regression
tests are in `upstream/tests/unit_tests/test_bringup_regressions.py`. Floor driving,
controller mappings and loss-of-link stopping still need separate validation.

## UDP video extension

Dedicated JPEG-over-UDP firmware and asynchronous PC receiver are implemented.
Build passes and partition table is unchanged. Flashed at 0x10000 with
esptool hash verification. Isolated camera delivered 178 decoded 800x600 frames
in 15 seconds; subscription expiry/restart/stop and HTTP fallback passed.
HTTP remains the default; use `--video udp` to select the new transport. See `docs/udp-video.md` for scope and rollback.

## Gamepad follow-up

8BitDo Ultimate 2C Wireless detected with complete SDL mapping. Client now uses
named gamepad inputs and handles hotplug before driving interlocks. Controller
fixes and 64 passing tests are documented in `docs/gamepad.md`. Live input
recording captured neutral state only; no physical driving test was performed.

## Analogue drive follow-up (2026-09-29)

New signed-wheel/absolute-pan mode and paired 115200-baud firmware builds are
ready. UNO uploaded and verified (31,894 bytes); all 512 bootloader bytes preserved.
150 zero-speed USB updates with sensor queries passed at 115200; no motion tested.
84 Python tests passed. ESP32 uploaded at 0x10000 and hash verified; isolated UDP
test decoded 95 frames in 8 seconds. Paired Wi-Fi check passed: 300 zero-speed
updates, ground queries and MPU while UDP decoded 119 frames in 10.43 seconds.
Acknowledgements averaged 19.0 ms (maximum 243.2 ms). Final stop sent; actual
analogue driving and physical lease-stop timing have not been tested.
See `docs/analogue-drive.md`; paired rollback files are in
`backups/working-before-analogue/`.

## Control corruption follow-up

User reported repeat 0xff reply crashes under use. PC now rejects corrupt replies,
requests stop and requires a valid zero acknowledgement plus neutral controls
before resuming. 88 tests pass. Guarded ESP32 reads and paired 38400-baud firmware
are built but not flashed. See `docs/control-recovery.md`. Root cause not confirmed.

Recovery UNO firmware is now uploaded and verified at 38400 baud; bootloader
unchanged. 150 zero-speed updates and sensors passed (mean ack 16.1 ms, max
20.1 ms). Matching ESP32 update is still required before reassembly.

Matching 38400-baud ESP32 application is now uploaded at 0x10000 and hash
verified. Isolated UDP video passed: 96 frames in 8 seconds, 800x600. Both boards
now have matching rates. Reassembly, longer paired test and loaded driving
validation remain pending; the original corruption is not yet proven resolved.

Longer 38400-baud paired test passed: 1,800 acknowledged zero-speed updates in
65.36 seconds, ground/MPU reads and 780 decoded 800x600 UDP frames. No corrupted
reply or timeout. Mean acknowledgement 27.1 ms, maximum 263.1 ms. Final stop sent.
Physical camera/motor-load testing is still required to confirm the reported
corruption is resolved. Evidence: `logs/control-recovery-2026-09-29/wifi-probe.json`.

## Input sensitivity and idle servo follow-up

User reports the revised link works well. Throttle/steering now use squared
response after deadzones; camera response and stop semantics unchanged. All 94
Python tests pass. A UNO-only candidate releases servo pulses after 500 ms at an
unchanged target; it builds (32,084 bytes) but is not flashed. See `docs/servo-idle.md`.

User requested still softer controls: throttle and steering now use a cubic
response after deadzones. All 94 tests pass. Idle-servo UNO update uploaded and
32,084 bytes verified; original bootloader preserved. 150 zero-speed USB updates
and ground/MPU queries passed at 38400 baud (mean 16.0 ms, maximum 18.3 ms).
ESP32 unchanged. Physical idle-twitch check is pending user observation.

## Motor breakaway and servo pulse follow-up

Added minimum moving-wheel PWM 11 above the cubic input curve, based on the
user's requested previous 40% trigger output. Exact zero and full output remain;
100 client tests pass including cancellation and camera tracing. Physical driving
validation pending. User reports idle twitch gone but intermittent full-right
camera movement, also after sitting still. Separate pulse-safe release candidate
builds (32,130 flash bytes, 1,231 global RAM); mocked pulse/interrupt tests pass.
Not flashed; actual cause of full-right events not established. See servo-idle.md.

Pulse-safe UNO candidate now uploaded and verified (32,130 bytes), with original
bootloader preserved. 150 zero-speed USB commands and ground/MPU queries passed
at 38400 baud. User also requested 50% more minimum motor input: 11 increased
to 17 PWM (16.5 rounded up) in both directions and pivot turns. All 100 client
tests pass. Physical driving/camera validation remains pending.

User reports good operation and no camera servo issues after the pulse-safe
update. Minimum moving-wheel output increased to 25 PWM at user request;
PC-only change, with cubic response and maximum 200 retained.

User reports 25 PWM is working well and requested trying 30 PWM as the minimum.
Updated the PC motor mapping; existing acceleration limit and stop behavior remain.

User reports the 30 PWM floor is ideal for straight driving and stationary turns,
but requests a larger initial wheel differential while driving. Added a 20%
moving steering floor, blended by post-cubic throttle up to 0.25 demand; zero
throttle preserves the existing pivot curve. At full throttle initial turning
targets about 200/143 PWM. No firmware change. Physical tuning pending.
All 40 analogue control tests pass, including forward/reverse boost, blend
continuity, wheel limits, acceleration limiting and immediate stop.

## Implemented driving dashboard

The analogue pygame client now uses the reviewed dashboard layout. Status,
commanded inputs/outputs, camera target, video metrics, controller/focus state,
Stop/Space latch and explicit neutral-before-resume are implemented. Offline
preview is available with `--dashboard-preview`. Rendering and control interlocks
are tested with mocked hardware; no robot commands or physical driving test were
performed for this change. See `docs/dashboard/README.md` for usage and limitations.

## Runtime video presets

Added Fast 320x240/JPEG20, Drive 640x480/JPEG15, Detail 1024x768/JPEG10,
and Max detail 1600x1200/JPEG10 to the dashboard. Runtime HTTP settings use
existing camera firmware, with background requests and readback plus fresh-frame
confirmation. Selection confirms Stop first and holds driving until explicit
Resume. No firmware, clock or buffering change; actual FPS comparison pending.
Max detail can exceed the existing 256 KiB frame cap; failures allow retry with
a smaller preset. No hardware commands were sent during implementation.

Preset request failures reproduced with UDP and TCP control active: separate
HTTP connections failed after the first write; a persistent Session succeeded.
Client now reuses the Session across preset selections and closes it on shutdown.
All 135 tests pass. Live Stop-only checks decoded all presets: Fast ~25 fps,
Drive ~11.3, Detail ~5.3, Max ~3.3 (brief 3-second samples). Restored and verified
800x600/JPEG10 afterward. See dashboard notes and local logs/camera-presets/probe.json.
The single startup control timeout in the user's report was not reproduced.

User reports Max detail pauses with stale-video indication (not a control timeout).
Preset changes now recover with fresh video and neutral controls, without a Resume
click; only explicit Stop/Space sets the manual latch. Manual stops are preserved.
Requested larger UDP receive buffering and added bounded stale-video diagnostics;
frame size/expiry/freshness limits are unchanged. Physical improvement to Max-detail
video is not yet confirmed; no live robot commands sent for this update.


## 2026-09-30 — Dashboard reconnection

Added automatic control-link retries and a Reconnect button to analogue mode.
A single background worker owns connection setup and control exchanges, repeats
Stop/calibration/firmware handshake, and replaces UDP or HTTP video. Fresh video
and neutral controls gate recovery; a manual Stop remains latched. Pending motor
commands are not queued or replayed. Camera preset status resets to unknown;
IP changes still require launching with the new address. No firmware changed.
Mocked restart/retry and safety tests cover this update; live reboot validation
has not been performed. See dashboard/README.md for details.

## 2026-09-30 — Optional upstream features

Retained upstream vision, person-following, autonomous helper and legacy controller
source while excluding heavy dependencies from the default installation. Vision,
navigation and calibration are installation extras; imports occur on explicit use.
The normal command now defaults to the dashboard with UDP video; the original
controller has a separate `elegoo-smartcar-legacy` entry point. Existing explicit
dashboard flags still work. `car-setup` accepts optional-extra arguments and plain
`car-setup` restores the minimal environment. Firmware and sensor APIs are unchanged.

Validation: 34 targeted tests passed with vision/navigation dependencies installed;
after synchronizing the minimal environment, the full suite passed 152 tests with
two optional checks skipped. The wheel and source distribution build offline.
The local environment now uses the minimal dependency set. No live robot commands
or firmware changes were needed for this update.
