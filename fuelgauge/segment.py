"""Semantic segmentation with a pretrained SegFormer-B2 (ADE20K, 150 classes) exported to ONNX.

Used to find the sky (for skyline matching) and to drop roads, buildings, water and people from the
ground measurements. Weights: Xenova/segformer-b2-finetuned-ade-512-512 on Hugging Face (ONNX export of
NVIDIA's SegFormer-B2). Downloaded on first use into ~/.cache/fuelgauge.
"""
from __future__ import annotations

import json
import os
import urllib.request

import numpy as np

REPO = "https://huggingface.co/Xenova/segformer-b2-finetuned-ade-512-512/resolve/main"
CACHE = os.environ.get("FUELGAUGE_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "fuelgauge"))
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
SKY = 2

VEG_WORDS = ('tree', 'grass', 'plant', 'field', 'flower', 'mountain', 'hill', 'earth', 'land', 'palm')
NOT_GROUND = ('sky', 'building', 'road', 'water', 'car', 'signboard', 'tower', 'pole', 'fence', 'wall', 'house',
              'sidewalk', 'truck', 'person', 'railing', 'bridge', 'sea', 'lake', 'river', 'streetlight', 'skyscraper',
              'tank', 'pier', 'ship', 'boat', 'van', 'bus', 'awning', 'windowpane', 'door', 'column', 'stairs', 'step',
              'swimming pool', 'path', 'dirt track', 'rock', 'sand', 'hovel', 'shed')

_sess = None
_labels = None


def _fetch(name):
    os.makedirs(CACHE, exist_ok=True)
    dst = os.path.join(CACHE, os.path.basename(name))
    if not os.path.exists(dst):
        urllib.request.urlretrieve(f"{REPO}/{name}", dst + ".part")
        os.replace(dst + ".part", dst)
    return dst


def labels_map() -> dict[int, str]:
    global _labels
    if _labels is None:
        cfg = json.load(open(_fetch("config.json")))
        _labels = {int(k): v.split(',')[0].strip() for k, v in cfg['id2label'].items()}
    return _labels


def session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        so = ort.SessionOptions(); so.intra_op_num_threads = 2
        _sess = ort.InferenceSession(_fetch("onnx/model.onnx"), so, providers=['CPUExecutionProvider'])
    return _sess


def logits(img: np.ndarray, tiles: bool = True) -> np.ndarray:
    """RGB uint8 image -> class logits (150, H, W). Full view plus four overlapping 60% tiles, averaged."""
    import cv2
    H, W = img.shape[:2]
    s = session(); name = s.get_inputs()[0].name

    def run(x):
        x = cv2.resize(x, (512, 512), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        return s.run(None, {name: ((x - MEAN) / STD).transpose(2, 0, 1)[None]})[0][0]

    acc = np.zeros((150, H, W), np.float32); cnt = np.zeros((H, W), np.float32)
    views = [(0, 0, W, H)]
    if tiles:
        tw, th = int(W * 0.6), int(H * 0.6)
        views += [(x0, y0, tw, th) for x0 in (0, W - tw) for y0 in (0, H - th)]
    for (x0, y0, w, h) in views:
        o = run(img[y0:y0 + h, x0:x0 + w])
        acc[:, y0:y0 + h, x0:x0 + w] += np.stack([cv2.resize(c, (w, h), interpolation=cv2.INTER_LINEAR) for c in o])
        cnt[y0:y0 + h, x0:x0 + w] += 1
    return acc / cnt


def labels(img: np.ndarray, tiles: bool = True) -> np.ndarray:
    return logits(img, tiles).argmax(0)


def masks(lab: np.ndarray):
    """sky, vegetation-like ground, and not-ground masks from a label image."""
    names = labels_map()
    lut_veg = np.array([names.get(i, '') in VEG_WORDS for i in range(150)])
    lut_bad = np.array([names.get(i, '') in NOT_GROUND for i in range(150)])
    return lab == SKY, lut_veg[lab], lut_bad[lab]
