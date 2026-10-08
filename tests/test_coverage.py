"""Viewshed and line-of-sight on a synthetic landscape: flat ground with a tall ridge east of the camera."""
import importlib.util
import os

import numpy as np

spec = importlib.util.spec_from_file_location("coverage", os.path.join(os.path.dirname(__file__), "..", "scripts", "coverage.py"))
cov = importlib.util.module_from_spec(spec); spec.loader.exec_module(cov)


def setup_grid(monkeypatch, n=700):
    monkeypatch.setattr(cov, 'NX', n); monkeypatch.setattr(cov, 'NY', n)
    monkeypatch.setattr(cov, 'W', -120.0); monkeypatch.setattr(cov, 'N', 37.0)
    dem = np.zeros((n, n), np.int16)
    dem[:, 400:405] = 500                       # a 500 m wall running north-south, east of centre
    return dem


def test_ridge_hides_the_ground_behind_it(monkeypatch):
    dem = setup_grid(monkeypatch)
    lat, lon = 37.0 - 350 * cov.RES, -120.0 + 350 * cov.RES      # camera at the centre, 10 m mast
    rr, cc, dd = cov.viewshed(dem, lat, lon, 10.0, r_max=25000)
    seen = np.zeros_like(dem, bool); seen[rr, cc] = True
    assert seen[350, 300] and seen[350, 380]                        # open ground to the west and before the wall
    assert seen[350, 400]                                           # the face of the wall
    assert not seen[350, 450] and not seen[350, 600]                # hidden behind it


def test_smoke_column_clears_the_ridge(monkeypatch):
    dem = setup_grid(monkeypatch)
    lat0, lon0 = 37.0 - 350 * cov.RES, -120.0 + 350 * cov.RES
    lat, lon = lat0, -120.0 + 430 * cov.RES                          # 2.2 km behind the wall
    assert not cov.sees_point(dem, lat0, lon0, 10.0, lat, lon, 2.0)  # the ground is hidden
    assert cov.sees_point(dem, lat0, lon0, 10.0, lat, lon, 2000.0)   # a tall smoke column is not


def test_package_viewshed_on_a_raster():
    from fuelgauge.terrain import Raster
    from fuelgauge import viewshed as V
    n, res = 400, 1 / 1200
    arr = np.zeros((n, n), np.float32); arr[:, 250:253] = 400.0          # a ridge east of the camera
    dem = Raster(arr, -120.0, res, 37.0, -res)
    lat, lon = 37.0 - 200.5 * res, -120.0 + 200.5 * res
    vis = V.viewshed(dem, lat, lon, mast_m=10, r_max=12000)
    assert vis[200, 150] and vis[200, 240]
    assert not vis[200, 300]
    assert not V.sees_point(dem, lat, lon, 10, 37.0 - 200.5 * res, -120.0 + 300.5 * res, 0)
    assert V.sees_point(dem, lat, lon, 10, 37.0 - 200.5 * res, -120.0 + 300.5 * res, 1500)


def test_siting_picks_the_hidden_valley():
    from fuelgauge.terrain import Raster
    from fuelgauge import viewshed as V
    n, res = 300, 1 / 1200
    arr = np.zeros((n, n), np.float32)
    arr[:, 140:146] = 600.0                                              # a tall ridge down the middle
    arr[150, 260] = 120.0                                                # a knoll in the hidden east valley
    dem = Raster(arr, -120.0, res, 37.0, -res)
    cam = (37.0 - 150.5 * res, -120.0 + 40.5 * res)                      # existing camera in the west valley
    cands = [(37.0 - 150.5 * res, -120.0 + 60.5 * res, 0.0),            # more of the west valley
             (37.0 - 150.5 * res, -120.0 + 260.5 * res, 120.0)]         # the east knoll
    picks = V.site(dem, existing=[cam], k=2, r_max=9000, cands=cands, az_step=1.0)
    assert picks[0]['lon'] == round(-120.0 + 260.5 * res, 5)
    assert picks[0]['new_km2'] > 5
    assert len(picks) == 1 or picks[1]['new_cells'] < picks[0]['new_cells']
