"""Daily live update for the HPWREN cameras (runs in GitHub Actions).

For each camera and each missing day (the CDN keeps ~90 days, so missed runs backfill themselves):
  1. pull the 12:30, 13:30 and 14:30 frames,
  2. undo small shifts against the camera's reference view (phase correlation),
  3. measure GRVI and GCC on the 16 px block grid, median over the three frames,
  4. append one line to docs/live/history/<cam>.jsonl (per-block GRVI, int8-quantised) and
     recompute docs/live/summary.json for the page.
Each camera's block -> ground lookup (distance, lat/lon, land cover, aspect) was made once with
fuelgauge.terrain and is stored in live/lookup/<cam>.json.

    python live/update.py                 # all cameras, all missing days up to yesterday
    python live/update.py --frames DIR    # backfill from frames already on disk (DIR/<cam>/<YYYYMMDD>_*.jpg)
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import glob
import json
import os
import sys
from zoneinfo import ZoneInfo

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, 'docs', 'live')
B = 16
W, H = 1536, 1024
Q = 500.0          # GRVI quantisation: int8 = round(grvi * 500), range about -0.25..0.25
TZ = ZoneInfo('America/Los_Angeles')


def load_lookup(cam):
    lk = json.load(open(os.path.join(HERE, 'lookup', f'{cam}.json')))
    lk['usable_idx'] = np.flatnonzero(np.array(lk['usable'], bool))
    ref = os.path.join(HERE, 'lookup', f'{cam}_ref.png')
    lk['ref'] = np.asarray(__import__('PIL.Image', fromlist=['Image']).open(ref).convert('L'), np.float32) if os.path.exists(ref) else None
    return lk


def measure(images, lk):
    """images: list of RGB uint8 arrays (H x W). Returns per-usable-block GRVI and GCC medians, shifts."""
    import cv2
    gh, gw = H // B, W // B
    grvis, gccs, shifts = [], [], []
    win = None
    for im in images:
        if im.shape[:2] != (H, W):
            im = cv2.resize(im, (W, H), interpolation=cv2.INTER_AREA)
        if lk['ref'] is not None:
            g = cv2.cvtColor(cv2.resize(im, (W // 2, H // 2)), cv2.COLOR_RGB2GRAY).astype(np.float32)
            if win is None:
                win = cv2.createHanningWindow(g.shape[::-1], cv2.CV_32F)
            (dx, dy), resp = cv2.phaseCorrelate(lk['ref'], g, win)
            dx, dy = 2 * dx, 2 * dy
            if resp > 0.08 and 1 < max(abs(dx), abs(dy)) < 40:
                im = cv2.warpAffine(im, np.float32([[1, 0, -dx], [0, 1, -dy]]), (W, H), borderMode=cv2.BORDER_REFLECT)
                shifts.append((round(dx, 1), round(dy, 1)))
        bm = im.astype(np.float32).reshape(gh, B, gw, B, 3).mean(axis=(1, 3)).reshape(-1, 3)[lk['usable_idx']]
        with np.errstate(invalid='ignore', divide='ignore'):
            grvis.append((bm[:, 1] - bm[:, 0]) / (bm[:, 1] + bm[:, 0]))
            gccs.append(bm[:, 1] / bm.sum(1))
    return np.nanmedian(np.stack(grvis), 0), np.nanmedian(np.stack(gccs), 0), shifts


def encode(v):
    q = np.clip(np.round(np.nan_to_num(v, nan=-128 / Q) * Q), -128, 127).astype(np.int8)
    return base64.b64encode(q.tobytes()).decode()


def decode(s):
    return np.frombuffer(base64.b64decode(s), np.int8).astype(np.float32) / Q


def history(cam):
    p = os.path.join(OUT, 'history', f'{cam}.jsonl')
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p) if l.strip()]


def append(cam, rec):
    os.makedirs(os.path.join(OUT, 'history'), exist_ok=True)
    with open(os.path.join(OUT, 'history', f'{cam}.jsonl'), 'a') as f:
        f.write(json.dumps(rec, separators=(',', ':')) + '\n')


def fetch_day(cam, day):
    """Midday frames for one day from the HPWREN CDN, and their unix times."""
    from fuelgauge.sources import hpwren
    ims, ts = [], []
    try:
        times = hpwren.nearest_frames(cam, day)
    except Exception:  # noqa: BLE001  (no list for that day: camera offline or day not on the CDN)
        return [], []
    for t in times:
        try:
            ims.append(np.asarray(hpwren.frame(cam, day, t))); ts.append(int(t))
        except Exception:  # noqa: BLE001
            pass
    return ims, ts


def disk_day(frames_dir, cam, day):
    """Frames saved as DIR/<cam>/<YYYYMMDD>_<HHMM>_<unix>.jpg."""
    from PIL import Image
    fs = sorted(glob.glob(os.path.join(frames_dir, cam, day.strftime('%Y%m%d') + '_*.jpg')))
    ts = []
    for f in fs:
        tail = os.path.basename(f)[:-4].split('_')[-1]
        ts.append(int(tail) if tail.isdigit() else None)
    return [np.asarray(Image.open(f).convert('RGB')) for f in fs], ts


def frame_url(cam, day, t):
    return f"https://cdn.hpwren.ucsd.edu/MTA/{cam}/large/{day.replace('-', '')}/Q5/{t}.jpg"


LC = {10: 'tree', 20: 'shrub', 30: 'grass'}


def summarise(cams):
    """docs/live/summary.json: daily medians by land cover, per-block change over the last 90 days (median of the
    last 7 days minus the first 14 days of the window) and the URL of the most recent midday frame."""
    out = dict(updated=dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes'), cams={})
    for cam in cams:
        lk = load_lookup(cam); hist = history(cam)
        if not hist:
            continue
        lc = np.array(lk['lc'])[lk['usable_idx']]; dist = np.array([d if d is not None else np.nan for d in lk['dist']], float)[lk['usable_idx']]
        G = np.stack([decode(h['grvi']) for h in hist]); G[G <= -0.255] = np.nan
        dates = [h['date'] for h in hist]
        series = {}
        for k, name in LC.items():
            m = (lc == k) & (dist < 8000)
            if m.sum() >= 20:
                series[name] = [None if np.isnan(v) else round(float(v), 4) for v in np.nanmedian(G[:, m], 1)]
        end = dt.date.fromisoformat(dates[-1])
        w0 = next(i for i, d in enumerate(dates) if dt.date.fromisoformat(d) >= end - dt.timedelta(days=89))
        first = np.nanmedian(G[w0:w0 + 14], 0); last = np.nanmedian(G[-7:], 0)
        change = last - first
        latest = next((h for h in reversed(hist) if h.get('t') and h['t'][-1]), None)
        out['cams'][cam] = dict(dates=dates, series=series, n_days=len(dates),
                                change=[None if np.isnan(v) else round(float(v) * 1000, 1) for v in change],
                                first_window=[dates[w0], dates[min(w0 + 13, len(dates) - 1)]], last_window=[dates[max(0, len(dates) - 7)], dates[-1]],
                                latest=dict(date=latest['date'], url=frame_url(cam, latest['date'], latest['t'][-1])) if latest else None)
    os.makedirs(OUT, exist_ok=True)
    json.dump(out, open(os.path.join(OUT, 'summary.json'), 'w'), separators=(',', ':'))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', help='backfill from a directory of frames instead of the CDN')
    ap.add_argument('--start', help='first day to fill (YYYY-MM-DD) if a camera has no history')
    ap.add_argument('--end', help='last day to fill (default: yesterday, Pacific time)')
    ap.add_argument('--cams', help='comma-separated camera ids (default: all with a lookup)')
    a = ap.parse_args()
    cams = a.cams.split(',') if a.cams else sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(HERE, 'lookup', '*.json')))
    end = dt.date.fromisoformat(a.end) if a.end else (dt.datetime.now(TZ).date() - dt.timedelta(days=1))
    for cam in cams:
        lk = load_lookup(cam)
        hist = history(cam)
        have = {h['date'] for h in hist}
        start = dt.date.fromisoformat(a.start) if a.start else (dt.date.fromisoformat(hist[-1]['date']) + dt.timedelta(days=1) if hist else end - dt.timedelta(days=80))
        start = max(start, end - dt.timedelta(days=85))  if not a.frames else start
        d = start; added = 0
        while d <= end:
            if d.isoformat() not in have:
                ims, ts = disk_day(a.frames, cam, d) if a.frames else fetch_day(cam, d)
                if ims:
                    grvi, gcc, shifts = measure(ims, lk)
                    append(cam, dict(date=d.isoformat(), n=len(ims), t=ts, shift=shifts, grvi=encode(grvi),
                                     gcc_med=round(float(np.nanmedian(gcc)), 5)))
                    added += 1
            d += dt.timedelta(days=1)
        print(cam, 'added', added, 'days', flush=True)
    summarise(cams)


if __name__ == '__main__':
    main()
