> **Local development checkpoint:** UDP video, analogue gamepad driving,
> control-link recovery and servo fixes are documented in
> [bring-up workspace notes](bringup/WORKSPACE.md). The dashboard mockup is in
> [bringup/docs/dashboard-mockup](bringup/docs/dashboard-mockup/README.md).
> These additions extend the upstream project described below.

# Software suite for the ELEGOO Smart Robot Car Kit V4.0 🤖🚗

This is my personal software suite for the **ELEGOO Smart Robot Car Kit V4.0**.
It requires and provides patches for
[the original software from **ELEGOO**](https://www.elegoo.com/blogs/arduino-projects/elegoo-smart-robot-car-kit-v4-0-tutorial).

I started modifying the original software for these main reasons:

1. It requires you to install an app on a smartphone if you want to control the
   robot, while I wanted to be able to do the same from my computer, e.g. with a
   game controller. Being able to control the robot from a computer opens a wide
   range of experimentation possibilities.
2. It does not provide a way to access the **MPU6050** sensor (a gyroscope +
   accelerometer) data out of the box.

Look at [a video presentation of what this software provides](https://www.youtube.com/watch?v=iasMmwncTi0).

## WARNING: THIS SOFTWARE IS PROVIDED AS IS, WITH NO WARRANTY

I modified only the software corresponding to the motor driver chip
and gyro module I own (see my hardware configuration below).
Also the original **ELEGOO** documentation warns about
this point. Verify which is your configuration before blindly uploading my
modified software on your robot boards.

## Clone the sources ⚠️

In order to customize the software for the Arduino boards of the robot you have
to clone the source repository on your machine and follow the instructions
below.

⚠️ **The package on PyPI provides only Python software** ⚠️

## Hardware configuration of my robot 🤖🔧⚙️

This is the hardware of my robot:

- motor driver: `TB6612`
- gyro module: `MPU6050`
- microcontroller version: `Elegoo UNO R3 Car v2.0`
- camera: `ESP32-WROVER`

## Repository organization 📂

[![prek](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/j178/prek/master/docs/assets/badge-v0.json)](https://github.com/j178/prek)

- `src/elegoo_robot_car4`: this directory contains a Python package that you can
  use to control the robot after you have uploaded to the boards the patched
  **ELEGOO** software. It also provides a simple Python
  application that allows you to use the robot as a drone.

- `elegoo-patches`: this directory contains patchfiles needed for patching the
   original **ELEGOO** software to make it work properly together with the
   provided Python code. I added code for acquiring gyroscope and accelerometer
   readings and I provide the possibility to make the robot connect to a
   router instead of creating a WiFi access point. Explore the patchfiles for
   more details.

- `justfile`: this file allows to download the official **ELEGOO** software for
  this robot and to patch it. If you already have the official zip file, then
  copy it into the root of the project, so that the `justfile` targets will
  skip the download. You have to install `just` into your system.

## Prepare the software for the electronic boards 🔧💻

If you are OK with controlling the robot from your smartphone, configure the
project with

`just config-ap`

Otherwise, if you want to control the robot from your computer, configure the
project with

`just config`

You will be requested to enter your router `SSID` and password.

This procedure works only from `Linux` or `Unix` operating systems. If you are
on `Windows`, you have to manually perform what the `just config` command is
doing.

Once configured and patched, upload **ELEGOO** software to the main board and
to the `ESP32` in the usual way (described into the official documentation).

**WARNING: Remember that you can choose to control the robot either from your
computer or from your smartphone but not both (at least with the software I
am providing here).**

## Uploading the ESP32 software 📤

Open the `ESP32_CameraServer_AP_<version>.ino` sketch of with the `Arduino IDE`.
Then, remove your `ESP32` module from the
robot and connect it to your computer through a `USB-C` cable. Then follow these
steps (also explained into the robot documentation):

- From `Tools -> Port` select the right port (for me, on Linux, is something
  like `/dev/ttyUSB0`).

- Push the reset button on the `ESP32` board. The serial monitor should print
  some information coming from tha board.

- Open `File->Preferences` and put
  `https://dl.espressif.com/dl/package_esp32_index.json` into the
  `Additional Boards Manager URLs` text box. Maybe you already did this in the
  past. Click "OK".

- Install the right board manager from the `Arduino IDE` (maybe you already
  did this in the past). Go to `Tools->Boards Manager...` and fill `esp32` into
  the search box. Select the package from `Espressif Systems` and install
  version `1.0.4`. I tried also version `1.0.6` and it works. Version `2.0.0` it
  does not and you would need to deeply change the code from **ELEGOO** (not
  recommended).

- Select the right board: `Tools->Board->esp32->ESP32 Dev Module`.

- Select the right partition scheme:
  `Tools->Partition Scheme->Huge APP (3MB No OTA/1MB SPIFFS)`.

- Enable `PSRAM`: `Tools->PSRAM->Enabled`.

- Verify the sketch. You may encounter the following issues:
  - `ModuleNotFoundError: No module named 'serial'`: you need to install the
    `pyserial` package into your Python environment (`pip install pyserial`).

  - `Arduino IDE` complaining that the built result is too large for fitting
    the board memory. To solve this check the parameters are all correctly set.
    If they are, it is possible that you had previously installed an `esp32`
    library version more recent than `1.0.6` and then downgraded. It seems that
    this operation leaves garbage into the downloaded packages. The only
    solution I've found up to now is to completely remove the `.arduinoIDE` and
    `.arduino15` directories into my home directory and restart the IDE. Then I
    had to restart from scratch with the configuration.

- Upload the code to the board.

Now you can check which is the IP address that your router assigned to the
board. I aliased it as `robot` in my `/etc/hosts`. At this point, we can check
the following:

- <http://robot> provides access to the standard `ESP32` web interface.
- <http://robot/capture> takes a photo.
- <http://robot:81/stream> provides the streaming from the browser.
- <http://robot/Test> works (it is an alias for the "stream" endpoint).

You can now reassemble the `ESP32` board on the robot.

## Uploading the modified main board software 📤

Follow these steps:

- Connect the main board to your computer with the provided `USB` cable.

- Set the `upload-cam` switch to `upload`.

- From the `Arduino IDE` open the `SmartRobotCarV4.0_V1_20230201.ino` sketch
  you find into the **ELEGOO** software tree, for the configuration with
  `TB6612` and `MPU6050` (I did not patch other configurations because I
  cannot test them).

- Ensure to select the right board: `Tools->Board->Arduino UNO` (or
  `Tools->Board->Arduino Yun` ... they both work). Maybe you need to install
  support for the arduino boards (in the boards manager, install
  `Arduino AVR Boards`).

- Verify the sketch with the `Verify` button. Maybe you need to install
  dependencies. These are the dependencies I had to install:
  - `Servo`, by Michael Margolis, Arduino.

- If everything is OK, upload the code to the board.

I did not need to install packages provided into the `addLibrary` directory
distributed together with **ELEGOO** software.

## Control the robot from your computer 💻🤖

Disconnect the robot from the computer and set back the `upload-cam` switch
to `cam`. Then, switch on the robot. On the `ESP32` you'll notice a blinking
green led: the `ESP32` is waiting for a client to connect.

### Install Python software

You have these options:

- install from `PyPI`: `pip install elegoo-robot-car4`.

- from within the sources root of the project, run `pip install .` (you need
  to install dependencies yourself).

- don't install anything and run through `uv` from the sources root of the
  project (you have to [install uv](https://docs.astral.sh/uv/getting-started/installation/)
  ).

⚠️ This package now exploits some AI features that depend on `ultralytics`
and `pytorch` (specifically `torch` and `torchvision`). The `pyproject.toml`
file specifies a `pytorch` version which is compatible also with older GPU
boards. If you encounter errors from `CUDA` you should provide the
`--extra-index-url` option with the same `url` specified into the
`pyproject.toml` file (look at the `[[tool.uv.index]]` section.
When running on hardware without `CUDA` the `ultralytics` package should
automatically fallback to using the CPU.

### Use Python software

The `elegoo_robot_car_4` Python package provides a `Car` class through which
you can provide instructions to the robot and get measurements from its
sensors. The class is well documented and you should be able to understand
how to use it.

In order to test robot control, stat a Python shell.
If `robot` is the alias assigned to the robot IP (configured into the
`/etc/hosts` file, like described before), you can create an instance with

```python
from elegoo_robot_car4 import Car

car = Car(ip="robot")
```

As soon as you do that, the green led stops blinking. It means the connection
is established. The default port for socket communication is 100 and it is
configured into the sketch you uploaded before. Now you can provide commands
through the `Car` instance. For example, to make the robot move forward,
type

```python
car.forward()
```

The robot will move forward indefinietly up to when you issue

```python
car.stop()
```

Notice that all the methods that have a `lazy` parameter can also be used in
_lazy mode_. Basically, you provide a command that will be executed only when
you use the `move` method. This `lazy` mode is mainly useful when controlling
the robot with a gamepad (a detailed description of the reason is out of scope
here, but has to do with the management of multiple arriving commands by the
used game engine). For example, the same effect experimented above can be,
achieved in the following way:

```python
car.forward(lazy=True)
car.move()
# Wait for a while
car.stop()
```

You are encouraged to explore the documentation of each method and to experiment
with all of them.

As soon as you close the Python shell you will see the green led blinking
again, meaning that it is ready to accept a new connection.

## Using the robot like a drone 🤖💻🎮

The `elegoo_robot_car4` Python package also provides a program named as
`elegoo-smartcar-control` through which you can control the robot with your
keyboard and with a gamepad.

When you have your robot switched on and the `ESP32` green led is blinking,
you simply have to run

```bash
elegoo-smartcar-control robot
```

if `robot` is the alias for the actual `ESP32` ip address, set into the
`/etc/hosts` file.

If you chose to run with `uv`, you have to run

```bash
uv run elegoo-smartcar-control robot
```

from the root of the project.

The `elegoo-smartcar-control` program has been developed like a video game,
using a game engine to handle user inputs. Furthermore, `OpenCV` is used for
acquiring and displaying the video stream acquired by the `ESP32` camera.

**WARNING: Remember that in order to properly issue commands to the robot
you have to maintain focus on the window showing the video stream.**
As soon as you move focus elsewhere, key presses and game pad events are not
captured anymore.

### Keyboard controls 🤖💻

Keyboard controls are clearly visible at the beginning of the
`elegoo_smartcar_control.py` file, where there is a dictionary mapping each
key input to a movement command. There are also mappings to change the mode
of the robot. By default, the robot waits for a remote move commands, but you
can switch its mode through console input (this is not possible with the
gamepad). To open the console menu, press "t". The program can be closed either
by closing the window with the camera streaming or pressing the escape key.
Remember that all the commands have an effect only if you have focus on the
streaming window.

### Gamepad controls 🤖🎮

Gamepad offers more degrees of freedom for the movement. I configured controls
for the `XBOX 360` gamepad. Here below there is a summary of what you can
do:

- the left stick and the _cross-hats_ control the movement. While the
  _cross_hat_ allows only forward, backward and left-rigt rotations
  _on-the-spot_, the stick allows you to move the robot forward-left,
  forward-right, backward-left and backward-right. This is not possible with the
  keyboard at present.

- the right trigger controls the speed of the robot. This is not possible
  with the keyboard at present.

- the right stick controls the rotation of the robot's head.

- the `X` key resets the head position.

## Acknowledgments 🙏✨

Before starting this project I took inspiration from the following videos and
sources:

- <https://www.youtube.com/watch?v=j7p44vxyvdM>
- <https://www.youtube.com/watch?v=LyReKO6Pg0g>
- <https://www.youtube.com/watch?v=y5xmYu25a6c>
- <https://github.com/bots4a11/ElegooRobotCarV4>
