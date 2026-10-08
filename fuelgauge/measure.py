"""Registered block colours -> a daily vegetation series you can compare across years.

For each view of the camera (a camera moved to a new spot has more than one):
  1. flag clear frames by haze score (edge agreement with the view's anchor frame, relative to the recent norm)
  2. pick measurement regions automatically: SegFormer vegetation labels plus a strong seasonal swing, and
     reference blocks (rock, soil, road, distant ridges) that stay flat through the year
  3. white-balance every frame against the reference blocks (trailing two-month median, so it follows the camera,
     not snow or wet soil)
  4. GRVI and GCC over the vegetation blocks, clear frames only, then a causal smooth (weekly 90th percentile,
     two-week mean) so each day uses only data up to that day

    from fuelgauge.measure import measure
    daily, regions, info = measure('out/mycam_blocks.npz', 'out/mycam')

Writes <out>_daily.csv, <out>_regions.png (vegetation in green, reference in orange) and <out>_measure.json.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import colour as C, quality as Q, rois


def daily(series, times, clear, ffill=21):
    """Per-frame values -> a causal daily series from clear frames only (None if fewer than 30 clear days)."""
    s = pd.Series(np.asarray(series, float), index=pd.to_datetime(times).normalize())
    s = s[~s.index.duplicated(keep='last')]
    c = pd.Series(np.asarray(clear, bool), index=pd.to_datetime(times).normalize())
    c = c[~c.index.duplicated(keep='last')]
    s = s[c.reindex(s.index).fillna(False).values].dropna()
    if len(s) < 30:
        return None
    return C.smooth_causal(s).resample('D').mean().ffill(limit=ffill)


def zscore(s):
    return None if s is None else (s - s.mean()) / s.std()


def combine(parts):
    """Join per-view series in time (views rarely overlap; where they do, average)."""
    parts = [p for p in parts if p is not None]
    if not parts:
        return None
    return pd.concat(parts, axis=1).mean(axis=1) if len(parts) > 1 else parts[0]


def semantic_fractions(master, gh, gw, use_model=True):
    """Per-block fraction of vegetation-like and not-ground pixels in a view's anchor frame. Without the
    segmentation model every block counts as vegetation and only the seasonal swing picks regions."""
    import cv2
    if not use_model:
        return np.ones((gh, gw), np.float32), np.zeros((gh, gw), np.float32)
    from . import segment as S
    _, veg, bad = S.masks(S.labels(master))
    f = [cv2.resize(m.astype(np.float32), (gw, gh), interpolation=cv2.INTER_AREA) for m in (veg, bad)]
    return f[0], f[1]


def view_series(rgb, valid, times, clear, master, use_model=True):
    """Automatic regions on one view, and that view's daily GRVI (raw and white-balanced)."""
    gh, gw = rgb.shape[1:3]
    vf, bf = semantic_fractions(master, gh, gw, use_model)
    R = rois.choose(rgb, valid, times, clear, vf, bf)
    vm = np.where(valid, 1.0, np.nan)
    grvi = np.nanmean((C.grvi(rgb) * vm)[:, R['veg']], 1)
    wb = C.white_balance(rgb, valid, R['ref'], times=times)
    grvi_wb = np.nanmean((C.grvi(wb) * vm)[:, R['veg']], 1)
    gcc_wb = np.nanmean((C.gcc(wb) * vm)[:, R['veg']], 1)
    return R, daily(grvi, times, clear), daily(grvi_wb, times, clear), daily(gcc_wb, times, clear)


def regions_image(master, R, path):
    """Anchor frame with vegetation blocks tinted green and reference blocks tinted orange."""
    from PIL import Image
    H, W = master.shape[:2]
    gh, gw = R['veg'].shape
    bh, bw = H // gh, W // gw
    out = master.astype(np.float32).copy()
    for mask, col in ((R['veg'], (40, 200, 90)), (R['ref'], (255, 110, 40))):
        m = np.kron(mask, np.ones((bh, bw), bool))
        m = np.pad(m, ((0, H - m.shape[0]), (0, W - m.shape[1])))
        out[m] = out[m] * 0.55 + np.array(col) * 0.45
    Image.fromarray(out.clip(0, 255).astype(np.uint8)).save(path)


def measure(blocks_npz, out_prefix=None, use_model=True):
    """Returns (daily DataFrame, regions of the first view, info dict). Columns: grvi (raw), grvi_wb, gcc_wb,
    each per view; `index` is the white-balanced GRVI standardised per view and joined across views, which is
    what to compare across years. With `out_prefix`, also writes the CSV, a regions PNG and a JSON summary."""
    z = np.load(blocks_npz, allow_pickle=True)
    rgb, valid, ec = z['rgb'], z['valid'], z['edge_corr']
    times = pd.to_datetime(z['dates'])
    view = z['view'] if 'view' in z.files else np.zeros(len(times), int)
    masters = z['masters'] if 'masters' in z.files else z['master'][None]
    cols, Rs, info_v, std = {}, [], [], []
    for v in range(len(masters)):
        m = view == v
        if m.sum() < 30:
            continue
        clear = Q.clear_flags(ec[m], times[m])
        R, g, gwb, cwb = view_series(rgb[m], valid[m], times[m], clear, masters[v], use_model)
        for k, s in (('grvi', g), ('grvi_wb', gwb), ('gcc_wb', cwb)):
            if s is not None:
                cols[f'{k}_v{v}'] = s
        std.append(zscore(gwb)); Rs.append(R)
        info_v.append(dict(view=v, frames=int(m.sum()), clear=int(clear.sum()), first=str(times[m].min().date()),
                           last=str(times[m].max().date()), veg_blocks=int(R['veg'].sum()), ref_blocks=int(R['ref'].sum())))
    if not Rs:
        raise ValueError('no view has 30 or more registered frames')
    df = pd.DataFrame(cols)
    idx = combine(std)
    if idx is not None:
        df['index'] = idx
    df.index.name = 'date'
    info = dict(frames=int(len(times)), views=info_v, days=int(df['index'].notna().sum()) if 'index' in df else 0,
                grid=[int(rgb.shape[2]), int(rgb.shape[1])], segmentation=bool(use_model))
    if out_prefix:
        df.round(5).to_csv(f'{out_prefix}_daily.csv')
        regions_image(masters[0], Rs[0], f'{out_prefix}_regions.png')
        json.dump(info, open(f'{out_prefix}_measure.json', 'w'), indent=1)
    return df, Rs[0], info
