"""Tie a fixed camera to the ground.

1. Render the panorama a camera should see from a DEM: for every azimuth, the elevation angle of the
   terrain at each distance (with earth curvature and refraction), its running maximum (the visible
   skyline), and the ground point at each distance.
2. Fit the camera pose (and optionally lens) by matching the image skyline to the rendered skyline.
3. Back-project pixels onto the ground: distance, latitude, longitude.

DEM access defaults to Copernicus GLO-30 on Microsoft Planetary Computer, but any (array, transform)
pair in geographic coordinates works, which is how the tests use a synthetic DEM.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

import numpy as np
from scipy import ndimage, optimize

from .camera import Camera

R_EARTH = 6371000.0
K_REFRACT = 0.13


@dataclass
class Raster:
    """Geographic raster: arr[row, col], with lon = lon0 + (col + .5) * dlon, lat = lat0 + (row + .5) * dlat."""
    arr: np.ndarray
    lon0: float
    dlon: float
    lat0: float
    dlat: float            # negative for north-up rasters

    def sample(self, lat, lon, order=1):
        col = (np.asarray(lon) - self.lon0) / self.dlon - 0.5
        row = (np.asarray(lat) - self.lat0) / self.dlat - 0.5
        return ndimage.map_coordinates(self.arr.astype(np.float32), [np.ravel(row), np.ravel(col)],
                                       order=order, mode='nearest').reshape(np.shape(lat))


def load_planetary(collection: str, asset: str, lat: float, lon: float, radius_m: float, cache: str | None = None,
                   prefer: str | None = None) -> Raster:
    """Mosaic tiles of a Planetary Computer collection around a point (e.g. 'cop-dem-glo-30'/'data',
    'esa-worldcover'/'map'). Cached as .npz when `cache` is given."""
    if cache and os.path.exists(cache):
        z = np.load(cache); t = z['transform']
        return Raster(z['arr'], *[float(v) for v in t])
    import rasterio
    from rasterio.merge import merge
    import pystac_client, planetary_computer
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                    modifier=planetary_computer.sign_inplace)
    dlat = radius_m / 110540.0; dlon = radius_m / (111320.0 * math.cos(math.radians(lat)))
    bbox = [lon - dlon, lat - dlat, lon + dlon, lat + dlat]
    items = list(cat.search(collections=[collection], bbox=bbox).items())
    if prefer:
        items = [i for i in items if prefer in i.id] or items
    srcs = [rasterio.open(i.assets[asset].href) for i in items]
    arr, tr = merge(srcs, bounds=bbox)
    for s in srcs:
        s.close()
    r = Raster(arr[0], tr.c, tr.a, tr.f, tr.e)
    if cache:
        os.makedirs(os.path.dirname(cache) or '.', exist_ok=True)
        np.savez_compressed(cache, arr=r.arr, transform=np.array([r.lon0, r.dlon, r.lat0, r.dlat]))
    return r


def destination(lat, lon, az_deg, d):
    az = np.radians(az_deg)
    return lat + d * np.cos(az) / 110540.0, lon + d * np.sin(az) / (111320.0 * np.cos(np.radians(lat)))


@dataclass
class Panorama:
    az: np.ndarray          # (A,) azimuths, continuous (may run below 0 or above 360)
    d: np.ndarray           # (D,) distances, m
    ang: np.ndarray         # (A, D) terrain elevation angle, deg
    cummax: np.ndarray      # (A, D) running max along distance: the visible horizon so far
    lat: np.ndarray         # (A, D)
    lon: np.ndarray         # (A, D)

    @property
    def skyline(self) -> np.ndarray:
        return self.cummax[:, -1]

    def unwrap(self, az):
        c = 0.5 * (self.az[0] + self.az[-1])
        return c + ((np.asarray(az) - c + 180.0) % 360.0 - 180.0)

    def skyline_at(self, az):
        return np.interp(self.unwrap(az), self.az, self.skyline)


def render_panorama(dem: Raster, lat: float, lon: float, height_m: float, az_lo: float, az_hi: float,
                    az_step: float = 0.05, max_d: float = 32000.0, step_d: float = 30.0) -> Panorama:
    azs = np.arange(az_lo, az_hi + 1e-9, az_step)
    ds = np.arange(60.0, max_d, step_d)
    A, D = np.meshgrid(azs, ds, indexing='ij')
    la, lo = destination(lat, lon, A, D)
    h = dem.sample(la, lo)
    drop = D ** 2 / (2 * R_EARTH) * (1 - K_REFRACT)
    ang = np.degrees(np.arctan2(h - drop - height_m, D))
    return Panorama(azs, ds, ang, np.maximum.accumulate(ang, axis=1), la, lo)


# ---------------------------------------------------------------------------------- skyline in the image
def skyline_rows(sky_mask: np.ndarray, gray: np.ndarray | None = None, edge_frac=0.05, snap=6, min_level=30):
    """Row of the first non-sky pixel per column, from a boolean sky mask connected to the top edge.
    Optionally snapped to the strongest vertical gradient within `snap` pixels."""
    import cv2
    H, W = sky_mask.shape
    n, cc = cv2.connectedComponents(sky_mask.astype(np.uint8))
    keep = set(np.unique(cc[:max(1, H // 50)])) - {0}
    sky = ndimage.binary_fill_holes(np.isin(cc, list(keep)))
    gy = None
    if gray is not None:
        g = cv2.GaussianBlur(gray.astype(np.float32), (3, 3), 0)
        gy = np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    rows = np.full(W, np.nan)
    for u in range(W):
        col = sky[:, u]
        if not col[0]:
            continue
        nz = np.flatnonzero(~col)
        if not len(nz) or nz[0] > H * 0.9:
            continue
        v = nz[0]
        if gy is not None:
            lo, hi = max(1, v - snap), min(H - 1, v + snap)
            v = lo + int(np.argmax(gy[lo:hi, u]))
            if gray[min(H - 1, v + 4), u] < min_level:          # vignette, not terrain
                continue
        rows[u] = v
    e = int(W * edge_frac)
    if e:
        rows[:e] = np.nan; rows[-e:] = np.nan
    med = ndimage.median_filter(np.nan_to_num(rows, nan=-1), size=25)
    rows[np.abs(rows - med) > 8] = np.nan
    return rows


# ---------------------------------------------------------------------------------- pose fitting
def skyline_residuals(cam: Camera, pano: Panorama, rows: np.ndarray):
    us = np.flatnonzero(~np.isnan(rows)).astype(float); vs = rows[~np.isnan(rows)].astype(float)
    az, el = cam.pixel_to_dir(us, vs)
    return el - pano.skyline_at(az)


def trimmed_loss(r, keep=0.8):
    a = np.sort(np.abs(r))
    return float(np.mean(a[: max(1, int(len(a) * keep))]))


def fit_extrinsics(cam: Camera, pano: Panorama, rows, yaw0: float, init=None, yaw_range=20.0):
    """Fit yaw, pitch, roll with the lens held fixed. Coarse grid, then bounded Powell."""
    def loss(p):
        return trimmed_loss(skyline_residuals(cam.with_params([p[0], p[1], p[2], cam.hfov, cam.k1]), pano, rows))
    if init is None:
        best = (1e9, None)
        for dy in np.arange(-15, 15.1, 1.0):
            for pt in np.arange(-10, 6.1, 1.0):
                l = loss([yaw0 + dy, pt, 0.0])
                if l < best[0]:
                    best = (l, [yaw0 + dy, pt, 0.0])
        init = best[1]
    res = optimize.minimize(loss, init, method='Powell',
                            bounds=[(yaw0 - yaw_range, yaw0 + yaw_range), (-15, 10), (-6, 6)],
                            options=dict(xtol=1e-4, ftol=1e-7))
    return cam.with_params([res.x[0], res.x[1], res.x[2], cam.hfov, cam.k1]), float(res.fun)


def fit_shared_lens(cams: list[Camera], panos: list[Panorama], rows: list, yaw0s: list[float],
                    hfov_grid=np.arange(94, 112.1, 2.0), k1_grid=np.arange(-0.04, 0.161, 0.04)):
    """Joint fit: one lens (hfov, k1) shared by every camera of the same model, extrinsics per camera.
    Cameras with a flat, hazy horizon cannot pin the lens down alone; the network can."""
    best = (1e9, None, None)
    inits = [None] * len(cams)
    for hf in hfov_grid:
        for k1 in k1_grid:
            fitted, tot = [], 0.0
            for i, (c, p, r, y0) in enumerate(zip(cams, panos, rows, yaw0s)):
                c2, l = fit_extrinsics(c.with_params([c.yaw, c.pitch, c.roll, hf, k1]), p, r, y0, inits[i])
                fitted.append(c2); tot += l
            if inits[0] is None:
                inits = [[c.yaw, c.pitch, c.roll] for c in fitted]
            if tot < best[0]:
                best = (tot, (float(hf), float(k1)), fitted)
    def joint(lens):
        return sum(fit_extrinsics(c.with_params([c.yaw, c.pitch, c.roll, lens[0], lens[1]]), p, r, y0, [c.yaw, c.pitch, c.roll])[1]
                   for c, p, r, y0 in zip(best[2], panos, rows, yaw0s))
    res = optimize.minimize(joint, list(best[1]), method='Powell', bounds=[(85, 125), (-0.1, 0.25)],
                            options=dict(xtol=1e-3, ftol=1e-6, maxiter=200))
    hf, k1 = [float(v) for v in res.x]
    out = []
    for c, p, r, y0 in zip(best[2], panos, rows, yaw0s):
        c2, _ = fit_extrinsics(c.with_params([c.yaw, c.pitch, c.roll, hf, k1]), p, r, y0, [c.yaw, c.pitch, c.roll])
        out.append(c2)
    return out, (hf, k1)


# ---------------------------------------------------------------------------------- back-projection
def backproject(cam: Camera, pano: Panorama, step: int = 8):
    """Ground hit for a grid of pixels: dict of u, v, az, el, dist (m), lat, lon (NaN = sky / beyond range)."""
    gu, gv = np.meshgrid(np.arange(step / 2, cam.width, step), np.arange(step / 2, cam.height, step))
    az, el = cam.pixel_to_dir(gu, gv)
    azu = pano.unwrap(az)
    ai = np.clip(np.round((azu - pano.az[0]) / (pano.az[1] - pano.az[0])).astype(int), 0, len(pano.az) - 1)
    dist = np.full(gu.shape, np.nan); lat = dist.copy(); lon = dist.copy()
    for idx in np.unique(ai):
        sel = ai == idx
        k = np.searchsorted(pano.cummax[idx], el[sel])     # first distance where terrain rises above the ray
        hit = k < len(pano.d)
        dd = np.full(k.shape, np.nan); la = dd.copy(); lo = dd.copy()
        dd[hit] = pano.d[k[hit]]; la[hit] = pano.lat[idx, k[hit]]; lo[hit] = pano.lon[idx, k[hit]]
        dist[sel] = dd; lat[sel] = la; lon[sel] = lo
    return dict(u=gu, v=gv, az=az, el=el, dist=dist, lat=lat, lon=lon)


def slope_aspect(dem: Raster, lat, lon):
    """Slope (deg) and the compass direction a slope faces (deg) at points."""
    dy_m = abs(dem.dlat) * 110540.0; dx_m = dem.dlon * 111320.0 * math.cos(math.radians(float(np.nanmean(lat))))
    gy, gx = np.gradient(dem.arr.astype(np.float32), dy_m, dx_m)
    ex = Raster(gx, dem.lon0, dem.dlon, dem.lat0, dem.dlat).sample(lat, lon)
    nn = Raster(-gy, dem.lon0, dem.dlon, dem.lat0, dem.dlat).sample(lat, lon)
    return np.degrees(np.arctan(np.hypot(ex, nn))), (np.degrees(np.arctan2(-ex, -nn)) + 360) % 360
