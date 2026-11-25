"""
Motion detection on the live picture.
"""

import numpy as np
import cv2


# ----------------------------------------------------------------------------- motion detection

class MotionDetector:
    def __init__(self):
        self.bg = None
        self.last_t = 0.0

    def feed(self, frame, now):
        """Fraction of the picture that changed (0..1), or None if it is too early."""
        if now - self.last_t < 0.4:
            return None
        self.last_t = now
        small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
        g = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0).astype(np.float32)
        if self.bg is None:
            self.bg = g
            return None
        diff = cv2.absdiff(g, self.bg)
        cv2.accumulateWeighted(g, self.bg, 0.25)
        return float(np.count_nonzero(diff > 22)) / diff.size

    def reset(self):
        self.bg = None
