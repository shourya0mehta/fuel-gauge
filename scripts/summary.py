"""Pool the per-camera results: skill by ecosystem, by distance to the sampling site, and across all samples.

    DATA=/path/to/data python scripts/summary.py
Writes $DATA/study/summary.json
"""
from __future__ import annotations

import glob
import json
import math
import os

import numpy as np
import pandas as pd

DATA = os.environ.get('DATA', 'data')
SETS = ['season', 'camera_auto', 'camera_auto_wb', 'sat_visible_view', 'sat_ir_view', 'sat_ir_site', 'camera_plus_sat_ir']


def anomaly_r(d, col):
    a = d.lfmc - d.clim; b = d[col] - d.clim
    return float(np.corrcoef(a, b)[0, 1]) if b.std() > 1e-9 and a.std() > 1e-9 else 0.0


def main():
    rows, cams = [], {}
    for f in sorted(glob.glob(os.path.join(DATA, 'study', '*.json'))):
        name = os.path.basename(f)[:-5]
        if name in ('summary', 'timing'):
            continue
        j = json.load(open(f))
        r0 = j.get('results', {}).get('season', {})
        if not r0.get('n') or r0['n'] < 40 or r0['years'] < 4:      # same rule as the site
            continue
        cams[name] = j
        p = pd.read_csv(os.path.join(DATA, 'study', f'{name}_preds.csv'), parse_dates=['date'])
        p = p.rename(columns={p.columns[0]: 'set'})
        w = p.pivot_table(index=['site', 'date'], columns='set', values='pred').reset_index()
        base = p[p.set == 'season'][['site', 'date', 'lfmc', 'clim']]
        w = w.merge(base, on=['site', 'date'])
        w['cam'] = name; w['veg'] = j.get('veg')
        dist = {s['name']: s['dist_km'] for s in j['sites']}
        w['dist_km'] = w.site.str.split(' | ', regex=False).str[0].map(dist)
        rows.append(w)
    t = pd.concat(rows, ignore_index=True)
    out = dict(n_cams=len(cams), n_samples=int(len(t)), pooled={}, by_veg={}, by_distance={}, per_unit=[])
    # pooled over every held-out sample (cameras weighted by their sample counts)
    for k in SETS:
        e = t[k] - t.lfmc
        out['pooled'][k] = dict(rmse=round(float(np.sqrt((e ** 2).mean())), 2), anomaly_r=round(anomaly_r(t, k), 3))
    # by ecosystem of the camera
    for v, d in t.groupby('veg'):
        out['by_veg'][v] = dict(cams=int(d.cam.nunique()), n=int(len(d)),
                                **{k: dict(rmse=round(float(np.sqrt(((d[k] - d.lfmc) ** 2).mean())), 2), anomaly_r=round(anomaly_r(d, k), 3)) for k in SETS})
    # by distance from camera to sampling site
    bins = [0, 10, 15, 20, 26]
    t['dbin'] = pd.cut(t.dist_km, bins, right=False)
    for b, d in t.groupby('dbin', observed=True):
        out['by_distance'][f'{int(b.left)}-{int(b.right)} km'] = dict(
            n=int(len(d)), units=int(d.groupby(['cam', 'site']).ngroups),
            **{k: dict(rmse=round(float(np.sqrt(((d[k] - d.lfmc) ** 2).mean())), 2), anomaly_r=round(anomaly_r(d, k), 3)) for k in SETS})
    # per sampling unit: does the camera's skill fall with distance?
    for (cam, site), d in t.groupby(['cam', 'site']):
        if len(d) < 15:
            continue
        rs = float(np.sqrt(((d.season - d.lfmc) ** 2).mean()))
        out['per_unit'].append(dict(cam=cam, unit=site, dist_km=float(d.dist_km.iloc[0]), n=int(len(d)),
                                    cam_skill=round(1 - float(np.sqrt(((d.camera_auto_wb - d.lfmc) ** 2).mean())) / rs, 4),
                                    sat_skill=round(1 - float(np.sqrt(((d.sat_ir_view - d.lfmc) ** 2).mean())) / rs, 4),
                                    cam_anom=round(anomaly_r(d, 'camera_auto_wb'), 3), sat_anom=round(anomaly_r(d, 'sat_ir_view'), 3)))
    pu = pd.DataFrame(out['per_unit'])
    if len(pu) > 5:
        from scipy.stats import spearmanr
        out['distance_trend'] = dict(units=int(len(pu)),
                                     cam_skill_vs_km=round(float(spearmanr(pu.dist_km, pu.cam_skill).correlation), 3),
                                     sat_skill_vs_km=round(float(spearmanr(pu.dist_km, pu.sat_skill).correlation), 3),
                                     cam_anom_vs_km=round(float(spearmanr(pu.dist_km, pu.cam_anom).correlation), 3))
    # sign test across cameras: is the colour-corrected camera better than season more often than chance?
    from scipy.stats import binomtest
    for k in SETS[1:]:
        wins = sum(c['results'][k]['rmse'] < c['results']['season']['rmse'] for c in cams.values() if c['results'].get(k, {}).get('n'))
        n = sum(1 for c in cams.values() if c['results'].get(k, {}).get('n'))
        out['pooled'][k]['cams_better'] = int(wins); out['pooled'][k]['cams'] = int(n)
        out['pooled'][k]['sign_test_p'] = round(float(binomtest(wins, n, 0.5, alternative='greater').pvalue), 4) if n else None
    # near-infrared comparison, pooled over the cameras with IR photos
    nrows = []
    for name in cams:
        f = os.path.join(DATA, 'study', f'{name}_nir_preds.csv')
        if not os.path.exists(f):
            continue
        p = pd.read_csv(f, parse_dates=['date']); p = p.rename(columns={p.columns[0]: 'set'})
        w = p.pivot_table(index=['site', 'date'], columns='set', values='pred').reset_index()
        w = w.merge(p[p.set == 'season'][['site', 'date', 'lfmc', 'clim']], on=['site', 'date']); w['cam'] = name
        nrows.append(w)
    if nrows:
        nt = pd.concat(nrows, ignore_index=True)
        NS = ['season', 'camera_auto_wb', 'camera_ndvi', 'sat_ir_view', 'sat_ir_site', 'camera_ndvi_plus_rgb']
        out['nir'] = dict(cams=int(nt.cam.nunique()), n=int(len(nt)), pooled={
            k: dict(rmse=round(float(np.sqrt(((nt[k] - nt.lfmc) ** 2).mean())), 2), anomaly_r=round(anomaly_r(nt, k), 3),
                    cams_better=int(sum(cams[c]['nir'][k]['rmse'] < cams[c]['nir']['season']['rmse'] for c in nt.cam.unique())))
            for k in NS})
        hs = [cams[c]['nir']['hand'] for c in nt.cam.unique() if cams[c]['nir'].get('hand', {}).get('season', {}).get('n')]
        out['nir']['hand_better'] = int(sum(h['camera_ndvi']['rmse'] < h['camera_ndvi_hand']['rmse'] for h in hs)); out['nir']['hand_cams'] = len(hs)
    tm = os.path.join(DATA, 'study', 'timing.json')
    if os.path.exists(tm):
        out['timing'] = json.load(open(tm))['pooled']
    json.dump(out, open(os.path.join(DATA, 'study', 'summary.json'), 'w'), indent=1)
    print(json.dumps({k: out[k] for k in ('n_cams', 'n_samples', 'pooled', 'distance_trend', 'nir') if k in out}, indent=1))


if __name__ == '__main__':
    main()
