"""Camera NDVI from PhenoCam's infrared twins, measured on the same registered blocks as the colour photos.

Each IR photo is taken seconds after its colour twin from the same position, so it is warped with the colour
photo's own registration transform. Camera NDVI follows Petach et al. (2014): pixel values are divided by the
square root of each photo's exposure, the IR photo (near-infrared plus visible light) minus the colour photo's
luminance estimates near-infrared, and NDVI = (NIR - red) / (NIR + red).

    DATA=data python scripts/nir.py cam1 cam2 ...
Writes $DATA/nir/<cam>_series.csv (daily camera NDVI on the automatic regions, plus PhenoCam's hand-drawn-region
NDVI) and $DATA/nir/<cam>_blocks.npz.
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import study  # noqa: E402
from fuelgauge import quality as Q  # noqa: E402

DATA = study.DATA
W, H, BLOCK = 768, 576, 24


def ir_blocks(cam, qa_recs, exp):
    import cv2
    rows, ir, e_ir, e_rgb = [], [], [], []
    gh, gw = H // BLOCK, W // BLOCK
    for i, r in enumerate(qa_recs):
        e = exp.get(r['file'])
        if not e or not e.get('e_ir') or not e.get('e_rgb'):
            continue
        p = os.path.join(DATA, 'nir', cam, e['ir'])
        im = cv2.imread(p)
        if im is None:
            continue
        im = cv2.resize(im, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32).mean(2)
        warped = cv2.warpAffine(im, np.float32(r['M']), (W, H), flags=cv2.INTER_LINEAR, borderValue=-1)
        cover = warped >= 0
        s = np.where(cover, warped, 0).reshape(gh, BLOCK, gw, BLOCK).sum(axis=(1, 3))
        n = cover.reshape(gh, BLOCK, gw, BLOCK).sum(axis=(1, 3))
        with np.errstate(invalid='ignore', divide='ignore'):
            ir.append(np.where(n > 0.9 * BLOCK * BLOCK, s / n, np.nan).astype(np.float32))
        rows.append(i); e_ir.append(e['e_ir']); e_rgb.append(e['e_rgb'])
    return np.array(rows), np.array(ir), np.array(e_ir, float), np.array(e_rgb, float)


def camera_ndvi(rgb, ir, e_rgb, e_ir):
    """Petach et al. (2014) exposure-adjusted camera NDVI per block."""
    sr = np.sqrt(e_rgb)[:, None, None]; si = np.sqrt(e_ir)[:, None, None]
    R, G, B = rgb[..., 0] / sr, rgb[..., 1] / sr, rgb[..., 2] / sr
    Y = 0.3 * R + 0.59 * G + 0.11 * B
    X = ir / si - Y
    with np.errstate(invalid='ignore', divide='ignore'):
        return (X - R) / (X + R)


def hand_ndvi(cam, d0, d1):
    fs = sorted(glob.glob(os.path.join(DATA, 'phenocam_roi', f'{cam}_*_ndvi_1day.csv')))
    best = None
    for f in fs:
        d = pd.read_csv(f, comment='#'); d['date'] = pd.to_datetime(d['date'])
        d = d.dropna(subset=['ndvi_mean'])
        n = int(((d.date >= d0) & (d.date <= d1)).sum())
        if best is None or n > best[0]:
            best = (n, f, d)
    if best is None or best[0] < 30:
        return None, None
    _, f, d = best
    return study.daily(d.ndvi_mean.values, d.date.values, np.ones(len(d), bool)), os.path.basename(f)


def main(cams):
    us = pd.read_parquet(os.path.join(DATA, 'globe', 'globe_usa.parquet'))
    sel = {r['cam']: r for r in json.load(open(os.path.join(os.path.dirname(__file__), '..', 'study', 'cameras.json')))}
    for cam in cams:
        ep = os.path.join(DATA, 'nir', f'{cam}_exposure.json')
        if not os.path.exists(ep):
            print(cam, 'no IR'); continue
        exp = {r['rgb']: r for r in json.load(open(ep))}
        z = np.load(os.path.join(DATA, 'proc', f'{cam}_blocks.npz'), allow_pickle=True)
        qa = json.load(open(os.path.join(DATA, 'proc', f'{cam}_qa.json')))
        recs = [r for r in qa['recs'] if r.get('reg')]
        assert len(recs) == len(z['dates'])
        rows, ir, e_ir, e_rgb = ir_blocks(cam, recs, exp)
        if len(rows) < 60:
            print(cam, 'only', len(rows), 'IR frames'); continue
        rgb, valid, ec = z['rgb'][rows], z['valid'][rows], z['edge_corr'][rows]
        times = pd.to_datetime(z['dates'][rows])
        view = (z['view'] if 'view' in z.files else np.zeros(len(z['dates']), int))[rows]
        masters = z['masters'] if 'masters' in z.files else z['master'][None]
        nd = camera_ndvi(rgb, ir, e_rgb, e_ir)
        parts, info = [], []
        for v in range(len(masters)):
            m = view == v
            if m.sum() < 30:
                continue
            clear = Q.clear_flags(ec[m], times[m])
            R, _, _ = study.view_series(rgb[m], valid[m], times[m], clear, masters[v])
            vm = np.where(valid[m] & np.isfinite(nd[m]), 1.0, np.nan)
            s = np.nanmedian((nd[m] * vm)[:, R['veg']], 1)
            parts.append(study.zscore(study.daily(s, times[m], clear)))
            info.append(dict(frames=int(m.sum()), clear=int(clear.sum())))
        auto = study.combine(parts)
        x = us[us['Site name'].isin([s[0] for s in sel[cam]['good']])]
        hand, hand_file = hand_ndvi(cam, x.date.min() - pd.Timedelta(days=30), x.date.max())
        df = pd.DataFrame({'ndvi_auto': auto})
        if hand is not None:
            df = df.join(pd.DataFrame({'ndvi_hand': hand}), how='outer')
        df.index.name = 'date'
        df.to_csv(os.path.join(DATA, 'nir', f'{cam}_series.csv'))
        np.savez_compressed(os.path.join(DATA, 'nir', f'{cam}_blocks.npz'), rows=rows, ndvi=nd.astype(np.float16), e_ir=e_ir, e_rgb=e_rgb)
        json.dump(dict(cam=cam, ir_frames=int(len(rows)), registered=int(len(recs)), views=info, hand_roi=hand_file),
                  open(os.path.join(DATA, 'nir', f'{cam}_info.json'), 'w'))
        print(cam, 'IR frames', len(rows), 'of', len(recs), 'daily values', int(df.ndvi_auto.notna().sum()) if auto is not None else 0,
              'hand', hand_file, flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
