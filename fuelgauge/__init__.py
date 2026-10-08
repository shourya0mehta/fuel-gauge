"""fuelgauge: turn fixed outdoor cameras into georeferenced vegetation sensors.

Modules
    camera     fisheye camera model (pixel <-> azimuth/elevation)
    terrain    DEM panoramas, skyline pose fitting, shared-lens network calibration, pixel -> ground
    track      multi-year registration: keyframe tracking, segment linking (loop closure)
    quality    frame screening and haze scoring
    colour     block colours, GCC / GRVI, white balance, causal smoothing
    rois       automatic measurement regions (no hand-drawn masks)
    segment    SegFormer-B2 (ADE20K) sky / ground segmentation via ONNX Runtime
    archive    end-to-end processing of a camera archive
    evaluate   leave-one-year-out comparison against field fuel moisture
    sources    PhenoCam, HPWREN, Globe-LFMC, MODIS
"""
__version__ = "0.2.0"
