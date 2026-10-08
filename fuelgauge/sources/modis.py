"""MODIS MCD43A4 v6.1 nadir BRDF-adjusted reflectance at points, via Microsoft Planetary Computer.

Each point gets the mean of a 3 x 3 window of 500 m pixels. Bands: 1 red, 2 NIR, 3 blue, 4 green, 6 SWIR 1.6 um.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np

BANDS = (1, 2, 3, 4, 6)


def catalog():
    import pystac_client, planetary_computer
    return pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                     modifier=planetary_computer.sign_inplace)


def tile_of(cat, lat, lon):
    it = next(iter(cat.search(collections=["modis-43A4-061"], intersects={"type": "Point", "coordinates": [lon, lat]},
                              datetime="2015-06-01/2015-06-02").items()))
    return it.properties['modis:horizontal-tile'], it.properties['modis:vertical-tile']


def read_item(item, points: dict):
    import rasterio
    from rasterio.warp import transform
    out = {}
    names = list(points)
    for b in list(BANDS) + ['q']:
        key = f'Nadir_Reflectance_Band{b}' if b != 'q' else 'BRDF_Albedo_Band_Mandatory_Quality_Band1'
        with rasterio.open(item.assets[key].href) as src:
            xs, ys = transform('EPSG:4326', src.crs, [points[n][1] for n in names], [points[n][0] for n in names])
            for n, x, y in zip(names, xs, ys):
                r, c = src.index(x, y)
                w = src.read(1, window=((r - 1, r + 2), (c - 1, c + 2))).astype(float)
                if b == 'q':
                    out.setdefault(n, {})['qa_full'] = float(np.mean(w == 0))
                else:
                    w[w == 32767] = np.nan
                    out.setdefault(n, {})[f'b{b}'] = None if np.all(np.isnan(w)) else float(np.nanmean(w) * 1e-4)
    return out


def indices(df):
    """Add NDVI, NDII (NIR vs SWIR 1.6 um), visible GCC and GRVI columns to a frame with b1..b6."""
    df['ndvi'] = (df.b2 - df.b1) / (df.b2 + df.b1)
    df['ndii'] = (df.b2 - df.b6) / (df.b2 + df.b6)
    df['gcc'] = df.b4 / (df.b1 + df.b3 + df.b4)
    df['grvi'] = (df.b4 - df.b1) / (df.b4 + df.b1)
    return df


def series(points: dict, years=range(2000, 2024), every_days=8, workers=16):
    """Point time series for all points sharing one MODIS tile (call per tile)."""
    cat = catalog()
    h, v = tile_of(cat, *next(iter(points.values())))
    recs = []
    for y in years:
        its = {it.datetime.date(): it for it in cat.search(collections=["modis-43A4-061"], datetime=f"{y}-01-01/{y}-12-31",
               query={"modis:horizontal-tile": {"eq": h}, "modis:vertical-tile": {"eq": v}}).items()}
        sel = sorted((d, it) for d, it in its.items() if d.timetuple().tm_yday % every_days == 1)
        with ThreadPoolExecutor(workers) as ex:
            for d, vals in zip([d for d, _ in sel], ex.map(lambda a: read_item(a[1], points), sel)):
                for n, v_ in vals.items():
                    recs.append(dict(date=d, site=n, **v_))
    import pandas as pd
    return indices(pd.DataFrame(recs))
