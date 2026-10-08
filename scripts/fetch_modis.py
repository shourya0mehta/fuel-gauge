"""MODIS MCD43A4 nadir reflectance (3x3 px mean, every 8 days) at every study camera view and fuel site."""
import json, os, time, math, sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, rasterio
from rasterio.warp import transform
import pystac_client, planetary_computer

ROOT = os.environ.get('DATA', 'data')
sel = json.load(open(os.path.join(os.path.dirname(__file__), '..', 'study', 'cameras.json')))
cams = json.load(open(f'{ROOT}/raw/phenocam_cameras.json')); cams = cams['results'] if isinstance(cams, dict) else cams
meta = {c['Sitename']: c for c in cams if isinstance(c, dict)}
us = pd.read_parquet(f'{ROOT}/globe/globe_usa.parquet')
ORI = {'N': 0, 'NNE': 22.5, 'NE': 45, 'ENE': 67.5, 'E': 90, 'ESE': 112.5, 'SE': 135, 'SSE': 157.5, 'S': 180, 'SSW': 202.5,
       'SW': 225, 'WSW': 247.5, 'W': 270, 'WNW': 292.5, 'NW': 315, 'NNW': 337.5}
points = {}
for r in sel:
    c = meta[r['cam']]; la, lo = float(c['Lat']), float(c['Lon'])
    o = (c.get('sitemetadata') or {}).get('camera_orientation')
    if o in ORI:
        a = math.radians(ORI[o]); la += 1000 * math.cos(a) / 110540; lo += 1000 * math.sin(a) / (111320 * math.cos(math.radians(la)))
    points[f"cam:{r['cam']}"] = (la, lo)
    for s in r['good']:
        x = us[us['Site name'] == s[0]].iloc[0]; points[s[0]] = (float(x.lat), float(x.lon))
print(len(points), 'points', flush=True)
cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=planetary_computer.sign_inplace)
# group points by MODIS tile
tiles = {}
for name, (la, lo) in points.items():
    its = list(cat.search(collections=["modis-43A4-061"], intersects={"type": "Point", "coordinates": [lo, la]}, datetime="2015-06-01/2015-06-02").items())
    if not its: continue
    k = (its[0].properties['modis:horizontal-tile'], its[0].properties['modis:vertical-tile'])
    tiles.setdefault(k, []).append(name)
print({f'h{k[0]:02d}v{k[1]:02d}': len(v) for k, v in tiles.items()}, flush=True)
BANDS = [1, 2, 3, 4, 6]
out_path = f'{ROOT}/modis_study.jsonl'
done = set()
if os.path.exists(out_path):
    for l in open(out_path):
        try: j = json.loads(l); done.add((j['tile'], j['date']))
        except Exception: pass

def read(args):
    tile, d, it, names = args
    rec = dict(tile=tile, date=d.isoformat(), pts={})
    try:
        for b in BANDS + ['q']:
            key = f'Nadir_Reflectance_Band{b}' if b != 'q' else 'BRDF_Albedo_Band_Mandatory_Quality_Band1'
            with rasterio.open(it.assets[key].href) as src:
                xs, ys = transform('EPSG:4326', src.crs, [points[n][1] for n in names], [points[n][0] for n in names])
                for n, x, y in zip(names, xs, ys):
                    r, c = src.index(x, y)
                    w = src.read(1, window=((r - 1, r + 2), (c - 1, c + 2))).astype(float)
                    if b == 'q':
                        rec['pts'].setdefault(n, {})['qa_full'] = float(np.mean(w == 0))
                    else:
                        w[w == 32767] = np.nan
                        rec['pts'].setdefault(n, {})[f'b{b}'] = None if np.all(np.isnan(w)) else float(np.nanmean(w) * 1e-4)
    except Exception as e:
        rec['error'] = str(e)[:200]
    return rec

t0 = time.time()
for (h, v), names in tiles.items():
    tile = f'h{h:02d}v{v:02d}'
    for y in range(2000, 2024):
        its = {}
        for it in cat.search(collections=["modis-43A4-061"], datetime=f"{y}-01-01/{y}-12-31",
                             query={"modis:horizontal-tile": {"eq": h}, "modis:vertical-tile": {"eq": v}}).items():
            its[it.datetime.date()] = it
        sel_ = sorted((d, it) for d, it in its.items() if d.timetuple().tm_yday % 8 == 1 and (tile, d.isoformat()) not in done)
        with ThreadPoolExecutor(16) as ex, open(out_path, 'a') as f:
            for rec in ex.map(read, [(tile, d, it, names) for d, it in sel_]):
                f.write(json.dumps(rec) + '\n')
        print(tile, y, len(sel_), 'dates', round(time.time() - t0), 's', flush=True)
print('DONE', flush=True)
