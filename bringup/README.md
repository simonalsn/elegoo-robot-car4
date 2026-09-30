> **Dashboard available:** run `elegoo-smartcar-control --robot-ip 192.168.0.213`.
> For an offline preview use `elegoo-smartcar-control --dashboard-preview`.
> See [dashboard usage](docs/dashboard/README.md) for Stop/Resume and display details.
> The current tested firmware pair uses 38400 baud; earlier notes below describe bring-up history.

# ELEGOO Smart Robot Car V4 bring-up

Enter the project environment from this directory:

```sh
nix-shell
car-setup
```

`shell.nix` provides Python 3.12, uv, native libraries for the Python client,
and firmware inspection/backup tools. `car-setup` installs the default driving
dependencies from `upstream/pyproject.toml` and test dependencies into
`upstream/.venv`, then activates it. Later `nix-shell` sessions activate that
environment automatically. Run `exit` to leave the shell.

The first setup needs network access. PyTorch/CUDA, vision, gyro navigation and
plotting dependencies are optional. Use `car-setup --extra vision`,
`car-setup --extra navigation` or `car-setup --extra calibration` to install them;
plain `car-setup` returns to the minimal environment. Source is retained for all
features. The original interface is available as `elegoo-smartcar-legacy`.
Entering the shell does not install Python packages, contact the car, or flash
firmware. Nix packages follow your configured `<nixpkgs>`; this shell does not
pin a separate Nixpkgs revision. uv generates `upstream/uv.lock` on first sync.

Check the installed client without connecting to hardware:

```sh
python -c 'from elegoo_robot_car4 import Car; print("Client imports successfully")'
cd upstream
pytest tests/
```

The existing integration tests use a mock robot. Separate physical bring-up
checks have now passed. Launch the upstream client with the documented local reliability fixes:

```sh
elegoo-smartcar-control --robot-ip 192.168.0.213
```

Router credentials are already configured. To change them before rebuilding
and reflashing the camera application, enter credentials locally:

```sh
python3 tools/configure-router.py
```

Use a 2.4 GHz network. The password prompt is hidden; credentials are written
only into the ignored router firmware directory, not printed. This replaces
upstream's interactive `just config` credential substitution with safely escaped
C++ strings; firmware logic stays unchanged. Compiled camera firmware will also
contain the credentials and should remain private.

See [bring-up status](docs/bring-up-status.md) for results and limitations. The UNO now
runs the upstream-patched firmware and passes USB sensor checks. The ESP32
runs upstream's router variant at `192.168.0.213` (DHCP address). Camera
capture, MJPEG streaming and sensor access through upstream's Wi-Fi client
pass. The user observed forward, backward, left and right during the attended
one-second pulse test, with explicit stops between commands and at completion.
Bring-up is complete; the final command was stop. Road driving, calibration
and loss-of-link stopping have not been tested.

The command above follows the actual upstream CLI parser; upstream's README
currently shows an outdated positional-IP invocation. Keep the robot still
when connecting because the client calibrates the IMU. Arrow keys drive;
releasing them sends stop, and Escape exits. Keep the controller window
focused and the power switch accessible: upstream disables the camera's
heartbeat timeout, so immediate stopping on a lost link is not guaranteed.
Use one control client at a time.

The dedicated UDP video extension is flashed and passes isolated camera tests.
Select it with `--video udp`; HTTP remains the default for compatibility.
See [UDP video](docs/udp-video.md) for commands, protocol and rollback.

8BitDo / Xbox-style gamepad controls and validation: [gamepad notes](docs/gamepad.md).

The new trigger/steering/absolute-pan mode is documented in [analogue drive](docs/analogue-drive.md).
It needs both 115200-baud firmware updates and `--analogue-drive`.
