#!/usr/bin/env python3
"""Prepare a separate UNO build with quiet idle servo; ESP32 is unchanged."""
from pathlib import Path
import shutil
import difflib
root=Path(__file__).resolve().parents[1]
source=root/'firmware/uno-control38400/SmartRobotCarV4.0_V1_20230201'
target=root/'firmware/uno-servo-idle/SmartRobotCarV4.0_V1_20230201'
shutil.copytree(source,target,dirs_exist_ok=True)
p=target/'ApplicationFunctionSet_xxx0.cpp'
original=p.read_text()
s=original.replace('static bool manualActive;', 'static bool manualActive;\nstatic uint8_t manualPan = 255;\nstatic uint32_t manualPanUpdated;')
needle='  if (manualActive && Application_SmartRobotCarxxx0.Functional_Mode == CMD_MotorControl_Speed) {'
s=s.replace(needle,needle+'''
    // Hold through travel/settling, then cease pulses while the target is idle.
    if (myservo.attached() && uint32_t(millis() - manualPanUpdated) > 500) {
      myservo.detach();
      digitalWrite(PIN_Servo_z, LOW);
    }''')
s=s.replace('  manualActive = false;\n\n  static boolean MotorControl', '''  if (manualActive) {
    myservo.detach();
    digitalWrite(PIN_Servo_z, LOW);
  }
  manualActive = false;

  static boolean MotorControl''')
old='''        if (!myservo.attached()) myservo.attach(PIN_Servo_z);
        myservo.write(constrain(doc["D3"].as<int>(), 10, 170));'''
new='''        if (!manualActive || manualPan != constrain(doc["D3"].as<int>(), 10, 170)) {
          manualPan = constrain(doc["D3"].as<int>(), 10, 170);
          // Repeated motor/lease updates must not reattach an idle servo.
          if (!myservo.attached()) myservo.attach(PIN_Servo_z);
          myservo.write(manualPan);
          manualPanUpdated = millis();
        }'''
assert old in s
s=s.replace(old,new)
p.write_text(s)
(root/'firmware-overlays/analogue-drive/servo-idle.patch').write_text(''.join(
    difflib.unified_diff(original.splitlines(True),s.splitlines(True),
                         fromfile=str(source.relative_to(root)/p.name),
                         tofile=str(target.relative_to(root)/p.name))))
print('Prepared separate quiet-idle UNO firmware; no flashing; ESP32 unchanged.')
