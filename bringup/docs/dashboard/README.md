# Pygame driving dashboard

The existing analogue controller now opens the dashboard automatically:

```sh
nix-shell
elegoo-smartcar-control --robot-ip 192.168.0.213 --video udp --analogue-drive
```

No firmware update or dependency install is required. Driving curves, 30 PWM
minimum, moving steering boost and camera targeting are unchanged. Legacy mode
without `--analogue-drive` retains its original camera-only interface.

## Interface

- Large video view with preserved aspect ratio, centre mark and camera target.
- Drive status and reasons for blocking: raised car, stale video, controller loss,
  lost focus, or control reply failure.
- Throttle/steering input indicators; signed wheel PWM and camera target updated
  after the combined command acknowledgement. These are not measured speed or
  servo position. Unknown wheel output is shown as `--` during faults/guards.
- Received video frame rate, local receive age and last combined-command reply
  duration. Receive age is not end-to-end camera latency. Reply timing includes
  command pacing. Old reply values are explicitly marked after two seconds.
- Controller name, focus status, and control guide.
- Resizable, letterboxed dashboard with mouse hitboxes scaled to the window.

Space or the Stop button sends Stop and latches driving off. Holding Space never
resumes driving. Release triggers and steering, then click Resume. Resuming also
requires valid video/ground/focus/controller state and a successfully acknowledged
zero-wheel command. Current inputs are checked again on the resume iteration;
a previous neutral reading does not authorize subsequent held throttle. A stop
request takes priority over a resume click in the same event batch. Both-trigger
stop remains immediate and does not require the explicit Resume action.

Startup and recovery from stale video, raised state, controller loss, focus loss
or command errors require neutral driving inputs. Escape/window close requests
Stop and releases the connection. There is no physical speed feedback or hardwired
emergency stop. The pre-existing synchronous network calls may briefly stall the
window during a timeout; the firmware's existing motor lease is unchanged.

## Offline review

```sh
elegoo-smartcar-control --dashboard-preview
```

No robot IP is needed; neither Car nor UdpVideo is constructed. Press 1 for Ready,
2 for simulated Driving, 3 for stale-video blocking. Try Stop/Space, Resume and
window resize; Escape exits. Offline values are explicitly labelled simulated.

For screenshots without opening a desktop window:

```sh
python tools/render-dashboard.py
```

The PNGs in this directory were rendered by the actual pygame dashboard using an
illustrated placeholder, not a live camera or robot connection. Settings toggles
and calibrated vehicle-width/turning-path overlays remain deferred.

Validation covers the full dashboard loop with mocked robot/video, neutral and
acknowledgement requirements for Resume, Stop priority, guard recovery, failed
Stop replies, aspect ratio, and resized mouse hitboxes. No physical movement or
live robot command was used to validate this UI change. An attended driving check
is still needed.

Final validation: all 117 Python tests passed. Screenshots were visually reviewed
for the driving and stale-video states; no firmware changes were made.
