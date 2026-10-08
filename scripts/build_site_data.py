"""Build the data and images behind the project site (docs/).

    DATA=/path/to/data python scripts/build_site_data.py

Reads $DATA/study/<cam>.json (from scripts/study.py) and writes
    docs/data/study.json          one record per camera + pooled results + western-states basemap
    docs/data/cam/<cam>.json      colour calendar, field samples with held-out estimates, measured blocks
    docs/assets/study/<cam>.jpg   the master view each camera was registered onto
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from fuelgauge import colour as C, quality as Q  # noqa: E402

DATA = os.environ.get('DATA', 'data')
REPO = os.path.join(os.path.dirname(__file__), '..')
DOCS = os.path.join(REPO, 'docs')
STATES = os.environ.get('STATES_GEOJSON')          # us-atlas states-10m converted to GeoJSON
os.makedirs(os.path.join(DOCS, 'data', 'cam'), exist_ok=True)
os.makedirs(os.path.join(DOCS, 'assets', 'study'), exist_ok=True)

SETS = [  # key, label, colour role
    ('season', 'Season alone (an average year)', 'straw'),
    ('camera_auto', 'Camera', 'cam'),
    ('camera_auto_wb', 'Camera, colour-corrected', 'cam'),
    ('sat_visible_view', 'Satellite visible colour, same slope', 'sat'),
    ('sat_ir_view', 'Satellite infrared, same slope', 'sat'),
    ('sat_ir_site', 'Satellite infrared, at the sampling site', 'sat'),
    ('camera_plus_sat_ir', 'Camera + satellite infrared', 'both'),
]
WEST = ['Washington', 'Oregon', 'California', 'Nevada', 'Idaho', 'Montana', 'Wyoming', 'Utah', 'Colorado', 'Arizona', 'New Mexico']
MIN_N, MIN_YEARS = 40, 4      # a camera enters the pooled results with at least this many common samples and years
SHORT = {'jasperridge': 'Jasper Ridge', 'cucamongasouth': 'San Bernardino NF', 'turtleback': 'Turtleback Dome',
         'sangabriel': 'Josephine Peak', 'ahwahnee': 'Ahwahnee Meadow', 'kaweah': 'Kaweah', 'sequoia': 'Lower Kaweah',
         'forbes': 'Sierra Foothill REC', 'grandteton': 'Grand Teton', 'glacier': 'West Glacier', 'mayberry': 'Mayberry Slough',
         'vaira': 'Vaira Ranch', 'farewellgap': 'Farewell Gap', 'nationalelkrefuge': 'National Elk Refuge', 'niwot2': 'Niwot Ridge',
         'tonzi': 'Tonzi Ranch', 'oregonYP': 'Metolius young pine', 'oregonMP': 'Metolius mature pine',
         'segalittlemountain': 'Little Mountain', 'segabradshaw': 'Bradshaw Ranch', 'NEON.D13.NIWO.DP1.00042': 'Niwot Ridge (NEON)',
         'bridger': 'Bridger Wilderness', 'sagehen': 'Sagehen Creek'}
B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
VEG = {'EN': 'conifer forest', 'SH': 'shrubland', 'GR': 'grassland', 'DB': 'oak woodland', 'WL': 'woodland', 'TN': 'alpine tundra', None: 'mixed'}


# ---------------- projection (Albers equal-area conic for the western US) ----------------
def albers(lon, lat, lon0=-112.0, lat0=40.0, p1=33.0, p2=45.0):
    r = math.radians
    n = (math.sin(r(p1)) + math.sin(r(p2))) / 2
    c = math.cos(r(p1)) ** 2 + 2 * n * math.sin(r(p1))
    rho0 = math.sqrt(c - 2 * n * math.sin(r(lat0))) / n
    rho = math.sqrt(c - 2 * n * math.sin(r(lat))) / n
    th = n * r(lon - lon0)
    return rho * math.sin(th), rho0 - rho * math.cos(th)


def basemap(width=1000):
    if not STATES or not os.path.exists(STATES):
        return None
    g = json.load(open(STATES))
    rings, rings_ll = [], []
    for f in g['features']:
        if f['properties']['name'] not in WEST:
            continue
        geom = f['geometry']
        polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
        for poly in polys:
            for ring in poly[:1]:
                rings.append((f['properties']['name'], [albers(lo, la) for lo, la in ring]))
                rings_ll.append((f['properties']['name'], [(lo, la) for lo, la in ring]))
    xs = [x for _, r in rings for x, _ in r]; ys = [y for _, r in rings for _, y in r]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    s = width / (x1 - x0); height = (y1 - y0) * s

    def P(lon, lat):
        x, y = albers(lon, lat)
        return round((x - x0) * s, 1), round((y1 - y) * s, 1)

    def inside(lon, lat):
        for name, ring_ll in rings_ll:
            n = len(ring_ll); c = False; j = n - 1
            for i in range(n):
                xi, yi = ring_ll[i]; xj, yj = ring_ll[j]
                if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                    c = not c
                j = i
            if c:
                return name
        return None

    labels = {}
    for name, ring in rings:
        pts = [((x - x0) * s, (y1 - y) * s) for x, y in ring]
        if name not in labels or len(pts) > labels[name][2]:
            labels[name] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), len(pts))
    paths = {}
    for name, ring in rings:
        pts = [((x - x0) * s, (y1 - y) * s) for x, y in ring]
        keep = [pts[0]]
        for p in pts[1:]:
            if abs(p[0] - keep[-1][0]) + abs(p[1] - keep[-1][1]) > 1.2:
                keep.append(p)
        d = 'M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in keep) + 'Z'
        paths[name] = paths.get(name, '') + d
    return (dict(w=width, h=round(height, 1), states=[dict(name=k, d=v) for k, v in paths.items()],
                 labels=[dict(name=k, x=round(v[0], 1), y=round(v[1], 1)) for k, v in labels.items()]), P, inside)


# ---------------- per-camera exports ----------------
def calendar(cam, R):
    """Years x day-of-year grid of colour-corrected camera greenness on the measured blocks, one character per day
    (64 levels, base64url alphabet; '.' = no clear view)."""
    z = np.load(os.path.join(DATA, 'proc', f'{cam}_blocks.npz'), allow_pickle=True)
    rgb, valid, ec = z['rgb'], z['valid'], z['edge_corr']
    times = pd.to_datetime(z['dates'])
    clear = Q.clear_flags(ec, times)
    vm = np.where(valid, 1.0, np.nan)
    wb = C.white_balance(rgb, valid, R['ref'], times=times)
    g = np.nanmean((C.grvi(wb) * vm)[:, R['veg']], 1)
    s = pd.Series(g, index=times.normalize())[clear]
    s = s[~s.index.duplicated(keep='last')].dropna()
    s = s.resample('D').median().rolling(9, center=True, min_periods=2).median()
    lo, hi = np.nanquantile(s, 0.02), np.nanquantile(s, 0.98)
    years = list(range(s.index.year.min(), s.index.year.max() + 1))
    grid = np.full((len(years), 366), -128, np.int16)
    for d, v in s.dropna().items():
        grid[d.year - years[0], d.dayofyear - 1] = int(round(np.clip((v - lo) / (hi - lo), 0, 1) * 63))
    rows = [''.join(B64[v] if v >= 0 else '.' for v in r) for r in grid]
    return dict(years=years, rows=rows, lo=round(float(lo), 4), hi=round(float(hi), 4))


def master_jpg(cam, master):
    import cv2
    h, w = master.shape[:2]
    sc = 960 / w
    im = cv2.resize(master, (960, int(round(h * sc))), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(DOCS, 'assets', 'study', f'{cam}.jpg'), im[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 80])
    return f'assets/study/{cam}.jpg', [960, int(round(h * sc))]


def samples(cam):
    p = pd.read_csv(os.path.join(DATA, 'study', f'{cam}_preds.csv'), parse_dates=['date'])
    p = p.rename(columns={p.columns[0]: 'set'})
    keep = {'season': 'k', 'camera_auto_wb': 'c', 'sat_ir_view': 's'}
    p = p[p.set.isin(keep)]
    w = p.pivot_table(index=['site', 'date'], columns='set', values='pred').reset_index()
    obs = p.drop_duplicates(['site', 'date']).set_index(['site', 'date']).lfmc
    w['o'] = obs.reindex(pd.MultiIndex.from_frame(w[['site', 'date']])).values
    units = sorted(w.site.unique(), key=lambda u: -int((w.site == u).sum()))
    out = []
    for _, r in w.sort_values('date').iterrows():
        rec = dict(u=units.index(r.site), d=r.date.strftime('%Y-%m-%d'), o=round(float(r.o), 1))
        for k, short in keep.items():
            if k in r and pd.notna(r[k]):
                rec[short] = round(float(r[k]), 1)
        out.append(rec)
    return units, out


def pct_change(a, b):
    """Relative change from a to b, as a phrase."""
    d = (b - a) / a * 100
    if abs(d) < 0.5:
        return 'the same error as'
    return f"{abs(d):.0f}% {'less' if d < 0 else 'more'} error than"


def narrative(out, summ, timing):
    """Site text built from the numbers, so words and results always ship together."""
    T, P = out['totals'], out['pooled']
    sp = summ['pooled']; s0 = sp['season']['rmse']
    cam, raw, sat, sats = sp['camera_auto_wb'], sp['camera_auto'], sp['sat_ir_view'], sp['sat_ir_site']
    hv = P['hand_vs_auto']
    text = {}
    text['answer'] = (f"<b>Short answer: not from colour alone, not yet.</b> Across {T['cams']} cameras and "
                      f"{summ['n_samples']:,} field samples, a camera's colour follows the seasons closely but tells you "
                      f"little about whether this year's brush is drier than usual. Below is the evidence and the code, "
                      f"with a live camera network that keeps the test running.")
    text['findings'] = [
        ['--cam', 'Cameras',
         f"A colour-corrected camera beats the calendar at {cam['cams_better']} of {cam['cams']} cameras. Pooled over all "
         f"{summ['n_samples']:,} held-out samples it has {pct_change(s0, cam['rmse'])} season alone, and its anomaly correlation "
         f"is {cam['anomaly_r']:.2f}: it sees a little of what makes each year different, but only a little."],
        ['--sat', 'Satellites',
         f"Satellite infrared looking at the same slope reaches an anomaly correlation of {sat['anomaly_r']:.2f}, and "
         f"{sats['anomaly_r']:.2f} at the sampling site itself, where it has {pct_change(s0, sats['rmse'])} season alone. "
         f"Even the best optical signal here leaves most of each year's swing unexplained."],
        ['--straw', 'What holds cameras back',
         f"Colour stability comes first. Uncorrected, the camera knows almost nothing beyond the season (anomaly correlation "
         f"{raw['anomaly_r']:.2f}). Correcting each photo against rock and soil in the same frame lifts it to "
         f"{cam['anomaly_r']:.2f}, about half of what satellite infrared gets on the same slope."],
    ]
    text['study'] = (
        f"<p>I searched the PhenoCam Network, an archive of daily photos from fixed research cameras, for every camera with "
        f"field measurements of live fuel moisture from the Globe-LFMC database within 25 km. {T['cams']} cameras had enough "
        f"overlapping samples to test, from chaparral in Southern California to sagebrush in Wyoming and pine in Oregon and "
        f"Montana. For each one, every daily photo was registered onto one view, the brush was found automatically, and its "
        f"colour became a daily index.</p>"
        f"<p>Each predictor is scored the same way. A model that already knows each sampling site's normal seasonal cycle is "
        f"fit on all years but one, then asked to predict the samples in the missing year. Beating \"season alone\" means "
        f"knowing something about this year that the calendar doesn't.</p>")
    text['pooled_note'] = (
        "Change in error is the median over cameras of the change in root-mean-square error against season alone, on "
        "held-out years; negative is better. Anomaly r is the median correlation between how unusual each sample was "
        "(measured minus the seasonal baseline) and how unusual the predictor said it would be; 0 means no skill beyond "
        "the calendar. Each camera's predictors are scored on the same samples. Several cameras share sampling sites, "
        f"so they are not fully independent tests. {len(out['skipped'])} more cameras were processed but had too few "
        "samples overlapping clear photos to score.")
    hard = {}
    hard['reg_stat'] = f"{T['frames'] / max(T['frames_ok'], 1) * 100:.0f}%"
    hard['reg_text'] = (
        f"of the {T['frames_ok']:,} usable photos were mapped onto a fixed view (of {T['frames_total']:,} downloaded). "
        f"Of the {T['cams']} cameras, {T['moved']} were moved to a new spot during their record and kept those years as a "
        f"second view, and {T['in_place']} open-grass close-ups had nothing stable to lock onto and were measured in place. "
        f"Below: the San Bernardino camera, tracked through 15 years and every bump.")
    if hv['cams']:
        hard['roi_stat'] = f"{hv['auto_better']} of {hv['cams']}"
        hard['roi_text'] = (
            f"cameras where automatic regions on registered photos beat PhenoCam's own hand-drawn regions (median anomaly "
            f"correlation {hv['median_auto_anom']:.2f} against {hv['median_hand_anom']:.2f}). Hand-drawn regions are fixed in "
            f"the image between redraws, so small drifts move them off the brush.")
    hard['wb_stat'] = f"{raw['anomaly_r']:.2f} → {cam['anomaly_r']:.2f}"
    hard['wb_text'] = (
        "anomaly correlation before and after colour correction, pooled over every sample. Cameras get swapped, settings "
        "change and sensors age. Dividing out the colour of rock and soil in the same frame, smoothed over two months so "
        "snow and rain don't count, is what moves the camera off zero.")
    if timing and 'camera' in timing:
        tc, tn = timing['camera'], timing.get('ndvi', {})
        text['timing'] = (
            f"Timing doesn't rescue it. Over {tc['years']} camera-years, the date the camera saw the brush turn brown barely "
            f"tracks the date fuel moisture fell below its usual level (correlation {tc['r']:.2f}), and satellite greenness "
            f"on the same slope does no better ({tn.get('r', float('nan')):.2f}).")
    return text, hard


def main():
    bm = basemap()
    proj = bm[1] if bm else (lambda lo, la: (lo, la))
    state_of = bm[2] if bm else (lambda lo, la: None)
    meta = json.load(open(os.path.join(DATA, 'raw', 'phenocam_cameras.json')))
    meta = meta['results'] if isinstance(meta, dict) else meta
    meta = {c['Sitename']: c for c in meta if isinstance(c, dict)}
    us = pd.read_parquet(os.path.join(DATA, 'globe', 'globe_usa.parquet'))
    cams, skipped = [], []
    for f in sorted(glob.glob(os.path.join(DATA, 'study', '*.json'))):
        if os.path.basename(f) in ('summary.json', 'timing.json'):
            continue
        j = json.load(open(f))
        r0 = j.get('results', {}).get('season', {})
        if not r0.get('n') or r0['n'] < MIN_N or r0['years'] < MIN_YEARS:
            skipped.append(dict(cam=j['cam'], n=r0.get('n', 0), years=r0.get('years', 0)))
            continue
        cam = j['cam']
        z = np.load(os.path.join(DATA, 'study', f'{cam}_roi.npz'))
        R = dict(veg=z['veg'], ref=z['ref'])
        img, size = master_jpg(cam, z['master'])
        units, smp = samples(cam)
        cal = calendar(cam, R)
        gh, gw = R['veg'].shape
        site_ll = {}
        for s in j['sites']:
            x = us[us['Site name'] == s['name']].iloc[0]
            site_ll[s['name']] = (float(x.lat), float(x.lon))
        detail = dict(cam=cam, img=img, size=size, grid=[gw, gh],
                      veg=''.join('1' if v else '0' for v in R['veg'].ravel()),
                      ref=''.join('1' if v else '0' for v in R['ref'].ravel()),
                      units=units, samples=smp, calendar=cal)
        json.dump(detail, open(os.path.join(DOCS, 'data', 'cam', f'{cam}.json'), 'w'), separators=(',', ':'))
        res = j['results']; base = res['season']['rmse']
        qa = json.load(open(os.path.join(DATA, 'proc', f'{cam}_qa.json')))
        m = meta.get(cam, {}); sm = m.get('sitemetadata') or {}
        x, y = proj(j['lon'], j['lat'])
        cams.append(dict(
            cam=cam, name=j.get('description') or cam, short=SHORT.get(cam), lat=j['lat'], lon=j['lon'], x=x, y=y, elev=j.get('elev'),
            veg=VEG.get(j.get('veg'), 'mixed'), facing=j.get('orientation'),
            years=([min(v['first'] for v in j['info']['views'])[:4], max(v['last'] for v in j['info']['views'])[:4]]
                   if j['info'].get('views') else [j['first'][:4], j['last'][:4]]),
            n=res['season']['n'], n_years=res['season']['years'],
            species=j['species'], n_units=len(j['units']),
            sites=[dict(name=s['name'], km=round(s['dist_km'], 1), xy=proj(site_ll[s['name']][1], site_ll[s['name']][0])) for s in j['sites']],
            state=state_of(j['lon'], j['lat']),
            frames=j['info']['frames_registered'], frames_total=len(qa['recs']), frames_ok=int(sum(r['ok'] for r in qa['recs'])),
            views=len(j['info'].get('views') or [1]), mode=qa.get('mode', 'registered'), clear=j['info']['clear'], segments=len(j['segments']['sizes']),
            linked=len(j['segments']['linked']),
            res={k: dict(rmse=round(v['rmse'], 2), skill=round(1 - v['rmse'] / base, 4), anom=round(v['anomaly_r'], 3),
                         r2=round(v['r2'], 3), beat=v['years_beat_season'], years=v['years'], below80=round(v['below80'], 3))
                 for k, v in res.items() if v.get('n')},
            hand={k: dict(rmse=round(v['rmse'], 2), anom=round(v['anomaly_r'], 3), n=v['n'])
                  for k, v in (j.get('hand_vs_auto') or {}).items() if v.get('n')},
            credit=sm.get('site_acknowledgements'), group=sm.get('group')))
    pooled = {}
    for k, label, role in SETS:
        sk = [c['res'][k]['skill'] for c in cams if k in c['res']]
        an = [c['res'][k]['anom'] for c in cams if k in c['res']]
        pooled[k] = dict(label=label, role=role, cams=len(sk), better=int(sum(s > 0 for s in sk)),
                         median_skill=round(float(np.median(sk)), 4) if sk else None,
                         median_anom=round(float(np.median(an)), 3) if an else None)
    hv = [c for c in cams if 'camera_hand' in c['hand'] and 'camera_auto' in c['hand']]
    pooled['hand_vs_auto'] = dict(cams=len(hv), auto_better=int(sum(c['hand']['camera_auto']['rmse'] < c['hand']['camera_hand']['rmse'] for c in hv)),
                                  median_auto_anom=round(float(np.median([c['hand']['camera_auto']['anom'] for c in hv])), 3) if hv else None,
                                  median_hand_anom=round(float(np.median([c['hand']['camera_hand']['anom'] for c in hv])), 3) if hv else None)
    both = [c for c in cams if 'camera_auto' in c['res'] and 'camera_auto_wb' in c['res']]
    pooled['wb_helps'] = f"{sum(c['res']['camera_auto_wb']['rmse'] < c['res']['camera_auto']['rmse'] for c in both)} of {len(both)}"
    y0 = min(int(c['years'][0]) for c in cams); y1 = max(int(c['years'][1]) for c in cams)
    out = dict(sets=[dict(key=k, label=l, role=r) for k, l, r in SETS], cams=cams, pooled=pooled, skipped=skipped,
               totals=dict(cams=len(cams), samples=int(sum(c['n'] for c in cams)), frames=int(sum(c['frames'] for c in cams)),
                           frames_total=int(sum(c['frames_total'] for c in cams)), frames_ok=int(sum(c['frames_ok'] for c in cams)),
                           states=len({c['state'] for c in cams if c['state']}), years_span=f'{y0}–{str(y1)[2:]}',
                           moved=int(sum(c['views'] > 1 for c in cams)), in_place=int(sum(c['mode'] == 'in_place' for c in cams)),
                           species=len({s for c in cams for s in c['species']}),
                           sites=len({s['name'] for c in cams for s in c['sites']})),
               map=bm[0] if bm else None)
    sp = os.path.join(DATA, 'study', 'summary.json'); tp = os.path.join(DATA, 'study', 'timing.json')
    if os.path.exists(sp):
        out['text'], out['hard'] = narrative(out, json.load(open(sp)), json.load(open(tp))['pooled'] if os.path.exists(tp) else None)
        out['summary'] = {k: v for k, v in json.load(open(sp)).items() if k != 'per_unit'}
    json.dump(out, open(os.path.join(DOCS, 'data', 'study.json'), 'w'), separators=(',', ':'))
    print(len(cams), 'cameras;', json.dumps(pooled, indent=1))


if __name__ == '__main__':
    main()
