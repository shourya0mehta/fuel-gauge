"""What can California's fire cameras actually see?

Every ALERTCalifornia camera site gets a terrain viewshed: rays every 0.1 degrees out to 30 km over the 90 m
Copernicus DEM, with earth curvature and refraction, from the camera's mast. The cameras pan through full
360-degree panoramas, so a site covers every direction it has line of sight in. Counting sites per 90 m cell
gives a statewide map of where the ground is in view, where two cameras overlap (enough to triangulate a smoke
column), and where nothing looks. Wildland is ESA WorldCover tree cover, shrubland and grassland. NIFC ignition
points are then checked against the map: was the ground where each fire started in view of any camera?

    DATA=data STATES_GEOJSON=states.geojson python scripts/coverage.py
Writes $DATA/coverage/*.npy (grids), coverage.json (statistics), and map images for the site.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import numpy as np

DATA = os.environ.get('DATA', 'data')
OUT = os.path.join(DATA, 'coverage'); os.makedirs(OUT, exist_ok=True)
RES = 1 / 1200                         # 3 arc-seconds, about 90 m
W, E, S, N = -124.5, -114.0, 32.5, 42.1
NX, NY = int(round((E - W) / RES)), int(round((N - S) / RES))
R_FAR, R_NEAR = 30000.0, 10000.0       # smoke-spotting range, close-watch range (m)
MAST = 10.0
K_REFR = 0.13
WILD = (10, 20, 30)                    # WorldCover: tree cover, shrubland, grassland


def transform():
    from rasterio.transform import from_origin
    return from_origin(W, N, RES, RES)


def mosaic(collection, asset, dtype, resampling, cache, nodata=0, decim=None):
    path = os.path.join(OUT, cache)
    if os.path.exists(path):
        return np.load(path, mmap_mode='r')
    import pystac_client, planetary_computer, rasterio
    from rasterio.warp import reproject, Resampling
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=planetary_computer.sign_inplace)
    items = list(cat.search(collections=[collection], bbox=[W, S, E, N]).items())
    arr = np.full((NY, NX), nodata, dtype)
    t0 = time.time()
    for k, it in enumerate(items):
        with rasterio.open(it.assets[asset].href) as src:
            b = src.bounds
            x0 = max(0, int(math.floor((b.left - W) / RES))); x1 = min(NX, int(math.ceil((b.right - W) / RES)))
            y0 = max(0, int(math.floor((N - b.top) / RES))); y1 = min(NY, int(math.ceil((N - b.bottom) / RES)))
            if x1 <= x0 or y1 <= y0:
                continue
            from rasterio.transform import from_origin
            dt = from_origin(W + x0 * RES, N - y0 * RES, RES, RES)
            dst = np.full((y1 - y0, x1 - x0), nodata, dtype)
            if decim:   # read a decimated overview first (WorldCover is 10 m)
                f = decim
                data = src.read(1, out_shape=(src.height // f, src.width // f), resampling=Resampling.mode)
                st = src.transform * src.transform.scale(src.width / data.shape[1], src.height / data.shape[0])
                reproject(data, dst, src_transform=st, src_crs=src.crs, dst_transform=dt, dst_crs='EPSG:4326',
                          resampling=resampling, src_nodata=nodata, dst_nodata=nodata)
            else:
                reproject(rasterio.band(src, 1), dst, dst_transform=dt, dst_crs='EPSG:4326', resampling=resampling, dst_nodata=nodata)
            sub = arr[y0:y1, x0:x1]
            m = dst != nodata
            sub[m] = dst[m]
        if k % 10 == 0:
            print(collection, k, len(items), round(time.time() - t0), 's', flush=True)
    np.save(path, arr)
    return np.load(path, mmap_mode='r')


def state_mask(geojson, name='California'):
    path = os.path.join(OUT, 'ca_mask.npy')
    if os.path.exists(path):
        return np.load(path, mmap_mode='r')
    from rasterio.features import rasterize
    g = json.load(open(geojson))
    geom = next(f['geometry'] for f in g['features'] if f['properties']['name'] == name)
    m = rasterize([(geom, 1)], out_shape=(NY, NX), transform=transform(), dtype=np.uint8).astype(bool)
    np.save(path, m)
    return m


def sites_from_cameras(path):
    feats = json.load(open(path))['features']
    cams = [f for f in feats if f['geometry']['coordinates'][0] is not None and f['properties'].get('state') == 'CA']
    groups = {}
    for f in cams:
        lon, lat = f['geometry']['coordinates'][:2]
        key = (round(lat / 0.002), round(lon / 0.002))
        groups.setdefault(key, []).append(f)
    sites = []
    for fs in groups.values():
        lon = float(np.mean([f['geometry']['coordinates'][0] for f in fs])); lat = float(np.mean([f['geometry']['coordinates'][1] for f in fs]))
        el = [f['geometry']['coordinates'][2] for f in fs if f['geometry']['coordinates'][2] is not None]
        sites.append(dict(lat=lat, lon=lon, elev=float(np.median(el)) if el else None, n=len(fs),
                          ids=[f['properties']['id'] for f in fs], names=[f['properties'].get('name') for f in fs],
                          county=fs[0]['properties'].get('county'), sponsor=fs[0]['properties'].get('sponsor'),
                          aims=[(f['properties'].get('az_current'), f['properties'].get('fov')) for f in fs]))
    return cams, sites


def viewshed(dem, lat, lon, h_obs, r_max=R_FAR, az_step=0.1, step=45.0):
    """Visible cells around (lat, lon) as (rows, cols, distance m) using radial sweeps with earth curvature."""
    r0 = (N - lat) / RES; c0 = (lon - W) / RES
    my = RES * 110540.0; mx = RES * 111320.0 * math.cos(math.radians(lat))      # metres per cell
    az = np.radians(np.arange(0, 360, az_step))[:, None]
    d = np.arange(step, r_max + step, step)[None, :]
    rr = np.rint(r0 - d * np.cos(az) / my).astype(np.int64); cc = np.rint(c0 + d * np.sin(az) / mx).astype(np.int64)
    ok = (rr >= 0) & (rr < NY) & (cc >= 0) & (cc < NX)
    rr = np.clip(rr, 0, NY - 1); cc = np.clip(cc, 0, NX - 1)
    z = dem[rr, cc].astype(np.float32)
    z[~ok] = -1e4
    drop = d ** 2 / (2 * 6371000.0) * (1 - K_REFR)
    ang = (z - drop - h_obs) / d
    prev = np.maximum.accumulate(np.concatenate([np.full((ang.shape[0], 1), -np.inf), ang[:, :-1]], 1), axis=1)
    vis = (ang >= prev) & ok
    dd = np.broadcast_to(d, vis.shape)
    return rr[vis], cc[vis], dd[vis]


def sees_point(dem, site_lat, site_lon, h_obs, lat, lon, z_top, step=60.0):
    """Line of sight from a camera to a point z_top metres above sea level (earth curvature and refraction)."""
    my = 110540.0; mx = 111320.0 * math.cos(math.radians((site_lat + lat) / 2))
    dy = (lat - site_lat) * my; dx = (lon - site_lon) * mx
    D = math.hypot(dx, dy)
    if D < 1 or D > R_FAR:
        return False
    t = np.arange(step, D - step / 2, step) / D
    la = site_lat + t * (lat - site_lat); lo = site_lon + t * (lon - site_lon)
    rr = np.clip(((N - la) / RES).astype(int), 0, NY - 1); cc = np.clip(((lo - W) / RES).astype(int), 0, NX - 1)
    d = t * D
    drop = d ** 2 / (2 * 6371000.0) * (1 - K_REFR)
    line = h_obs + (z_top - D ** 2 / (2 * 6371000.0) * (1 - K_REFR) - h_obs) * t     # straight sight line, curvature removed
    return bool(np.all(dem[rr, cc] - drop < line))


def main():
    states = os.environ.get('STATES_GEOJSON')
    print('grid', NX, NY, flush=True)
    dem = mosaic('cop-dem-glo-90', 'data', np.int16, __import__('rasterio.warp', fromlist=['Resampling']).Resampling.bilinear, 'dem90.npy', nodata=-32768)
    lc = mosaic('esa-worldcover', 'map', np.uint8, __import__('rasterio.warp', fromlist=['Resampling']).Resampling.nearest, 'lc90.npy', nodata=0, decim=10)
    ca = state_mask(states)
    cams, sites = sites_from_cameras(os.path.join(DATA, 'raw', 'acal', 'all_cameras.json'))
    print(len(cams), 'cameras at', len(sites), 'sites', flush=True)
    far = np.zeros((NY, NX), np.uint8); near = np.zeros((NY, NX), np.uint8)
    t0 = time.time()
    for k, s in enumerate(sites):
        r0 = int((N - s['lat']) / RES); c0 = int((s['lon'] - W) / RES)
        ground = float(dem[r0, c0])
        h = max(ground + MAST, s['elev'] or -1e9)
        rr, cc, dd = viewshed(dem, s['lat'], s['lon'], h)
        idx = np.unique(rr * NX + cc)
        f = far.reshape(-1); f[idx] = np.minimum(f[idx].astype(np.int16) + 1, 255)
        nidx = np.unique((rr * NX + cc)[dd <= R_NEAR])
        n_ = near.reshape(-1); n_[nidx] = np.minimum(n_[nidx].astype(np.int16) + 1, 255)
        s['visible_km2'] = round(len(idx) * 0.0081, 1)
        if k % 100 == 0:
            print('viewshed', k, len(sites), round(time.time() - t0), 's', flush=True)
    np.save(os.path.join(OUT, 'far.npy'), far); np.save(os.path.join(OUT, 'near.npy'), near)
    json.dump(sites, open(os.path.join(OUT, 'sites.json'), 'w'))
    print('viewsheds done', round(time.time() - t0), 's', flush=True)


if __name__ == '__main__':
    main()
