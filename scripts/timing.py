"""Timing study: does the camera see the season turn when the fuel does?

For every camera-year, the camera's brown-down date is when its colour-corrected greenness falls halfway from the
spring peak to the summer low. For every sampling unit (site and species) and year, the fuel's dry-down date is
when field moisture first falls below that unit's long-run median after its spring high. The same half-way rule
gives satellite NDVI and NDII dates on the camera's slope. Dates are compared as departures from each camera's
and unit's own average date, so a late year is late for both or it isn't.

    DATA=/path/to/data python scripts/timing.py
Writes $DATA/study/timing.json
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

DATA = study.DATA


def halfway_date(s: pd.Series, year: int, min_cover=0.6):
    """Day of year when a series first drops halfway from its spring peak (Feb 1 - Jul 15) to the following low."""
    w = s[(s.index >= f'{year}-02-01') & (s.index <= f'{year}-10-31')]
    if len(w) < 100 or w.notna().mean() < min_cover:
        return None
    w = w.interpolate(limit=20)
    spring = w[: f'{year}-07-15']
    if spring.dropna().empty:
        return None
    tp = spring.idxmax(); peak = spring.max()
    after = w[tp:]
    lo = after.min()
    if not np.isfinite(lo) or peak - lo <= 0:
        return None
    below = after[after < (peak + lo) / 2]
    if below.empty:
        return None
    return int(below.index[0].dayofyear)


def drydown_date(g: pd.DataFrame, thr: float):
    """Day of year when sampled moisture first crosses below `thr` after the year's spring high (interpolated)."""
    g = g.sort_values('date')
    spring = g[(g.date.dt.month >= 3) & (g.date.dt.month <= 7)]
    if len(g[(g.date.dt.month >= 4) & (g.date.dt.month <= 9)]) < 4 or spring.empty:
        return None
    i0 = spring.lfmc.idxmax()
    after = g.loc[i0:]
    if after.lfmc.iloc[0] < thr:
        return None
    prev = None
    for _, r in after.iterrows():
        if r.lfmc < thr and prev is not None:
            f = (prev.lfmc - thr) / (prev.lfmc - r.lfmc)
            d = prev.date + (r.date - prev.date) * f
            return int(d.dayofyear) if (r.date - prev.date).days <= 45 else None
        prev = r
    return None


def main():
    sel = {r['cam']: r for r in json.load(open(os.path.join(os.path.dirname(__file__), '..', 'study', 'cameras.json')))}
    us = pd.read_parquet(os.path.join(DATA, 'globe', 'globe_usa.parquet'))
    sat = study.modis_points()
    rows = []
    cams = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(DATA, 'study', '*.json')) if not p.endswith(('timing.json', 'summary.json')))
    for cam in cams:
        j = json.load(open(os.path.join(DATA, 'study', f'{cam}.json')))
        r0 = j.get('results', {}).get('season', {})
        if not r0.get('n') or r0['n'] < 40 or r0['years'] < 4:      # same rule as the site
            continue
        cs, R, info, master = study.camera_series(cam)
        s = cs['auto_wb']
        if s is None:
            continue
        sv = sat.get(f'cam:{cam}')
        units = set(j['units'])
        x = us[us['Site name'].isin([u['name'] for u in j['sites']])].copy()
        x['unit'] = x['Site name'] + ' | ' + x['Species collected']
        x = x[x.unit.isin(units) & x.lfmc.between(20, 400)]
        x = x.groupby(['unit', 'date']).lfmc.mean().reset_index()
        for unit, g in x.groupby('unit'):
            thr = float(g.lfmc.median())
            for y, gy in g.groupby(g.date.dt.year):
                fd = drydown_date(gy, thr)
                if fd is None:
                    continue
                cd = halfway_date(s, y)
                nd = halfway_date(sv['ndvi'], y, 0.5) if sv is not None else None
                wd = halfway_date(sv['ndii'], y, 0.5) if sv is not None else None
                rows.append(dict(cam=cam, unit=unit, year=int(y), fuel=fd, camera=cd, ndvi=nd, ndii=wd))
    t = pd.DataFrame(rows)
    out = dict(n_pairs=int(len(t)), per_cam={}, pooled={})
    for k in ('camera', 'ndvi', 'ndii'):
        d = t.dropna(subset=[k, 'fuel']).copy()
        if len(d) < 8:
            continue
        # departures from each unit's average dry-down date and each camera's average turn date
        d['fa'] = d.fuel - d.groupby('unit').fuel.transform('mean')
        d['ka'] = d[k] - d.groupby('unit')[k].transform('mean')
        r = float(np.corrcoef(d.fa, d.ka)[0, 1])
        slope = float(np.polyfit(d.ka, d.fa, 1)[0])
        out['pooled'][k] = dict(n=int(len(d)), cams=int(d.cam.nunique()), years=int(d.drop_duplicates(['cam', 'year']).shape[0]),
                                r=round(r, 3), slope=round(slope, 3), fuel_sd_days=round(float(d.fa.std()), 1),
                                resid_sd_days=round(float((d.fa - slope * d.ka).std()), 1))
    for cam, d in t.groupby('cam'):
        d = d.dropna(subset=['camera', 'fuel'])
        if len(d) >= 5:
            fa = d.fuel - d.groupby('unit').fuel.transform('mean'); ka = d.camera - d.groupby('unit').camera.transform('mean')
            out['per_cam'][cam] = dict(n=int(len(d)), r=round(float(np.corrcoef(fa, ka)[0, 1]), 3) if ka.std() > 0 else None)
    t.to_csv(os.path.join(DATA, 'study', 'timing_pairs.csv'), index=False)
    json.dump(out, open(os.path.join(DATA, 'study', 'timing.json'), 'w'), indent=1)
    print(json.dumps(out['pooled'], indent=1)); print(out['per_cam'])


if __name__ == '__main__':
    main()
