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
