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
emergency stop. In the original dashboard implementation, synchronous network calls could briefly stall the
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

## Runtime camera presets

The dashboard now offers four presets below the video:

| Preset | Resolution | JPEG setting |
| --- | --- | --- |
| Fast | 320 x 240 | 20 |
| Drive | 640 x 480 | 15 |
| Detail | 1024 x 768 | 10 |
| Max detail | 1600 x 1200 | 10 |

Lower JPEG setting means higher quality/larger frames, not a percentage. Startup
leaves the camera's existing settings unchanged; no preset is selected implicitly.
These presets use the HTTP `/control` and `/status` endpoints already present in
the installed camera firmware. No firmware update is required for this car. Frame
size IDs are specifically those of Arduino-ESP32 1.0.6 (5, 8, 10, 13); they must
not be assumed compatible with arbitrary newer firmware.

Selecting a preset requests and confirms Stop before starting the HTTP worker.
Driving is temporarily paused. Requests run off the GUI/control thread, one preset
at a time. The client writes quality and resolution, verifies both via `/status`,
then waits for a fresh decoded frame at the requested size before highlighting
the preset. It discards early frames for confirmation purposes; old video may
remain visible during the transition. After the mode is ready, release driving
inputs to recover automatically. Resume is required only if you explicitly
pressed Stop/Space; a preset change preserves any existing manual stop. The post-switch video-rate sample starts afresh.

If settings fail, the camera may have applied only part of the change. The UI
reports failure rather than assuming rollback or success. Select a preset again.
If settings are accepted but no matching fresh frame arrives within eight seconds,
try Drive or Fast. The existing 256 KiB JPEG limit is unchanged; Max detail at
quality 10 may exceed it in some scenes. There is no automatic quality fallback.
Settings are runtime-only and the firmware startup defaults return on reboot.

Compare video FPS, receive age and control reply time under similar lighting.
Live preset switching has now been checked with video and control connected;
see the validation below. FPS varies with lighting, scene and Wi-Fi conditions. The offline preview buttons simulate
selection labels only and do not alter the placeholder image or access hardware.

Preset validation: all 132 client tests pass, including setting values/readback,
HTTP errors, request serialization, confirmed-stop gating, fresh-frame matching,
timeout recovery, pending-mode Resume blocking and scaled preset hitboxes.

### Preset HTTP connection fix and live check

The first settings write succeeded with UDP video and TCP control connected,
but opening new HTTP connections for later writes produced RemoteDisconnected.
Adding Connection: close did not resolve it. Reusing one requests.Session made
all writes and readback succeed. This is consistent with socket pressure in the
legacy firmware (CONFIG_LWIP_MAX_SOCKETS=10); its internal failure errno was not
captured. The client now retains one Session across preset selections, consumes
and closes responses, and closes the Session when the settings worker is finished
at shutdown. It does not share or modify the robot control socket.

Live validation used only N100 Stop commands, no movement or servo commands.
All four resolutions were decoded with UDP and control connected. Three-second
samples after each switch yielded approximately:

| Preset | Received FPS |
| --- | ---: |
| Fast | 25.0 |
| Drive | 11.3 |
| Detail | 5.3 |
| Max detail | 3.3 |

These are brief stationary observations, not guaranteed rates or latency results.
Original 800x600/quality10 settings were restored and verified. A JPEG decoder
warning was seen during an earlier resolution transition; steady frames recovered.
The initially reported control timeout was not reproduced by these checks.

Reproduction/verification tool: `tools/probe-camera-presets.py` (close other
clients first). Local evidence: `logs/camera-presets/probe.json`. All 135 client
tests pass, including persistent-session reuse and shutdown while a request is
active. No firmware update was needed.

### Automatic recovery and Max-detail stale video

Preset changes no longer set the explicit manual Stop latch. They pause output
until settings/fresh video are ready and driving inputs are neutral, then return
to Ready without a Resume click. Temporary video/ground/focus guards likewise
require neutral input, not an explicit Resume. Only Space or Stop latches Resume.
Neither preset changes nor recovery can clear an existing manually requested Stop.

User clarified that Max-detail dropouts show stale video, not control timeouts.
At the observed ~3 fps, lost or delayed frames can exceed the existing 750 ms
freshness threshold. The exact loss mechanism has not been established. The
receiver now requests 1 MiB of UDP socket buffering (OS may cap this) to accommodate
bursts. It still discards superseded frames; the 256 KiB JPEG cap, 250 ms assembly
deadline and 750 ms driving freshness guard remain unchanged.

During stale periods the terminal reports approximate completed/incomplete/expired
assembly counts, last complete JPEG byte size, actual socket buffer size and frame
age at most once per two seconds. Incomplete means superseded by a newer frame;
expired means exceeding the assembly deadline. Firmware-skipped oversized frames
cannot be identified from these receiver counters alone. This change has not yet
been shown to resolve Max-detail freezes on the car; use the diagnostics for the
next occurrence. No camera settings or firmware were changed for this update.

Validation for automatic recovery and receiver diagnostics: all 138 tests pass,
including preservation of a manual stop and prevention of held-throttle replay.


### Reconnecting after a restart (2026-09-30)

The analogue dashboard now retries control-link failures automatically after a
2-second delay. **Reconnect** (top right) explicitly replaces both control and
video connections. The window also opens when the car is offline; retries,
network timeouts, the firmware handshake and IMU calibration run on a single
background worker. Legacy keyboard mode is unchanged. No firmware flash is needed.

Keep the car stationary during reconnection: each new connection sends Stop,
recalibrates the IMU, repeats the analogue firmware handshake and confirms zero
wheel speeds. The dashboard discards old video and pending motor demands. Driving
waits for fresh video, the ground guard, window focus, an attached controller,
a zero-speed acknowledgement and neutral triggers/steering. Only an explicit
Stop still requires Resume; reconnecting cannot clear that latch. A stale picture
alone pauses driving rather than repeatedly recalibrating an otherwise healthy
control link; use Reconnect if video alone does not recover.

Camera preset selection is reset to unknown after reconnect (settings are not
silently reapplied). Any in-progress preset request is allowed to finish before
opening the replacement connection, then its result is discarded. Select the
preset again after recovery if needed. Use the same IP address; a DHCP reservation
is useful because this does not discover a car whose router address has changed.

Control transactions are serialized with no motor-command backlog. Stop,
Reconnect and safety pauses invalidate an unsent demand even if the worker is
still waiting for its ground-sensor reply. A command already on the wire cannot
be recalled; the firmware's existing 400 ms command lease remains the fallback.
Ground polling remains at 10 Hz to preserve the serial bandwidth budget.

Validation: mocked offline/reboot, failed retries, manual reconnect, held trigger,
manual Stop preservation, socket cleanup, background polling and resized button
hitboxes. Physical power-cycle validation is still pending.

### Optional features and default launch (2026-09-30)

`elegoo-smartcar-control --robot-ip ADDRESS` now selects this dashboard and UDP
video by default. The existing `--video udp --analogue-drive` command still works.
`elegoo-smartcar-legacy --robot-ip ADDRESS` explicitly opens the retained original
controller, including its keyboard input and terminal mode menu.

Vision/person following and gyro-navigation dependencies are excluded from the
default installation and loaded only on explicit activation. Their source remains
available; `car-setup --extra vision`, `car-setup --extra navigation` or
`car-setup --extra calibration` installs the corresponding optional dependencies.
Plain `car-setup` restores the minimal driving/test environment. Sensor access,
calibration on connection, firmware, analogue tuning and driving interlocks are
unchanged. See the main README for activation and test instructions.
