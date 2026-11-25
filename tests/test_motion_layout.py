"""Motion detector and the live grid layout."""
import numpy as np

from vigilo_app.motion import MotionDetector
from vigilo_app.ui.main_window import best_grid


def test_motion_detector():
    still = np.zeros((360, 640, 3), np.uint8)
    moved = still.copy()
    moved[100:300, 200:400] = 255
    d = MotionDetector()
    assert d.feed(still, 100.0) is None         # first frame: background only
    assert d.feed(still, 100.2) is None         # too early (2.5 checks per second)
    assert d.feed(still, 101.0) == 0.0
    assert d.feed(moved, 102.0) > 0.1


def test_best_grid():
    assert best_grid(1, 1600, 900) == (1, 1)
    assert best_grid(3, 1600, 900) == (2, 2)
    assert best_grid(4, 1600, 900) == (2, 2)
    assert best_grid(9, 1600, 900) == (3, 3)
