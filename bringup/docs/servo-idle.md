# Idle camera servo follow-up

User reports brief periodic camera twitch at neutral controls. Root cause has
not been measured. The PC has an 8% camera deadzone and sends exactly centred
angles inside it; a regression test covers several seconds of neutral noise.

The preceding analogue UNO firmware continuously refreshed Servo.write and
kept the servo attached. Servo uses interrupt-timed pulse edges. The UNO's LED
routine calls FastLED.clear(true) every loop, and the installed AVR FastLED code
masks interrupts when sending LED data. Pulse timing interference is therefore
a plausible source of jitter; stick drift, power and the servo itself remain
possible contributors. Repeating an identical Servo.write alone does not command
a different position.

## Installed UNO update

`tools/prepare-servo-idle.py` copies the known 38400-baud UNO source to
`firmware/uno-servo-idle/SmartRobotCarV4.0_V1_20230201` and changes only manual
camera pulse handling:

- Write and attach only for a changed target or entry into manual mode.
- After 500 ms with no target change, detach and set the servo pin LOW.
- Repeated wheel/lease updates do not restart the servo settling timer.
- Leaving manual mode detaches as well.
- The next changed target reattaches promptly. No blocking delay is added.

This resembles the stock servo's idle release, while retaining smooth absolute
one-degree panning and simultaneous wheel commands. Once released, the head
holds by mechanical friction and does not actively resist a bump. Returning to
an unchanged target cannot correct a physical bump until the commanded target
changes; there is no servo position feedback.

The motor lease, 38400 baud, corruption guards, ground checks and LED/battery
warnings are unchanged. ESP32 does not need updating.

Build in nix-shell:

```sh
python3 tools/prepare-servo-idle.py
arduino-cli compile --fqbn arduino:avr:uno --build-property compiler.c.extra_flags=-mcall-prologues --build-property compiler.cpp.extra_flags=-mcall-prologues --build-property compiler.c.elf.extra_flags=-mcall-prologues --build-path .cache/build/uno-servo-idle firmware/uno-servo-idle/SmartRobotCarV4.0_V1_20230201
```

Build: 32,084/32,256 flash bytes; 1,231/2,048 global RAM bytes. No original source
or working firmware image was overwritten. Reviewable diff:
`firmware-overlays/analogue-drive/servo-idle.patch`; hash in `firmware-artifacts.json`.
Rollback is the verified `.cache/build/uno-control38400/...ino.hex`; ESP32 stays
at 38400 either way. Uploaded and verified on 2026-09-29. All 512 original bootloader bytes were
preserved. USB validation passed at 38400 baud: 150 zero-speed updates, ground
and MPU queries; mean acknowledgement 16.0 ms, maximum 18.3 ms. Evidence is in
`logs/servo-idle-2026-09-29/`. Physical idle twitch validation remains pending.

Separate PC-only update: throttle and steering now use cubic response after
the existing deadzones. Full output, both-trigger stop, wheel normalization and
camera response are preserved. All 94 client tests pass. Restarting the same
`--video udp --analogue-drive` command enables this change without a flash.

The user liked the squared curve but requested a softer response. The cubic
curve now gives 1.5625%, 12.5% and 42.1875% demand at quarter, half and
three-quarter usable travel (after deadzone rescaling). All 94 tests passed
after this adjustment.

## Follow-up: unexpected rightward movement

The user confirms idle twitch stopped, but occasionally the camera moves all the
way right, including after several seconds sitting still. Touching the camera
stick restores control. This timing means the cutoff defect below is not a
confirmed explanation for every event; idle release also removes holding torque.

The previous implementation unconditionally detached and drove the signal LOW.
If called during a high pulse, that truncates the final pulse. A separate
candidate now checks LOW and detaches with interrupts masked around both actions,
so a Servo ISR cannot begin a new pulse between the check and detach. If HIGH,
it returns immediately and retries on later loop iterations, leaving the normal
falling edge intact. Mode-exit release uses the same helper. A changed target is
written before reattaching to avoid sending a stale target on the first pulse.
No blocking wait or periodic reattachment was added.

Prepare with `python3 tools/prepare-servo-pulse-safe.py`; build with the same
UNO command above, substituting `uno-servo-pulse-safe` for `uno-servo-idle`.
The candidate is 32,130/32,256 flash bytes and 1,231/2,048 global RAM bytes.
`nix-shell --run 'python3 tools/test-servo-pulse-safe.py'` passes host checks of
the actual release helper with mocked pin/interrupt/Servo operations. These
checks cannot verify electrical timing on real hardware. Review the source diff
in `firmware-overlays/analogue-drive/servo-pulse-safe.patch` and artifact hash in
`firmware-artifacts.json`. Uploaded and verified on 2026-09-29; original 512-byte bootloader preserved.
150 zero-speed USB updates and ground/MPU reads passed at 38400 baud (mean
16.0 ms, maximum 17.9 ms). Evidence: `logs/servo-pulse-safe-2026-09-29/`.
Physical camera behavior remains to be checked. ESP32 needs no update.
The previous images and verified readbacks remain available for rollback.

Optional client `--trace-camera` logging now reports acknowledged targets and
stick inputs, including once-per-second unchanged targets. Use this if the
problem recurs to distinguish a requested turn from unexpected physical motion;
it cannot rule out downstream serial corruption or power/signal faults.

User follow-up: driving looks good and no camera servo issues observed after
the pulse-safe update. This is user-observed validation, not an electrical
measurement of the original fault.
