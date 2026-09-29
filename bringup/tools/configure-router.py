"""Generate upstream's router header locally without exposing Wi-Fi credentials."""
from getpass import getpass
from pathlib import Path
import json
import os
import re

root = Path(__file__).resolve().parents[1]
sketch = root / "firmware/camera-router/ESP32_CameraServer_AP_20220120"
ssid = input("2.4 GHz Wi-Fi network name (SSID): ")
password = getpass("Wi-Fi password (hidden; empty for an open network): ")
if not 1 <= len(ssid.encode("utf-8")) <= 32:
    raise SystemExit("SSID must contain 1–32 UTF-8 bytes.")
if any(c in ssid + password for c in ("\0", "\r", "\n")):
    raise SystemExit("Credentials cannot contain NUL or newline characters.")
text = (sketch / "CameraWebServer_AP.h.source").read_text()
values = {"SSID": ssid, "PASSWORD": password}
text, count = re.subn(
    r'"\[ROUTER_(SSID|PASSWORD)\]"',
    lambda match: json.dumps(values[match[1]], ensure_ascii=False),
    text,
)
assert count == 2, "Unexpected upstream header template"
target = sketch / "CameraWebServer_AP.h"
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as out:
    os.fchmod(out.fileno(), 0o600)
    out.write(text)
print("Router configuration saved locally. Credentials were not printed.")
print("Ready to compile the upstream router-mode firmware; nothing was flashed.")
