"""Read-only sensor smoke check for upstream firmware over the UNO USB UART.

Run with motor battery disconnected and the shield switch at upload.
Only stop and sensor commands are sent; this is not a replacement client.
"""
import json
import os
import select
import termios
import time

PORT = "/dev/serial/by-id/usb-HOLTEK_USB_TO_UART_BRIDGE_0000-if00"
fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)


def receive(seconds):
    result = b""
    until = time.monotonic() + seconds
    while (remaining := until - time.monotonic()) > 0:
        if select.select([fd], [], [], remaining)[0]:
            result += os.read(fd, 4096)
    return result.decode("utf-8", errors="replace")


def request(command):
    payload = json.dumps(command, separators=(",", ":")).encode()
    assert os.write(fd, payload) == len(payload)
    response = receive(1.5)
    print(json.dumps({"sent": command, "received": response}), flush=True)
    return response


try:
    attrs = termios.tcgetattr(fd)
    attrs[0] = attrs[1] = attrs[3] = 0
    attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
    attrs[4] = attrs[5] = termios.B9600
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    print(json.dumps({"startup": receive(5)}), flush=True)
    assert "{ok}" in request({"N": 100}), "Stop response missing"
    for i in range(5):
        name = f"mpu{i}"
        data = json.loads(request({"H": name, "N": 1000}))
        assert data["id"] == name and isinstance(data["t"], int)
        assert len(data["a"]) == len(data["g"]) == 3
        assert all(isinstance(x, int) for x in data["a"] + data["g"])
        assert any(data["a"] + data["g"]), "All MPU channels are zero"
    for name, code, d1 in [("distance", 21, 2), ("ir0", 22, 0),
                           ("ir1", 22, 1), ("ir2", 22, 2)]:
        response = request({"H": name, "N": code, "D1": d1})
        assert f"{{{name}_" in response and "}" in response
    assert "{ground_" in request({"H": "ground", "N": 23})
    print("PASS: stop, MPU samples, ultrasonic, three IR channels and ground-status responses")
finally:
    try:
        os.write(fd, b'{"N":100}')
        termios.tcdrain(fd)
    finally:
        os.close(fd)
