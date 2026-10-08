"""Tracking and segment linking on a synthetic camera that drifts and is then re-aimed."""
import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from fuelgauge import track as T


def scene(seed=0, size=(1400, 1000)):
    """Textured synthetic landscape: rocks, ridges and brush blobs."""
    rng = np.random.default_rng(seed)
    w, h = size
    img = np.full((h, w, 3), (120, 140, 150), np.uint8)
    img[: h // 4] = (200, 160, 110)                         # sky band (BGR)
    for _ in range(900):
        x, y = int(rng.integers(0, w)), int(rng.integers(h // 4, h))
        r = int(rng.integers(3, 18)); col = tuple(int(c) for c in rng.integers(30, 220, 3))
        cv2.circle(img, (x, y), r, col, -1)
    for _ in range(60):
        pts = rng.integers(0, [w, h], size=(4, 2)).astype(np.int32)
        cv2.polylines(img, [pts], False, tuple(int(c) for c in rng.integers(0, 255, 3)), 2)
    return cv2.GaussianBlur(img, (3, 3), 0)


def view(world, tx, ty, ang=0.0, s=1.0, size=(768, 576)):
    c = (world.shape[1] / 2, world.shape[0] / 2)
    M = cv2.getRotationMatrix2D(c, ang, s)
    M[:, 2] += (tx, ty)
    warped = cv2.warpAffine(world, M, (world.shape[1], world.shape[0]))
    x0 = (world.shape[1] - size[0]) // 2; y0 = (world.shape[0] - size[1]) // 2
    return warped[y0:y0 + size[1], x0:x0 + size[0]]


def test_tracks_drift_and_links_after_reaim():
    world = scene()
    poses = [(i * 0.6, i * 0.3, 0.0, 1.0) for i in range(12)]                  # slow drift
    poses += [(60 + i * 0.4, -40, 2.0, 1.04) for i in range(12)]              # sudden re-aim + zoom
    frames = [(view(world, *p), 3.0) for p in poses]
    res = T.track(frames, lost_after=3)
    links, master, used = T.link_segments(res, min_size=3)
    Ts = T.to_master(res, links)
    assert sum(t is not None for t in Ts) >= len(poses) - 2
    # every registered frame should map a reference point to the same master location
    m = T.Matcher()
    sx = 768 / m.size[0]
    probe = np.array([300.0, 300.0, 1.0])
    pts = []
    for k, Tk in enumerate(Ts):
        if Tk is None:
            continue
        Mf = Tk.copy(); Mf[:, 2] *= sx
        # world point -> frame k pixel, then -> master
        p, a, ang, s = poses[k]
        c = (world.shape[1] / 2, world.shape[0] / 2)
        Mw = cv2.getRotationMatrix2D(c, ang, s); Mw[:, 2] += (p, a)
        x0 = (world.shape[1] - 768) // 2; y0 = (world.shape[0] - 576) // 2
        wpt = np.array([probe[0] + x0, probe[1] + y0, 1.0])
        fpt = Mw @ wpt - np.array([x0, y0])
        pts.append(Mf @ np.array([fpt[0], fpt[1], 1.0]))
    pts = np.array(pts)
    assert np.max(np.linalg.norm(pts - np.median(pts, 0), axis=1)) < 4.0


def test_sustained_moves_detects_a_jump():
    import pandas as pd
    t = pd.date_range('2010-01-01', periods=200, freq='D')
    tx = np.r_[np.zeros(100), np.full(100, 80.0)] + np.random.default_rng(1).normal(0, 2, 200)
    moves = T.sustained_moves(t, tx, np.zeros(200))
    assert len(moves) == 1 and abs((moves[0][0] - t[100]).days) <= 2


def test_moved_camera_gets_a_second_view():
    a, b = scene(seed=0), scene(seed=7)                  # same camera, two unrelated spots
    import pandas as pd
    frames = [(view(a, i * 0.5, 0), 3.0) for i in range(14)] + [(view(b, i * 0.5, 0), 3.0) for i in range(14)]
    times = pd.date_range('2015-01-01', periods=28, freq='30D')
    res = T.track(frames, lost_after=3)
    views = T.group_views(res, times, min_size=3, min_frames=5, min_span_days=200)
    assert len(views) == 2
    assert all(len(v['to_view']) >= 1 for v in views)
    assert sum(v['frames'] for v in views) >= 26


def test_archive_end_to_end(tmp_path):
    import json
    import pandas as pd
    from fuelgauge.archive import process
    world = scene(seed=3)
    paths = []
    for i in range(16):
        p = tmp_path / f'f{i:02d}.jpg'; cv2.imwrite(str(p), view(world, i * 0.8, -i * 0.4)); paths.append(str(p))
    times = pd.date_range('2016-01-01', periods=16, freq='25D')
    out = process(paths, list(times), str(tmp_path / 'cam'), log=lambda *a: None)
    z = np.load(out)
    qa = json.load(open(tmp_path / 'cam_qa.json'))
    assert qa['mode'] == 'registered' and len(z['dates']) >= 14
    assert z['rgb'].shape[1:] == (576 // 24, 768 // 24, 3) and z['masters'].shape[0] == 1
