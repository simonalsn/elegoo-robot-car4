#!/usr/bin/env python3
"""Render dashboard review images offline; never constructs a robot connection."""
import argparse
import os
from pathlib import Path
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import pygame as pg
from elegoo_robot_car4.dashboard import Dashboard, DashboardState

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=Path('docs/dashboard'))
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
pg.init()
try:
    dash=Dashboard('192.168.0.213', preview=True)
    scene=pg.Surface((800,600));scene.fill('#809093')
    pg.draw.polygon(scene,'#6b7069',[(0,335),(460,290),(800,320),(800,600),(0,600)])
    pg.draw.rect(scene,'#37494e',(485,75,115,220))
    for x in range(-700,1600,300):pg.draw.line(scene,'#889089',(460,290),(x,600))
    scene.blit(pg.font.SysFont('sans',20).render('Illustrated placeholder - no live video',True,'white'),(20,20))
    dash.set_frame(scene)
    for name,values in {
        'driving':dict(status='Driving',reason='Manual input active. You have control.',level='good',throttle=.65,steering=.24,left=108,right=39),
        'stopped':dict(status='Stopped by you',reason='Release driving controls, then click Resume.',level='error',stopped=True,can_resume=True,left=0,right=0),
        'stale':dict(status='Driving blocked',reason='Video is stale. Wait for fresh frames, then release driving controls.',video_stale=True,frame_age=1.2,fps=0),
    }.items():
        values={**dict(controller='8BitDo Ultimate 2C Wireless Controller',focused=True,fps=12,frame_age=.042,video_stale=False,ack_ms=18,ack_at=10),**values}
        dash.draw(DashboardState(**values),10)
        pg.image.save(dash.canvas,args.output/f'{name}.png')
    print(f'Rendered three offline dashboard states in {args.output}')
finally:pg.quit()
