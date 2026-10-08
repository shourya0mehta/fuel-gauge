import numpy as np
import pandas as pd

from fuelgauge import colour as C


def test_indices():
    rgb = np.array([[[100.0, 150.0, 50.0]]])
    assert abs(C.gcc(rgb)[0, 0] - 0.5) < 1e-12
    assert abs(C.grvi(rgb)[0, 0] - 0.2) < 1e-12


def test_white_balance_removes_a_colour_cast():
    rng = np.random.default_rng(0)
    base = rng.uniform(50, 200, size=(1, 6, 8, 3))
    cast = np.array([1.3, 1.0, 0.8])
    frames = np.concatenate([base, base * cast])
    valid = np.ones(frames.shape[:3], bool)
    ref = np.zeros((6, 8), bool); ref[:2] = True
    wb = C.white_balance(frames, valid, ref)
    assert np.allclose(C.grvi(wb[0]), C.grvi(wb[1]))


def test_block_means_and_coverage():
    img = np.zeros((48, 48, 3), np.float32); img[:24, :24] = 10
    cover = np.ones((48, 48), bool); cover[24:, 24:] = False
    mean, ok = C.block_means(img, cover, 24)
    assert mean[0, 0, 0] == 10 and ok[0, 0] and not ok[1, 1]


def test_causal_smoothing_uses_only_the_past():
    idx = pd.date_range('2020-01-01', periods=60, freq='D')
    s = pd.Series(np.arange(60.0), index=idx)
    a = C.smooth_causal(s)
    s2 = s.copy(); s2.iloc[40:] = 1e6                       # change the future
    b = C.smooth_causal(s2)
    assert np.allclose(a.iloc[:40].dropna(), b.iloc[:40].dropna())


def test_white_balance_follows_the_camera_not_a_snowy_day():
    rng = np.random.default_rng(1)
    base = rng.uniform(60, 180, size=(1, 6, 8, 3))
    times = pd.date_range('2015-01-01', periods=120, freq='D')
    frames = np.repeat(base, 120, axis=0).copy()
    frames[60:] *= np.array([1.25, 1.0, 0.85])               # camera swapped on day 60: lasting colour cast
    ref = np.zeros((6, 8), bool); ref[:2] = True
    frames[30, :2] = 250.0                                    # one snowy day whitens the reference blocks only
    valid = np.ones(frames.shape[:3], bool)
    g = C.grvi(C.white_balance(frames, valid, ref, times=times))[:, 3:].mean(axis=(1, 2))
    assert abs(g[30] - g[29]) < 1e-6                          # the snow day leaves the brush alone
    assert abs(g[119] - g[0]) < 1e-6                          # the lasting cast is removed once the window has passed
