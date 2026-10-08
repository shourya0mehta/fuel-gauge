"""Command line interface.

    fuelgauge register-archive FRAMES_DIR OUT_PREFIX      # PhenoCam-style daily frames -> registered block colours
    fuelgauge calibrate CAM_ID IMAGE [--lat --lon --elev --agl --yaw]   # skyline -> camera pose + ground lookup
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys


def cmd_register_archive(a):
    from .archive import process
    from .sources.phenocam import path_date
    paths = sorted(glob.glob(os.path.join(a.frames, '*.jpg')))
    times = [path_date(p) for p in paths]
    keep = [(p, t) for p, t in zip(paths, times) if t is not None]
    process([p for p, _ in keep], [t.isoformat() for _, t in keep], a.out)


def cmd_calibrate(a):
    import numpy as np
    from PIL import Image
    from .camera import Camera
    from . import terrain as T, segment as S
    img = np.asarray(Image.open(a.image).convert('RGB'))
    H, W = img.shape[:2]
    import cv2
    small = cv2.resize(img, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    sky, _, _ = S.masks(S.labels(small))
    sky = cv2.resize(sky.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST).astype(bool)
    rows = T.skyline_rows(sky, cv2.cvtColor(img, cv2.COLOR_RGB2GRAY))
    dem = T.load_planetary('cop-dem-glo-30', 'data', a.lat, a.lon, 34000, cache=f'.cache/dem_{a.cam}.npz')
    pano = T.render_panorama(dem, a.lat, a.lon, a.elev + a.agl, a.yaw - 85, a.yaw + 85)
    cam = Camera(W, H, yaw=a.yaw, hfov=a.hfov, k1=a.k1)
    cam, loss = T.fit_extrinsics(cam, pano, rows, a.yaw)
    bp = T.backproject(cam, pano)
    json.dump(dict(camera=cam.to_dict(), loss=loss), sys.stdout, indent=1)
    np.savez_compressed(f'{a.cam}_lookup.npz', **bp)


def main(argv=None):
    p = argparse.ArgumentParser(prog='fuelgauge')
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('register-archive'); r.add_argument('frames'); r.add_argument('out'); r.set_defaults(fn=cmd_register_archive)
    c = sub.add_parser('calibrate'); c.add_argument('cam'); c.add_argument('image')
    for k, d in (('lat', None), ('lon', None), ('elev', None), ('agl', 10.0), ('yaw', 0.0), ('hfov', 101.15), ('k1', 0.08)):
        c.add_argument(f'--{k}', type=float, required=d is None, default=d)
    c.set_defaults(fn=cmd_calibrate)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == '__main__':
    main()
