#!/usr/bin/env python3
"""Build separate firmware sources; preserve working 9600-baud images/sources."""
from pathlib import Path
import shutil
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--baud", type=int, choices=(115200,38400), default=38400)
baud=parser.parse_args().baud
suffix="gamepad" if baud==115200 else "control38400"
root=Path(__file__).resolve().parents[1]
uno=root/f'firmware/uno-{suffix}/SmartRobotCarV4.0_V1_20230201'
cam=root/f'firmware/camera-{suffix}/ESP32_CameraServer_AP_20220120'
shutil.copytree(root/'firmware/uno/SmartRobotCarV4.0_V1_20230201',uno,dirs_exist_ok=True)
shutil.copytree(root/'firmware/camera-router/ESP32_CameraServer_AP_20220120',cam,dirs_exist_ok=True)
def edit(p,fn):
    s=p.read_text();p.write_text(fn(s))
# A is physically the right side, B the left, established by upstream turn code.
p=uno/'ApplicationFunctionSet_xxx0.cpp'
s=p.read_text().replace('Serial.begin(9600);','Serial.begin(115200);')
s=s.replace('DeviceDriverSet_Servo AppServo;', '''DeviceDriverSet_Servo AppServo;
// Local signed-wheel drive: explicit lease applies only to the new mode.
static int16_t manualLeft, manualRight;
static uint32_t manualUpdated;
static bool manualActive;
extern Servo myservo;
''')
# Servo type is supplied by the original device driver's Servo.h include.
s=s.replace('#include "ApplicationFunctionSet_xxx0.h"','#include "ApplicationFunctionSet_xxx0.h"\n#include <Servo.h>')
needle='void ApplicationFunctionSet::CMD_MotorControlSpeed_xxx0(void)\n{'
s=s.replace(needle,needle+'''
  if (manualActive && Application_SmartRobotCarxxx0.Functional_Mode == CMD_MotorControl_Speed) {
    if (uint32_t(millis() - manualUpdated) > 400 || !Car_LeaveTheGround) {
      manualLeft = manualRight = 0;
    }
    AppMotor.DeviceDriverSet_Motor_control(
      manualRight < 0 ? direction_back : direction_just, abs(manualRight),
      manualLeft < 0 ? direction_back : direction_just, abs(manualLeft), control_enable);
    return;
  }
  manualActive = false;
''')
s=s.replace('        CMD_is_MotorSpeed_L = doc["D1"];', '        manualActive = false; // legacy N4 must not retain a previous manual lease\n        CMD_is_MotorSpeed_L = doc["D1"];')
s=s.replace('      case 1000:', '''      case 1002: // Read-only capability handshake; never moves motors.
        Serial.print(F("{drive_v1}"));
        break;
      case 1001: // Signed left/right PWM and absolute camera angle, one transaction.
        if (!doc["D1"].is<int>() || !doc["D2"].is<int>() || !doc["D3"].is<int>()) break;
        manualLeft = constrain(doc["D1"].as<int>(), -200, 200);
        manualRight = constrain(doc["D2"].as<int>(), -200, 200);
        if (!myservo.attached()) myservo.attach(PIN_Servo_z);
        myservo.write(constrain(doc["D3"].as<int>(), 10, 170));
        manualUpdated = millis();
        manualActive = true;
        Application_SmartRobotCarxxx0.Functional_Mode = CMD_MotorControl_Speed;
        Serial.print('{' + CommandSerialNumber + "_ok}");
        break;
      case 1000:''')
if baud==38400:
    s=s.replace('Serial.begin(115200);','Serial.begin(38400);').replace('{drive_v1}','{drive_v2_38400}')
p.write_text(s)
p=cam/'ESP32_CameraServer_AP_20220120.ino'
s=p.read_text().replace('Serial.begin(9600);','Serial.begin(115200);').replace('Serial2.begin(9600,','Serial2.begin(115200,')
s=s.replace('    WA_en = true;', '    client.setNoDelay(true);\n    WA_en = true;', 1)
# HardwareSerial.read returns -1 if its second availability check sees no byte.
# Do not narrow that sentinel to char (0xff) and inject it into an ASCII reply.
s=s.replace('char c = Serial2.read();', 'int value = Serial2.read();\n        if (value < 0) continue;\n        char c = static_cast<char>(value);', 1)
s=s.replace('char c = Serial2.read();', 'int value = Serial2.read();\n    if (value < 0) return;\n    char c = static_cast<char>(value);', 1)
s=s.replace('char c = client.read();', 'int value = client.read();\n        if (value < 0) continue;\n        char c = static_cast<char>(value);', 1)
s=s.replace('Serial.print(c);','/* Local: do not mirror control traffic to debug UART. */').replace('Serial.print(sendBuff);','/* Local: no debug echo of replies. */')
if baud==38400:
    s=s.replace('Serial2.begin(115200,','Serial2.begin(38400,')
p.write_text(s)
print(f'Prepared separate UNO/ESP32 analogue-drive sources at {baud} baud; not flashed.')
