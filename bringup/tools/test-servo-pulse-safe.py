#!/usr/bin/env python3
"""Host check of the actual candidate helper with mocked AVR/Servo operations."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
source=(root/'firmware/uno-servo-pulse-safe/SmartRobotCarV4.0_V1_20230201/ApplicationFunctionSet_xxx0.cpp').read_text()
start=source.index('static bool releaseManualPan()')
helper=source[start:source.index('\n}',start)+2]
mock=r'''
#include <cassert>
#include <cstdint>
uint8_t SREG=0x80;
const int PIN_Servo_z=10, LOW=0;
int pin=0;
void cli(){ SREG &= ~0x80; }
int digitalRead(int){ assert(!(SREG & 0x80)); return pin; }
struct Servo {
  bool active=true;
  void detach(){ assert(!(SREG & 0x80)); assert(pin==LOW); active=false; }
} myservo;
'''
checks=r'''
int main(){
  // A high pulse is left intact; interrupts resume so its falling edge can run.
  pin=1;
  assert(!releaseManualPan());
  assert(myservo.active && pin==1 && SREG==0x80);
  // After the natural falling edge, release without another signal transition.
  pin=0;
  assert(releaseManualPan());
  assert(!myservo.active && pin==0 && SREG==0x80);
  // Preserve callers that already had interrupts disabled as well.
  SREG=0;
  assert(releaseManualPan());
  assert(SREG==0);
}
'''
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp)/'check.cpp';p.write_text(mock+helper+checks)
    exe=Path(tmp)/'check'
    subprocess.run(['c++','-std=c++11','-Wall','-Wextra','-Werror',str(p),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
print('Servo release checks passed: high pulse preserved, low-phase detach atomic, interrupt state restored.')
