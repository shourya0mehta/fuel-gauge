"""Colour measurements on registered frames.

Indices are computed from block-mean RGB:
    GCC  = G / (R + G + B)              green chromatic coordinate (the PhenoCam standard)
    GRVI = (G - R) / (G + R)            green-red vegetation index; tracks browning of evergreen brush better
A diagonal (von Kries) white balance against stable non-vegetation ground in the same frame removes part of
the camera's colour drift: red and blue are rescaled so the reference blocks keep a constant red/green and
blue/green balance. Given frame times, the reference balance is first smoothed with a trailing two-month median,
so the correction follows the camera (sensor drift, replacement, settings) and not the weather on the reference
ground (snow, rain-darkened soil, shadow).
"""
from __future__ import annotations

import numpy as np


def block_means(img_rgb_f32, cover, block):
    """Mean RGB per block over covered pixels; blocks with <90% coverage are marked invalid."""
    H, W, _ = img_rgb_f32.shape
    gh, gw = H // block, W // block
    w = np.where(cover[..., None], img_rgb_f32, 0)[: gh * block, : gw * block]
    c = cover[: gh * block, : gw * block].astype(np.float32)
    s = w.reshape(gh, block, gw, block, 3).sum(axis=(1, 3))
    n = c.reshape(gh, block, gw, block).sum(axis=(1, 3))
    with np.errstate(invalid='ignore', divide='ignore'):
        mean = s / n[..., None]
    return mean, n > 0.9 * block * block


def gcc(rgb):
    with np.errstate(invalid='ignore', divide='ignore'):
        return rgb[..., 1] / rgb.sum(-1)


def grvi(rgb):
    with np.errstate(invalid='ignore', divide='ignore'):
        return (rgb[..., 1] - rgb[..., 0]) / (rgb[..., 1] + rgb[..., 0])


def white_balance(rgb_blocks, valid, ref_mask, times=None, window='61D'):
    """rgb_blocks (N, gh, gw, 3). Returns blocks with red and blue rescaled so the reference blocks' red/green and
    blue/green ratios stay at their long-run median. With `times`, the per-frame reference ratios are smoothed with
    a trailing median over `window` first (robust to snow or wet ground on the reference blocks)."""
    ref = np.where(valid[..., None], rgb_blocks, np.nan)[:, ref_mask]          # (N, nref, 3)
    with np.errstate(invalid='ignore', divide='ignore'):
        med = np.nanmedian(ref, axis=1)                                         # (N, 3)
        lr = np.log(med[:, 0] / med[:, 1]); lb = np.log(med[:, 2] / med[:, 1])
    if times is not None:
        import pandas as pd
        idx = pd.to_datetime(np.asarray(times))
        df = pd.DataFrame(dict(r=lr, b=lb), index=idx)
        order = np.argsort(idx.values, kind='stable')
        sm = df.iloc[order].rolling(window, min_periods=1).median()
        lr = np.empty_like(lr); lb = np.empty_like(lb)
        lr[order] = sm.r.values; lb[order] = sm.b.values
    lr = lr - np.nanmedian(lr); lb = lb - np.nanmedian(lb)
    gain = np.stack([np.exp(-lr), np.ones_like(lr), np.exp(-lb)], 1)            # (N, 3)
    return rgb_blocks * gain[:, None, None, :]


def smooth_causal(series, p90_window='7D', mean_days=15):
    """Trailing 90th percentile over a week, then a trailing two-week mean. Uses only data up to each day."""
    p90 = series.rolling(p90_window, min_periods=1).quantile(0.9)
    return p90.rolling(f'{mean_days}D', min_periods=1).mean()
