"""Pygame driving dashboard. Rendering has no robot or gamepad side effects."""
from dataclasses import dataclass
import math
import os
from collections import OrderedDict
import pygame as pg
from .camera_presets import PRESETS


@dataclass
class DashboardState:
    status: str = 'Waiting'
    reason: str = 'Waiting for video and controller.'
    level: str = 'warning'
    controller: str = 'No controller connected'
    focused: bool = False
    throttle: float = 0.0
    steering: float = 0.0
    head: int = 0
    left: int | None = None
    right: int | None = None
    ack_ms: float | None = None
    ack_at: float | None = None
    fps: float | None = None
    frame_age: float = float('inf')
    video_stale: bool = True
    stopped: bool = False
    can_resume: bool = False
    preset: str | None = None
    preset_pending: bool = False
    preset_message: str = 'Current camera settings unchanged. Select a preset to compare.'
    preset_error: bool = False


class Dashboard:
    SIZE = (1280, 1060)
    BG = '#101619'
    PANEL = '#1a2328'
    EDGE = '#303c43'
    TEXT = '#eff5f6'
    MUTED = '#a5b4bc'
    GREEN = '#7be1bf'
    AMBER = '#f8c876'
    RED = '#ff9399'
    STOP = pg.Rect(930, 237, 304, 46)
    RECONNECT = pg.Rect(1090, 27, 166, 44)
    RESUME = pg.Rect(930, 291, 304, 32)
    PRESET_RECTS = {key: pg.Rect(244+i*246, 876, 234, 43) for i, key in enumerate(PRESETS)}

    def __init__(self, robot_ip='', transport='udp', preview=False):
        # Our Surface renderer needs no OpenGL context. SDL's automatic window
        # acceleration can terminate X11 clients on incompatible GLX drivers.
        # Keep an explicit user override available for other display setups.
        os.environ.setdefault('SDL_FRAMEBUFFER_ACCELERATION', '0')
        pg.font.init()
        self.screen = pg.display.set_mode((1200, 960), pg.RESIZABLE)
        self.canvas = pg.Surface(self.SIZE)
        self.fonts = {size: pg.font.SysFont('sans', size) for size in (14, 16, 18, 22, 28, 32)}
        self.robot_ip, self.transport, self.preview = robot_ip, transport, preview
        self.frame = None
        self.frame_size = None
        self._scaled_frame = None
        self._text_cache = OrderedDict()
        self._scaled_canvas = None
        self._stale_overlay = pg.Surface((864, 648), pg.SRCALPHA)
        self._stale_overlay.fill((12, 20, 26, 185))
        self.offset = (0, 0)
        self.scale = 1.0
        self._transform()

    def _transform(self):
        w, h = self.screen.get_size()
        self.scale = min(w/self.SIZE[0], h/self.SIZE[1])
        self.offset = ((w-round(self.SIZE[0]*self.scale))//2,
                       (h-round(self.SIZE[1]*self.scale))//2)

    def action(self, event):
        if event.type == pg.VIDEORESIZE:
            self.screen = pg.display.set_mode((max(640, event.w), max(480, event.h)), pg.RESIZABLE)
            self._transform()
        if event.type == pg.KEYDOWN and event.key == pg.K_SPACE:
            return 'stop'
        if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
            self._transform()
            point = tuple((p-o)/self.scale for p, o in zip(event.pos, self.offset))
            if self.RECONNECT.collidepoint(point):
                return 'reconnect'
            if self.STOP.collidepoint(point):
                return 'stop'
            if self.RESUME.collidepoint(point):
                return 'resume'
            for key, rect in self.PRESET_RECTS.items():
                if rect.collidepoint(point):
                    return 'preset:'+key
        return None

    def set_frame(self, surface):
        self.frame = surface
        self.frame_size = surface.get_size()
        box = pg.Rect(24, 140, 864, 648)
        rect = surface.get_rect().fit(box)
        self._scaled_frame = (pg.transform.smoothscale(surface, rect.size), rect)

    def text(self, text, x, y, size=18, color=None):
        key = (str(text), size, tuple(pg.Color(color or self.TEXT)))
        surface = self._text_cache.get(key)
        if surface is None:
            surface = self.fonts[size].render(key[0], True, key[2])
            self._text_cache[key] = surface
            if len(self._text_cache) > 256:
                self._text_cache.popitem(last=False)
        self._text_cache.move_to_end(key)
        self.canvas.blit(surface, (x, y))

    def wrapped(self, text, x, y, width, size=16, color=None):
        words, line = text.split(), ''
        for word in words:
            candidate = (line+' '+word).strip()
            if line and self.fonts[size].size(candidate)[0] > width:
                self.text(line, x, y, size, color)
                y += size+5
                line = word
            else:
                line = candidate
        if line:
            self.text(line, x, y, size, color)
        return y+size+5

    def panel(self, rect):
        pg.draw.rect(self.canvas, self.PANEL, rect, border_radius=10)
        pg.draw.rect(self.canvas, self.EDGE, rect, 1, border_radius=10)

    def meter(self, y, label, value, description):
        self.text(label, 930, y, 18)
        font = self.fonts[16]
        self.text(description, 1234-font.size(description)[0], y+2, 16, self.GREEN)
        pg.draw.rect(self.canvas, '#36434a', (930, y+31, 304, 7), border_radius=3)
        value = max(-1, min(1, value))
        length = round(abs(value)*152)
        pg.draw.rect(self.canvas, self.GREEN, (1082-length if value<0 else 1082, y+31, length, 7), border_radius=3)
        pg.draw.line(self.canvas, self.TEXT, (1082, y+27), (1082, y+42))

    def draw(self, state, now):
        self.canvas.fill(self.BG)
        self.text('Car dashboard', 24, 19, 32)
        self.text('ELEGOO V4  /  Manual control', 25, 57, 16, self.MUTED)
        connected = state.ack_at is not None and now-state.ack_at < 2
        label = 'OFFLINE PREVIEW - no robot connection' if self.preview else (
            ('Control responding' if connected else 'Control awaiting reply')+'  /  '+self.robot_ip)
        self.text(label, 610, 45, 16, self.AMBER if self.preview or not connected else self.GREEN)
        pg.draw.rect(self.canvas, '#29453d', self.RECONNECT, border_radius=5)
        self.text('Reconnect', 1115, 39, 18)
        self.panel(pg.Rect(24, 98, 864, 750))
        self.text('Camera', 42, 108, 22)
        resolution = 'Waiting for frames' if self.frame_size is None else f'{self.frame_size[0]} x {self.frame_size[1]}'
        self.text(f'{resolution}  /  {self.transport.upper()}', 612, 112, 16, self.MUTED)
        pg.draw.rect(self.canvas, '#11191d', (24, 140, 864, 648))
        if self._scaled_frame:
            self.canvas.blit(*self._scaled_frame)
            if not state.video_stale:
                pg.draw.line(self.canvas, '#ffffff', (446, 464), (466, 464))
                pg.draw.line(self.canvas, '#ffffff', (456, 454), (456, 474))
        if state.video_stale:
            self.canvas.blit(self._stale_overlay, (24, 140))
            self.text('Waiting for fresh video', 298, 433, 28)
            self.text('Driving is blocked while the image is stale.', 276, 479, 18, self.MUTED)
        else:
            pg.draw.rect(self.canvas, '#17232b', (42, 744, 300, 30), border_radius=5)
            self.text(f'Camera target: {self.pan_label(state.head)}', 53, 749, 16)
        age = '--' if not math.isfinite(state.frame_age) else f'{state.frame_age*1000:.0f} ms'
        ack = '--' if state.ack_ms is None else f'{state.ack_ms:.0f} ms'
        if state.ack_at is not None and now-state.ack_at >= 2:
            ack += ' (old)'
        metrics = [('VIDEO RATE', '--' if state.fps is None else f'{state.fps:.1f} fps'),
                   ('RECEIVE AGE', age), ('CONTROL EXCHANGE', ack)]
        for x, (title, value) in zip((42, 325, 608), metrics):
            self.text(title, x, 798, 14, self.MUTED)
            self.text(value, x, 819, 18)
        self.panel(pg.Rect(908, 98, 348, 237))
        color = {'good': self.GREEN, 'warning': self.AMBER, 'error': self.RED}.get(state.level, self.AMBER)
        pg.draw.line(self.canvas, color, (920, 99), (1244, 99), 3)
        self.text('DRIVE STATUS', 930, 113, 14, self.MUTED)
        self.text(state.status, 930, 139, 28, color)
        self.wrapped(state.reason, 930, 180, 302, 16)
        pg.draw.rect(self.canvas, '#eaa3a7', self.STOP, border_radius=6)
        self.text('Stop driving', 945, 246, 22, '#2a141a')
        self.text('SPACE', 1174, 250, 14, '#2a141a')
        if state.stopped:
            pg.draw.rect(self.canvas, '#29453d' if state.can_resume else '#29333a', self.RESUME, border_radius=5)
            self.text('Resume' if state.can_resume else 'Resume - waiting for neutral / ready', 940, 296, 16,
                      self.GREEN if state.can_resume else self.MUTED)
        self.panel(pg.Rect(908, 351, 348, 320))
        self.text('Commanded inputs', 930, 365, 22)
        self.text('Inputs / targets, not measured speed', 930, 395, 14, self.MUTED)
        throttle = 'Neutral' if abs(state.throttle)<.04 else f'{"Forward" if state.throttle>0 else "Reverse"} {abs(state.throttle)*100:.0f}%'
        steering = 'Centred' if abs(state.steering)<=.08 else f'{"Right" if state.steering>0 else "Left"} {abs(state.steering)*100:.0f}%'
        self.meter(426, 'Throttle', state.throttle, throttle)
        self.meter(479, 'Steering', state.steering, steering)
        self.meter(532, 'Camera target', -state.head/80, self.pan_label(state.head))
        for x, label, pwm in ((930, 'LEFT WHEELS', state.left), (1090, 'RIGHT WHEELS', state.right)):
            pg.draw.rect(self.canvas, '#121b20', (x, 592, 144, 64), border_radius=5)
            self.text(label, x+10, 599, 14, self.MUTED)
            self.text('--' if pwm is None else f'{pwm} PWM', x+10, 620, 22)
        self.panel(pg.Rect(908, 687, 348, 161))
        self.text('Controller', 930, 702, 22)
        self.wrapped(state.controller, 930, 739, 300, 16, self.MUTED)
        self.text('Window focused' if state.focused else 'Window unfocused - driving blocked', 930, 798, 16,
                  self.GREEN if state.focused else self.AMBER)
        self.panel(pg.Rect(24, 866, 1232, 86))
        self.text('Camera presets', 42, 886, 22)
        for key, rect in self.PRESET_RECTS.items():
            preset = PRESETS[key]
            selected = state.preset == key
            pg.draw.rect(self.canvas, '#29453d' if selected else '#25323a', rect, border_radius=5)
            self.text(preset.name, rect.x+10, rect.y+3, 18, self.GREEN if selected else self.TEXT)
            self.text(f'{preset.size[0]} x {preset.size[1]}  /  JPEG {preset.quality}', rect.x+10, rect.y+24, 14, self.MUTED)
        message = state.preset_message
        while self.fonts[14].size(message)[0] > 1196:
            message = message[:-4]+'...'
        self.text(message, 42, 928, 14, self.AMBER if state.preset_error or state.preset_pending else self.MUTED)
        self.panel(pg.Rect(24, 968, 1232, 68))
        guides = [('RT / LT', 'Forward / reverse', 'Both triggers stop'),
                  ('LEFT STICK', 'Steer / stationary pivot', 'Mix steering with throttle'),
                  ('RIGHT STICK', 'Aim camera', 'Release or X to centre'),
                  ('SPACE / STOP', 'Stop and hold', 'Neutral, then click Resume')]
        for x, (key, title, detail) in zip((42, 350, 658, 966), guides):
            self.text(key, x, 974, 14, self.GREEN)
            self.text(title, x, 993, 16)
            self.text(detail, x, 1015, 14, self.MUTED)
        self.text('Manual mode / ground and fresh-video checks enabled', 24, 1042, 14, self.MUTED)
        self.text('Esc: exit', 1170, 1042, 14, self.MUTED)
        self._transform()
        size = (round(self.SIZE[0]*self.scale), round(self.SIZE[1]*self.scale))
        self.screen.fill(self.BG)
        if self._scaled_canvas is None or self._scaled_canvas.get_size() != size:
            self._scaled_canvas = pg.Surface(size)
        pg.transform.smoothscale(self.canvas, size, self._scaled_canvas)
        self.screen.blit(self._scaled_canvas, self.offset)
        pg.display.flip()

    @staticmethod
    def pan_label(head):
        return 'centred' if head == 0 else f'{abs(head)} deg {"right" if head<0 else "left"}'


def preview():
    """Offline preview, deliberately without constructing Car or UdpVideo."""
    import time
    pg.init()
    dashboard = Dashboard(preview=True)
    pg.display.set_caption('Car dashboard - OFFLINE preview (1 Ready, 2 Driving, 3 Video lost)')
    scene = pg.Surface((800, 600))
    scene.fill('#809093')
    pg.draw.polygon(scene, '#6b7069', [(0, 335), (460, 290), (800, 320), (800, 600), (0, 600)])
    pg.draw.rect(scene, '#37494e', (485, 75, 115, 220))
    for x in range(-700, 1600, 300):
        pg.draw.line(scene, '#889089', (460, 290), (x, 600))
    scene.blit(pg.font.SysFont('sans', 20).render('Illustrated placeholder - no live video', True, 'white'), (20, 20))
    dashboard.set_frame(scene)
    state = DashboardState(status='Ready', reason='Offline preview. Press 1, 2 or 3 to change state.', level='good',
                           controller='8BitDo Ultimate 2C (simulated)', focused=True, left=0, right=0,
                           frame_age=.042, fps=12, ack_ms=18, video_stale=False)
    clock = pg.time.Clock()
    running = True
    try:
        while running:
            for e in pg.event.get():
                if e.type == pg.QUIT or (e.type == pg.KEYDOWN and e.key == pg.K_ESCAPE):
                    running = False
                action = dashboard.action(e)
                if action and action.startswith('preset:'):
                    key = action.split(':')[1]
                    state.preset = key
                    state.preset_message = PRESETS[key].name+' selected (offline illustration only; no camera settings sent).'
                if action == 'stop':
                    state.status, state.reason, state.level = 'Stopped by you', 'Offline stop preview. Click Resume to reset.', 'error'
                    state.stopped = state.can_resume = True
                    state.left = state.right = 0
                elif action == 'resume' and state.can_resume:
                    state = DashboardState(status='Ready', reason='Offline preview - no robot connected.', level='good', focused=True,
                                           controller='Simulated controller', frame_age=.042, fps=12, video_stale=False, left=0, right=0)
                if e.type == pg.KEYDOWN and e.key in (pg.K_1, pg.K_2, pg.K_3):
                    state.stopped = state.can_resume = False
                    state.status = {pg.K_1:'Ready', pg.K_2:'Driving', pg.K_3:'Driving blocked'}[e.key]
                    state.reason = 'Offline preview - simulated data only.'
                    state.video_stale = e.key == pg.K_3
                    state.level = 'warning' if state.video_stale else 'good'
                    state.throttle, state.steering = ((.65, .24) if e.key==pg.K_2 else (0,0))
                    state.left, state.right = ((108,39) if e.key==pg.K_2 else (0,0))
                    state.frame_age = 1.2 if state.video_stale else .042
                    state.fps = 0 if state.video_stale else 12
            state.ack_at = time.monotonic()
            dashboard.draw(state, time.monotonic())
            clock.tick(30)
    finally:
        pg.quit()
