"""Cheap frame screening (night, glare, blank, blur) and a haze score after registration."""
from __future__ import annotations

import numpy as np


def screen(img_bgr, work=(512, 384)) -> dict:
    """Global checks on a frame. Returns metrics plus `ok` and a `clarity` score used to pick keyframes."""
    import cv2
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(img_bgr, work)
    H = work[1]
    lower = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)[int(H * 0.45):]
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    m = dict(mean=float(g.mean()), lap=float(cv2.Laplacian(lower, cv2.CV_64F).var()), std=float(lower.std()),
             sat=float((g > 250).mean()), sky_sat=float(hsv[: int(H * 0.25), :, 1].mean()),
             ground_sat=float(hsv[int(H * 0.55):, :, 1].mean()))
    m['ok'] = bool(40 < m['mean'] < 225 and m['lap'] > 40 and m['std'] > 20 and m['sat'] < 0.2)
    m['clarity'] = m['lap'] / 500 + m['sky_sat'] / 100 + m['ground_sat'] / 80
    return m


def edge_map(img_bgr):
    import cv2
    g = cv2.GaussianBlur(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32), (5, 5), 0)
    return cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))


def edge_agreement(warped_bgr, master_edges, cover, lower_from=0.4) -> float:
    """Correlation of edge strength with the master view over the lower frame. Fog and haze wash out edges."""
    H = warped_bgr.shape[0]
    e = edge_map(warped_bgr)
    sl = slice(int(H * lower_from), H)
    a, b = e[sl][cover[sl]], master_edges[sl][cover[sl]]
    return float(np.corrcoef(a, b)[0, 1]) if a.size > 1000 else 0.0


def clear_flags(edge_corr, times, window='90D', q=0.8, frac=0.8):
    """Clear if edge agreement is at least `frac` of its recent 80th percentile. Relative to the recent norm,
    so a camera re-aim (which changes how well edges match the master) does not read as months of fog."""
    import pandas as pd
    s = pd.Series(np.asarray(edge_corr, float), index=pd.to_datetime(times))
    ref = s.rolling(window, min_periods=5).quantile(q)
    return (s >= frac * ref).values
