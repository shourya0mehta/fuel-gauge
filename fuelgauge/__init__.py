"""fuelgauge: turn fixed outdoor cameras into georeferenced vegetation sensors.

Modules
    camera     fisheye camera model (pixel <-> azimuth/elevation)
    terrain    DEM panoramas, skyline pose fitting, shared-lens network calibration, pixel -> ground
    track      multi-year registration: keyframe tracking, segment linking (loop closure)
    quality    frame screening and haze scoring
    colour     block colours, GCC / GRVI, white balance, causal smoothing
    rois       automatic measurement regions (no hand-drawn masks)
    segment    SegFormer-B2 (ADE20K) sky / ground segmentation via ONNX Runtime
    archive    end-to-end registration of a camera archive (photos -> registered block colours)
    measure    registered blocks -> daily vegetation series: haze, automatic regions, white balance, smoothing
    evaluate   leave-one-year-out comparison against field fuel moisture
    viewshed   terrain line of sight, smoke-column visibility and greedy camera siting
    sources    PhenoCam, HPWREN, Globe-LFMC, MODIS
"""
__version__ = "0.3.0"
