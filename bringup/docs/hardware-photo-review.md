# Hardware photo review — 2026-09-28

Reviewed all five new originals in `car pictures/`, including the UNO and IMU
photos at original resolution. No firmware changes were made during review.

| Component | Evidence | Assessment |
| --- | --- | --- |
| Camera | `20260927_221837.jpg`: ESP32-WROVER module, Camera V1.5 PCB; previous electronic identification and 4 MiB dump | Identified. V1.5 versus supplied V1.2 schematic remains a documented revision difference. |
| Shield | Earlier pictures and `20260928_111313.jpg`: SmartCar-Shield-V1.1 | Confirmed. |
| Motor driver | `20260928_111313.jpg`: clear `6612FNG` marking on U1 | Confirms TB6612FNG variant, matching the upstream motor-driver target. |
| Main board | `20260928_111344.jpg` and `20260928_111351.jpg`: ELEGOO UNO R3, Atmel-marked square MCU, Holtek USB bridge | Consistent with the ATmega328P UNO target and prior signature/Optiboot results. Full MCU model engraving is too faint for a confident character-by-character transcription. |
| IMU | `20260928_111242.jpg`: blue HW-123 / ITG/MPU module, VCC/GND/SCL/SDA/XDA/XCL/AD0/INT pins | Consistent with the expected MPU6050 module, but the actual chip's model engraving is not confidently readable. Module silkscreen alone is not exact chip identification. |

No more whole-car or camera pictures are needed. The useful remaining detail
is a direct reading of the IMU chip model, and preferably the UNO MCU model
while the shield is already lifted. Side lighting can expose the engraving;
the user can transcribe it instead of obtaining another photograph.
An electronic IMU identity/register check is an alternative, but the current
stock protocol has no generic I2C-register read command, so it is not available
through the unchanged stock UNO firmware without additional tooling or a
reviewed diagnostic firmware step. Do not report MPU6050 as physically confirmed
solely from the breakout-board appearance.

## Accepted working assumptions

The user explicitly requested proceeding on an educated assumption rather
than obtaining more readable markings. Use ATmega328P and MPU6050 as working
targets, supported by the UNO/Atmel photographs, matching Optiboot, reported
signature, and IMU module layout. This resolves the photograph requirement;
do not keep asking for the same markings. TB6612FNG and the ESP32-WROVER
Camera V1.5 are confirmed. The MCU and IMU model uncertainty remains documented
and must be revisited if upload verification or sensor acquisition fails.

Use only the existing upstream patches, preserve EEPROM and bootloader through
application-only UNO programming, and test the added MPU command while powered
by USB with the motor battery disconnected before powered movement tests.
