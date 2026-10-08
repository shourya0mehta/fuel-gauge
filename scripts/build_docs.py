"""Build docs/docs.html (guide + API reference) from the package's own docstrings and CLI.

    python scripts/build_docs.py
Rerun after changing a public function; the reference is generated, the guide text lives below.
"""
from __future__ import annotations

import html
import importlib
import inspect
import io
import os
import re
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import fuelgauge  # noqa: E402
from fuelgauge import cli  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
MODULES = [('Pipeline', ['archive', 'measure', 'track', 'quality', 'colour', 'rois', 'segment']),
           ('Geometry', ['camera', 'terrain', 'viewshed']),
           ('Evaluation and data', ['evaluate', 'sources.phenocam', 'sources.hpwren', 'sources.lfmc', 'sources.modis'])]
SKIP = {'cli'}

GUIDE = [
    ('install', 'Install', '''
<p>Python 3.10 or newer. The core package needs NumPy, SciPy, pandas, OpenCV and Pillow. Extras add what each stage needs:</p>
<pre class="code">pip install "fuelgauge[geo,seg,eval] @ git+https://github.com/shourya0mehta/fuel-gauge"</pre>
<table class="ref"><tbody>
<tr><td><code>geo</code></td><td>rasterio, pystac-client, planetary-computer: terrain and land cover from Microsoft Planetary Computer, GeoTIFF output</td></tr>
<tr><td><code>seg</code></td><td>onnxruntime: the SegFormer-B2 model for sky and vegetation (about 100 MB, downloaded once to <code>~/.cache/fuelgauge</code>, override with <code>FUELGAUGE_CACHE</code>)</td></tr>
<tr><td><code>eval</code></td><td>scikit-learn, pyarrow, openpyxl: scoring against field data</td></tr>
</tbody></table>'''),
    ('quickstart', 'Quickstart', '''
<p>Put the photos from one fixed camera in a folder. Capture times are read from the file name (<code>2019-06-14_1230.jpg</code>, <code>IMG_20190614T123000.jpg</code>, PhenoCam's <code>site_2019_06_14_123005.jpg</code>, or a Unix timestamp as HPWREN uses) and otherwise from EXIF.</p>
<pre class="code">fuelgauge run photos/ out/ridge</pre>
<p>That registers every usable photo onto fixed views, then measures them. A thousand photos take about five minutes on two CPU cores. You get:</p>
<table class="ref"><tbody>
<tr><td><code>out/ridge_blocks.npz</code></td><td>dates, mean RGB of every 24-pixel block of every registered photo (768 x 576 working size), block validity, haze score, stretch and view index, and each view's anchor frame</td></tr>
<tr><td><code>out/ridge_qa.json</code></td><td>per-photo screening metrics and registration transform, the stretches and how they were joined into views</td></tr>
<tr><td><code>out/ridge_daily.csv</code></td><td>daily <code>grvi</code>, <code>grvi_wb</code> and <code>gcc_wb</code> per view (suffix <code>_v0</code>, <code>_v1</code>...) and <code>index</code>, the white-balanced GRVI standardised per view and joined across views</td></tr>
<tr><td><code>out/ridge_regions.png</code></td><td>the anchor frame with measured vegetation (green) and colour reference blocks (orange)</td></tr>
</tbody></table>
<p>Open the regions image first. If the green blocks sit on the vegetation you care about, the series is measuring it. Without the <code>seg</code> extra, run <code>fuelgauge measure out/ridge --no-model</code> and regions are chosen by seasonal swing alone.</p>'''),
    ('calibrate', 'Calibrate a camera', '''
<p>Calibration needs one clear photo with a visible skyline, the camera's latitude and longitude, its ground elevation in metres, and a rough heading. Height above ground defaults to 10 m.</p>
<pre class="code">fuelgauge calibrate ridge frame.jpg --lat 33.4008 --lon -117.1905 --elev 483 --yaw 90</pre>
<p>It prints the fitted camera (heading, tilt, roll, field of view, distortion) and the skyline loss, and writes <code>ridge_lookup.npz</code> with the distance, latitude and longitude of every 8-pixel block. The default lens (101.15&deg;, k&#8321; = 0.080) is the one fitted to HPWREN's Mobotix cameras; pass <code>--hfov</code> and <code>--k1</code> for other hardware, or fit a shared lens for several cameras of one model with <code>terrain.fit_shared_lens</code>.</p>
<p>Check the fit by drawing the rendered skyline over the photo (<code>terrain.skyline_residuals</code> gives the per-column error). Errors under 0.2&deg; are typical; a large error usually means the heading guess is more than 20&deg; off or the location is wrong.</p>'''),
    ('network', 'Map coverage and site cameras', '''
<p>Both commands take a CSV with <code>lat</code> and <code>lon</code> columns, one row per camera, and pull a 90 m terrain model for the area around them.</p>
<pre class="code">fuelgauge viewshed cameras.csv coverage.tif --radius 30000 --mast 10
fuelgauge site cameras.csv --k 10 --block 6000 > new_sites.csv</pre>
<p><code>coverage.tif</code> counts the cameras with line of sight to each cell. <code>site</code> ranks hilltops (the highest cell in every <code>--block</code>-metre square) by how much unseen ground each would add, counting each cell once; <code>--area</code> (metres) and <code>--lat</code>/<code>--lon</code> set the search area. For a statewide run like the one on this site, see <code>scripts/coverage.py</code> and <code>scripts/siting.py</code>, which tile the work.</p>'''),
    ('evaluate', 'Score against field data', '''
<p><code>evaluate.compare</code> runs leave-one-year-out ridge regressions on top of a baseline with its own intercept and seasonal harmonics for every site and species. Predictors only get credit for knowing a year was unusual. The input is one row per field sample with <code>site</code>, <code>date</code>, <code>year</code>, <code>lfmc</code> and your predictor columns.</p>
<pre class="code">from fuelgauge import evaluate
samples = evaluate.add_season(samples)
scores, preds = evaluate.compare(samples, {"camera": ["cam_g", "cam_d"], "season": []})
scores["camera"]["anomaly_r"], scores["camera"]["years_beat_season"]</pre>'''),
]


