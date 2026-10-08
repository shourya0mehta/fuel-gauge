"""PhenoCam Network archive (https://phenocam.nau.edu). Midday images and curated ROI series are public."""
from __future__ import annotations

import io
import os
import re
import time
import urllib.request
import datetime as dt

BASE = "https://phenocam.nau.edu"


def _get(url, timeout=60, tries=4):
    for a in range(tries):
        try:
            return urllib.request.urlopen(url, timeout=timeout).read()
        except Exception as e:  # noqa: BLE001
            err = e; time.sleep(2 * (a + 1))
    raise err


def cameras():
    import json
    return json.loads(_get(f"{BASE}/api/cameras/?format=json&limit=2000"))


def midday_paths(site):
    """Archive paths of one midday image per day."""
    txt = _get(f"{BASE}/data/archive/{site}/ROI/{site}-midday.txt").decode()
    return [l.strip() for l in txt.splitlines() if l.strip().endswith('.jpg')]


def path_date(p):
    m = re.search(r'_(\d{4})_(\d{2})_(\d{2})_(\d{2})(\d{2})', p)
    return dt.datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5])) if m else None


def download(path, dst, max_side=960):
    from PIL import Image
    if os.path.exists(dst):
        return dst
    im = Image.open(io.BytesIO(_get(BASE + path))).convert('RGB')
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
    im.save(dst, quality=90)
    return dst


def roi_series(site):
    """Curated (hand-drawn ROI) 1-day greenness CSV names for a site."""
    html = _get(f"{BASE}/data/archive/{site}/ROI/").decode()
    return sorted(f for f in set(re.findall(r'href="([^"]+_1day\.csv)"', html)) if 'transition' not in f)
