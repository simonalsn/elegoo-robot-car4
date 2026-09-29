# Analogue driving and camera control

A subsequent control-reply fault and recovery changes are documented in
[control recovery](control-recovery.md). The 115200 results below are historical;
they do not establish reliability while driving.

Local extension of upstream; the existing UDP transport and YOLO dependencies
are retained. This mode needs the matching UNO and ESP32 builds at 115200 baud.
The client refuses to send the new drive commands without a capability reply.

## Use after both firmware updates

```sh
nix-shell
elegoo-smartcar-control --robot-ip 192.168.0.213 --video udp --analogue-drive
```

The controller window must have focus. The first connected mapped controller is
used; disconnecting it or losing focus requests stop. Escape exits. In this mode
keyboard driving, the D-pad and terminal autonomous modes are not mixed into
motor control; omit `--analogue-drive` for the previous keyboard/gamepad layout.

- Right trigger: proportional forward throttle, from zero to PWM 200.
- Left trigger: proportional reverse throttle.
- Both triggers above 4%: immediate zero wheel demand, regardless of steering.
- Left stick horizontal: proportional turning with an 8% deadzone; vertical ignored.
- Right stick horizontal: absolute camera pan within +/-80 degrees; release centres.
- X: camera centre override.

Steering is robot-relative: stick right turns the nose right, also when reversing.
With no throttle, steering rotates in place. At very low throttle and large
steering deflection, the inside wheels can reverse for a tight turn. This is
skid steering, not a simulated passenger-car steering rack.

## Mixing and smoothing

After rescaling deadzones, throttle and steering use a cubic response (`x^3`)
for finer adjustment near centre. Quarter/half/three-quarter usable travel gives
1.5625%/12.5%/42.1875% demand, with full travel still giving 100%. This PC-only change
takes effect on client restart; the camera response curve is unchanged. Left/right demands are `throttle + steering` and `throttle - steering`.
Divide both by `max(1, abs(left), abs(right))` to retain their ratio when saturated.
Thus the outside wheel stays at its limit while the inside wheel slows at full
throttle; at lower throttle either wheel has headroom to increase.

Both wheel changes are scaled together to a maximum 800 PWM units/second.
Starting from rest to full speed takes about 0.25 seconds. Both-trigger stop and
neutral controls bypass the ramp. Reversals ramp through zero. Long scheduling
pauses are capped to 100 ms of ramp time. PWM is not a speed measurement; motor
stall thresholds have not been calibrated and no arbitrary minimum PWM is added.

Pan targets use an 8% deadzone and a 450 degrees/second slew limit. Full centre-
to-side command travel takes about 0.18 seconds; physical servo speed adds its
own limit. Servo updates use one-degree positions without the legacy half-second
wait or detach between commands. The controller loop targets 30 Hz, with ground
queries at up to 10 Hz. Firmware also enforces the ground interlock locally.

## Firmware/protocol

New `N=1002` with `H=cap` returns `{drive_v1}` without changing motion mode.
New `N=1001` combines signed left/right PWM and camera position:

```json
{"H":"d1","N":1001,"D1":120,"D2":60,"D3":107}
```

D1 is physical left, D2 physical right (-200..200); D3 is absolute servo angle
10..170, with 90 centred. The physical motor driver A is right and B is left,
as established by the original left/right movement code. The response is
`{d1_ok}`; sequence IDs change for every update and even identical demands are
resent to renew the lease. The client allows only one outstanding drive reply.

The UNO sets zero wheel demand after 400 ms without a fresh N1001 or when its
IR ground check reports raised. The lease applies only to this new drive mode;
it does not retrofit protection to legacy keyboard/autonomous commands. Camera
position holds if the connection disappears. Host stop remains best-effort;
the local lease handles missing updates independently of Wi-Fi. Physical stopping
distance and timing under load are still unmeasured.

The old N4 unsigned-wheel command explicitly exits the new manual lease mode.
Other original commands are retained. New mode uses direct wheel PWM rather
than the legacy straight-line gyro correction; trim/calibration may be needed
if the car drifts under equal commands.

Both UNO hardware UART and ESP32 Serial2 are changed from 9600 to 115200.
ESP32 debug UART is also 115200 and per-character control/reply echo is removed.
TCP_NODELAY is enabled on the bridge client and on the Python socket after the
handshake. Default Python pacing remains conservative for legacy firmware;
the new mode uses compact JSON and baud-aware pacing plus acknowledgement.

Nothing in the inspected code requires 9600; it was the stock configuration.
A 60-byte 8N1 message takes about 62.5 ms at 9600 versus 5.2 ms at 115200.
UNO's 16 MHz baud divisor introduces about +2.1% error at 115200; reliable operation
is verified on hardware rather than inferred from the nominal speed alone.
See the installed Arduino AVR core `HardwareSerial.cpp` for divisor selection.

## Reproducible builds

`tools/prepare-analogue-drive.py` makes separate working source directories from
the previously patched firmware. It never prints credentials. Source diff:
`firmware-overlays/analogue-drive/changes.patch`.

