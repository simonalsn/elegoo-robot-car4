#!/usr/bin/env python3
"""Check runtime presets with UDP and control connected; sends only Stop commands.

Close other clients first. Restores the original resolution/quality in finally.
"""
import argparse
import json
import socket
import time
from pathlib import Path
import requests
from elegoo_robot_car4.camera_presets import apply_preset, PRESETS
from elegoo_robot_car4.udp_video import UdpVideo

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--robot-ip',default='192.168.0.213')
parser.add_argument('--output',type=Path,default=Path('logs/camera-presets/probe.json'))
args=parser.parse_args()
base=f'http://{args.robot_ip}'
result={'presets':{},'movement_commands_sent':False}
s=None;video=None
with requests.Session() as http:
    def get(path,**kwargs):
        with http.get(base+path,timeout=(2,3),**kwargs) as response:
            response.raise_for_status()
            return response.json() if path=='/status' else None
    original=get('/status')
    result['original']={k:original[k] for k in ('framesize','quality')}
    def stop():
        s.sendall(b'{"H":"stop","N":100}')
        data=b'';end=time.monotonic()+3
        while b'{ok}' not in data:
            if time.monotonic()>end:raise TimeoutError('Stop acknowledgement')
            packet=s.recv(4096)
            if not packet:raise ConnectionError('Control disconnected')
            data+=packet
    try:
        s=socket.create_connection((args.robot_ip,100),timeout=3)
        stop()
        video=UdpVideo(args.robot_ip)
        for key,preset in PRESETS.items():
            stop()
            apply_preset(args.robot_ip,key,http.get)
            deadline=time.monotonic()+8
            matched=False
            while time.monotonic()<deadline:
                frame,age=video.latest()
                if frame is not None and age<.25 and (frame.shape[1],frame.shape[0])==preset.size:
                    matched=True;break
                time.sleep(.05)
            start=time.monotonic();count=video.frames
            time.sleep(3)
            elapsed=time.monotonic()-start
            frame,age=video.latest()
            record={'matched_resolution':matched,'received_fps':(video.frames-count)/elapsed,
                    'frame_age':age if frame is not None else None,
                    'shape':list(frame.shape) if frame is not None else None}
            result['presets'][key]=record
            print(key,json.dumps(record),flush=True)
    finally:
        try:
            for variable in ('quality','framesize'):
                get('/control',params={'var':variable,'val':original[variable]})
            status=get('/status')
            result['restored']=all(status[k]==original[k] for k in ('framesize','quality'))
            if s:stop()
        finally:
            if video:video.close()
            if s:s.close()
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2)+'\n')
            print('Original camera settings restored:',result.get('restored',False),flush=True)
