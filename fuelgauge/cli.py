"""Command line interface.

    fuelgauge run PHOTOS_DIR OUT_PREFIX                   # register + measure in one go
    fuelgauge register-archive PHOTOS_DIR OUT_PREFIX      # years of photos from one camera -> registered block colours
    fuelgauge measure OUT_PREFIX [--no-model]             # registered blocks -> daily vegetation series + regions image
    fuelgauge calibrate CAM_ID IMAGE --lat --lon --elev [--agl --yaw]  # skyline -> camera pose + pixel-to-ground lookup
    fuelgauge viewshed CAMERAS.csv OUT.tif [--radius 30000 --mast 10]  # what a set of cameras can see (lat,lon per row)
    fuelgauge site CAMERAS.csv [--k 10 --radius 30000]    # where new cameras would see the most unseen ground

Photo times come from the file name (2019-06-14_1230, 20190614T123000, PhenoCam's site_2019_06_14_123005)
or, failing that, the photo's EXIF capture time.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys


_STAMP = re.compile(r'(\d{4})[-_]?(\d{2})[-_]?(\d{2})(?:[T_ -]?(\d{2})[-_:]?(\d{2})(?:[-_:]?(\d{2}))?)?')


def photo_time(path):
    """Capture time from the file name, else EXIF DateTimeOriginal, else None."""
    import datetime as dt
    for m in _STAMP.finditer(os.path.basename(path)):
        y, mo, d, h, mi, se = (int(x) if x else 0 for x in m.groups())
        if 1990 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31 and h < 24 and mi < 60:
            return dt.datetime(y, mo, d, h, mi, se if se < 60 else 0)
    m = re.search(r'(?<!\d)(1[0-9]{9})(?!\d)', os.path.basename(path))      # Unix time, as HPWREN names frames
    if m:
        return dt.datetime.fromtimestamp(int(m[1]), dt.timezone.utc).replace(tzinfo=None)
    try:
        from PIL import Image
        ex = Image.open(path).getexif()
        v = ex.get_ifd(0x8769).get(36867) or ex.get(306)
        return dt.datetime.strptime(v, '%Y:%m:%d %H:%M:%S') if v else None
    except Exception:
        return None


def _photos(folder):
    paths = sorted(p for p in glob.glob(os.path.join(folder, '*')) if p.lower().endswith(('.jpg', '.jpeg', '.png')))
    keep = [(p, t) for p, t in ((p, photo_time(p)) for p in paths) if t is not None]
    if not keep:
        sys.exit(f'no photos with a readable date in {folder}')
    keep.sort(key=lambda x: x[1])
    print(f'{len(keep)} of {len(paths)} photos dated, {keep[0][1]:%Y-%m-%d} to {keep[-1][1]:%Y-%m-%d}')
    return [p for p, _ in keep], [t.isoformat() for _, t in keep]


def cmd_register_archive(a):
    from .archive import process
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    process(*_photos(a.frames), a.out)


def cmd_measure(a):
    from .measure import measure
    df, R, info = measure(f'{a.out}_blocks.npz', a.out, use_model=not a.no_model)
    print(f"{info['days']} days measured over {len(info['views'])} view(s); wrote {a.out}_daily.csv and {a.out}_regions.png")


def cmd_run(a):
    cmd_register_archive(a)
    cmd_measure(a)


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


def cmd_viewshed(a):
    import csv
    import numpy as np
    from . import terrain as T, viewshed as V
    cams = [(float(r['lat']), float(r['lon'])) for r in csv.DictReader(open(a.cameras))]
    lat = float(np.mean([c[0] for c in cams])); lon = float(np.mean([c[1] for c in cams]))
    span = max(max(abs(c[0] - lat) * 110540 for c in cams), max(abs(c[1] - lon) * 111320 * np.cos(np.radians(lat)) for c in cams))
    dem = T.load_planetary('cop-dem-glo-90', 'data', lat, lon, span + a.radius + 2000)
    count = V.coverage(dem, cams, a.mast, a.radius)
    import rasterio
    from rasterio.transform import from_origin
    with rasterio.open(a.out, 'w', driver='GTiff', height=count.shape[0], width=count.shape[1], count=1, dtype='uint16',
                       crs='EPSG:4326', transform=from_origin(dem.lon0, dem.lat0, dem.dlon, -dem.dlat), compress='deflate') as dst:
        dst.write(count, 1)
    print(f'{len(cams)} cameras; {(count > 0).mean() * 100:.1f}% of the area in view; wrote {a.out}')


def cmd_site(a):
    import csv
    import numpy as np
    from . import terrain as T, viewshed as V
    cams = [(float(r['lat']), float(r['lon'])) for r in csv.DictReader(open(a.cameras))]
    lat = a.lat if a.lat is not None else float(np.mean([c[0] for c in cams]))
    lon = a.lon if a.lon is not None else float(np.mean([c[1] for c in cams]))
    span = a.area or max(max(abs(c[0] - lat) * 110540 for c in cams), max(abs(c[1] - lon) * 111320 * np.cos(np.radians(lat)) for c in cams)) + a.radius
    dem = T.load_planetary('cop-dem-glo-90', 'data', lat, lon, span)
    picks = V.site(dem, cams, a.k, a.mast, a.radius, block_m=a.block, progress=lambda j, n: j % 50 == 0 and print(f'candidate {j}/{n}'))
    w = csv.DictWriter(sys.stdout, ['lat', 'lon', 'elev', 'new_cells', 'new_km2'])
    w.writeheader(); w.writerows(picks)


HELP = {'run': 'register a folder of photos and measure it', 'register-archive': 'register years of photos from one camera onto fixed views', 'measure': 'registered blocks -> daily vegetation series and a regions image', 'calibrate': 'solve camera pose from its skyline; write a pixel-to-ground lookup', 'viewshed': 'map what a set of cameras can see', 'site': 'pick new camera sites that see the most unseen ground'}


def main(argv=None):
    p = argparse.ArgumentParser(prog='fuelgauge')
    sub = p.add_subparsers(dest='cmd', required=True)
    for name, fn in (('run', cmd_run), ('register-archive', cmd_register_archive)):
        r = sub.add_parser(name, help=HELP[name]); r.add_argument('frames'); r.add_argument('out'); r.set_defaults(fn=fn, no_model=False)
        if name == 'run':
            r.add_argument('--no-model', action='store_true')
    m = sub.add_parser('measure', help=HELP['measure']); m.add_argument('out'); m.add_argument('--no-model', action='store_true'); m.set_defaults(fn=cmd_measure)
    c = sub.add_parser('calibrate', help=HELP['calibrate']); c.add_argument('cam'); c.add_argument('image')
    for k, d in (('lat', None), ('lon', None), ('elev', None), ('agl', 10.0), ('yaw', 0.0), ('hfov', 101.15), ('k1', 0.08)):
        c.add_argument(f'--{k}', type=float, required=d is None, default=d)
    c.set_defaults(fn=cmd_calibrate)
    v = sub.add_parser('viewshed', help=HELP['viewshed']); v.add_argument('cameras'); v.add_argument('out')
    v.add_argument('--radius', type=float, default=30000.0); v.add_argument('--mast', type=float, default=10.0)
    v.set_defaults(fn=cmd_viewshed)
    st = sub.add_parser('site', help=HELP['site']); st.add_argument('cameras')
    for k, d in (('k', 10), ('radius', 30000.0), ('mast', 10.0), ('block', 6000.0), ('area', None), ('lat', None), ('lon', None)):
        st.add_argument(f'--{k}', type=type(d) if d is not None else float, default=d)
    st.set_defaults(fn=cmd_site)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == '__main__':
    main()
