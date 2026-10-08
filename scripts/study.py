"""Multi-site study: do ridge and landscape cameras track live fuel moisture?

For every camera/fuel-site pair: registered block colours -> automatic vegetation regions -> daily camera index,
PhenoCam's own hand-drawn region series, MODIS at the camera's view and at the sampling sites, and Globe-LFMC field
samples. Each predictor set is scored leave-one-year-out against the same samples.

    DATA=/path/to/data python scripts/study.py [cam ...]
Writes $DATA/study/<cam>.json and $DATA/study/summary.json
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from fuelgauge import evaluate as E, quality as Q  # noqa: E402
from fuelgauge.measure import daily, zscore, combine, view_series as _view_series  # noqa: E402

warnings.filterwarnings('ignore')
DATA = os.environ.get('DATA', 'data')
OUT = os.path.join(DATA, 'study'); os.makedirs(OUT, exist_ok=True)


def hav(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c); dl = math.radians(d - b); dp = p2 - p1
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def level_change(s, prefix, days=30):
    if s is None:
        return pd.DataFrame()
    return pd.DataFrame({f'{prefix}_g': s, f'{prefix}_d': s - s.shift(days)})


def view_series(rgb, valid, times, clear, master):
    R, g, gwb, _ = _view_series(rgb, valid, times, clear, master)
    return R, g, gwb


def camera_series(cam):
    """Registered block colours -> daily camera index. A camera that was moved to a new spot has more than one
    view; each view gets its own automatic regions and is standardised on its own (a per-era calibration that
    uses camera data only), then the views are joined in time."""
    z = np.load(os.path.join(DATA, 'proc', f'{cam}_blocks.npz'), allow_pickle=True)
    rgb, valid, ec = z['rgb'], z['valid'], z['edge_corr']
    times = pd.to_datetime(z['dates'])
    view = z['view'] if 'view' in z.files else np.zeros(len(times), int)
    masters = z['masters'] if 'masters' in z.files else z['master'][None]
    raw, wb, Rs, info_v = [], [], [], []
    clear_all = np.zeros(len(times), bool)
    for v in range(len(masters)):
        m = view == v
        if m.sum() < 30:
            continue
        clear = Q.clear_flags(ec[m], times[m]); clear_all[np.flatnonzero(m)] = clear
        R, g, gw_ = view_series(rgb[m], valid[m], times[m], clear, masters[v])
        raw.append(zscore(g)); wb.append(zscore(gw_)); Rs.append(R)
        info_v.append(dict(frames=int(m.sum()), clear=int(clear.sum()), first=str(times[m].min().date()), last=str(times[m].max().date()),
                           veg_blocks=int(R['veg'].sum()), ref_blocks=int(R['ref'].sum())))
    gh, gw = rgb.shape[1:3]
    info = dict(frames_registered=int(len(times)), clear=int(clear_all.sum()), veg_blocks=int(Rs[0]['veg'].sum()),
                ref_blocks=int(Rs[0]['ref'].sum()), grid=[int(gw), int(gh)], views=info_v)
    return dict(auto=combine(raw), auto_wb=combine(wb)), Rs[0], info, masters[0]


def curated_series(cam, d0=None, d1=None):
    """PhenoCam's hand-drawn regions: of the camera's curated ROI series, the one with the most days between d0 and
    d1 (the fuel-sample period), as GRVI from its daily mean red and green."""
    fs = sorted(f for f in glob.glob(os.path.join(DATA, 'phenocam_roi', f'{cam}_*_1day.csv')) if 'simplified' not in f and 'ndvi' not in f)
    best = None
    for f in fs:
        d = pd.read_csv(f, comment='#')
        d['date'] = pd.to_datetime(d['date'])
        d = d.dropna(subset=['r_mean', 'g_mean'])
        n = int(((d.date >= (d0 or d.date.min())) & (d.date <= (d1 or d.date.max()))).sum())
        if best is None or n > best[0]:
            best = (n, f, d)
    if best is None or best[0] < 30:
        return None, None
    _, f, d = best
    grvi = (d.g_mean - d.r_mean) / (d.g_mean + d.r_mean)
    return daily(grvi.values, d.date.values, np.ones(len(d), bool)), os.path.basename(f)


def modis_points():
    rows = []
    for l in open(os.path.join(DATA, 'modis_study.jsonl')):
        r = json.loads(l)
        if 'error' in r:
            continue
        for n, v in r['pts'].items():
            rows.append(dict(date=r['date'], site=n, **v))
    m = pd.DataFrame(rows); m['date'] = pd.to_datetime(m['date'])
    m = m.dropna(subset=['b1', 'b2', 'b3', 'b4', 'b6'])
    m = m[m.qa_full >= 0.5]
    m['ndvi'] = (m.b2 - m.b1) / (m.b2 + m.b1); m['ndii'] = (m.b2 - m.b6) / (m.b2 + m.b6)
    m['gcc'] = m.b4 / (m.b1 + m.b3 + m.b4)
    out = {}
    for n, g in m.groupby('site'):
        g = g.drop_duplicates('date').set_index('date').sort_index()[['ndvi', 'ndii', 'gcc']]
        g = g.rolling('17D', min_periods=1).median().resample('D').mean().ffill(limit=16)
        for c in ('ndvi', 'ndii', 'gcc'):
            g[c + '_d'] = g[c] - g[c].shift(32)
        out[n] = g
    return out


def main(cams):
    sel = {r['cam']: r for r in json.load(open(os.path.join(os.path.dirname(__file__), '..', 'study', 'cameras.json')))}
    allcams = json.load(open(os.path.join(DATA, 'raw', 'phenocam_cameras.json')))
    allcams = allcams['results'] if isinstance(allcams, dict) else allcams
    meta = {c['Sitename']: c for c in allcams if isinstance(c, dict)}
    us = pd.read_parquet(os.path.join(DATA, 'globe', 'globe_usa.parquet'))
    sat = modis_points()
    for cam in cams:
        if not os.path.exists(os.path.join(DATA, 'proc', f'{cam}_blocks.npz')):
            print(cam, 'no blocks yet'); continue
        r = sel[cam]; m = meta[cam]
        cs, R, info, master = camera_series(cam)
        xs = us[us['Site name'].isin([s[0] for s in r['good']])]
        cur, cur_file = curated_series(cam, xs.date.min() - pd.Timedelta(days=30), xs.date.max())
        nir = {}
        npath = os.path.join(DATA, 'nir', f'{cam}_series.csv')
        if os.path.exists(npath):
            nd = pd.read_csv(npath, parse_dates=['date']).set_index('date')
            nir = {c: nd[c] for c in ('ndvi_auto', 'ndvi_hand') if c in nd and nd[c].notna().sum() > 30}
        feats = pd.concat([level_change(cs['auto'], 'auto'), level_change(cs['auto_wb'], 'autowb'),
                           level_change(cur, 'hand'), level_change(nir.get('ndvi_auto'), 'nir'),
                           level_change(nir.get('ndvi_hand'), 'nirh')], axis=1)
        sv = sat.get(f'cam:{cam}')
        sites = [s[0] for s in r['good']]
        x = us[us['Site name'].isin(sites)].copy()
        first, last = pd.to_datetime(m['date_first']), min(pd.to_datetime(m['date_last']), pd.Timestamp('2023-06-30'))
        x = x[(x.date >= first) & (x.date <= last) & x.lfmc.between(20, 400)]
        x['unit'] = x['Site name'] + ' | ' + x['Species collected']
        g = x.groupby(['unit', 'Site name', 'Species collected', 'date']).agg(lfmc=('lfmc', 'mean'), lat=('lat', 'first'), lon=('lon', 'first')).reset_index()
        rows = []
        for _, s in g.iterrows():
            d = s.date.normalize()
            rec = dict(site=s.unit, date=d, year=d.year, lfmc=s.lfmc, sample_site=s['Site name'], species=s['Species collected'])
            if d in feats.index:
                rec.update(feats.loc[d].to_dict())
            if sv is not None and d in sv.index:
                rec.update({f'sv_{k}': v for k, v in sv.loc[d].to_dict().items()})
            ss = sat.get(s['Site name'])
            if ss is not None and d in ss.index:
                rec.update({f'ss_{k}': v for k, v in ss.loc[d].to_dict().items()})
            rows.append(rec)
        t = E.add_season(pd.DataFrame(rows))
        # units with too few samples add noise to the site intercepts
        t = t[t.groupby('site').lfmc.transform('size') >= 15]
        sets = {
            'season': E.SEASON,
            'camera_auto': ['auto_g', 'auto_d'] + E.SEASON,
            'camera_auto_wb': ['autowb_g', 'autowb_d'] + E.SEASON,
            'sat_visible_view': ['sv_gcc', 'sv_gcc_d'] + E.SEASON,
            'sat_ir_view': ['sv_ndvi', 'sv_ndii', 'sv_ndvi_d', 'sv_ndii_d'] + E.SEASON,
            'sat_ir_site': ['ss_ndvi', 'ss_ndii', 'ss_ndvi_d', 'ss_ndii_d'] + E.SEASON,
            'camera_plus_sat_ir': ['auto_g', 'auto_d', 'sv_ndvi', 'sv_ndii', 'sv_ndvi_d', 'sv_ndii_d'] + E.SEASON,
        }
        for c in sorted(set(sum(sets.values(), [])) | {'hand_g', 'hand_d', 'nir_g', 'nir_d', 'nirh_g', 'nirh_d'}):
            if c not in t.columns:
                t[c] = np.nan
        # main comparison: every predictor scored on the same samples
        res, preds = E.compare(t, sets, common=True)
        # registration + automatic regions vs PhenoCam's hand-drawn region, on the samples where both exist
        hand_sets = {'season': E.SEASON, 'camera_auto': sets['camera_auto'], 'camera_hand': ['hand_g', 'hand_d'] + E.SEASON}
        hand_res, _ = E.compare(t, hand_sets, common=True) if t.hand_g.notna().any() else ({}, None)
        # near-infrared: camera NDVI on the automatic regions (and on PhenoCam's hand-drawn regions), on the samples
        # where the camera had an IR photo, against the same colour and satellite predictors
        nir_res, nir_preds = ({}, None)
        if t.nir_g.notna().sum() >= 30:
            nir_sets = {'season': E.SEASON, 'camera_auto_wb': sets['camera_auto_wb'], 'camera_ndvi': ['nir_g', 'nir_d'] + E.SEASON,
                        'sat_ir_view': sets['sat_ir_view'], 'sat_ir_site': sets['sat_ir_site'],
                        'camera_ndvi_plus_rgb': ['nir_g', 'nir_d', 'autowb_g', 'autowb_d'] + E.SEASON}
            nir_res, nir_preds = E.compare(t, nir_sets, common=True)
            if t.nirh_g.notna().sum() >= 30:
                hres, _ = E.compare(t, {'season': E.SEASON, 'camera_ndvi': nir_sets['camera_ndvi'],
                                        'camera_ndvi_hand': ['nirh_g', 'nirh_d'] + E.SEASON}, common=True)
                nir_res['hand'] = hres
        # also: camera alone against all samples where the camera had a view (bigger n, not comparable across sets)
        _, auto_only = E.loyo(t, ['auto_g', 'auto_d'] + E.SEASON)
        _, season_same = E.loyo(t.dropna(subset=['auto_g', 'auto_d']), E.SEASON)
        qa = json.load(open(os.path.join(DATA, 'proc', f'{cam}_qa.json')))
        dist = {s[0]: s[1] for s in r['good']}
        out = dict(cam=cam, lat=float(m['Lat']), lon=float(m['Lon']), elev=m.get('Elev'), veg=(m.get('sitemetadata') or {}).get('primary_veg_type'),
                   description=(m.get('sitemetadata') or {}).get('site_description'), orientation=(m.get('sitemetadata') or {}).get('camera_orientation'),
                   first=str(first.date()), last=str(last.date()), sites=[dict(name=k, dist_km=v) for k, v in dist.items()],
                   species=sorted(t.species.unique().tolist()), units=sorted(t.site.unique().tolist()),
                   n_samples_total=int(len(t)), curated_roi=cur_file, info=info,
                   segments=dict(sizes=qa['sizes'], linked=qa['linked']), results=res, hand_vs_auto=hand_res, nir=nir_res,
                   camera_vs_season_all=dict(camera=auto_only, season=season_same))
        json.dump(out, open(os.path.join(OUT, f'{cam}.json'), 'w'), indent=1, default=float)
        pd.concat({k: v for k, v in preds.items()}).to_csv(os.path.join(OUT, f'{cam}_preds.csv'))
        if nir_preds:
            pd.concat({k: v for k, v in nir_preds.items()}).to_csv(os.path.join(OUT, f'{cam}_nir_preds.csv'))
        np.savez_compressed(os.path.join(OUT, f'{cam}_roi.npz'), veg=R['veg'], ref=R['ref'], amp=R['amp'], master=master)
        sm = {k: (round(v['rmse'], 1) if v.get('n') else None) for k, v in res.items()}
        print(cam, 'n', res['season'].get('n'), 'years', res['season'].get('years'), sm, flush=True)


if __name__ == '__main__':
    cams = sys.argv[1:] or [os.path.basename(p)[:-11] for p in glob.glob(os.path.join(DATA, 'proc', '*_blocks.npz')) if '_hero_' not in p]
    main(cams)
