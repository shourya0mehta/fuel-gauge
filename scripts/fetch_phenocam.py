"""PhenoCam inputs for the study: camera metadata, curated ROI series, and one midday photo per day for every
camera in study/cameras.json, limited to dates that overlap its fuel samples (90 days before the first through
the last, capped at mid-2023). Photos are resized to 960 px on the long side.

    DATA=data python scripts/fetch_phenocam.py [camera,camera,...]
"""
import datetime as dt
import io
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from PIL import Image

DATA = os.environ.get('DATA', 'data')
HERE = os.path.dirname(__file__)
BASE = 'https://phenocam.nau.edu'
sel = json.load(open(os.path.join(HERE, '..', 'study', 'cameras.json')))
names = sys.argv[1].split(',') if len(sys.argv) > 1 else [r['cam'] for r in sel]
us = pd.read_parquet(os.path.join(DATA, 'globe', 'globe_usa.parquet'))


def get(url, timeout=60):
    for a in range(4):
        try:
            return urllib.request.urlopen(url, timeout=timeout).read()
        except Exception as e:  # noqa: BLE001
            err = e; time.sleep(2 * (a + 1))
    raise err


os.makedirs(os.path.join(DATA, 'raw'), exist_ok=True)
meta = os.path.join(DATA, 'raw', 'phenocam_cameras.json')
if not os.path.exists(meta):
    open(meta, 'wb').write(get(f'{BASE}/api/cameras/?format=json&limit=2000'))
roi_dir = os.path.join(DATA, 'phenocam_roi'); os.makedirs(roi_dir, exist_ok=True)
jobs = []
for r in sel:
    site = r['cam']
    if site not in names:
        continue
    # curated (hand-drawn) ROI series, for the comparison with automatic regions
    try:
        listing = get(f'{BASE}/data/archive/{site}/ROI/').decode()
        for f in sorted(set(re.findall(rf'({re.escape(site)}_[A-Z]{{2}}_\d{{4}}_1day\.csv)', listing))):
            dst = os.path.join(roi_dir, f)
            if not os.path.exists(dst):
                open(dst, 'wb').write(get(f'{BASE}/data/archive/{site}/ROI/{f}'))
    except Exception as e:  # noqa: BLE001
        print(site, 'no ROI listing', e)
    out = os.path.join(DATA, 'phenocam', site); os.makedirs(out, exist_ok=True)
    mp = os.path.join(DATA, 'phenocam', f'{site}-midday.txt')
    if not os.path.exists(mp):
        open(mp, 'wb').write(get(f'{BASE}/data/archive/{site}/ROI/{site}-midday.txt'))
    x = us[us['Site name'].isin([s[0] for s in r['good']])]
    d0 = (x.date.min() - pd.Timedelta(days=90)).date(); d1 = min(x.date.max(), pd.Timestamp('2023-06-30')).date()
    for p in (l.strip() for l in open(mp)):
        m = re.search(r'_(\d{4})_(\d{2})_(\d{2})_', p)
        if p.endswith('.jpg') and m and d0 <= dt.date(int(m[1]), int(m[2]), int(m[3])) <= d1:
            jobs.append((out, p))


def dl(job):
    out, p = job
    dst = os.path.join(out, os.path.basename(p))
    if os.path.exists(dst):
        return 'skip'
    try:
        im = Image.open(io.BytesIO(get(BASE + p))).convert('RGB')
        im.thumbnail((960, 960), Image.LANCZOS); im.save(dst, quality=90)
        return 'ok'
    except Exception:  # noqa: BLE001
        return 'fail'


st = {}
with ThreadPoolExecutor(16) as ex:
    for i, r in enumerate(ex.map(dl, jobs)):
        st[r] = st.get(r, 0) + 1
        if i % 1000 == 0:
            print(i, len(jobs), st, flush=True)
print('done', st)
