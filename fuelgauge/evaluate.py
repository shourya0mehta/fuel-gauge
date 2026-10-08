"""Leave-one-year-out comparison of predictors of live fuel moisture.

Every model is ridge regression on top of a per-unit seasonal baseline: one intercept and one set of
day-of-year harmonics per sampling unit (a site and species), so "the calendar" already knows that sagebrush
and chamise dry down on different schedules. Predictors add to that baseline with shared coefficients. For each
held-out year, the model (and the baseline-only climatology used to score anomalies) is refit on the other
years only, and the held-out year's predictor values are clipped to the range seen in the training years.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SEASON = ['doy_s1', 'doy_c1', 'doy_s2', 'doy_c2']


def add_season(df, date_col='date'):
    doy = df[date_col].dt.dayofyear / 365.25 * 2 * np.pi
    df['doy_s1'], df['doy_c1'] = np.sin(doy), np.cos(doy)
    df['doy_s2'], df['doy_c2'] = np.sin(2 * doy), np.cos(2 * doy)
    return df


def _fit_predict(tr, te, feats, basecols):
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler
    Xtr = tr[feats].values; Xte = te[feats].values
    if feats:   # a held-out year is never extrapolated beyond the predictor range seen in training years
        Xte = np.clip(Xte, Xtr.min(0), Xtr.max(0))
        sc = StandardScaler().fit(Xtr); Xtr = sc.transform(Xtr); Xte = sc.transform(Xte)
    Xtr = np.hstack([Xtr, tr[basecols].values]); Xte = np.hstack([Xte, te[basecols].values])
    m = RidgeCV(alphas=np.logspace(-2, 3, 20)).fit(Xtr, tr.lfmc.values)
    return m.predict(Xte)


def loyo(df, feats, site_col='site', min_train=30, season_per_site=True):
    """df needs columns: site, date, year, lfmc, the season columns and `feats`. Returns (pred df, metrics).

    With season_per_site (default) the baseline is an intercept plus seasonal harmonics for every unit, and any
    SEASON columns listed in `feats` are folded into that baseline."""
    feats = [f for f in feats if not (season_per_site and f in SEASON)]
    t = df.dropna(subset=list(feats) + ['lfmc'] + SEASON).copy()
    sites = sorted(t[site_col].unique())
    base = {}
    for s in sites:
        ind = (t[site_col] == s).astype(float)
        base[f'_site_{s}'] = ind
        for h in SEASON:
            if season_per_site:
                base[f'_site_{s}_{h}'] = ind * t[h]
    t = pd.concat([t, pd.DataFrame(base, index=t.index)], axis=1)
    basecols = list(base) + ([] if season_per_site else SEASON)
    if not season_per_site:
        feats = [f for f in feats if f not in SEASON]
    t['pred'] = np.nan; t['clim'] = np.nan
    for y in sorted(t.year.unique()):
        tr, te = t[t.year != y], t[t.year == y]
        if len(tr) < min_train or not len(te):
            continue
        t.loc[te.index, 'pred'] = _fit_predict(tr, te, list(feats), basecols)
        t.loc[te.index, 'clim'] = _fit_predict(tr, te, [], basecols)
    t = t.dropna(subset=['pred'])
    return t, metrics(t)


def metrics(t, crit=80.0):
    if not len(t):
        return dict(n=0)
    err = t.pred - t.lfmc
    obs_a, pred_a = t.lfmc - t.clim, t.pred - t.clim
    by_year = t.assign(se=err ** 2, se_c=(t.clim - t.lfmc) ** 2).groupby('year')[['se', 'se_c']].mean()
    return dict(n=int(len(t)), years=int(t.year.nunique()), rmse=float(np.sqrt(np.mean(err ** 2))),
                mae=float(np.mean(np.abs(err))),
                r2=float(1 - np.sum(err ** 2) / np.sum((t.lfmc - t.lfmc.mean()) ** 2)),
                anomaly_r=float(np.corrcoef(obs_a, pred_a)[0, 1]) if pred_a.std() > 1e-9 and obs_a.std() > 1e-9 else 0.0,
                below80=float(((t.pred < crit) == (t.lfmc < crit)).mean()),
                years_beat_season=int((by_year.se < by_year.se_c - 1e-9).sum()))


def compare(df, sets: dict, common=True):
    """Run every predictor set on the same rows (rows where all sets' features exist when common=True)."""
    if common:
        need = sorted(set(sum(sets.values(), [])) | set(SEASON))
        df = df.dropna(subset=need + ['lfmc'])
    out, preds = {}, {}
    for name, feats in sets.items():
        p, m = loyo(df, feats)
        out[name] = m; preds[name] = p[['site', 'date', 'year', 'lfmc', 'pred', 'clim']]
    return out, preds
