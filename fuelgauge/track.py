"""Long-term registration for fixed cameras that drift, get bumped, re-aimed or re-zoomed over years.

Visual-odometry style keyframe tracking inside segments, then loop closure between segments:

  track()          match each frame (SIFT + RANSAC 4-DOF similarity) to the latest keyframes of the
                   current segment; when tracking is lost for several clear frames, start a new segment.
  link_segments()  match every segment's clearest keyframes against every other segment's and join them
                   with a maximum-inlier spanning tree anchored on the largest segment.
  to_master()      compose per-frame transforms into the master view.

Transforms are 2x3 affine matrices in registration-resolution pixels.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

I2 = np.float64([[1, 0, 0], [0, 1, 0]])


def compose(A, B):
    """Apply A, then B."""
    return (np.vstack([B, [0, 0, 1]]) @ np.vstack([A, [0, 0, 1]]))[:2]


def invert(A):
    return np.linalg.inv(np.vstack([A, [0, 0, 1]]))[:2]


class Matcher:
    """SIFT on CLAHE-equalised grey, ratio test, RANSAC similarity. Only the frame
    (below the top sky band) contributes features."""

    def __init__(self, size=(512, 384), nfeatures=1500, terrain_from=0.15, ratio=0.75, min_scale=0.85, max_scale=1.18):
        import cv2
        self.cv2 = cv2
        self.size = size
        self.sift = cv2.SIFT_create(nfeatures=nfeatures, contrastThreshold=0.02)
        self.clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        self.mask = np.zeros(size[::-1], np.uint8); self.mask[int(size[1] * terrain_from):] = 255
        self.flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=4), dict(checks=48))
        self.ratio, self.min_scale, self.max_scale = ratio, min_scale, max_scale

    def feats(self, img_bgr):
        cv2 = self.cv2
        g = cv2.cvtColor(cv2.resize(img_bgr, self.size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        k, d = self.sift.detectAndCompute(self.clahe.apply(g), self.mask)
        return (np.float32([p.pt for p in k]) if k else np.zeros((0, 2), np.float32)), d

    def match(self, a, b):
        """Similarity transform mapping frame a onto frame b and its RANSAC inlier count."""
        pa_all, da = a; pb_all, db = b
        if da is None or db is None or len(pa_all) < 30 or len(pb_all) < 30:
            return None, 0
        pairs = self.flann.knnMatch(da, db, k=2)
        good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < self.ratio * n.distance]
        if len(good) < 20:
            return None, len(good)
        pa = pa_all[[m.queryIdx for m in good]]; pb = pb_all[[m.trainIdx for m in good]]
        M, inl = self.cv2.estimateAffinePartial2D(pa, pb, method=self.cv2.RANSAC, ransacReprojThreshold=2.5,
                                                  maxIters=5000, confidence=0.995)
        if M is None:
            return None, 0
        s = float(np.hypot(M[0, 0], M[1, 0]))
        if not self.min_scale < s < self.max_scale:
            return None, 0
        return M, int(inl.sum())


@dataclass
class Segment:
    ref: int
    keyframes: list = field(default_factory=list)      # (feats, T_to_segment_ref, frame_index, clarity)


@dataclass
class TrackResult:
    seg: np.ndarray                 # segment id per frame (-1 = not registered)
    T: list                         # per-frame transform to its segment reference (None if not registered)
    inliers: np.ndarray
    segments: list


def track(frames, matcher: Matcher | None = None, min_inliers=35, lost_after=4, kf_inliers=160, kf_clarity=1.6,
          progress=None) -> TrackResult:
    """frames: iterable of (bgr_image or None, clarity score). Images flagged None are skipped."""
    m = matcher or Matcher()
    segs: list[Segment] = []
    seg, T, inl = [], [], []
    cur = None; lost = []
    for k, (img, clear) in enumerate(frames):
        seg.append(-1); T.append(None); inl.append(0)
        if progress and k % 250 == 0:
            progress(k, len(segs))
        if img is None:
            continue
        f = m.feats(img)
        if cur is None:
            segs.append(Segment(k, [(f, I2, k, clear)])); cur = len(segs) - 1
            seg[k], T[k], inl[k] = cur, I2, 999
            continue
        kfs = segs[cur].keyframes
        best = (0, None)
        for kf in kfs[-3:] + ([kfs[0]] if len(kfs) > 3 else []):
            Mi, n = m.match(f, kf[0])
            if Mi is not None and n > best[0]:
                best = (n, compose(Mi, kf[1]))
        if best[0] < min_inliers and len(kfs) > 4:          # relocalise within the segment
            for kf in kfs[:-3][::max(1, len(kfs) // 8)]:
                Mi, n = m.match(f, kf[0])
                if Mi is not None and n > best[0]:
                    best = (n, compose(Mi, kf[1]))
        if best[0] >= min_inliers:
            seg[k], T[k], inl[k] = cur, best[1], best[0]; lost = []
            if best[0] < kf_inliers and clear > kf_clarity:
                kfs.append((f, best[1], k, clear))
            continue
        lost.append((k, f, clear))
        if len(lost) >= lost_after:                          # new segment at the clearest lost frame
            kk, ff, cc = max(lost, key=lambda t: t[2])
            segs.append(Segment(kk, [(ff, I2, kk, cc)])); cur = len(segs) - 1
            for (j, fj, _) in lost:
                if j == kk:
                    seg[j], T[j], inl[j] = cur, I2, 999
                else:
                    Mi, n = m.match(fj, ff)
                    if Mi is not None and n >= min_inliers:
                        seg[j], T[j], inl[j] = cur, Mi, n
            lost = []
    return TrackResult(np.array(seg), T, np.array(inl), segs)


def pairwise_links(res: TrackResult, matcher: Matcher | None = None, min_size=20, reps=10):
    """Best match between every pair of segments with at least `min_size` frames, using each segment's clearest
    keyframes. Returns (links {(a, b): (inliers, T a->b)}, big segment ids, sizes)."""
    m = matcher or Matcher()
    sizes = np.bincount(res.seg[res.seg >= 0], minlength=len(res.segments))
    big = [s for s in range(len(res.segments)) if sizes[s] >= min_size]
    rep = {}
    for s in big:
        kf = sorted(res.segments[s].keyframes, key=lambda t: -t[3])
        rep[s] = kf[:6] + kf[6:][::max(1, len(kf[6:]) // 4)][:reps - 6]
    links = {}
    for a in big:
        for b in big:
            if a >= b:
                continue
            best = (0, None)
            for fa in rep[a]:
                for fb in rep[b]:
                    Mi, n = m.match(fa[0], fb[0])
                    if Mi is not None and n > best[0]:
                        best = (n, compose(compose(invert(fa[1]), Mi), fb[1]))
            if best[1] is not None:
                links[(a, b)] = best; links[(b, a)] = (best[0], invert(best[1]))
    return links, big, sizes


def _grow(seed, links, taken, min_inliers):
    group = {seed: I2}; used = []
    while True:
        cand = [(v[0], a, b, v[1]) for (a, b), v in links.items()
                if a not in group and a not in taken and b in group and v[0] >= min_inliers]
        if not cand:
            return group, used
        n, a, b, Tab = max(cand, key=lambda c: c[0])
        group[a] = compose(Tab, group[b]); used.append((a, b, n))


def link_segments(res: TrackResult, matcher: Matcher | None = None, min_size=20, min_inliers=30, reps=10):
    """Join segments into one map around the largest. Returns (to_master dict seg->T, master seg, list of links)."""
    links, big, sizes = pairwise_links(res, matcher, min_size, reps)
    if not big:
        return {}, None, []
    master = max(big, key=lambda s: sizes[s])
    group, used = _grow(master, links, set(), min_inliers)
    return group, master, used


def group_views(res: TrackResult, times, matcher: Matcher | None = None, min_size=20, min_inliers=30,
                min_frames=60, min_span_days=300, reps=10):
    """Like link_segments, but a camera that was moved to a new spot keeps its later years: every connected group
    of segments becomes its own view, anchored on its largest segment, if it holds at least `min_frames` frames
    over at least `min_span_days`. Views are ordered by size. Returns a list of dict(anchor, to_view, links)."""
    import pandas as pd
    links, big, sizes = pairwise_links(res, matcher, min_size, reps)
    t = pd.to_datetime(pd.Series(list(times)))
    views, taken = [], set()
    for seed in sorted(big, key=lambda s: -sizes[s]):
        if seed in taken:
            continue
        group, used = _grow(seed, links, taken, min_inliers)
        taken |= set(group)
        idx = np.flatnonzero(np.isin(res.seg, list(group)))
        span = (t.iloc[idx].max() - t.iloc[idx].min()).days if len(idx) else 0
        views.append(dict(anchor=seed, to_view=group, links=used, frames=int(len(idx)), span_days=int(span)))
    keep = [v for v in views if v['frames'] >= min_frames and v['span_days'] >= min_span_days]
    return sorted(keep or views[:1], key=lambda v: -v['frames'])


def to_master(res: TrackResult, links: dict):
    """Per-frame transform into the master view (None where the frame or its segment is unregistered)."""
    out = []
    for s, T in zip(res.seg, res.T):
        out.append(compose(T, links[s]) if (s >= 0 and s in links and T is not None) else None)
    return out


def sustained_moves(times, tx, ty, window=15, min_px=30, min_gap_days=60):
    """Dates where the median camera offset jumps and stays: bumps, re-aims, re-zooms."""
    import pandas as pd
    df = pd.DataFrame(dict(tx=tx, ty=ty), index=pd.to_datetime(times))
    before = df.rolling(window, min_periods=window // 2).median()
    after = df[::-1].rolling(window, min_periods=window // 2).median()[::-1]
    jump = np.hypot(after.tx.shift(-1) - before.tx, after.ty.shift(-1) - before.ty)
    moves = []
    for t, v in jump[jump > min_px].items():
        if moves and (t - moves[-1][0]).days < min_gap_days:
            if v > moves[-1][1]:
                moves[-1] = (t, float(v))
            continue
        moves.append((t, float(v)))
    return moves
