"""Globe-LFMC 2.0 field live fuel moisture (Yebra et al. 2024, Scientific Data; figshare collection 6980418)."""
from __future__ import annotations

import os
import urllib.request

URL = "https://ndownloader.figshare.com/files/45049786"


def load(cache_dir='data/globe', country='USA'):
    """Returns a DataFrame: site, lat, lon, date, lfmc, species, plus the original columns."""
    import pandas as pd
    os.makedirs(cache_dir, exist_ok=True)
    pq = os.path.join(cache_dir, 'globe_lfmc_2.parquet')
    if not os.path.exists(pq):
        xl = os.path.join(cache_dir, 'globe_lfmc_2.xlsx')
        if not os.path.exists(xl):
            urllib.request.urlretrieve(URL, xl)
        df = pd.read_excel(xl, sheet_name='LFMC data')
        for c in df.columns:
            if df[c].dtype == object:
                df[c] = df[c].astype(str)
        df.to_parquet(pq)
    df = pd.read_parquet(pq)
    if country:
        df = df[df['Country'] == country].copy()
    df['site'] = df['Site name']
    df['lat'] = pd.to_numeric(df['Latitude (WGS84, EPSG:4326)'], errors='coerce')
    df['lon'] = pd.to_numeric(df['Longitude (WGS84, EPSG:4326)'], errors='coerce')
    df['date'] = pd.to_datetime(df['Sampling date (YYYYMMDD)'], errors='coerce')
    df['lfmc'] = pd.to_numeric(df['LFMC value (%)'], errors='coerce')
    df['species'] = df['Species collected']
    return df.dropna(subset=['lat', 'lon', 'date', 'lfmc'])
