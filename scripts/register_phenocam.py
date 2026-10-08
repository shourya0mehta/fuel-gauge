"""Camera pipeline for long-running fixed cameras (years of daily frames).

Pass A  track: frames are matched (SIFT + RANSAC, 4-DOF similarity) to the latest keyframes of the
        current segment, visual-odometry style. When tracking is lost for several clear frames
        (camera re-aimed, lens swapped, scene changed) a new segment starts.
Pass B  link:  every segment's clearest keyframes are matched against every other segment's; the
        strongest links join segments into one map anchored on a master view (relocalisation /
        loop closure). Segments that never link are kept separate and flagged.
Pass C  measure: each frame is warped into the master view; fog/haze is scored by how well its
        edges agree with the master; mean RGB is stored on a 40 x 30 block grid.

Output: $DATA/proc/<site>_blocks.npz, $DATA/proc/<site>_qa.json

This is the exact script used for the study (fuelgauge.archive is the packaged equivalent).
    DATA=data STRIDE=2 python scripts/register_phenocam.py <camera>     # STRIDE=2 keeps every other day
"""
import os, re, sys, json, glob, datetime as dt
import numpy as np, cv2

DATA = os.environ.get('DATA', 'data')
W, H = 768, 576            # measurement resolution
RW, RH = 512, 384          # registration resolution
BLOCK = 24
SC = W / RW
MIN_INL = 35
LOST_AFTER = 4


def parse_date(path):
    m = re.search(r'_(\d{4})_(\d{2})_(\d{2})_(\d{2})(\d{2})', os.path.basename(path))
    return dt.datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]))


def load(path):
    im = cv2.imread(path)
    return None if im is None else cv2.resize(im, (W, H), interpolation=cv2.INTER_AREA)


def cheap_quality(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(img, (RW, RH))
    lower = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)[int(RH * 0.45):]
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    m = dict(mean=float(g.mean()), lap=float(cv2.Laplacian(lower, cv2.CV_64F).var()),
             std=float(lower.std()), sat=float((g > 250).mean()),
             sky_sat=float(hsv[: int(RH * 0.25), :, 1].mean()), ground_sat=float(hsv[int(RH * 0.55):, :, 1].mean()))
    m['ok'] = bool(40 < m['mean'] < 225 and m['lap'] > 40 and m['std'] > 10 and m['sat'] < 0.2)
    m['clear'] = m['lap'] / 500 + m['sky_sat'] / 100 + m['ground_sat'] / 80
    return m


class Matcher:
    def __init__(self):
        self.sift = cv2.SIFT_create(nfeatures=1500, contrastThreshold=0.02)
        self.clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        mask = np.zeros((RH, RW), np.uint8); mask[int(RH * 0.15):] = 255
        self.mask = mask
        self.flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=4), dict(checks=48))

    def feats(self, img):
        g = self.clahe.apply(cv2.cvtColor(cv2.resize(img, (RW, RH), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY))
        k, d = self.sift.detectAndCompute(g, self.mask)
        return (np.float32([p.pt for p in k]) if k else np.zeros((0, 2), np.float32)), d

    def match(self, a, b):
        pa_all, da = a; pb_all, db = b
        if da is None or db is None or len(pa_all) < 30 or len(pb_all) < 30:
            return None, 0
        good = [m for m, n in (p for p in self.flann.knnMatch(da, db, k=2) if len(p) == 2) if m.distance < 0.75 * n.distance]
        if len(good) < 20:
            return None, len(good)
        pa = pa_all[[m.queryIdx for m in good]]; pb = pb_all[[m.trainIdx for m in good]]
        M, inl = cv2.estimateAffinePartial2D(pa, pb, method=cv2.RANSAC, ransacReprojThreshold=2.5, maxIters=5000, confidence=0.995)
        if M is None:
            return None, 0
        s = float(np.hypot(M[0, 0], M[1, 0]))
        if not 0.85 < s < 1.18:
            return None, 0
        return M, int(inl.sum())


def compose(A, B):
    return (np.vstack([B, [0, 0, 1]]) @ np.vstack([A, [0, 0, 1]]))[:2]


def edge_map(img):
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32), (5, 5), 0)
    return cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))


