"""The leave-one-year-out evaluation must never let a year's own samples into its prediction."""
import numpy as np
import pandas as pd

from fuelgauge import evaluate as E


def make(seed=0, years=range(2005, 2015)):
    rng = np.random.default_rng(seed)
    rows = []
    for y in years:
        wet = rng.normal(0, 15)
        for d in pd.date_range(f'{y}-02-01', f'{y}-11-30', freq='14D'):
            for site, off in (('a', 0.0), ('b', 10.0)):
                season = 40 * np.cos((d.dayofyear - 100) / 365.25 * 2 * np.pi)
                x = season + wet + rng.normal(0, 3)
                rows.append(dict(site=site, date=d, year=y, x=x, lfmc=90 + off + season + wet + rng.normal(0, 4)))
    return E.add_season(pd.DataFrame(rows))


def test_held_out_year_predictions_ignore_that_years_targets():
    df = make()
    p1, _ = E.loyo(df, ['x'])
    df2 = df.copy()
    m = df2.year == 2010
    df2.loc[m, 'lfmc'] = df2.loc[m, 'lfmc'].sample(frac=1, random_state=3).values + 500   # scramble + shift
    p2, _ = E.loyo(df2, ['x'])
    a = p1[p1.year == 2010].sort_values(['site', 'date']).pred.values
    b = p2[p2.year == 2010].sort_values(['site', 'date']).pred.values
    assert np.allclose(a, b)


def test_informative_predictor_beats_season_alone():
    df = make()
    res, _ = E.compare(df, {'season': E.SEASON, 'x + season': ['x'] + E.SEASON})
    assert res['x + season']['rmse'] < res['season']['rmse']
    assert res['x + season']['anomaly_r'] > 0.5
    assert res['x + season']['years_beat_season'] >= 8
