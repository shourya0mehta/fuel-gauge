import importlib.util
import os

import numpy as np

spec = importlib.util.spec_from_file_location("live_update", os.path.join(os.path.dirname(__file__), "..", "live", "update.py"))
live = importlib.util.module_from_spec(spec); spec.loader.exec_module(live)


def test_quantisation_round_trip():
    v = np.array([-0.2, -0.031, 0.0, 0.05, 0.24, np.nan])
    d = live.decode(live.encode(v))
    assert np.allclose(d[:5], v[:5], atol=1 / live.Q)
    assert d[5] <= -0.255                                   # missing values decode below the valid range


def test_measure_on_a_flat_green_image():
    lk = dict(usable_idx=np.arange(10), ref=None)
    im = np.zeros((live.H, live.W, 3), np.uint8); im[..., 0] = 80; im[..., 1] = 120; im[..., 2] = 60
    grvi, gcc, shifts = live.measure([im, im], lk)
    assert np.allclose(grvi, (120 - 80) / 200) and np.allclose(gcc, 120 / 260)
