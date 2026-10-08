"""Near-infrared companions of the registered PhenoCam photos.

IR-capable PhenoCams take a second photo with the infrared-cut filter removed a few seconds after each colour
photo, from the same position. For every registered colour photo this downloads its IR twin plus the exposure
settings of both (from the archive's .meta files), which camera NDVI needs (Petach et al. 2014).

    DATA=data python scripts/fetch_nir.py cam1,cam2,...
Writes $DATA/nir/<cam>/<IR file>.jpg and $DATA/nir/<cam>_exposure.json
"""
import io
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

DATA = os.environ.get('DATA', 'data')
BASE = 'https://phenocam.nau.edu/data/archive'


def get(url, timeout=60, tries=3):
    for a in range(tries):
        try:
            return urllib.request.urlopen(url, timeout=timeout).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            err = e
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(2 * (a + 1))
    return None


def exposure(meta):
    if not meta:
        return None
    m = re.search(rb'^exposure=(\d+)', meta, re.M)
    return int(m.group(1)) if m else None


IR_BY_DATE = {}


def ir_by_date(cam):
    """Midday IR file per date from PhenoCam's NDVI products (used when the IR twin has a different timestamp)."""
    import glob
    import pandas as pd
    out = {}
    for f in glob.glob(os.path.join(DATA, 'phenocam_roi', f'{cam}_*_ndvi_1day.csv')):
        d = pd.read_csv(f, comment='#', usecols=['date', 'midday_ir_filename']).dropna()
        out.update(dict(zip(d.date, d.midday_ir_filename)))
    return out


def job(args):
    cam, rgb = args
    m = re.search(r'_(\d{4})_(\d{2})_(\d{2})_\d{6}', rgb)
    d = f'{BASE}/{cam}/{m[1]}/{m[2]}'
    ir = rgb.replace(f'{cam}_', f'{cam}_IR_', 1)
    out = dict(rgb=rgb, ir=ir)
    dst = os.path.join(DATA, 'nir', cam, ir)
    if not os.path.exists(dst):
        b = get(f'{d}/{ir}')
        if b is None:      # twin not at the same second: fall back to that day's midday IR photo
            alt = IR_BY_DATE.get(cam, {}).get(f'{m[1]}-{m[2]}-{m[3]}')
            if not alt:
                return out
            ir = alt; out['ir'] = ir; dst = os.path.join(DATA, 'nir', cam, ir)
            b = None if os.path.exists(dst) else get(f'{d}/{ir}')
            if b is None and not os.path.exists(dst):
                return out
        if b is not None:
            im = Image.open(io.BytesIO(b)).convert('RGB'); im.thumbnail((960, 960), Image.LANCZOS); im.save(dst, quality=90)
    out['e_ir'] = exposure(get(f'{d}/{ir[:-4]}.meta'))
    out['e_rgb'] = exposure(get(f'{d}/{rgb[:-4]}.meta'))
    return out


def main(cams):
    for cam in cams:
        qa = json.load(open(os.path.join(DATA, 'proc', f'{cam}_qa.json')))
        files = [r['file'] for r in qa['recs'] if r.get('reg')]
        os.makedirs(os.path.join(DATA, 'nir', cam), exist_ok=True)
        IR_BY_DATE[cam] = ir_by_date(cam)
        ep = os.path.join(DATA, 'nir', f'{cam}_exposure.json')
        have = {r['rgb']: r for r in json.load(open(ep))} if os.path.exists(ep) else {}
        todo = [(cam, f) for f in files if f not in have or have[f].get('e_ir') is None]
        t0 = time.time()
        with ThreadPoolExecutor(12) as ex:
            for i, r in enumerate(ex.map(job, todo)):
                have[r['rgb']] = r
                if i % 500 == 0:
                    print(cam, i, len(todo), round(time.time() - t0), 's', flush=True)
                    json.dump(list(have.values()), open(ep, 'w'))
        json.dump(list(have.values()), open(ep, 'w'))
        ok = sum(1 for r in have.values() if r.get('e_ir') and r.get('e_rgb'))
        print(cam, 'done', ok, 'of', len(files), 'with IR and exposures', flush=True)


if __name__ == '__main__':
    main(sys.argv[1].split(','))
