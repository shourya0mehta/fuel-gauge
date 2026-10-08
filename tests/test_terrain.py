"""Pose recovery on a synthetic DEM: render the skyline a known camera would see, then fit it back."""
import numpy as np

from fuelgauge.camera import Camera
from fuelgauge import terrain as T

LAT, LON = 33.0, -116.5


def synthetic_dem():
    """A few gaussian mountains on a 0.002 deg grid around the camera."""
    n = 801
    lat0, lon0, d = LAT + 0.8, LON - 0.8, 0.002
    lats = lat0 - (np.arange(n) + 0.5) * d; lons = lon0 + (np.arange(n) + 0.5) * d
    LA, LO = np.meshgrid(lats, lons, indexing='ij')
    z = np.full(LA.shape, 400.0)
    for la, lo, h, s in [(33.15, -116.45, 1500, 0.05), (33.10, -116.30, 1100, 0.04), (33.20, -116.60, 1300, 0.06),
                         (32.95, -116.35, 900, 0.03), (33.05, -116.20, 1700, 0.05)]:
        z += h * np.exp(-((LA - la) ** 2 + (LO - lo) ** 2) / (2 * s ** 2))
    return T.Raster(z, lon0, d, lat0, -d)


def rows_from_camera(cam, pano):
    rows = np.full(cam.width, np.nan)
    v = np.arange(0, cam.height, 0.25)
    for u in range(cam.width):
        az, el = cam.pixel_to_dir(np.full_like(v, u), v)
        below = np.flatnonzero(el < pano.skyline_at(az))
        if len(below) and below[0] > 0:
            rows[u] = v[below[0]]
    return rows


def test_pose_recovered_from_skyline():
    dem = synthetic_dem()
    pano = T.render_panorama(dem, LAT, LON, 600.0, -20, 160, az_step=0.05, max_d=30000)
    truth = Camera(768, 512, yaw=70.0, pitch=-1.5, roll=0.8, hfov=100.0, k1=0.05)
    rows = rows_from_camera(truth, pano)
    start = Camera(768, 512, yaw=60.0, pitch=0.0, roll=0.0, hfov=100.0, k1=0.05)
    fit, loss = T.fit_extrinsics(start, pano, rows, yaw0=62.0)
    assert abs(fit.yaw - truth.yaw) < 0.2
    assert abs(fit.pitch - truth.pitch) < 0.2
    assert abs(fit.roll - truth.roll) < 0.3
    assert loss < 0.05


def test_backprojection_hits_ground_below_horizon_and_sky_above():
    dem = synthetic_dem()
    pano = T.render_panorama(dem, LAT, LON, 600.0, -20, 160, max_d=30000)
    cam = Camera(768, 512, yaw=70.0, pitch=-5.0, roll=0.0, hfov=100.0)
    bp = T.backproject(cam, pano, step=16)
    assert np.isnan(bp['dist'][0]).all()                  # top row looks at sky
    bottom = bp['dist'][-1]
    assert np.isfinite(bottom).all() and (bottom < 30000).all()
    # nearer ground lower in the frame (same column)
    col = bp['dist'][:, bp['dist'].shape[1] // 2]
    finite = col[np.isfinite(col)]
    assert finite[-1] <= finite[0]


def test_raster_sampling_matches_grid_values():
    dem = synthetic_dem()
    r, c = 400, 300
    lat = dem.lat0 + (r + 0.5) * dem.dlat; lon = dem.lon0 + (c + 0.5) * dem.dlon
    assert abs(dem.sample(np.array([lat]), np.array([lon]))[0] - dem.arr[r, c]) < 1e-3
