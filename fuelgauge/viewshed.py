"""What can a camera see? Terrain viewsheds and smoke-column line of sight.

Works on any north-up elevation raster (fuelgauge.terrain.Raster, e.g. from load_planetary('cop-dem-glo-90', 'data', ...)).
Rays are cast from the camera at a fixed angular step; along each ray a sample is visible if its elevation angle,
after earth curvature and atmospheric refraction, is at least the steepest angle seen so far.

    from fuelgauge import terrain, viewshed
    dem = terrain.load_planetary('cop-dem-glo-90', 'data', lat, lon, 32000)
    vis = viewshed.viewshed(dem, lat, lon, mast_m=10)          # boolean grid on the DEM's cells
    viewshed.sees_point(dem, lat, lon, 10, lat2, lon2, 300)     # can it see a 300 m smoke column there?
    picks = viewshed.site(dem, existing=[(lat, lon)], k=5)      # where would five more cameras see the most?
"""
from __future__ import annotations

import math

import numpy as np

R_EARTH = 6371000.0
K_REFRACT = 0.13


def _drop(d):
    return d ** 2 / (2 * R_EARTH) * (1 - K_REFRACT)


def _metres(lat):
    return 110540.0, 111320.0 * math.cos(math.radians(lat))


def rays(dem, lat, lon, mast_m=10.0, r_max=30000.0, az_step=0.1, step=None):
    """Visible samples around a camera. Returns (lat, lon, distance_m) arrays of the visible ray samples.
    The camera stands `mast_m` above the ground at its location."""
    my, mx = _metres(lat)
    cell = min(abs(dem.dlat) * my, abs(dem.dlon) * mx)
    step = step or cell * 0.5
    h_obs = float(dem.sample(np.array([lat]), np.array([lon]))[0]) + mast_m
    az = np.radians(np.arange(0, 360, az_step))[:, None]
    d = np.arange(step, r_max + step, step)[None, :]
    la = lat + d * np.cos(az) / my; lo = lon + d * np.sin(az) / mx
    z = dem.sample(la, lo, order=0)
    ang = (z - _drop(d) - h_obs) / d
    prev = np.maximum.accumulate(np.concatenate([np.full((ang.shape[0], 1), -np.inf), ang[:, :-1]], 1), axis=1)
    vis = ang >= prev
    return la[vis], lo[vis], np.broadcast_to(d, vis.shape)[vis]


def viewshed(dem, lat, lon, mast_m=10.0, r_max=30000.0, az_step=0.1):
    """Boolean grid, same shape as dem.arr, True where the camera has line of sight to the ground."""
    la, lo, _ = rays(dem, lat, lon, mast_m, r_max, az_step)
    rows = np.floor((la - dem.lat0) / dem.dlat).astype(int); cols = np.floor((lo - dem.lon0) / dem.dlon).astype(int)
    ok = (rows >= 0) & (rows < dem.arr.shape[0]) & (cols >= 0) & (cols < dem.arr.shape[1])
    out = np.zeros(dem.arr.shape, bool)
    out[rows[ok], cols[ok]] = True
    return out


def sees_point(dem, lat, lon, mast_m, lat2, lon2, above_ground_m=0.0, step=None):
    """Line of sight from a camera to a point `above_ground_m` over the terrain at (lat2, lon2)."""
    my, mx = _metres((lat + lat2) / 2)
    D = math.hypot((lat2 - lat) * my, (lon2 - lon) * mx)
    if D < 1:
        return True
    step = step or min(abs(dem.dlat) * my, abs(dem.dlon) * mx) * 0.5
    h_obs = float(dem.sample(np.array([lat]), np.array([lon]))[0]) + mast_m
    z_top = float(dem.sample(np.array([lat2]), np.array([lon2]))[0]) + above_ground_m
    t = np.arange(step, D - step / 2, step) / D
    if not len(t):
        return True
    z = dem.sample(lat + t * (lat2 - lat), lon + t * (lon2 - lon), order=0)
    line = h_obs + (z_top - _drop(D) - h_obs) * t
    return bool(np.all(z - _drop(t * D) < line))


def coverage(dem, cameras, mast_m=10.0, r_max=30000.0, az_step=0.1):
    """Count of cameras with line of sight to each cell. `cameras` is a list of (lat, lon) pairs."""
    count = np.zeros(dem.arr.shape, np.uint16)
    for lat, lon in cameras:
        count += viewshed(dem, lat, lon, mast_m, r_max, az_step)
    return count


def candidates(dem, block_m=6000.0, mask=None):
    """Hilltops: the highest cell in each block of about `block_m` metres (inside `mask` if given).
    Returns a list of (lat, lon, elevation)."""
    lat_c = dem.lat0 + dem.dlat * dem.arr.shape[0] / 2
    my, mx = _metres(lat_c)
    br = max(1, int(round(block_m / (abs(dem.dlat) * my)))); bc = max(1, int(round(block_m / (abs(dem.dlon) * mx))))
    out = []
    H, W = dem.arr.shape
    for r0 in range(0, H, br):
        for c0 in range(0, W, bc):
            b = np.asarray(dem.arr[r0:r0 + br, c0:c0 + bc], float)
            if mask is not None:
                b = np.where(mask[r0:r0 + br, c0:c0 + bc], b, -np.inf)
            if not np.isfinite(b).any():
                continue
            i = int(np.nanargmax(b)); r, c = r0 + i // b.shape[1], c0 + i % b.shape[1]
            out.append((dem.lat0 + (r + 0.5) * dem.dlat, dem.lon0 + (c + 0.5) * dem.dlon, float(dem.arr[r, c])))
    return out


def site(dem, existing=(), k=10, mast_m=10.0, r_max=30000.0, target=None, block_m=6000.0, az_step=0.25, cands=None,
         progress=None):
    """Greedy camera siting: pick `k` new sites, one at a time, each the candidate that brings the most
    currently unseen target cells into view (each newly seen cell counts once).

    existing  (lat, lon) pairs of cameras already in place
    target    boolean grid like dem.arr of the ground worth watching (default: every cell)
    cands     (lat, lon, elev) candidates; default: the highest cell in every `block_m` square
    Returns a list of dicts: lat, lon, elev, new_cells, new_km2.
    """
    H, W = dem.arr.shape
    target = np.ones((H, W), bool) if target is None else np.asarray(target, bool)
    seen = np.zeros((H, W), bool)
    for lat, lon in existing:
        seen |= viewshed(dem, lat, lon, mast_m, r_max, az_step)
    unseen = (target & ~seen).ravel()
    lat_c = dem.lat0 + dem.dlat * H / 2
    my, mx = _metres(lat_c)
    cell_km2 = abs(dem.dlat) * my * abs(dem.dlon) * mx / 1e6
    cands = candidates(dem, block_m, target) if cands is None else cands
    views = []
    for j, (lat, lon, z) in enumerate(cands):
        views.append(np.flatnonzero(viewshed(dem, lat, lon, mast_m, r_max, az_step).ravel() & unseen))
        if progress:
            progress(j + 1, len(cands))
    picks = []
    for _ in range(k):
        gains = [int(unseen[v].sum()) for v in views]
        if not gains or max(gains) == 0:
            break
        j = int(np.argmax(gains))
        lat, lon, z = cands[j]
        picks.append(dict(lat=round(float(lat), 5), lon=round(float(lon), 5), elev=round(float(z), 1),
                          new_cells=gains[j], new_km2=round(gains[j] * cell_km2, 2)))
        unseen[views[j]] = False
    return picks
