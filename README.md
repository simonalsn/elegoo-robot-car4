# ELEGOO Robot Car V4 — smooth driving and a desktop dashboard

This is a fork of [micdestefano/elegoo-robot-car4](https://github.com/micdestefano/elegoo-robot-car4),
originally developed by Michele De Stefano. It builds on that project's Python
client, ELEGOO firmware patches, router Wi-Fi support, and sensor access.

**This fork focuses on making the car pleasant to drive from a computer:** smooth
analogue gamepad control, a useful driving interface, and lower-latency video and
control. The priority is responsive manual driving rather than adding more
computer-vision or autonomous-driving features.

![Pygame driving dashboard, shown with an offline placeholder](bringup/docs/dashboard/driving.png)

*The screenshot is the implemented dashboard in offline preview mode, with
illustrative values and a camera placeholder.*

## What this fork adds

- **Smooth gamepad driving:** right trigger for forward, left trigger for reverse,
  left stick for steering, and simultaneous driving and turning. Cubic response
  curves, a tuned minimum motor output, acceleration limiting, and extra steering
  authority while moving make fine adjustments easier. Both triggers together stop.
- **Runtime camera presets:** switch between Fast (320×240), Drive (640×480),
  Detail (1024×768) and Max detail (1600×1200). Changing modes holds the car
  paused until settings, fresh video and neutral driving inputs are confirmed.
- **Camera control:** the right stick sets the pan target and releasing it centres
  the camera. Servo firmware changes address idle twitch and pulse cutoff.
- **A proper desktop dashboard:** a large camera view, clear driving/blocking
  status, command indicators, controller/focus state, connection metrics, and a
  control guide. The window is resizable and preserves the camera's aspect ratio.
- **Lower-latency video:** a dedicated JPEG-over-UDP stream displays the newest
  complete frame instead of building up a queue. Stale video blocks driving.
- **More responsive control:** combined wheel/camera commands, a matched
  38400-baud UNO–ESP32 link, corrupt-reply handling, and a firmware motor-command
  lease. These changes substantially improved responsiveness on the tested car;
  there is no guaranteed latency figure for other networks or hardware.
- **Reconnect without restarting:** the analogue dashboard automatically retries
  a lost control connection; its Reconnect button also restarts the link and video.
  Keep the car stationary during sensor calibration. Fresh video and neutral
  controls are required before driving, and manual Stop stays latched.
- **Explicit Stop/Resume:** Space or the Stop button latches driving off. Release
  the driving controls, then click Resume. Recovery from lost focus, stale video,
  or control errors also requires neutral controls.

The indicators show requested inputs and acknowledged command targets, **not
measured vehicle speed or physical servo position**. In the analogue dashboard,
control I/O and reconnection run on a background worker so network timeouts do
not freeze the interface. The legacy keyboard controller remains synchronous.

## Hardware and firmware

Development has used an older ELEGOO Smart Robot Car Kit V4.0 with a
SmartCar-Shield-V1.1, TB6612 motor driver, MPU6050-compatible IMU, UNO-compatible
main board, and an ESP32-WROVER camera board. The current gamepad is an
8BitDo Ultimate 2C Wireless using SDL's standard controller mapping.

**UDP video and analogue driving require this fork's matching firmware changes.**
Installing the Python client alone does not add those capabilities to stock
firmware. Confirm your board revision and preserve a stock-firmware rollback
before flashing. Firmware preparation scripts and overlays are included; private
Wi-Fi credentials, compiled images and flash backups are not.

Start with the [workspace and firmware notes](bringup/WORKSPACE.md),
[hardware review](bringup/docs/hardware-photo-review.md), and
[bring-up record](bringup/docs/bring-up-status.md). Historical notes include earlier
firmware versions; the current tested serial link uses **38400 baud**.

## Run the controller

With the Python environment installed and the matching firmware running:

```sh
elegoo-smartcar-control --robot-ip YOUR_ROBOT_IP
```

The robot joins your router's Wi-Fi network. Use its assigned IP address and keep
the controller window focused. Escape closes the controller and requests Stop.
The dashboard and UDP video are now the defaults. Existing commands using
`--video udp --analogue-drive` still work. The original controller is retained as
`elegoo-smartcar-legacy --robot-ip YOUR_ROBOT_IP` (HTTP video by default).
This fork's additions are in this repository;
the upstream PyPI package does not include them.

To inspect the interface **without connecting to a robot**:

```sh
elegoo-smartcar-control --dashboard-preview
```

Press 1, 2 or 3 to preview Ready, Driving or stale-video states. Try Stop/Space,
Resume and window resizing. See [dashboard usage](bringup/docs/dashboard/README.md).

### Nix development environment

The `bringup/` directory preserves the surrounding development workspace. To
recreate its layout in a new directory:

```sh
mkdir elegoo-car
cd elegoo-car
git clone https://github.com/simonalsn/elegoo-robot-car4.git upstream
cp -a upstream/bringup/. .
nix-shell
car-setup
```

This installs the default driving environment and tests; it does not configure or
flash the boards. Optional vision, navigation and plotting dependencies are excluded.
See [workspace notes](bringup/WORKSPACE.md)
for the layout and [original documentation](UPSTREAM_README.md) for upstream context.

### Optional features

All upstream feature source remains in the repository and Python package. The
default installation requires only NumPy, OpenCV, pygame-ce and Requests (plus
their dependencies). It does not install or import Ultralytics, Torch, Torchvision,
LAP, SciPy or plotting packages. Optional modules are loaded only when requested;
installing an extra does not automatically activate driving or tracking modes.

| Feature | Install from the workspace's Nix shell | Activate |
| --- | --- | --- |
| YOLO tracking / person following | `car-setup --extra vision` | Launch `elegoo-smartcar-legacy`, press T, select 4 or 5 |
| Gyro navigation | `car-setup --extra navigation` | Explicit library calls such as `Car.turn_by()` |
| Calibration plotting | `car-setup --extra calibration` | Run `compute_ultrasonic_calibration.py` from `upstream/data/` |

Extras can be combined, for example `car-setup --extra vision --extra navigation`.
Run plain `car-setup` to return to the default environment. Outside the Nix shell,
use `uv sync --no-dev --group test --extra vision` from the repository, or install
the local checkout with `pip install '.[vision]'`. Substitute the desired extra.

The legacy controller retains keyboard/gamepad input and its terminal menu for
stock line tracking, obstacle avoidance and ultrasonic following. Those modes are
not exposed in the dashboard. They retain the original synchronous behavior and
do not gain the dashboard's reconnect and Stop/Resume interlocks. Autonomous
navigation helpers remain available for explicit experiments; sensor APIs and
startup IMU calibration remain part of normal operation. Firmware is unchanged.

Vision activation may download model weights on first use. If optional
dependencies are absent, activation reports the required extra and leaves tracking
disabled. The retained source is included in builds; extras select dependencies,
not which source files go into the package.

## Development notes

- [Analogue mixing and tuning](bringup/docs/analogue-drive.md)
- [UDP video protocol](bringup/docs/udp-video.md)
- [Control-link recovery](bringup/docs/control-recovery.md)
- [Servo fixes](bringup/docs/servo-idle.md)
- [Dashboard controls and validation](bringup/docs/dashboard/README.md)

Tests cover mocked control faults, Stop/Resume interlocks, UDP handling, dashboard
resizing and default startup with optional imports blocked. Run `pytest tests/ -q`
in the configured environment. Tests requiring real vision/navigation packages
skip when those extras are absent; to exercise the retained features, run
`car-setup --all-extras` then the same test command from `upstream/`. Hardware observations
and limitations are recorded in the bring-up notes; automated tests do not replace
an attended driving check on another car.

Possible next steps include display toggles, calibrated vehicle-width and
turning-path overlays.

## Credits and license

Thanks to [Michele De Stefano](https://github.com/micdestefano/elegoo-robot-car4)
for the project this fork builds on, and to ELEGOO for the original robot firmware.
The upstream [MIT license](LICENSE) and attribution are retained. Third-party
libraries and vendor firmware retain their own licenses.
