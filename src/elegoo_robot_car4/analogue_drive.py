"""Pure gamepad mixing and time-based smoothing; no hardware access."""
from dataclasses import dataclass
import math


def deadzone(value: float, width: float) -> float:
    value = max(-1.0, min(1.0, value))
    return math.copysign(max(0.0, (abs(value)-width)/(1-width)), value)


def expo(value: float) -> float:
    """Cubic response, preserving sign and full-scale output."""
    return value ** 3


# Extra steering authority while driving; blend out completely for stationary pivots.
MOVING_STEERING_FLOOR = 0.20
STEERING_BLEND_THROTTLE = 0.25


def mix_wheels(forward: float, reverse: float, steering: float):
    """Return normalized L/R demand. Positive steering turns the nose right."""
    if forward > 0.04 and reverse > 0.04:
        return 0.0, 0.0
    throttle = expo(deadzone(forward, 0.04)) - expo(deadzone(reverse, 0.04))
    steer = expo(deadzone(steering, 0.08))
    if steer != 0:
        blend = min(1.0, abs(throttle)/STEERING_BLEND_THROTTLE)
        floor = MOVING_STEERING_FLOOR * blend
        steer = math.copysign(floor + (1-floor)*abs(steer), steer)
    left, right = throttle + steer, throttle - steer
    scale = max(1.0, abs(left), abs(right))
    return left/scale, right/scale


# User-tuned minimum moving-wheel output, applied after mixing.
MIN_MOVING_PWM = 30
MAX_PWM = 200


def motor_pwm(demand: float) -> float:
    """Map mixed wheel demand to PWM with a minimum for each moving wheel."""
    if abs(demand) < 1e-12:  # ignore floating-point cancellation residue
        return 0.0
    return math.copysign(MIN_MOVING_PWM + (MAX_PWM-MIN_MOVING_PWM)*abs(demand), demand)


@dataclass
class AnalogueDrive:
    left: float = 0.0
    right: float = 0.0
    head: float = 0.0
    previous_time: float | None = None

    def stop(self):
        self.left = self.right = 0.0
        self.previous_time = None

    def update(self, forward, reverse, steering, camera, now):
        dt = 1/30 if self.previous_time is None else max(0.0, min(0.1, now-self.previous_time))
        self.previous_time = now
        left, right = mix_wheels(forward, reverse, steering)
        if left == right == 0:
            self.left = self.right = 0.0  # stop is never ramped
        else:
            # Scale the change vector together, preserving its direction.
            dl, dr = motor_pwm(left)-self.left, motor_pwm(right)-self.right
            scale = min(1.0, 800*dt/max(abs(dl), abs(dr), 1e-9))
            self.left += dl*scale
            self.right += dr*scale
        target = -80*deadzone(camera, 0.08)
        delta = max(-450*dt, min(450*dt, target-self.head))
        self.head += delta
        return round(self.left), round(self.right), round(self.head)
