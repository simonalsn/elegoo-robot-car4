"""Bounded JPEG-quality reductions when detailed video exceeds its budget."""


class VideoAdaptation:
    def __init__(self):
        self.last_check = 0.0
        self.previous = None

    def reset(self, now):
        self.last_check = now
        self.previous = None

    def recommend(self, diagnostics, age, preset, quality, now):
        if preset != 'detail' or quality is None or quality >= 40 or now-self.last_check < 5:
            return None
        self.last_check = now
        sender = diagnostics.get('sender') or {}
        counters = (diagnostics.get('completed', 0),
                    diagnostics.get('incomplete', 0)+diagnostics.get('expired', 0),
                    sender.get('oversized', 0), sender.get('failed', 0))
        previous, self.previous = self.previous, counters
        lost = False
        if previous is not None:
            complete, dropped, oversized, failed = [max(0, current-old) for current, old in zip(counters, previous)]
            lost = oversized > 0 or failed > 0 or (complete+dropped >= 10 and dropped/(complete+dropped) > .2)
        large = max(diagnostics.get('last_jpeg_bytes', 0), sender.get('bytes', 0)) > 220*1024
        if lost or large or age > 2:
            return min(40, quality+5)
        return None
