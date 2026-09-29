#!/usr/bin/env python3
"""115200-baud UNO check: battery disconnected, ESP cable unplugged, upload switch.

Only zero wheel speeds and centred camera are commanded. No movement test.
"""
import argparse
import json
import os
import select
import termios
import time
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baud',type=int,choices=(115200,38400),default=115200)
parser.add_argument('--output',type=Path,default=Path('logs/analogue-drive-2026-09-29/uno-probe.json'))
args=parser.parse_args()
port='/dev/serial/by-id/usb-HOLTEK_USB_TO_UART_BRIDGE_0000-if00'
fd=os.open(port,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
buffer=b''

def request(command, expected, timeout=2):
    global buffer
    payload=json.dumps(command,separators=(',',':')).encode()
    start=time.monotonic()
    assert os.write(fd,payload)==len(payload)
    end=start+timeout
    while expected not in buffer:
        remaining=end-time.monotonic()
        if remaining <= 0:raise TimeoutError((command,buffer.decode(errors='replace')))
        if select.select([fd],[],[],remaining)[0]:buffer+=os.read(fd,4096)
    index=buffer.index(expected)+len(expected)
    answer=buffer[:index]; buffer=buffer[index:]
    return time.monotonic()-start,answer.decode(errors='replace')

try:
    attrs=termios.tcgetattr(fd)
    attrs[0]=attrs[1]=attrs[3]=0
    attrs[2]=termios.CS8|termios.CLOCAL|termios.CREAD
    attrs[4]=attrs[5]=getattr(termios,f'B{args.baud}')
    attrs[6][termios.VMIN]=attrs[6][termios.VTIME]=0
    termios.tcsetattr(fd,termios.TCSANOW,attrs)
    time.sleep(3)
    termios.tcflush(fd,termios.TCIFLUSH)
    request({'H':'stop','N':100},b'{ok}')
    request({'H':'cap','N':1002},b'{drive_v2_38400}' if args.baud==38400 else b'{drive_v1}')
    delays=[]
    for i in range(150):
        name=f'd{i}'
        delay,reply=request({'H':name,'N':1001,'D1':0,'D2':0,'D3':90},f'{{{name}_ok}}'.encode())
        delays.append(delay)
        if i%10==0:
            request({'H':'ground','N':23},b'}')
        time.sleep(max(0,1/30-delay))
    _,ground=request({'H':'ground','N':23},b'}')
    _,mpu=request({'H':'mpu','N':1000},b'}')
    mpu=json.loads(mpu)
    assert mpu['id']=='mpu' and len(mpu['a'])==len(mpu['g'])==3
    request({'H':'stop','N':100},b'{ok}')
    result=dict(passed=True,baud=args.baud,zero_speed_updates=len(delays),
                mean_ack_ms=1000*sum(delays)/len(delays),max_ack_ms=1000*max(delays),
                ground=ground,mpu=mpu,movement_tested=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
finally:
    try:
        os.write(fd,b'{"H":"stop","N":100}')
        termios.tcdrain(fd)
    finally:os.close(fd)
