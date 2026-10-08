# Fuel Gauge

**What can California's fire cameras actually see, and can their photos tell how dry the brush is?**

[Project site with the coverage map, the interactive study and the live camera network](https://shourya0mehta.github.io/fuel-gauge/) · [tests](.github/workflows/tests.yml) · MIT licence

![Fifteen years of one hillside in the San Bernardino National Forest, every April and September, registered onto one view](docs/assets/readme/hillside.gif)

*One Forest Service camera, 2003 to 2018, April and September of each year. Every frame was shifted, turned and scaled onto one shared view, so the only thing that changes is the brush.*

## Why

Thousands of fixed cameras already watch Western hillsides, most of them to spot smoke. Two questions about them have no public answer. Which ground can they actually see, once terrain gets in the way? And could the same photos measure live fuel moisture, the water in living plants that sets how easily brush ignites and how fast fire runs through it? Crews still measure that by hand every two to four weeks at a few hundred sites, and satellites see it only at 500 m pixels.

This project answers both on public data alone, and ships the tools as an open package.

## What I found

**1. Coverage.** I traced lines of sight from all 1,309 ALERTCalifornia cameras (740 sites) across a 90 m terrain model, then checked every California wildfire from 2020 to 2025 against the result.

- **46%** of California's wildland is in line of sight of at least one camera within 30 km, and **20%** of two, the overlap needed to triangulate a smoke column.
- Of the **277** fires over 1,000 acres, the ground where each started was in view of a camera for **43%**. Smoke rises, so a looser test asks whether a 300 m column above the ignition was in view: **79%**, and **59%** from two cameras.
- The **21%** that started where no camera could see even that burned **1.4 million acres**, among them the SCU Lightning Complex and the Claremont Fire in 2020.
- The largest blind spots: Klamath Mountains (11,406 km²), Yosemite high country (8,250 km²), Modoc Plateau (5,178 km²), Diablo Range (4,164 km²).

![California shaded by how many fire cameras can see each patch of wildland, with big fires since 2020](docs/assets/coverage/ca_light.png)

**2. Fuel moisture.** I registered **29,047 daily photos from 21 PhenoCam cameras in 6 states** onto fixed views, found the brush in each view automatically, and scored the cameras against **3,832 field samples** from Globe-LFMC alongside MODIS satellite data. Every predictor is fit on all years but one and tested on the missing year, on top of a baseline that already knows each site's seasonal cycle.

- **Cameras.** After colour correction, a camera beats season alone at 10 of 21 cameras. Pooled over all 3,832 held-out samples its error matches season alone (20.5 against 20.5 points RMSE), and its anomaly correlation, how well it tracks a year's departure from normal, is 0.13.
- **Satellites.** MODIS infrared at the sampling site beats season alone at 15 of 21 cameras (sign test p = 0.04), cuts pooled error by 4% and reaches an anomaly correlation of 0.31. Looking at the camera's own slope it reaches 0.29.
- **Colour correction is the camera's biggest lever.** Uncorrected, cameras reach an anomaly correlation of 0.08. Correcting each photo against rock and soil in the same frame lifts that to 0.13.
- **Automatic regions beat hand-drawn ones** at 12 of 20 cameras with both (median anomaly correlation 0.13 against 0.07).
- **Timing doesn't rescue it.** The date a camera sees the brush turn brown barely tracks the date fuel moisture falls below its usual level (r = 0.11 over 141 camera-years); satellite greenness does no better (0.09).
- **Registration held up.** 92% of 31,451 usable photos landed on a fixed view. Six cameras that were moved to a new spot kept those years as a second view; three featureless grass close-ups were measured in place.
- **Near-infrared doesn't rescue it.** Ten of the cameras also record a near-infrared photo seconds after each colour one. Camera NDVI from those twins, on the same registered regions, reached an anomaly correlation of **0.02** on 1,267 shared samples and beat the calendar at 1 of 10 cameras.

What it means: fire cameras leave large parts of California's backcountry unwatched, and the gaps line up with where some of the biggest recent fires started. And greenness, from a camera or from orbit, carries little of the year-to-year swing in fuel moisture, so a camera fuel gauge would need a different signal. The reusable part is the toolkit: it makes years of fixed-camera photos comparable, ties every pixel to the ground, and maps what any set of cameras can see.

## What's in here

| Path | What it is |
| --- | --- |
| [`fuelgauge/`](fuelgauge) | The Python package: multi-year registration, terrain calibration, automatic regions, colour correction, evaluation, data readers |
| [`scripts/`](scripts) | The fuel moisture study and the statewide coverage map, end to end: download, register, score, map, build the site data |
| [`live/`](live) | The daily updater for eight terrain-calibrated HPWREN fire cameras, run by GitHub Actions every morning |
| [`docs/`](docs) | The project site (GitHub Pages), including the live numbers the Action commits |
| [`study/`](study) | Camera list, per-camera results and coverage statistics used on the site |
| [`tests/`](tests) | Synthetic drift, re-aims, relocations and terrain; no-leakage checks on the evaluation |

## Use it on your own camera

```bash
pip install "fuelgauge[geo,seg,eval] @ git+https://github.com/shourya0mehta/fuel-gauge"

# years of daily photos from one fixed camera -> registered block colours (+ a QA report)
fuelgauge register-archive photos/ out/mycam

# skyline + 30 m terrain -> camera pose, and a lookup from every pixel block to a spot on the ground
fuelgauge calibrate mycam frame.jpg --lat 33.40 --lon -117.19 --elev 483
```

```python
from fuelgauge import track, colour, rois, evaluate

res = track.track(frames, track.Matcher())                 # keyframe tracking within stretches
views = track.group_views(res, times)                      # join stretches; a relocated camera gets a second view
moves = track.sustained_moves(times, tx, ty)               # dates the camera was bumped or re-aimed
wb = colour.white_balance(blocks, valid, ref, times=times) # follow the camera's colour drift, not the weather
```

## How it works

**Registration.** SIFT features on contrast-equalised frames, 4-degree-of-freedom similarity transforms by RANSAC. Frames are tracked against a growing set of keyframes; after four lost frames a new stretch starts at the clearest of them. Stretches are then joined by matching their clearest keyframes (loop closure, at least 30 inliers). A camera moved to a new spot becomes a second view with its own calibration rather than being thrown away. Featureless views (open-grass close-ups) fragment into short stretches; when fewer than half of the usable frames land in a view, frames are measured in place, as fixed PhenoCam regions are.

**Measuring the right pixels.** A SegFormer-B2 model (ADE20K, run through ONNX Runtime) labels the master view. Vegetation blocks are those labelled as plants and with a strong seasonal swing; reference blocks are covered, not vegetation, and seasonally flat (rock, soil, road). No hand-drawn masks.

**Colour that holds still.** Red and blue are rescaled so the reference blocks keep a constant balance against green, smoothed over a trailing two months so the correction follows the camera (sensor drift, replacements, settings) and not the weather on the reference ground (snow, wet soil). The daily index is GRVI = (G − R) / (G + R) on clear days, with haze scored by how well each frame's edges agree with the master view.

**Scoring.** Ridge regression with one intercept and one set of day-of-year harmonics per sampling unit (site and species), plus the predictor's level and 30-day change. Leave one year out; report RMSE, anomaly correlation (does it know this year differs from normal?), and the number of held-out years it beats season alone.

**Live network.** For each HPWREN camera, the skyline in the photo (from SegFormer's sky class) is matched to a skyline rendered from the Copernicus 30 m DEM, with earth curvature and refraction. A bounded pose fit with a trimmed loss gives heading, tilt and roll; one equidistant fisheye lens is fitted jointly across all eight cameras. Each 16-pixel block is then traced to the ground for distance, slope, aspect and ESA WorldCover land cover. Every morning a GitHub Action pulls the previous day's midday frames from the HPWREN CDN, corrects small shifts by phase correlation, measures every ground block and commits the numbers to `docs/live/`.

## Reproduce the study

```bash
pip install -e ".[geo,seg,eval,dev]"
export DATA=data
python scripts/fetch_lfmc.py                  # Globe-LFMC 2.0 field samples
python scripts/fetch_phenocam.py              # midday photos for the cameras in study/cameras.json
python scripts/fetch_modis.py                 # MODIS MCD43A4 at each camera view and sampling site
python scripts/register_phenocam.py <camera>  # once per camera (STRIDE=2 keeps every other day)
python scripts/fetch_nir.py <cam,cam,...>     # near-infrared twins + exposures for IR-capable cameras
python scripts/nir.py <cam> ...               # camera NDVI on the registered regions
python scripts/study.py && python scripts/timing.py && python scripts/summary.py
python scripts/fetch_fires.py                 # NIFC WFIGS California wildfire ignitions
python scripts/coverage.py && python scripts/coverage_report.py   # statewide viewsheds, stats and maps
python scripts/build_site_data.py             # docs/data/ for the site
```

The full run downloads about 60,000 photos and took a few hours on two CPU cores. The San Bernardino camera was registered from every daily photo at 960 px; the others from every other day at 768 px, since field samples are two to four weeks apart.

## Limits

- The coverage map uses today's camera network against fires from 2020 to 2025, so it asks what today's cameras would have seen. It assumes each site can pan through a full circle, sees 30 km, and ignores haze, night, trees right around the mast and where a camera happened to be pointed. Ignition points come from incident reports and can be off by hundreds of metres; a lightning complex is a single point for many starts.

- Field samples sit up to 25 km from each camera, often on a different slope and sometimes a different species from the brush in view. That is the biggest drag on every optical predictor here, and the camera most of all.
- Ordinary cameras record red, green and blue. Leaf water shows most clearly in shortwave infrared, which only the satellite has. Colour tracks greenness, which follows moisture with a lag.
- The study cameras are research cameras, mostly retired. The live fire cameras have no field samples close enough to score, so the live network reports change, not fuel moisture.
- Crews sample every two to four weeks, so each camera has tens to hundreds of samples over 4 to 16 years. Several cameras share sampling sites, so cameras are not fully independent tests.

## Data and credits

- **PhenoCam Network** (phenocam.nau.edu). Richardson et al. (2018), *Tracking vegetation phenology across diverse North American biomes using PhenoCam imagery*, Scientific Data 5:180028. Per-camera acknowledgements are in [study/ACKNOWLEDGEMENTS.md](study/ACKNOWLEDGEMENTS.md).
- **HPWREN** camera network, University of California San Diego (hpwren.ucsd.edu). Images courtesy of HPWREN.
- **Globe-LFMC 2.0**. Yebra et al. (2024), Scientific Data 11:332, compiled in part from the US National Fuel Moisture Database.
- **MODIS MCD43A4 v6.1** (NASA LP DAAC), **Copernicus DEM GLO-30** (ESA) and **ESA WorldCover 2021**, all through Microsoft Planetary Computer.
- **SegFormer-B2** fine-tuned on ADE20K (NVIDIA), ONNX export by Xenova on Hugging Face.
- **ALERTCalifornia** camera network (UC San Diego, with CAL FIRE): camera positions from the public camera map.
- **NIFC WFIGS** wildland fire incident locations (National Interagency Fire Center, public ArcGIS service).
- Camera NDVI method: Petach et al. (2014), *Monitoring vegetation phenology using an infrared-enabled security camera*, Agricultural and Forest Meteorology 195-196:143-151.

This is a research project, not an operational fire-danger product.

## Citation

See [CITATION.cff](CITATION.cff).
