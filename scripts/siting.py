"""Where would the next ten fire cameras do the most good?

Candidate sites are terrain high points (the highest 90 m cell in each 6 km square) inside California. Each gets
the same 360-degree, 30 km viewshed as the existing cameras. A greedy pass then picks, ten times, the candidate
that brings the most currently unseen wildland into view, counting each newly seen cell once. A second pass looks
back at 2020-2025: it picks the sites that would have put the most acres in view, counting fires of 10+ acres that
no existing camera could see as a 300 m smoke column.

    DATA=data python scripts/siting.py
Writes $DATA/coverage/siting.json and adds the picks to docs/data/coverage.json
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from coverage import OUT, RES, W, N, NX, NY, WILD, MAST, R_FAR, viewshed, sees_point  # noqa: E402
from coverage_report import region_name, DOCS  # noqa: E402

BLOCK = 66          # 6 km candidate squares
COARSE = 3          # newly seen cells are tallied on a 270 m grid


def candidates(dem, ca, unseen=None, min_unseen=60):
    out = []
    for r0 in range(0, NY - BLOCK, BLOCK):
        blk = np.asarray(dem[r0:r0 + BLOCK])
        for c0 in range(0, NX - BLOCK, BLOCK):
            b = blk[:, c0:c0 + BLOCK]
            i = int(np.argmax(b)); rr, cc = r0 + i // BLOCK, c0 + i % BLOCK
            if not ca[rr, cc] or b.max() < 0:
                continue
            if unseen is not None:
                rq, cq = rr // COARSE, cc // COARSE; rad = 55
                if unseen[max(0, rq - rad):rq + rad, max(0, cq - rad):cq + rad].sum() < min_unseen:
                    continue
            out.append((rr, cc, float(b.max())))
    return out


def fire_siting(k_pick=10):
    import pandas as pd
    dem = np.load(os.path.join(OUT, 'dem90.npy'), mmap_mode='r'); ca = np.load(os.path.join(OUT, 'ca_mask.npy'), mmap_mode='r')
    fi = pd.read_parquet(os.path.join(OUT, 'ignitions.parquet'))
    miss = fi[(fi.acres >= 10) & (fi.smoke300 == 0)].reset_index(drop=True)
    cands = candidates(dem, ca)
    clat = np.array([N - (r + 0.5) * RES for r, _, _ in cands]); clon = np.array([W + (c + 0.5) * RES for _, c, _ in cands])
    cz = np.array([z for _, _, z in cands])
    covers = [set() for _ in cands]
    for j, f in miss.iterrows():
        z0 = float(dem[int((N - f.lat) / RES), int((f.lon - W) / RES)])
        d = np.hypot((clat - f.lat) * 110540.0, (clon - f.lon) * 111320.0 * np.cos(np.radians(f.lat)))
        for i in np.flatnonzero(d < R_FAR):
            if sees_point(dem, clat[i], clon[i], cz[i] + MAST, f.lat, f.lon, z0 + 300):
                covers[i].add(j)
    acres = miss.acres.values
    left = set(range(len(miss))); picks = []
    for _ in range(k_pick):
        best = max(range(len(cands)), key=lambda i: acres[list(covers[i] & left)].sum() if covers[i] & left else 0)
        got = covers[best] & left
        if not got:
            break
        names = miss.loc[sorted(got, key=lambda j: -acres[j])[:3], 'IncidentName'].tolist()
        picks.append(dict(lat=round(float(clat[best]), 4), lon=round(float(clon[best]), 4), elev=round(float(cz[best])),
                          fires=len(got), acres=round(float(acres[list(got)].sum())), examples=[str(n).title() for n in names],
                          region=region_name(clat[best], clon[best])))
        left -= got
        print(picks[-1], flush=True)
    res = dict(candidates=len(cands), missed_fires=int(len(miss)), missed_acres=round(float(acres.sum())), picks=picks,
               fires=int(sum(p['fires'] for p in picks)), acres=round(float(sum(p['acres'] for p in picks))))
    json.dump(res, open(os.path.join(OUT, 'siting_fires.json'), 'w'), indent=1)
    print('ten sites would have seen', res['fires'], 'of', res['missed_fires'], 'missed fires,', res['acres'], 'of', res['missed_acres'], 'acres')
    return res


def main(k_pick=10):
    dem = np.load(os.path.join(OUT, 'dem90.npy'), mmap_mode='r'); lc = np.load(os.path.join(OUT, 'lc90.npy'), mmap_mode='r')
    ca = np.load(os.path.join(OUT, 'ca_mask.npy'), mmap_mode='r'); far = np.load(os.path.join(OUT, 'far.npy'), mmap_mode='r')
    hq, wq = NY // COARSE, NX // COARSE
    # unseen wildland on the coarse grid, in km2 per coarse cell
    lat_c = N - (np.arange(hq) + 0.5) * COARSE * RES
    cell_km2 = (COARSE * RES * 110.54) * (COARSE * RES * 111.32 * np.cos(np.radians(lat_c)))
    unseen = np.zeros((hq, wq), np.float32)
    for r0 in range(0, hq, 256):
        r1 = min(hq, r0 + 256)
        sl = slice(r0 * COARSE, r1 * COARSE)
        u = (np.isin(lc[sl, : wq * COARSE], WILD) & ca[sl, : wq * COARSE] & (far[sl, : wq * COARSE] == 0)).astype(np.float32)
        unseen[r0:r1] = u.reshape(r1 - r0, COARSE, wq, COARSE).mean(axis=(1, 3)) * cell_km2[r0:r1, None]
    total_wild = json.load(open(os.path.join(OUT, 'coverage.json')))['wild_km2']
    # candidates: highest cell per 6 km square, inside the state, with unseen wildland within ~15 km
    cands = []
    for r0 in range(0, NY - BLOCK, BLOCK):
        blk = np.asarray(dem[r0:r0 + BLOCK])
        for c0 in range(0, NX - BLOCK, BLOCK):
            b = blk[:, c0:c0 + BLOCK]
            i = int(np.argmax(b)); rr, cc = r0 + i // BLOCK, c0 + i % BLOCK
            if not ca[rr, cc] or b.max() < 0:
                continue
            rq, cq = rr // COARSE, cc // COARSE; rad = 55
            if unseen[max(0, rq - rad):rq + rad, max(0, cq - rad):cq + rad].sum() < 60:
                continue
            cands.append((rr, cc, float(b.max())))
    print(len(cands), 'candidate sites', flush=True)
    gains, t0 = [], time.time()
    for k, (rr, cc, z) in enumerate(cands):
        lat = N - (rr + 0.5) * RES; lon = W + (cc + 0.5) * RES
        vr, vc, _ = viewshed(dem, lat, lon, z + MAST)
        idx = np.unique((vr // COARSE).clip(0, hq - 1) * wq + (vc // COARSE).clip(0, wq - 1))
        idx = idx[unseen.reshape(-1)[idx] > 0].astype(np.int32)
        gains.append((lat, lon, z, idx))
        if k % 200 == 0:
            print('candidate', k, len(cands), round(time.time() - t0), 's', flush=True)
    flat = unseen.reshape(-1).copy()
    picks = []
    for _ in range(k_pick):
        best = max(range(len(gains)), key=lambda i: flat[gains[i][3]].sum())
        lat, lon, z, idx = gains[best]
        g = float(flat[idx].sum())
        picks.append(dict(lat=round(lat, 4), lon=round(lon, 4), elev=round(z), new_km2=round(g), region=region_name(lat, lon)))
        flat[idx] = 0
        print(picks[-1], flush=True)
    added = sum(p['new_km2'] for p in picks)
    res = dict(candidates=len(cands), picks=picks, added_km2=round(added), added_share=round(added / total_wild, 4))
    json.dump(res, open(os.path.join(OUT, 'siting.json'), 'w'), indent=1)
    cov_path = os.path.join(DOCS, 'data', 'coverage.json')
    cov = json.load(open(cov_path)); cov['siting'] = res
    json.dump(cov, open(cov_path, 'w'), separators=(',', ':'))
    print('ten new sites would add', round(added), 'km2 =', round(added / total_wild * 100, 1), 'points of wildland coverage')


if __name__ == '__main__':
    main()
    fire_siting()
