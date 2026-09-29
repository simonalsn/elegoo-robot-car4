# 8BitDo Ultimate 2C Wireless

For the newer trigger-throttle, proportional steering and self-centring camera
layout, see [analogue drive](analogue-drive.md). The layout below remains the
legacy mode when `--analogue-drive` is omitted.

Detected on this PC by pygame-ce 2.5.8 / SDL 2.32.10 as
`8BitDo Ultimate 2C Wireless Controller`, GUID
`0300604ec82d00000a31000014010000`. Six raw axes, eleven buttons and one hat.
SDL provides a complete Linux Xbox-style mapping. The read-only hardware probe
confirmed neutral sticks and released triggers; the recording did not capture
user-operated controls. No motor commands were sent in this investigation.

Start in `nix-shell`, with the pad connected and the robot on the ground:

```sh
elegoo-smartcar-control --robot-ip 192.168.0.213 --video udp
```

Keep the application focused. A terminal message confirms gamepad registration.

| Input | Action |
| --- | --- |
| Left stick | Forward/back, turn in place left/right, or diagonal drive |
| D-pad | Same directions, including diagonals |
| Right trigger | Raises speed ceiling from PWM 50 to 200 |
| Stick deflection | Scales speed within the trigger-selected range |
| Right stick left/right | Stop wheels, then pan camera in 10-degree steps |
| X | Stop wheels, then centre camera |
| Release driving controls | Stop |
| Escape on keyboard | Exit and request stop |

Start with the trigger released; increase gradually. The values are motor PWM
commands, not measured speed. Direction uses eight sectors and a 20% per-axis
deadzone; it is not continuously variable left/right wheel mixing. With the
trigger released, movement remains at PWM 50. Full trigger and full stick/D-pad
reach 200. At full trigger, half of the usable stick travel commands about 125.
Panning pauses driving because upstream's queue only permits one action per
iteration. Normal camera/ground interlocks remain active. A PC-side stop still
does not guarantee stop on Wi-Fi loss.

## Changes from upstream

- Use SDL's named game-controller axes/buttons rather than assumed raw indices.
- Process connect/disconnect events before video/ground interlocks: previously
  the initial connection could be lost while raised or waiting for video.
- Correct horizontal-only turning and consistently apply the stick deadzone.
- Ignore unsupported controllers instead of reading nonexistent axes.
- Skip idle/disconnected controllers instead of masking a later active one.
- Stop previous wheel movement before sending a pan/centre command.
- Close controller handles during cleanup; safely ignore unknown disconnects.

Mapping read from this physical pad: left X/Y = raw a0/a1; right X/Y = a3/a4;
left/right trigger = a2/a5; X = b2; D-pad = h0. SDL handles these details.
See https://pyga.me/docs/ref/sdl2_controller.html for the named input API.

Read-only input diagnostic (does not connect to the robot):

```sh
python3 tools/probe-gamepad.py --seconds 60
```

Validation: all 64 tests pass, including 15 new gamepad cases for directions,
neutral/deadzone, proportional speed, multiple pads, pan/centre, hotplug while
raised and disconnect. Live device/mapping evidence: `logs/gamepad-input.log`.
User-operated input and assembled-car driving remain to be confirmed.
