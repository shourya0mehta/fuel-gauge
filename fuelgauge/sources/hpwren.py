"""HPWREN camera network (https://hpwren.ucsd.edu). The public CDN keeps roughly the last 90 days.

Image lists:  https://cdn.hpwren.ucsd.edu/hpwren-cameras/<cam>/<YYYY>/<YYYYMMDD>/<YYYYMMDD>_<cam>_Q<n>.txt
Images:       https://cdn.hpwren.ucsd.edu/MTA/<cam>/large/<YYYYMMDD>/Q<n>/<unix>.jpg
Q1..Q8 are three-hour blocks of local time starting at midnight (Q5 = 12:00-15:00).
Camera positions and nominal headings: https://www.hpwren.ucsd.edu/cameras/sites.js
Attribution: images courtesy of HPWREN (http://hpwren.ucsd.edu).
"""
from __future__ import annotations

import datetime as dt
import io
import json
import time
import urllib.request
from zoneinfo import ZoneInfo

CDN = "https://cdn.hpwren.ucsd.edu"
TZ = ZoneInfo("America/Los_Angeles")


def _get(url, timeout=60, tries=4):
    for a in range(tries):
        try:
            return urllib.request.urlopen(url, timeout=timeout).read()
        except Exception as e:  # noqa: BLE001
            err = e; time.sleep(2 * (a + 1))
    raise err


def sites():
    """Camera sites with lat/long/elev and per-camera azimuth, from the public camera page."""
    src = _get("https://www.hpwren.ucsd.edu/cameras/sites.js").decode()
    return json.loads(src[src.index('{'): src.rindex('}') + 1])


def frame_times(cam, day: dt.date, quarter=5):
    ds = day.strftime('%Y%m%d')
    txt = _get(f"{CDN}/hpwren-cameras/{cam}/{day.year}/{ds}/{ds}_{cam}_Q{quarter}.txt").decode().split()
    return [int(x[:-4]) for x in txt if x.endswith('.jpg') and x[:-4].isdigit()]


def nearest_frames(cam, day: dt.date, targets=((12, 30), (13, 30), (14, 30)), tol_s=1200):
    ts = frame_times(cam, day)
    out = []
    for hh, mm in targets:
        t0 = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=TZ).timestamp()
        if not ts:
            break
        t = min(ts, key=lambda x: abs(x - t0))
        if abs(t - t0) <= tol_s:
            out.append(t)
    return out


def frame(cam, day: dt.date, unix_t: int, max_side=1536):
    from PIL import Image
    ds = day.strftime('%Y%m%d')
    im = Image.open(io.BytesIO(_get(f"{CDN}/MTA/{cam}/large/{ds}/Q5/{unix_t}.jpg"))).convert('RGB')
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    return im
