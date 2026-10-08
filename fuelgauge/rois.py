"""Automatic measurement regions on a registered camera.

Vegetation blocks: covered by every camera period, labelled as plants / trees / grass / hillside by the
segmentation model in the master view, in the lower part of the frame, and with a strong seasonal swing in
greenness. Reference blocks (for white balance): covered, not vegetation, little seasonal swing. Blocks of sky
along the horizon can qualify; leaving them out made the correction worse on the 21-camera study (anomaly
correlation 0.13 -> 0.10), since sky colour carries the same daylight and sensor balance as the ground.
No hand-drawn masks.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def seasonal_amplitude(index_blocks, times, good):
    N, gh, gw = index_blocks.shape
    s = pd.DataFrame(index_blocks[good].reshape(int(good.sum()), -1), index=pd.to_datetime(np.asarray(times)[good]))
    sm = s.resample('7D').median().rolling(3, min_periods=1, center=True).median()   # works for daily or thinned archives
    return (sm.quantile(0.95) - sm.quantile(0.05)).values.reshape(gh, gw)


def choose(rgb_blocks, valid, times, good, veg_frac, bad_frac, lower_from=0.45, cover_min=0.85, amp_quantile=0.5):
    """Returns dict(veg, ref, amp). veg_frac / bad_frac: per-block fraction of vegetation / not-ground pixels
    in the master view (from segment.masks)."""
    with np.errstate(invalid='ignore', divide='ignore'):
        g = rgb_blocks[..., 1] / rgb_blocks.sum(-1)
    g = np.where(valid, g, np.nan)
    N, gh, gw = g.shape
    cover = valid.mean(0)
    amp = seasonal_amplitude(g, times, good)
    rows = np.arange(gh)[:, None] * np.ones((1, gw))
    cand = (cover > cover_min) & (veg_frac > 0.6) & (bad_frac < 0.2) & (rows >= gh * lower_from)
    if cand.sum() < 10:                               # small or odd views: relax the semantic filter
        cand = (cover > cover_min) & (bad_frac < 0.4) & (rows >= gh * 0.3)
    thr = np.nanquantile(amp[cand], amp_quantile) if cand.sum() else 0
    veg = cand & (amp >= thr)
    ground = (cover > cover_min) & (rows >= gh * 0.3) & ~veg
    ref = ground & (amp <= np.nanquantile(amp[cover > cover_min], 0.3))
    if ref.sum() < 5:
        ref = ground
    return dict(veg=veg, ref=ref, amp=amp)
