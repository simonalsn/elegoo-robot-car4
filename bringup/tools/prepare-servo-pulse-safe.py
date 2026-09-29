#!/usr/bin/env python3
"""Prepare a separate UNO candidate that never truncates the last servo pulse."""
from pathlib import Path
import shutil
import difflib
root=Path(__file__).resolve().parents[1]
source=root/'firmware/uno-servo-idle/SmartRobotCarV4.0_V1_20230201'
target=root/'firmware/uno-servo-pulse-safe/SmartRobotCarV4.0_V1_20230201'
shutil.copytree(source,target,dirs_exist_ok=True)
p=target/'ApplicationFunctionSet_xxx0.cpp'
original=p.read_text()
helper='''
// Check and detach atomically: a Servo ISR must not start a pulse between them.
// If a pulse is high, leave its falling edge to Servo and retry next loop.
static bool releaseManualPan()
{
  uint8_t savedSREG = SREG;
  cli();
  bool released = digitalRead(PIN_Servo_z) == LOW;
  if (released) myservo.detach();
  SREG = savedSREG;
  return released;
}
'''
s=original.replace('extern Servo myservo;', 'extern Servo myservo;\n'+helper)
old='''      myservo.detach();
      digitalWrite(PIN_Servo_z, LOW);'''
assert s.count(old)==1
s=s.replace(old,'      releaseManualPan();')
old='''  if (manualActive) {
    myservo.detach();
    digitalWrite(PIN_Servo_z, LOW);
  }
  manualActive = false;'''
assert old in s
s=s.replace(old,'''  if (manualActive && releaseManualPan()) manualActive = false;''')
old='''          if (!myservo.attached()) myservo.attach(PIN_Servo_z);
          myservo.write(manualPan);'''
assert old in s
s=s.replace(old,'''          myservo.write(manualPan);
          if (!myservo.attached()) myservo.attach(PIN_Servo_z);''')
p.write_text(s)
(root/'firmware-overlays/analogue-drive/servo-pulse-safe.patch').write_text(''.join(
    difflib.unified_diff(original.splitlines(True),s.splitlines(True),
                         fromfile=str(source.relative_to(root)/p.name),
                         tofile=str(target.relative_to(root)/p.name))))
print('Prepared pulse-safe UNO candidate; no flash; ESP32 unchanged.')