```sh
python3 tools/prepare-analogue-drive.py --baud 115200
arduino-cli compile --fqbn arduino:avr:uno --build-property compiler.c.extra_flags=-mcall-prologues --build-property compiler.cpp.extra_flags=-mcall-prologues --build-property compiler.c.elf.extra_flags=-mcall-prologues --build-path .cache/build/uno-gamepad firmware/uno-gamepad/SmartRobotCarV4.0_V1_20230201
arduino-cli compile --fqbn esp32:esp32:esp32:PartitionScheme=huge_app,PSRAM=enabled --build-path .cache/build/camera-gamepad firmware/camera-gamepad/ESP32_CameraServer_AP_20220120
```

AVR's `-mcall-prologues` shares function entry/exit code to fit the additional
commands without removing existing features. Final UNO build uses 31,894/32,256
flash bytes and 1,227/2,048 global RAM bytes. ESP32 program uses 2,612,730 bytes;
its partition table is identical to the working UDP firmware. ESP32 images
contain Wi-Fi credentials and must stay private.

## Validation and rollback

94 Python tests pass: saturation/ratio, low-throttle mixing, deadzones, monotonic
steering, reverse/pivot, both-trigger priority, immediate stop, timed smoothing,
simultaneous pan/drive, protocol gating, repeated lease renewal, focus loss and
failure handling, plus the existing tests. Actual floor feel remains untested.

UNO uploaded and verified: 31,894 bytes. Post-upload readback confirms all 512
bootloader bytes unchanged. USB 115200 test: 150 acknowledged zero-speed updates
with ground queries, plus MPU; mean acknowledgement 6.8 ms, max 8.2 ms. ESP32 application uploaded at 0x10000 and esptool hash verified. Isolated UDP
test decoded 95 frames in 8.01 seconds at 800x600. Paired Wi-Fi validation passed: 300 zero-speed updates in 10.43 seconds with
ground queries and MPU reads while UDP delivered 119 decoded 800x600 frames.
Command acknowledgements averaged 19.0 ms, maximum 243.2 ms. Final stop sent.
These are command round trips, not measured motor response times. Physical
driving feel and lease stopping under load remain to be checked. Logs: `logs/analogue-drive-2026-09-29/`.

The known-working pair is copied into `backups/working-before-analogue/`, with
SHA256SUMS. `uno-full-read.bin` matched the previous verified working flash;
`uno-application.bin` excludes the 512-byte bootloader. `esp32-udp-9600.bin` is
the verified working UDP application. Restore BOTH sides for rollback because
their UART rates must match. Isolate each board as for upload. For UNO restore
the application through its bootloader; for ESP32 write only offset 0x10000.
Full factory backups are still separate and untouched. Destructive rollback
has not been exercised.

The idle-servo investigation and installed UNO update are
documented in [servo idle](servo-idle.md).

## Minimum moving-wheel output (2026-09-29)

The cubic curve remains, but normalized wheel demands now pass through a PWM
mapping before the existing acceleration limiter: zero stays zero; nonzero
magnitude maps to `30 + 170*abs(demand)`. Thus each moving wheel starts at about
30/255 electrical PWM duty (the application maximum remains 200/255). The user tuned the initial 11 PWM estimate through 17 and 25 to the current 30 PWM. It needs driving validation and is
not a measured minimum under every battery/load condition. It applies in both
directions and to pivot turns. Mixed demands are normalized first; this motor
compensation changes their PWM ratio. Floating-point cancellation residue below
1e-12 is treated as zero so a cancelled inside wheel stays stopped. Acceleration
limiting can briefly pass through values below the floor, especially reversing.
Both-trigger and neutral stops still bypass the ramp. Full demand stays 200.

Restart the client to use it. All 100 client tests pass. For camera diagnosis,
add `--trace-camera`: after successful combined command acknowledgements it logs
stick input and absolute camera target on target changes and once per second.
This confirms what was acknowledged, not physical servo position. Note the time
of any unwanted swing and compare the nearby targets (90 degrees is centre).

## Stronger initial steering while driving

User requested a deliberately strong starting point for moving turns, retaining
straight-line throttle and stationary pivot tuning. After the cubic curves,
nonzero steering is mapped to `sign(s) * (floor + (1-floor)*abs(s))`, where
`floor = 0.20 * min(1, abs(throttle)/0.25)`. Throttle here is the post-deadzone,
post-cubic demand, not raw trigger travel or measured vehicle speed. This gives
a 20% initial steering demand at moderate/high throttle, blending continuously
to no extra steering at zero throttle. The full boost is reached at about 64.5%
raw trigger travel. Inside the steering deadzone there is no boost or turn.
Full steering remains full steering; reverse retains nose-right stick semantics.

At full forward throttle, just crossing the 8% steering deadzone targets roughly
200 PWM outside and 143 PWM inside (a 57 PWM difference). This is an intentional
step outside the deadzone, softened over time by the existing acceleration limit.
At lower throttle the boost is reduced; small steering inputs do not immediately
reverse the inside wheel. Larger steering inputs can still pivot while moving.
The existing wheel normalization, 30 PWM motor floor, camera handling, and
immediate neutral/both-trigger stops remain. Constants are in `analogue_drive.py`;
this PC-only change takes effect on client restart. Physical tuning is pending.