def run(site):
    files = sorted(glob.glob(os.path.join(DATA, 'phenocam', site, '*.jpg')))
    stride = int(os.environ.get('STRIDE', '2'))      # every other day: fuel samples are 2-4 weeks apart
    files = files[::stride]
    M_ = Matcher()
    I2 = np.float64([[1, 0, 0], [0, 1, 0]])
    recs = []
    segs = []              # each: dict(ref=index, keyframes=[(feat, T_to_segref, idx, clear)])
    cur = None; lost = []
    # ---------------- Pass A: track ----------------
    for i, f in enumerate(files):
        img = load(f)
        if img is None:
            continue
        q = cheap_quality(img)
        r = dict(file=os.path.basename(f), time=parse_date(f).isoformat(), seg=-1, inliers=0, **q)
        recs.append(r); k = len(recs) - 1
        if k % 250 == 0:
            print(site, 'A', k, len(files), 'segments', len(segs), flush=True)
        if not q['ok']:
            continue
        feat = M_.feats(img)
        if cur is None:
            segs.append(dict(ref=k, keyframes=[(feat, I2, k, q['clear'])])); cur = len(segs) - 1
            r.update(seg=cur, inliers=999, T=I2.tolist()); continue
        kfs = segs[cur]['keyframes']
        best = (0, None)
        tries = kfs[-3:] + ([kfs[0]] if len(kfs) > 3 else [])
        for kf in tries:
            Mi, n = M_.match(feat, kf[0])
            if Mi is not None and n > best[0]:
                best = (n, compose(Mi, kf[1]))
        if best[0] < MIN_INL and len(kfs) > 4:              # relocalise inside the segment
            for kf in kfs[:-3][::max(1, len(kfs) // 8)]:
                Mi, n = M_.match(feat, kf[0])
                if Mi is not None and n > best[0]:
                    best = (n, compose(Mi, kf[1]))
        if best[0] >= MIN_INL:
            r.update(seg=cur, inliers=best[0], T=best[1].tolist()); lost = []
            if best[0] < 160 and q['clear'] > 1.6:
                kfs.append((feat, best[1], k, q['clear']))
            continue
        lost.append((k, feat, q['clear']))
        if len(lost) >= LOST_AFTER:                          # start a new segment at the clearest lost frame
            kk, ff, cc = max(lost, key=lambda t: t[2])
            segs.append(dict(ref=kk, keyframes=[(ff, I2, kk, cc)])); cur = len(segs) - 1
            for (j, fj, cj) in lost:
                if j == kk:
                    recs[j].update(seg=cur, inliers=999, T=I2.tolist())
                else:
                    Mi, n = M_.match(fj, ff)
                    if Mi is not None and n >= MIN_INL:
                        recs[j].update(seg=cur, inliers=n, T=Mi.tolist())
            lost = []
    sizes = [sum(1 for r in recs if r['seg'] == s) for s in range(len(segs))]
    print(site, 'segments', len(segs), 'sizes', sizes, flush=True)

    # ---------------- Pass B: link segments ----------------
    big = [s for s in range(len(segs)) if sizes[s] >= 20]
    reps = {}
    for s in big:
        kf = sorted(segs[s]['keyframes'], key=lambda t: -t[3])
        reps[s] = kf[:6] + kf[6:][::max(1, len(kf[6:]) // 4)][:4]
    master_seg = max(big, key=lambda s: sizes[s])
    links = {}
    for a in big:
        for b in big:
            if a >= b:
                continue
            best = (0, None)
            for fa in reps[a]:
                for fb in reps[b]:
                    Mi, n = M_.match(fa[0], fb[0])
                    if Mi is not None and n > best[0]:
                        # T maps segA-ref -> segB-ref:  inv(T_fa) then Mi then T_fb
                        Ta = np.vstack([fa[1], [0, 0, 1]]); inv = np.linalg.inv(Ta)[:2]
                        best = (n, compose(compose(inv, Mi), fb[1]))
            links[(a, b)] = best
            if best[1] is not None:
                links[(b, a)] = (best[0], np.linalg.inv(np.vstack([best[1], [0, 0, 1]]))[:2])
    # views: connected groups of segments (links with >= 30 inliers); each group is measured in the frame of its
    # largest segment. View 0 holds the largest group. A camera that was moved to a new spot gets a second view.
    comp = {}
    for s0 in sorted(big, key=lambda s: -sizes[s]):
        if s0 in comp:
            continue
        group = {s0: I2}
        while True:
            cand = [(v[0], a, b, v[1]) for (a, b), v in links.items()
                    if a not in group and a not in comp and b in group and v[1] is not None and v[0] >= 30]
            if not cand:
                break
            n, a, b, T = max(cand, key=lambda c: c[0])
            group[a] = compose(T, group[b])
            print(site, f'link segment {a} -> {b} with {n} inliers', flush=True)
        for s1, T in group.items():
            comp[s1] = (s0, T)
    anchors = sorted({a for a, _ in comp.values()}, key=lambda a: -sum(sizes[s] for s in comp if comp[s][0] == a))
    def span_days(a):
        ts = sorted(r['time'] for r in recs if r['seg'] in comp and comp[r['seg']][0] == a)
        return (np.datetime64(ts[-1]) - np.datetime64(ts[0])) / np.timedelta64(1, 'D') if ts else 0
    # a view must cover at least most of a year with a reasonable number of frames to support its own calibration
    anchors = [a for a in anchors if sum(sizes[s] for s in comp if comp[s][0] == a) >= 60 and span_days(a) >= 300] or anchors[:1]
    view_of = {s: anchors.index(a) for s, (a, _) in comp.items() if a in anchors}
    to_view = {s: comp[s][1] for s in view_of}
    master_seg = anchors[0]
    to_master = {s: T for s, T in to_view.items() if view_of[s] == 0}
    unlinked = [s for s in big if s not in to_master]
    segs_ref = None
    print(site, 'views', [[s for s in view_of if view_of[s] == v] for v in range(len(anchors))], 'dropped', [s for s in big if s not in view_of], flush=True)

    # Featureless views (open-grass close-ups) fragment into many short stretches that cannot be joined. When
    # fewer than half of the usable frames end up in a view, measure every usable frame in place instead, the
    # way PhenoCam's fixed regions do; homogeneous grass tolerates the few-pixel shifts this leaves.
    n_ok = sum(1 for r in recs if r['ok'])
    n_view = sum(sizes[s] for s in view_of)
    mode = 'registered'
    if n_view < 0.5 * n_ok:
        mode = 'in_place'
        anchor_rec = max((r for r in recs if r['ok']), key=lambda r: r['lap'] / 500 + r['sky_sat'] / 100 + r['ground_sat'] / 80)
        anchors = [-2]; view_of = {-2: 0}; to_view = {-2: I2}; master_seg = -2
        for r in recs:
            if r['ok']:
                r['seg_tracked'] = r['seg']; r['seg'] = -2; r['T'] = I2.tolist()
        segs_ref = anchor_rec
        print(site, f'only {n_view} of {n_ok} usable frames in a joined view: measuring {n_ok} frames in place', flush=True)

    # ---------------- Pass C: measure ----------------
    view_imgs = []
    for a in anchors:
        ref_rec = segs_ref if mode == 'in_place' else recs[segs[a]['ref']]
        view_imgs.append(load(os.path.join(DATA, 'phenocam', site, ref_rec['file'])))
    view_edges = [edge_map(v) for v in view_imgs]
    master_rec = segs_ref if mode == 'in_place' else recs[segs[master_seg]['ref']]
    master_img = view_imgs[0]
    gh, gw = H // BLOCK, W // BLOCK
    dates, rgb, valid, fog, segid, viewid = [], [], [], [], [], []
    for k, r in enumerate(recs):
        r['reg'] = False
        if r['seg'] not in to_view:
            continue
        v = view_of[r['seg']]
        T = compose(np.float64(r['T']), to_view[r['seg']])
        Mf = T.copy(); Mf[:, 2] *= SC
        img = load(os.path.join(DATA, 'phenocam', site, r['file']))
        warped = cv2.warpAffine(img.astype(np.float32), Mf, (W, H), flags=cv2.INTER_LINEAR, borderValue=(-1, -1, -1))
        cover = warped[..., 0] >= 0
        e = edge_map(np.clip(warped, 0, 255).astype(np.uint8))
        sl = slice(int(H * 0.4), H)
        a_, b_ = e[sl][cover[sl]], view_edges[v][sl][cover[sl]]
        corr = float(np.corrcoef(a_, b_)[0, 1]) if a_.size > 1000 else 0.0
        r.update(reg=True, view=v, edge_corr=corr, M=Mf.tolist(), tx=float(Mf[0, 2]), ty=float(Mf[1, 2]),
                 rot=float(np.degrees(np.arctan2(Mf[1, 0], Mf[0, 0]))), scale=float(np.hypot(Mf[0, 0], Mf[1, 0])))
        w = np.where(warped < 0, 0, warped)
        bs = w.reshape(gh, BLOCK, gw, BLOCK, 3).sum(axis=(1, 3))
        cs = cover.astype(np.float32).reshape(gh, BLOCK, gw, BLOCK).sum(axis=(1, 3))
        with np.errstate(invalid='ignore', divide='ignore'):
            mean = bs / cs[..., None]
        dates.append(r['time']); rgb.append(mean[..., ::-1].astype(np.float32))
        valid.append(cs > 0.9 * BLOCK * BLOCK); fog.append(corr); segid.append(r['seg']); viewid.append(v)
        if len(dates) % 500 == 0:
            print(site, 'C', len(dates), flush=True)
    out = os.path.join(DATA, 'proc'); os.makedirs(out, exist_ok=True)
    np.savez_compressed(os.path.join(out, f'{site}_blocks.npz'), dates=np.array(dates), rgb=np.array(rgb),
                        valid=np.array(valid), edge_corr=np.array(fog), seg=np.array(segid), view=np.array(viewid),
                        masters=np.array([v[..., ::-1] for v in view_imgs]),
                        master=master_img[..., ::-1], master_file=master_rec['file'])
    json.dump(dict(recs=recs, sizes=sizes, linked=sorted(int(s) for s in to_master), unlinked=unlinked,
                   views=[[int(s) for s in view_of if view_of[s] == v] for v in range(len(anchors))], mode=mode,
                   master_seg=master_seg, seg_refs=[recs[s['ref']]['file'] for s in segs]),
              open(os.path.join(out, f'{site}_qa.json'), 'w'))
    print(f'{site}: {len(recs)} frames, {sum(r["ok"] for r in recs)} pass checks, {len(dates)} registered into the master view; master {master_rec["file"]}', flush=True)


if __name__ == '__main__':
    if os.path.exists(os.path.join(DATA, 'proc', f'{sys.argv[1]}_blocks.npz')) and not os.environ.get('FORCE'):
        print(sys.argv[1], 'already processed (set FORCE=1 to redo)'); sys.exit(0)
    lock = os.path.join(DATA, 'proc', f'{sys.argv[1]}.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.close(fd)
    except FileExistsError:
        print(sys.argv[1], 'is being processed by another runner'); sys.exit(0)
    try:
        run(sys.argv[1])
    finally:
        os.remove(lock)
