"""Reset the isolated camera into its existing app and capture its serial log."""
import array
import fcntl
import os
from pathlib import Path
import select
import termios
import time

port = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
try:
    attrs = termios.tcgetattr(fd)
    attrs[0] = attrs[1] = attrs[3] = 0
    attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
    attrs[4] = attrs[5] = termios.B9600
    attrs[6][termios.VMIN] = attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    fcntl.ioctl(fd, termios.TIOCMBIC, array.array("i", [termios.TIOCM_DTR]))
    fcntl.ioctl(fd, termios.TIOCMBIS, array.array("i", [termios.TIOCM_RTS]))
    time.sleep(0.2)
    fcntl.ioctl(fd, termios.TIOCMBIC, array.array("i", [termios.TIOCM_RTS]))
    data = b""
    until = time.monotonic() + 20
    while (remaining := until - time.monotonic()) > 0:
        if select.select([fd], [], [], remaining)[0]:
            data += os.read(fd, 4096)
    text = data.decode(errors="replace")
    Path("logs/esp32-2026-09-28/startup.log").write_text(text)
    # Omit the SSID-bearing wifi_name line from console output.
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "wifi_name:" in line or (i and "wifi_name:" in lines[i-1]):
            continue
        if line.isascii():
            print(line)
finally:
    os.close(fd)
