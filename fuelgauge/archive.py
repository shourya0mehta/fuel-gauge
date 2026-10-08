"""Process a camera archive end to end: screen -> track -> link -> warp into each view -> block colours.

A camera that was moved to a new spot gets a second view (its own anchor frame) instead of losing those years.
Featureless scenes (open-grass close-ups) fragment into short stretches that cannot be joined; when fewer than
half of the usable frames land in a view, every usable frame is measured in place, the way fixed PhenoCam
regions are.

    from fuelgauge.archive import process
    out = process(sorted(glob('frames/*.jpg')), times, 'out/mycam')

Writes <out>_blocks.npz (dates, per-block mean RGB, validity, haze score, segment) and <out>_qa.json.
"""
from __future__ import annotations

import json
import os

import numpy as np

from . import quality, track as T
from .colour import block_means

W, H = 768, 576
BLOCK = 24


def _load(path, size=(W, H)):
    import cv2
    im = cv2.imread(path)
    return None if im is None else cv2.resize(im, size, interpolation=cv2.INTER_AREA)


def process(paths, times, out_prefix, log=print):
    import cv2
    matcher = T.Matcher()
    sx = W / matcher.size[0]
    recs = []

    def frames():
        for p, t in zip(paths, times):
            img = _load(p)
            if img is None:
                recs.append(dict(file=os.path.basename(p), time=str(t), ok=False)); yield None, 0; continue
            q = quality.screen(img)
            recs.append(dict(file=os.path.basename(p), time=str(t), **q))
            yield (img if q['ok'] else None), q['clarity']

    res = T.track(frames(), matcher, progress=lambda k, s: log(f'track {k}/{len(paths)} segments {s}'))
    import pandas as pd
    n_ok = sum(1 for r in recs if r.get('ok'))
    tt = pd.to_datetime(pd.Series(list(times)))
    span_all = (tt.max() - tt.min()).days
    # thresholds scale down for short archives
    views = T.group_views(res, times, matcher, min_size=max(3, min(20, n_ok // 20)), min_frames=max(5, min(60, n_ok // 10)),
                          min_span_days=min(300, span_all // 2))
    n_view = sum(v['frames'] for v in views)
    mode = 'registered'
    if n_view < 0.5 * n_ok:
        mode = 'in_place'
        ok_idx = [k for k, r in enumerate(recs) if r.get('ok')]
        anchor = max(ok_idx, key=lambda k: recs[k]['clarity'])
        per_frame = [(0, T.I2) if k in set(ok_idx) else (None, None) for k in range(len(paths))]
        anchors = [anchor]
        log(f'only {n_view} of {n_ok} usable frames in a joined view: measuring in place')
    else:
        per_frame = []
        for s_k, T_k in zip(res.seg, res.T):
            v = next((i for i, vw in enumerate(views) if s_k in vw['to_view']), None)
            per_frame.append((v, T.compose(T_k, views[v]['to_view'][s_k])) if (v is not None and T_k is not None) else (None, None))
        anchors = [res.segments[v['anchor']].ref for v in views]
        log(f'segments {len(res.segments)}, views {[sorted(v["to_view"]) for v in views]}')
    view_imgs = [_load(paths[a]) for a in anchors]
    view_edges = [quality.edge_map(v) for v in view_imgs]
    dates, rgb, valid, haze, seg, view = [], [], [], [], [], []
    for k, (p, (v, Tk)) in enumerate(zip(paths, per_frame)):
        recs[k]['reg'] = Tk is not None
        if Tk is None:
            continue
        Mf = Tk.copy(); Mf[:, 2] *= sx
        img = _load(p)
        warped = cv2.warpAffine(img.astype(np.float32), Mf, (W, H), flags=cv2.INTER_LINEAR, borderValue=(-1, -1, -1))
        cover = warped[..., 0] >= 0
        corr = quality.edge_agreement(np.clip(warped, 0, 255).astype(np.uint8), view_edges[v], cover)
        mean, ok = block_means(np.where(cover[..., None], warped, 0)[..., ::-1], cover, BLOCK)
        recs[k].update(edge_corr=corr, M=Mf.tolist(), tx=float(Mf[0, 2]), ty=float(Mf[1, 2]),
                       scale=float(np.hypot(Mf[0, 0], Mf[1, 0])), seg=int(res.seg[k]), view=int(v))
        dates.append(str(times[k])); rgb.append(mean.astype(np.float32)); valid.append(ok); haze.append(corr)
        seg.append(int(res.seg[k])); view.append(int(v))
    master, master_idx = view_imgs[0], anchors[0]
    np.savez_compressed(f'{out_prefix}_blocks.npz', dates=np.array(dates), rgb=np.array(rgb), valid=np.array(valid),
                        edge_corr=np.array(haze), seg=np.array(seg), view=np.array(view),
                        masters=np.array([v[..., ::-1] for v in view_imgs]),
                        master=master[..., ::-1], master_file=os.path.basename(paths[master_idx]))
    sizes = np.bincount(res.seg[res.seg >= 0], minlength=len(res.segments)).tolist()
    json.dump(dict(recs=recs, sizes=sizes, mode=mode,
                   views=[] if mode == 'in_place' else [dict(anchor=int(v['anchor']), segments=sorted(int(s) for s in v['to_view']),
                                                         links=[(int(a), int(b), int(n)) for a, b, n in v['links']]) for v in views]),
              open(f'{out_prefix}_qa.json', 'w'))
    log(f'{len(paths)} frames, {sum(r.get("ok", False) for r in recs)} pass checks, {len(dates)} registered')
    return f'{out_prefix}_blocks.npz'