def sig(obj):
    try:
        return str(inspect.signature(obj))
    except (TypeError, ValueError):
        return '(...)'


def doc(obj):
    d = inspect.getdoc(obj) or ''
    return html.escape(d)


def members(mod):
    out = []
    for name, obj in vars(mod).items():
        if name.startswith('_') or getattr(obj, '__module__', None) != mod.__name__:
            continue
        if inspect.isfunction(obj) or inspect.isclass(obj):
            out.append((name, obj))
    return sorted(out, key=lambda x: inspect.getsourcelines(x[1])[1])


def cli_help():
    p = []
    for name in ['run', 'register-archive', 'measure', 'calibrate', 'viewshed', 'site']:
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                cli.main([name, '--help'])
        except SystemExit:
            pass
        p.append((name, buf.getvalue().replace('usage: fuelgauge', 'fuelgauge')))
    return p


def main():
    nav, body = [], []
    nav.append('<p class="grp">Guide</p>')
    for slug, title, text in GUIDE:
        nav.append(f'<a href="#{slug}">{title}</a>')
        body.append(f'<section id="{slug}"><h2>{title}</h2>{text}</section>')
    nav.append('<a href="#cli">Command line</a>')
    cl = ''.join(f'<h3 id="cli-{n}"><code>fuelgauge {n}</code></h3><pre class="code">{html.escape(t.strip())}</pre>' for n, t in cli_help())
    body.append(f'<section id="cli"><h2>Command line</h2><p>{html.escape(cli.HELP["run"]).capitalize()}, or run each stage on its own.</p>{cl}</section>')
    for group, mods in MODULES:
        nav.append(f'<p class="grp">{group}</p>')
        for m in mods:
            mod = importlib.import_module(f'fuelgauge.{m}')
            nav.append(f'<a href="#mod-{m}">{m}</a>')
            items = []
            for name, obj in members(mod):
                kind = 'class' if inspect.isclass(obj) else 'def'
                items.append(f'<div class="fn" id="{m}.{name}"><p class="sig"><span class="k">{kind}</span> <b>{name}</b>{html.escape(sig(obj))}</p>'
                             + (f'<pre class="doc">{doc(obj)}</pre>' if doc(obj) else '') + '</div>')
                if inspect.isclass(obj):
                    for mn, mo in vars(obj).items():
                        if mn.startswith('_') or not (inspect.isfunction(mo) or isinstance(mo, property)):
                            continue
                        f = mo.fget if isinstance(mo, property) else mo
                        items.append(f'<div class="fn sub"><p class="sig"><b>{name}.{mn}</b>{"" if isinstance(mo, property) else html.escape(sig(f))}</p>'
                                     + (f'<pre class="doc">{doc(f)}</pre>' if doc(f) else '') + '</div>')
            body.append(f'<section id="mod-{m}"><h2><code>fuelgauge.{m}</code></h2><pre class="doc mod">{doc(mod)}</pre>{"".join(items)}</section>')
    page = open(os.path.join(os.path.dirname(__file__), 'docs_template.html')).read()
    page = page.replace('{{NAV}}', '\n'.join(nav)).replace('{{BODY}}', '\n'.join(body)).replace('{{VERSION}}', fuelgauge.__version__)
    open(os.path.join(ROOT, 'docs', 'docs.html'), 'w').write(page)
    print('wrote docs/docs.html', len(page) // 1024, 'KB')


if __name__ == '__main__':
    main()
