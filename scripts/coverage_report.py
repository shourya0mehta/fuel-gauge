"""Statistics, blind spots and map images from the statewide camera viewsheds (run after scripts/coverage.py).

    DATA=data python scripts/coverage_report.py
Writes $DATA/coverage/coverage.json, docs/data/coverage.json and docs/assets/coverage/*.png
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from coverage import DATA, OUT, RES, W, N, NX, NY, WILD, MAST, R_FAR, sees_point  # noqa: E402

REPO = os.path.join(os.path.dirname(__file__), '..')
DOCS = os.path.join(REPO, 'docs')
YEARS = (2020, 2025)
REGIONS = [('Klamath Mountains', 41.3, -123.3), ('Trinity Alps', 40.9, -123.0), ('Yosemite high country', 37.9, -119.4),
           ('Modoc Plateau', 41.3, -120.6), ('Diablo Range', 36.3, -120.7), ('Kern Plateau', 35.9, -118.1),
           ('Mojave National Preserve', 35.2, -115.5), ('Mendocino National Forest', 39.6, -122.9), ('Death Valley', 36.5, -117.0),
           ('Eastern Sierra', 37.5, -118.6), ('Los Padres backcountry', 34.8, -119.6), ('Santa Lucia Range', 36.1, -121.5),
           ('Lassen country', 40.5, -121.4), ('Feather River country', 39.9, -121.2), ('Sequoia backcountry', 36.5, -118.6),
           ('Owens Valley', 36.8, -118.2), ('Inyo Mountains', 36.7, -117.9), ('Tehachapi Mountains', 35.0, -118.6)]


UNITS = {'SCU', 'LNU', 'CZU', 'SQF', 'KNP', 'SHU', 'BTU', 'TCU', 'MEU', 'AMR', 'BEU', 'SLU', 'RRU', 'BDU', 'LMU', 'NEU', 'FKU',
         'MMU', 'TGU', 'HUU', 'SKU', 'MVU', 'LAC', 'ORC', 'VNC', 'SBC', 'KRN', 'TUU', 'MRN', 'ENF', 'STF', 'SNF', 'TNF', 'SRF', 'KNF'}


def fire_name(n):
    fix = lambda w: w.upper() if w.upper() in UNITS else ('Mc' + w[2:].capitalize() if w.startswith('Mc') and len(w) > 3 else w)
    return ' '.join(fix(w) for w in str(n).title().split())


def region_name(lat, lon):
    return min(REGIONS, key=lambda r: (r[1] - lat) ** 2 + ((r[2] - lon) * 0.8) ** 2)[0]


def cell_km2(rows):
    lat = N - (rows + 0.5) * RES
    return (RES * 110.540) * (RES * 111.320 * np.cos(np.radians(lat)))


def main():
    far = np.load(os.path.join(OUT, 'far.npy'), mmap_mode='r'); near = np.load(os.path.join(OUT, 'near.npy'), mmap_mode='r')
    lc = np.load(os.path.join(OUT, 'lc90.npy'), mmap_mode='r'); ca = np.load(os.path.join(OUT, 'ca_mask.npy'), mmap_mode='r')
    sites = json.load(open(os.path.join(OUT, 'sites.json')))
    area_row = cell_km2(np.arange(NY))
    stats = dict(sites=len(sites), cameras=int(sum(s['n'] for s in sites)))
    land = np.zeros(NY); wild = np.zeros(NY); w1 = np.zeros(NY); w2 = np.zeros(NY); wn = np.zeros(NY); l1 = np.zeros(NY)
    for r0 in range(0, NY, 512):
        sl = slice(r0, min(NY, r0 + 512))
        c = ca[sl]; l = lc[sl]; f = far[sl]; n = near[sl]
        lnd = c & (l != 0) & (l != 80)
        wl = c & np.isin(l, WILD)
        land[sl] = lnd.sum(1); wild[sl] = wl.sum(1)
        w1[sl] = (wl & (f >= 1)).sum(1); w2[sl] = (wl & (f >= 2)).sum(1); wn[sl] = (wl & (n >= 1)).sum(1); l1[sl] = (lnd & (f >= 1)).sum(1)
    A = lambda v: float((v * area_row).sum())
    stats.update(land_km2=round(A(land)), wild_km2=round(A(wild)), wild_seen_km2=round(A(w1)), wild_seen2_km2=round(A(w2)),
                 wild_near_km2=round(A(wn)), land_seen_km2=round(A(l1)))
    stats.update(wild_seen=round(A(w1) / A(wild), 4), wild_seen2=round(A(w2) / A(wild), 4), wild_near=round(A(wn) / A(wild), 4))
    print(json.dumps(stats, indent=1), flush=True)

    # ignitions
    fi = pd.read_parquet(os.path.join(DATA, 'fires', 'ca_wildfire_incidents.parquet'))
    fi = fi[(fi.date.dt.year >= YEARS[0]) & (fi.date.dt.year <= YEARS[1])].copy()
    fi['r'] = ((N - fi.lat) / RES).astype(int); fi['c'] = ((fi.lon - W) / RES).astype(int)
    fi = fi[(fi.r >= 0) & (fi.r < NY) & (fi.c >= 0) & (fi.c < NX)]
    fi = fi[np.asarray(ca)[fi.r.values, fi.c.values]]
    fi['cams'] = np.asarray(far)[fi.r.values, fi.c.values]; fi['cams_near'] = np.asarray(near)[fi.r.values, fi.c.values]
    fi['wild'] = np.isin(np.asarray(lc)[fi.r.values, fi.c.values], WILD)
    fi['acres'] = fi.IncidentSize.fillna(0)
    # smoke columns: can any camera see a point 100 m or 300 m above the ignition? (fires of 10+ acres)
    dem = np.load(os.path.join(OUT, 'dem90.npy'), mmap_mode='r')
    slat = np.array([s['lat'] for s in sites]); slon = np.array([s['lon'] for s in sites])
    sh = []
    for s in sites:
        g = float(dem[int((N - s['lat']) / RES), int((s['lon'] - W) / RES)])
        sh.append(max(g + MAST, s['elev'] or -1e9))
    sh = np.array(sh)
    for H in (100, 300):
        fi[f'smoke{H}'] = -1
    big10 = fi.index[fi.acres >= 10]
    for i in big10:
        r = fi.loc[i]
        dist = np.hypot((slat - r.lat) * 110540.0, (slon - r.lon) * 111320.0 * math.cos(math.radians(r.lat)))
        near_sites = np.flatnonzero(dist < R_FAR)
        z0 = float(dem[int(r.r), int(r.c)])
        for H in (100, 300):
            fi.at[i, f'smoke{H}'] = int(sum(sees_point(dem, slat[k], slon[k], sh[k], r.lat, r.lon, z0 + H) for k in near_sites))
    ign = {}
    for label, m in [('all', fi.acres >= 0), ('10+ acres', fi.acres >= 10), ('100+ acres', fi.acres >= 100),
                     ('1,000+ acres', fi.acres >= 1000), ('10,000+ acres', fi.acres >= 10000)]:
        d = fi[m]
        sm = {}
        if (d.smoke300 >= 0).all() and len(d):
            sm = dict(smoke100=round(float((d.smoke100 >= 1).mean()), 4), smoke300=round(float((d.smoke300 >= 1).mean()), 4),
                      smoke300_2=round(float((d.smoke300 >= 2).mean()), 4), acres_nosmoke=round(float(d.acres[d.smoke300 == 0].sum())))
        ign[label] = dict(**sm, n=int(len(d)), seen=round(float((d.cams >= 1).mean()), 4), seen2=round(float((d.cams >= 2).mean()), 4),
                          near=round(float((d.cams_near >= 1).mean()), 4), acres=round(float(d.acres.sum())),
                          acres_unseen=round(float(d.acres[d.cams == 0].sum())))
    stats['ignitions'] = ign; stats['years'] = list(YEARS)
    big_unseen = fi[(fi.acres >= 1000) & (fi.smoke300 == 0)].sort_values('acres', ascending=False)
    stats['unseen_large'] = [dict(name=fire_name(r.IncidentName), year=int(r.date.year), acres=round(float(r.acres)), smoke300=int(r.smoke300),
                                  county=str(r.POOCounty or ''), lat=round(float(r.lat), 4), lon=round(float(r.lon), 4))
                             for r in big_unseen.head(12).itertuples()]
    cty = fi[fi.POOCounty.notna()].groupby('POOCounty').agg(n=('cams', 'size'), seen=('cams', lambda v: float((v >= 1).mean())),
                                                            acres=('acres', 'sum'),
                                                            acres_unseen=('acres', lambda v: float(v[fi.loc[v.index, 'cams'] == 0].sum())))
    cty = cty[cty.n >= 100].sort_values('acres_unseen', ascending=False)
    stats['counties'] = [dict(county=k, n=int(v.n), seen=round(v.seen, 3), acres=round(v.acres), acres_unseen=round(v.acres_unseen))
                         for k, v in cty.head(15).iterrows()]
    print(json.dumps({k: stats[k] for k in ('ignitions', 'unseen_large')}, indent=1), flush=True)

    # blind spots: connected unseen wildland on a 1 km grid
    from scipy import ndimage
    f = 11
    h, w = NY // f, NX // f
    def coarse(a, fn):
        return fn(np.asarray(a)[: h * f, : w * f].reshape(h, f, w, f), axis=(1, 3))
    wl_c = coarse(np.isin(lc, WILD) & ca, np.mean) > 0.5
    seen_c = coarse(np.asarray(far) >= 1, np.mean) > 0.1
    blind = wl_c & ~seen_c
    lab, nlab = ndimage.label(blind)
    sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, nlab + 1))
    order = np.argsort(-sizes)[:8]
    km_cell = (f * RES * 110.54) * (f * RES * 111.32 * math.cos(math.radians(37)))
    spots = []
    for k in order:
        ys, xs = np.nonzero(lab == k + 1)
        lat = N - (ys.mean() + 0.5) * f * RES; lon = W + (xs.mean() + 0.5) * f * RES
        inside = fi[(lab[np.clip(fi.r.values // f, 0, h - 1), np.clip(fi.c.values // f, 0, w - 1)] == k + 1)]
        big = inside.sort_values('acres', ascending=False).head(1)
        spots.append(dict(name=region_name(lat, lon), km2=round(float(sizes[k] * km_cell)), lat=round(lat, 3), lon=round(lon, 3), ignitions=int(len(inside)),
                          acres=round(float(inside.acres.sum())),
                          biggest=(dict(name=fire_name(big.IncidentName.iloc[0]), year=int(big.date.iloc[0].year), acres=round(float(big.acres.iloc[0])))
                                   if len(big) and big.acres.iloc[0] > 0 else None)))
    stats['blind_spots'] = spots
    print(json.dumps(spots[:5], indent=1), flush=True)

    # map images (light and dark), 1/4 resolution then resized
    from PIL import Image, ImageDraw
    q = 4
    hq, wq = NY // q, NX // q
    def sub(a):
        return np.asarray(a)[: hq * q: q, : wq * q: q]
    z = sub(dem).astype(np.float32); z[z < -1000] = 0
    gy, gx = np.gradient(z, 4 * 92.0)
    shade = np.clip(0.88 + 0.55 * (-gx * 0.7 + gy * 0.7) / np.sqrt(1 + gx ** 2 + gy ** 2), 0.62, 1.08)
    caq, lcq, fq = sub(ca), sub(lc), sub(far)
    wildq = np.isin(lcq, WILD)
    themes = {
        'light': dict(bg=(236, 239, 232), land=(212, 216, 208), blind=(228, 186, 112), one=(150, 198, 142), two=(46, 133, 64),
                      site=(24, 33, 27), fire=(178, 58, 43), ring=(24, 33, 27), coast=(150, 160, 150)),
        'dark': dict(bg=(21, 26, 22), land=(46, 53, 48), blind=(150, 106, 36), one=(58, 98, 64), two=(70, 160, 88),
                     site=(226, 232, 224), fire=(224, 100, 79), ring=(226, 232, 224), coast=(80, 92, 84)),
    }
    os.makedirs(os.path.join(DOCS, 'assets', 'coverage'), exist_ok=True)
    big = fi[fi.acres >= 1000]
    for name, th in themes.items():
        img = np.empty((hq, wq, 3), np.float32); img[:] = th['bg']
        col = np.empty((hq, wq, 3), np.float32); col[:] = th['land']
        col[wildq & (fq == 0)] = th['blind']; col[wildq & (fq == 1)] = th['one']; col[wildq & (fq >= 2)] = th['two']
        k = shade[..., None] if name == 'light' else (0.6 + 0.4 * shade[..., None])
        img[caq] = (col * k)[caq]
        im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
        scale = 1400 / wq
        im = im.resize((1400, int(hq * scale)), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        P = lambda lat, lon: ((lon - W) / RES / q * scale, (N - lat) / RES / q * scale)
        for s in sites:
            x, y = P(s['lat'], s['lon']); d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=th['site'])
        for r in big.itertuples():
            x, y = P(r.lat, r.lon); rr = 2.5 + 1.6 * math.log10(max(r.acres, 1000) / 1000 + 1) * 3
            if r.smoke300 == 0:
                d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=th['fire'])
            else:
                d.ellipse((x - rr, y - rr, x + rr, y + rr), outline=th['ring'], width=1)
        im.save(os.path.join(DOCS, 'assets', 'coverage', f'ca_{name}.png'), optimize=True)
    stats['map'] = dict(w=1400, h=int(hq * 1400 / wq), west=W, north=N, res=RES * q * wq / 1400)
    stats['sites_list'] = [dict(lat=round(s['lat'], 4), lon=round(s['lon'], 4), n=s['n'], name=(s['names'][0] or '').rsplit(' ', 1)[0],
                                km2=s.get('visible_km2')) for s in sites]
    fi[['IncidentName', 'date', 'acres', 'lat', 'lon', 'POOCounty', 'cams', 'cams_near', 'smoke100', 'smoke300']].to_parquet(os.path.join(OUT, 'ignitions.parquet'))
    stats['fires_1000'] = [dict(n=fire_name(r.IncidentName), y=int(r.date.year), a=round(float(r.acres)), lat=round(float(r.lat), 4),
                                lon=round(float(r.lon), 4), g=int(r.cams), s=int(r.smoke300)) for r in big.itertuples()]
    json.dump(stats, open(os.path.join(OUT, 'coverage.json'), 'w'), indent=1)
    os.makedirs(os.path.join(DOCS, 'data'), exist_ok=True)
    json.dump(stats, open(os.path.join(DOCS, 'data', 'coverage.json'), 'w'), separators=(',', ':'))
    print('done')


if __name__ == '__main__':
    main()
