"""measure(): automatic regions + white balance recover a seasonal cycle through camera colour drift."""
import numpy as np
import pandas as pd

from fuelgauge.measure import measure


def test_measure_recovers_season_through_drift(tmp_path):
    rng = np.random.default_rng(0)
    times = pd.date_range('2018-01-01', '2020-12-31', freq='3D')
    n, gh, gw = len(times), 24, 32
    doy = times.dayofyear.values
    season = np.cos(2 * np.pi * (doy - 100) / 365.25)                  # green in April, cured in October
    drift = np.linspace(1.0, 1.35, n)                                   # the sensor slowly reddens
    rgb = np.empty((n, gh, gw, 3), np.float32)
    rgb[:] = (110, 110, 110)                                            # grey sky / rock
    veg = np.zeros((gh, gw), bool); veg[11:, :24] = True                # brush across most of the lower frame
    rgb[:, veg, 0] = (95 - 12 * season)[:, None]
    rgb[:, veg, 1] = (100 + 12 * season)[:, None]
    rgb[:, veg, 2] = 70
    rgb += rng.normal(0, 0.8, rgb.shape).astype(np.float32)
    rgb[..., 0] *= drift[:, None, None]
    masters = np.full((1, 576, 768, 3), 120, np.uint8)
    np.savez_compressed(tmp_path / 'cam_blocks.npz', dates=np.array([str(t) for t in times]), rgb=rgb,
                        valid=np.ones((n, gh, gw), bool), edge_corr=np.full(n, 0.9), view=np.zeros(n, int),
                        masters=masters, master=masters[0])
    df, R, info = measure(str(tmp_path / 'cam_blocks.npz'), str(tmp_path / 'cam'), use_model=False)
    assert R['veg'][veg].mean() > 0.5 and veg[R['veg']].mean() > 0.95   # regions found without a model
    assert not (R['ref'] & veg).any()
    truth = pd.Series(season, index=times).resample('D').mean().interpolate()
    j = pd.concat([df, truth.rename('truth')], axis=1).dropna()
    raw = np.corrcoef(j.grvi_v0, j.truth)[0, 1]
    wb = np.corrcoef(j['index'], j.truth)[0, 1]
    assert wb > 0.9 and wb > raw + 0.05                                  # white balance removes the drift
    assert (tmp_path / 'cam_daily.csv').exists() and (tmp_path / 'cam_regions.png').exists()
