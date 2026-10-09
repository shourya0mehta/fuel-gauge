/* Fuel Gauge site. Plain JS, no build step. Data: data/*.json (built by scripts/build_site_data.py)
   and live/summary.json (rewritten every morning by .github/workflows/site.yml). */
(async function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const NS = 'http://www.w3.org/2000/svg';
  const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
  const DAY = 86400000;
  const toT = (s) => Date.parse(s + 'T12:00:00Z');
  const fmtDate = (t) => new Date(t).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' });
  const fmtShort = (t) => new Date(t).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
  const season = (t) => { const m = new Date(t).getUTCMonth(); return ['Winter', 'Winter', 'Spring', 'Spring', 'Spring', 'Summer', 'Summer', 'Summer', 'Fall', 'Fall', 'Fall', 'Winter'][m] + ' ' + new Date(t).getUTCFullYear(); };
  const pct = (v, d = 0) => (v * 100).toFixed(d) + '%';
  const signed = (v, d = 0) => { const t = Math.abs(v * 100).toFixed(d); return (Number(t) === 0 ? '' : v > 0 ? '+' : '−') + t + '%'; };
  const getJSON = async (u) => { const r = await fetch(u, { cache: 'no-cache' }); if (!r.ok) throw new Error(u + ' ' + r.status); return r.json(); };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
  const STATE_AB = { Washington: 'WA', Oregon: 'OR', California: 'CA', Nevada: 'NV', Idaho: 'ID', Montana: 'MT', Wyoming: 'WY', Utah: 'UT', Colorado: 'CO', Arizona: 'AZ', 'New Mexico': 'NM' };

  const [S, H, L] = await Promise.all([getJSON('data/study.json'), getJSON('data/hero.json'), getJSON('data/live.json')]);
  let LS = null, C = null, NIR = null;
  try { LS = await getJSON('live/summary.json'); } catch (e) { LS = null; }
  try { C = await getJSON('data/coverage.json'); } catch (e) { C = null; }
  const P = S.pooled, T = S.totals;
  const CAMSET = 'camera_auto_wb', SATSET = 'sat_ir_view';
  const shortName = (c) => c.short || c.name.split(',')[0];
  const states = new Set(S.cams.map((c) => c.state).filter(Boolean));

  /* ---------------- masthead ---------------- */
  const camHelps = S.cams.filter((c) => c.res[CAMSET] && c.res[CAMSET].skill > 0).length;
  $('figures').innerHTML = [
    ...(C ? [[C.cameras.toLocaleString(), 'California fire cameras traced across the terrain'], [Math.round(C.wild_seen * 100) + '%', 'of the state\'s wildland in line of sight of one']] : [[T.cams, 'study cameras']]),
    [T.frames.toLocaleString(), `daily photos from ${T.cams} cameras registered onto fixed views`],
    [T.samples.toLocaleString(), 'field samples of live fuel moisture, ' + T.species + ' species'],
    [L.cams.length, 'live fire cameras, re-measured every morning'],
  ].map(([b, s]) => `<div><b>${b}</b><span>${s}</span></div>`).join('');
  $('answer').innerHTML = (S.text && S.text.answer) || '';
  const F = S.text && S.text.findings ? S.text.findings : [
    ['--cam', 'Cameras', `A colour-corrected camera beats the calendar at ${P[CAMSET].better} of ${P[CAMSET].cams} cameras, with a median error change of ${signed(-P[CAMSET].median_skill, 1)}. The signal is real but small.`],
    ['--sat', 'Satellites', `Satellite infrared on the same slope beats the calendar at ${P[SATSET].better} of ${P[SATSET].cams}, median ${signed(-P[SATSET].median_skill, 1)}. Infrared sees leaf water; a colour camera only sees the browning that follows.`],
    ['--straw', 'What limits cameras', `Colour drift, not resolution. Correcting each photo's colour against rock and soil in the same frame helps at ${S.pooled.wb_helps || '–'} cameras, and automatic regions on registered photos beat hand-drawn ones at ${P.hand_vs_auto.auto_better} of ${P.hand_vs_auto.cams}.`],
  ];
  $('findings').innerHTML = F.map(([c, k, t]) => `<div><span class="k"><i style="background:var(${c})"></i>${k}</span><p>${t}</p></div>`).join('');


  /* ---------------- statewide coverage ---------------- */
  function drawCoverage() {
    if (!C) { document.getElementById('coverage').hidden = true; return; }
    const I = C.ignitions, big = I['1,000+ acres'], fmt = (v) => Math.round(v * 100) + '%';
    $('cov-span').textContent = `${C.cameras.toLocaleString()} cameras at ${C.sites} sites, fires from ${C.years[0]} to ${C.years[1]}`;
    $('cov-dek').textContent = (S.text && S.text.coverage_dek) || '';
    $('cov-stats').innerHTML = [
      [fmt(C.wild_seen), 'of California\'s wildland is in line of sight of at least one ALERTCalifornia camera (within 30 km)'],
      [fmt(C.wild_seen2), 'is seen by two or more, enough to triangulate a smoke column'],
      [fmt(big.smoke300), `of the ${big.n} fires over 1,000 acres started where a camera could see a 300 m smoke column`],
      [Math.round(big.acres_nosmoke / 1e6 * 10) / 10 + 'M', 'acres burned in big fires that started where no camera could see even that'],
    ].map(([b, t]) => `<div><b>${b}</b><span>${t}</span></div>`).join('');
    const tb = $('cov-ign').querySelector('tbody'); tb.innerHTML = '';
    ['10+ acres', '100+ acres', '1,000+ acres', '10,000+ acres'].forEach((k) => {
      const v = I[k]; if (!v) return;
      tb.insertAdjacentHTML('beforeend', `<tr><td>${k}</td><td class="num">${v.n.toLocaleString()}</td><td class="num">${fmt(v.seen)}</td><td class="num">${fmt(v.smoke300)}</td><td class="num">${fmt(v.smoke300_2)}</td></tr>`);
    });
    $('cov-unseen').innerHTML = (C.unseen_large || []).filter((f) => f.smoke300 === 0).slice(0, 6).map((f) => `<li>${esc(f.name)} Fire, ${f.year} <small>${f.acres.toLocaleString()} acres, ${esc(f.county)} County</small></li>`).join('') || '<li>None</li>';
    $('cov-blind').innerHTML = (C.blind_spots || []).slice(0, 6).map((b) => `<li>${esc(b.name)} <small>${b.km2.toLocaleString()} km² of wildland${b.biggest ? `, ${esc(b.biggest.name)} Fire ${b.biggest.year}` : ''}</small></li>`).join('');
    $('cov-method').textContent = (S.text && S.text.coverage_method) || '';
    const SI = C.siting, SF = C.siting_fires;
    if (SI || SF) {
      $('cov-siting-card').hidden = false; $('cov-key-site').hidden = false;
      const parts = [];
      if (SI) parts.push(`Searching ${SI.candidates.toLocaleString()} hilltops one site at a time, ten new sites would add ${SI.added_km2.toLocaleString()} km² of watched wildland, ${Math.round(SI.added_share * 1000) / 10} points of the state.`);
      if (SF) parts.push(`Looking back, the ten sites below would have seen a 300 m smoke column from ${SF.fires} of the ${SF.missed_fires} fires no camera could see, ${(SF.acres / 1e6).toFixed(2)} million of their ${(SF.missed_acres / 1e6).toFixed(2)} million acres.`);
      $('cov-siting-text').textContent = parts.join(' ');
      const P = SF ? SF.picks : SI.picks;
      $('cov-siting').innerHTML = P.map((p) => `<li>${esc(p.region)} <small>${SF ? p.acres.toLocaleString() + ' acres, incl. ' + esc(p.examples[0]) + ' Fire' : '+' + p.new_km2.toLocaleString() + ' km²'}, at ${p.lat.toFixed(2)}, ${p.lon.toFixed(2)}</small></li>`).join('');
    }
    const sv = $('cov-hit'), M = C.map;
    sv.setAttribute('viewBox', `0 0 ${M.w} ${M.h}`); sv.innerHTML = '';
    const X = (lon) => (lon - M.west) / M.res, Y = (lat) => (M.north - lat) / M.res;
    (C.fires_1000 || []).forEach((f) => {
      const r = 2.5 + 1.6 * Math.log10(Math.max(f.a, 1000) / 1000 + 1) * 3 + 3;
      const c = el('circle', { cx: X(f.lon), cy: Y(f.lat), r }, sv);
      c.addEventListener('pointerenter', () => {
        const tip = $('cov-tip'), bb = sv.getBoundingClientRect();
        tip.hidden = false; tip.style.left = (X(f.lon) / M.w * bb.width) + 'px'; tip.style.top = (Y(f.lat) / M.h * bb.height) + 'px';
        tip.innerHTML = `${esc(f.n)} Fire, ${f.y}, ${f.a.toLocaleString()} acres<br>ground in view of ${f.g} camera site${f.g === 1 ? '' : 's'}<br>300 m smoke in view of ${f.s}`;
      });
      c.addEventListener('pointerleave', () => { $('cov-tip').hidden = true; });
    });
    ((SF || SI) ? (SF || SI).picks : []).forEach((p, i) => {
      const x = X(p.lon), y = Y(p.lat), r = 9;
      const d = el('path', { d: `M${x} ${y - r}L${x + r} ${y}L${x} ${y + r}L${x - r} ${y}Z`, class: 'pick' }, sv);
      d.addEventListener('pointerenter', () => {
        const tip = $('cov-tip'), bb = sv.getBoundingClientRect();
        tip.hidden = false; tip.style.left = (x / M.w * bb.width) + 'px'; tip.style.top = (y / M.h * bb.height) + 'px';
        tip.innerHTML = `Proposed site ${i + 1}: ${esc(p.region)}<br>` + (p.acres != null ? `would have seen ${p.fires} missed fire${p.fires === 1 ? '' : 's'}, ${p.acres.toLocaleString()} acres` : `+${p.new_km2.toLocaleString()} km² of unwatched wildland`);
      });
      d.addEventListener('pointerleave', () => { $('cov-tip').hidden = true; });
    });
  }
  drawCoverage();

  /* ---------------- hero: one hillside ---------------- */
  const daily = H.daily.d.map((d, i) => ({ t: toT(d), g: H.daily.g[i] }));
  const lfm = H.lfm.map((r) => ({ t: toT(r.d), s: r.s, o: r.o, pc: r.pc }));
  const frames = H.frames.map((f) => ({ t: toT(f.d), f: f.f, d: f.d }));
  const t0 = Math.min(daily[0].t, frames[0].t), t1 = Math.max(daily[daily.length - 1].t, frames[frames.length - 1].t);
  const gVals = daily.map((d) => d.g).filter((v) => v != null).sort((a, b) => a - b);
  const gMin = gVals[Math.floor(gVals.length * 0.01)], gMax = gVals[Math.floor(gVals.length * 0.99)];
  const g100 = (v) => Math.max(0, Math.min(100, 100 * (v - gMin) / (gMax - gMin)));
  function nearestDaily(t) { let lo = 0, hi = daily.length - 1; while (hi - lo > 1) { const m = (lo + hi) >> 1; if (daily[m].t < t) lo = m; else hi = m; } return Math.abs(daily[lo].t - t) < Math.abs(daily[hi].t - t) ? daily[lo] : daily[hi]; }
  function nearestFrame(t) { let b = frames[0]; for (const f of frames) if (Math.abs(f.t - t) < Math.abs(b.t - t)) b = f; return b; }
  const img = $('hs-img');
  const preload = new Map();
  function getImg(src) { if (!preload.has(src)) { const im = new Image(); im.src = src; preload.set(src, im); } return preload.get(src); }
  const scored = lfm.filter((r) => r.pc != null && [3, 4, 5].includes(new Date(r.t).getUTCMonth()));
  const errs = scored.map((r) => Math.abs(r.pc - r.o)).sort((a, b) => a - b), medErr = errs[Math.floor(errs.length / 2)];
  const typical = scored.reduce((a, r) => (Math.abs(Math.abs(r.pc - r.o) - medErr) < Math.abs(Math.abs(a.pc - a.o) - medErr) ? r : a), scored[0]);
  const startFrame = typical ? frames.reduce((a, f) => (Math.abs(f.t - typical.t) < Math.abs(a.t - typical.t) ? f : a), frames[0]) : frames[0];
  let cur = startFrame.t;
  $('hs-span').textContent = new Date(t0).getUTCFullYear() + '–' + new Date(t1).getUTCFullYear();
  function setTime(t) {
    cur = Math.max(t0, Math.min(t1, t));
    const fr = nearestFrame(cur);
    if (img.getAttribute('src') !== fr.f) img.src = fr.f;
    [-2, -1, 1, 2].forEach((k) => { const i = frames.indexOf(fr) + k; if (frames[i]) getImg(frames[i].f); });
    $('hs-date').textContent = fmtDate(fr.t);
    $('hs-season').textContent = season(fr.t);
    const dd = nearestDaily(fr.t);
    const okDay = dd && Math.abs(dd.t - fr.t) < 20 * DAY && dd.g != null;
    $('g-cam').textContent = okDay ? Math.round(g100(dd.g)) + ' / 100' : 'no clear view';
    $('g-cam-bar').style.width = okDay ? g100(dd.g).toFixed(1) + '%' : '0%';
    let best = null;   // nearest sample within two weeks, preferring one that was scored
    for (const r of lfm) { const dt = Math.abs(r.t - fr.t); if (dt < 16 * DAY && (!best || (r.pc != null) > (best.pc != null) || ((r.pc != null) === (best.pc != null) && dt < Math.abs(best.t - fr.t)))) best = r; }
    if (best) {
      const s = H.sites[best.s];
      $('g-lfm').textContent = Math.round(best.o) + '%';
      $('g-lfm-bar').style.width = Math.min(100, best.o / 1.6) + '%';
      $('g-lfm-sub').textContent = `${s.name}, ${s.dist_km} km ${s.dir} of the camera, sampled ${fmtDate(best.t)}. Water in live chamise as a share of its dry weight; the red mark is 60%.`;
      $('g-pred').textContent = best.pc != null ? Math.round(best.pc) + '%' : 'not scored';
    } else {
      $('g-lfm').textContent = 'no sample';
      $('g-lfm-bar').style.width = '0%';
      $('g-lfm-sub').textContent = 'No field sample within two weeks of this photo. Crews sample every two to four weeks, less often in winter.';
      $('g-pred').textContent = '–';
    }
    $('g-crit').style.left = (60 / 1.6) + '%';
    drawCursor();
  }
  const tl = $('timeline');
  let TL = null;
  function drawTimeline() {
    const w = tl.clientWidth || 900, h = 210, m = { l: 40, r: 44, t: 14, b: 26 };
    tl.setAttribute('viewBox', `0 0 ${w} ${h}`); tl.setAttribute('height', h); tl.innerHTML = '';
    const x = (t) => m.l + (t - t0) / (t1 - t0) * (w - m.l - m.r);
    const yg = (v) => m.t + (1 - g100(v) / 100) * (h - m.t - m.b);
    const lMin = 30, lMax = 170;
    const yl = (v) => m.t + (1 - (v - lMin) / (lMax - lMin)) * (h - m.t - m.b);
    const grid = el('g', { class: 'grid' }, tl);
    for (let y = new Date(t0).getUTCFullYear() + 1; y <= new Date(t1).getUTCFullYear(); y++) {
      const xx = x(Date.UTC(y, 0, 1));
      el('line', { x1: xx, x2: xx, y1: m.t, y2: h - m.b }, grid);
      if (y % (w < 520 ? 4 : w < 760 ? 2 : 1) === 0) el('text', { x: xx + 3, y: h - 8 }, tl).textContent = y;
    }
    [60, 100, 140].forEach((v) => { el('line', { x1: m.l, x2: w - m.r, y1: yl(v), y2: yl(v) }, grid); el('text', { x: w - m.r + 6, y: yl(v) + 4 }, tl).textContent = v + '%'; });
    el('line', { x1: m.l, x2: w - m.r, y1: yl(60), y2: yl(60), stroke: css('--crit'), 'stroke-width': 1 }, tl);
    el('text', { x: 4, y: m.t + 8 }, tl).textContent = 'cam';
    el('text', { x: w - m.r + 6, y: m.t + 8 }, tl).textContent = 'LFM';
    let dpath = '', last = null;
    for (const d of daily) { if (d.g == null) { last = null; continue; } dpath += (last && d.t - last < 20 * DAY ? 'L' : 'M') + x(d.t).toFixed(1) + ',' + yg(d.g).toFixed(1); last = d.t; }
    el('path', { d: dpath, fill: 'none', stroke: css('--cam'), 'stroke-width': 1.5, 'stroke-linejoin': 'round' }, tl);
    for (const r of lfm) el('circle', { cx: x(r.t), cy: yl(r.o), r: 2.4, fill: css('--ink-2') }, tl);
    const cursor = el('line', { y1: m.t - 4, y2: h - m.b, stroke: css('--ink'), 'stroke-width': 1.5 }, tl);
    const knob = el('circle', { cy: m.t - 4, r: 5, fill: css('--ink') }, tl);
    TL = { x, w, m, cursor, knob };
    drawCursor();
  }
  function drawCursor() { if (!TL) return; const xx = TL.x(cur); TL.cursor.setAttribute('x1', xx); TL.cursor.setAttribute('x2', xx); TL.knob.setAttribute('cx', xx); }
  function tFromEvent(ev) { const r = tl.getBoundingClientRect(); const px = (ev.clientX - r.left) / r.width * TL.w; return t0 + (px - TL.m.l) / (TL.w - TL.m.l - TL.m.r) * (t1 - t0); }
  let dragging = false;
  tl.addEventListener('pointerdown', (e) => { dragging = true; tl.setPointerCapture(e.pointerId); stop(); setTime(tFromEvent(e)); });
  tl.addEventListener('pointermove', (e) => {
    const t = tFromEvent(e);
    if (dragging) setTime(t);
    const tip = $('tl-tip'), d = nearestDaily(t);
    if (t < t0 || t > t1 || !d) { tip.hidden = true; return; }
    const r = tl.getBoundingClientRect();
    tip.hidden = false; tip.style.left = (e.clientX - r.left) + 'px'; tip.style.top = '18px';
    tip.textContent = fmtDate(d.t) + (d.g != null ? ', greenness ' + Math.round(g100(d.g)) : ', no clear view');
  });
  tl.addEventListener('pointerup', () => { dragging = false; });
  tl.addEventListener('pointerleave', () => { $('tl-tip').hidden = true; });
  tl.style.touchAction = 'none'; tl.style.cursor = 'ew-resize'; tl.tabIndex = 0;
  tl.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight') { setTime(cur + 30 * DAY); e.preventDefault(); }
    if (e.key === 'ArrowLeft') { setTime(cur - 30 * DAY); e.preventDefault(); }
  });
  let timer = null;
  function stop() { if (timer) { clearInterval(timer); timer = null; } $('hs-play').setAttribute('aria-pressed', 'false'); $('hs-play').textContent = 'Play'; }
  $('hs-play').addEventListener('click', () => {
    if (timer) { stop(); return; }
    if (cur >= t1 - 40 * DAY) cur = t0;
    $('hs-play').setAttribute('aria-pressed', 'true'); $('hs-play').textContent = 'Pause';
    timer = setInterval(() => { const i = frames.indexOf(nearestFrame(cur)); if (i >= frames.length - 1) { stop(); return; } setTime(frames[i + 1].t); }, 260);
  });
  let showRoi = false;
  function drawBlocks(canvas, gw, gh, veg, ref, on) {
    const r = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    canvas.width = r.width * dpr; canvas.height = r.height * dpr; const g = canvas.getContext('2d'); g.scale(dpr, dpr); g.clearRect(0, 0, r.width, r.height);
    if (!on) return;
    const bw = r.width / gw, bh = r.height / gh;
    for (let i = 0; i < gw * gh; i++) {
      const cx = (i % gw) * bw, cy = Math.floor(i / gw) * bh;
      if (veg[i]) { g.fillStyle = 'rgba(70, 200, 95, 0.34)'; g.fillRect(cx + 0.5, cy + 0.5, bw - 1, bh - 1); }
      if (ref[i]) { g.strokeStyle = 'rgba(255, 200, 80, 0.95)'; g.lineWidth = 1.4; g.strokeRect(cx + 1, cy + 1, bw - 2, bh - 2); }
    }
  }
  const drawHeroRoi = () => drawBlocks($('hs-roi'), H.roi.gw, H.roi.gh, H.roi.veg, H.roi.ref, showRoi);
  $('hs-roi-btn').addEventListener('click', (e) => { showRoi = !showRoi; e.currentTarget.setAttribute('aria-pressed', String(showRoi)); e.currentTarget.textContent = showRoi ? 'Hide measured brush' : 'Show measured brush'; drawHeroRoi(); });
  img.addEventListener('load', drawHeroRoi);

  /* ---------------- study: map + scoreboard + pooled table ---------------- */
  const yrs = S.cams.flatMap((c) => c.years.map(Number));
  $('study-span').textContent = `${T.cams} cameras, ${T.samples.toLocaleString()} samples, ${Math.min(...yrs)} to ${Math.max(...yrs)}`;
  $('study-prose').innerHTML = (S.text && S.text.study) || `<p>I searched the PhenoCam Network, a long-running archive of daily photos from fixed cameras, for every camera with field measurements of live fuel moisture from the Globe-LFMC database within 25 km. ${T.cams} cameras qualified, from Southern California chaparral to Wyoming sagebrush and Montana conifers. For each one, every daily photo was registered onto one view, the brush was found automatically, and its colour was turned into a daily index.</p><p>Each predictor is scored the same way: a model that already knows each site's normal seasonal cycle is fit on all years but one, then asked to predict the samples in the missing year. Beating "season alone" means knowing something about this year that the calendar doesn't.</p>`;
  let selCam = S.cams.reduce((a, c) => (c.n > a.n ? c : a), S.cams[0]).cam;
  const camColor = (c) => (c.res[CAMSET] && c.res[CAMSET].skill > 0 ? css('--cam') : css('--ink-3'));
  function drawMap() {
    const sv = $('westmap'); const M = S.map; if (!M) return;
    sv.setAttribute('viewBox', `0 0 ${M.w} ${M.h}`); sv.innerHTML = '';
    for (const s of M.states) {
      el('path', { d: s.d, class: 'state' }, sv);
    }
    for (const s of (M.labels || [])) el('text', { x: s.x, y: s.y, 'text-anchor': 'middle', 'font-size': 22, opacity: 0.9 }, sv).textContent = STATE_AB[s.name] || '';
    const R = M.w / 80;
    for (const c of S.cams) for (const s of c.sites) el('line', { x1: c.x, y1: c.y, x2: s.xy[0], y2: s.xy[1], class: 'link' }, sv);
    const seen = new Set();
    for (const c of S.cams) for (const s of c.sites) { if (seen.has(s.name)) continue; seen.add(s.name); el('circle', { cx: s.xy[0], cy: s.xy[1], r: R * 0.55, class: 'site' }, sv); }
    for (const c of S.cams) {
      const d = el('circle', { cx: c.x, cy: c.y, r: R, fill: camColor(c), class: 'cam' + (c.cam === selCam ? ' sel' : '') }, sv);
      const t = el('title', {}, d); t.textContent = `${c.name}: ${c.n} samples`;
      d.addEventListener('click', () => selectCam(c.cam, true));
    }
  }
  function drawBoard() {
    const sv = $('scoreboard');
    const rows = S.cams.filter((c) => c.res[CAMSET]).slice().sort((a, b) => b.res[CAMSET].skill - a.res[CAMSET].skill);
    const w = sv.clientWidth || 560, rh = 22, m = { l: Math.min(190, w * 0.38), r: 14, t: 20, b: 28 }, h = m.t + m.b + rows.length * rh;
    sv.setAttribute('viewBox', `0 0 ${w} ${h}`); sv.setAttribute('height', h); sv.innerHTML = '';
    const vals = rows.flatMap((c) => [c.res[CAMSET].skill, c.res[SATSET] ? c.res[SATSET].skill : 0]);
    const need = Math.max(...vals.map(Math.abs)), lim = [0.1, 0.2, 0.3, 0.4, 0.6].find((v) => v >= need) || 0.6;
    const x = (v) => m.l + (v + lim) / (2 * lim) * (w - m.l - m.r);
    const grid = el('g', { class: 'grid' }, sv);
    for (let v = -lim; v <= lim + 1e-9; v += lim / 2) { el('line', { x1: x(v), x2: x(v), y1: m.t - 4, y2: h - m.b }, grid); el('text', { x: x(v), y: h - 10, 'text-anchor': 'middle' }, sv).textContent = (v > 0 ? '+' : v < 0 ? '−' : '') + Math.round(Math.abs(v) * 100) + '%'; }
    el('text', { x: x(-lim), y: 11 }, sv).textContent = '← worse than season';
    el('text', { x: x(lim), y: 11, 'text-anchor': 'end' }, sv).textContent = 'better →';
    el('line', { x1: x(0), x2: x(0), y1: m.t - 4, y2: h - m.b, stroke: css('--straw'), 'stroke-width': 2 }, sv);
    rows.forEach((c, i) => {
      const y = m.t + i * rh + rh / 2;
      const g = el('g', { class: 'row' + (c.cam === selCam ? ' sel' : '') }, sv);
      el('rect', { class: 'bg', x: 0, y: y - rh / 2, width: w, height: rh, fill: 'transparent', rx: 2 }, g);
      const lab = shortName(c), maxc = Math.max(8, Math.floor((m.l - 10) / 6.7));
      el('text', { x: 4, y: y + 4 }, g).textContent = lab.length > maxc ? lab.slice(0, maxc - 1) + '…' : lab;
      const a = c.res[CAMSET].skill, b = c.res[SATSET] ? c.res[SATSET].skill : null;
      if (b != null) el('line', { x1: x(Math.max(-lim, Math.min(lim, a))), x2: x(Math.max(-lim, Math.min(lim, b))), y1: y, y2: y, stroke: css('--rule'), 'stroke-width': 2 }, g);
      if (b != null) el('circle', { cx: x(Math.max(-lim, Math.min(lim, b))), cy: y, r: 5, fill: css('--sat') }, g);
      el('circle', { cx: x(Math.max(-lim, Math.min(lim, a))), cy: y, r: 5.5, fill: css('--cam'), stroke: css('--paper'), 'stroke-width': 1.2 }, g);
      g.addEventListener('click', () => selectCam(c.cam, true));
      g.addEventListener('pointermove', (e) => {
        const tip = $('sb-tip'), r = sv.getBoundingClientRect();
        tip.hidden = false; tip.style.left = (e.clientX - r.left) + 'px'; tip.style.top = (y / h * r.height) + 'px';
        tip.innerHTML = `${esc(c.name)}<br>${c.n} samples, ${c.n_years} years, ${esc(c.veg)}<br>camera ${signed(-a, 1)} error, satellite ${b != null ? signed(-b, 1) : '–'}`;
      });
      g.addEventListener('pointerleave', () => { $('sb-tip').hidden = true; });
    });
  }
  const tb = $('pooled').querySelector('tbody');
  S.sets.forEach((s) => {
    if (s.key === 'season') return;
    const p = P[s.key]; if (!p || !p.cams) return;
    const tr = document.createElement('tr'); if (s.key === CAMSET) tr.className = 'hl';
    const col = { cam: '--cam', sat: '--sat', straw: '--straw', both: '--ink-2' }[s.role];
    tr.innerHTML = `<td><span class="chip" style="background:var(${col})"></span>${esc(s.label)}</td><td class="num">${p.better} of ${p.cams}</td><td class="num">${signed(-p.median_skill, 1)}</td><td class="num">${p.median_anom.toFixed(2)}</td>`;
    tb.appendChild(tr);
  });
  $('pooled-note').textContent = (S.text && S.text.pooled_note) || 'Error is root-mean-square error in fuel moisture points on held-out years; negative change means smaller error than season alone. Anomaly r is the correlation between how unusual each sample was (measured minus the seasonal baseline) and how unusual the predictor said it would be; 0 means no skill beyond the calendar. Each camera\'s predictors are scored on the same samples. Several cameras share sampling sites, so cameras are not fully independent tests.';

  if (S.text && S.text.timing) { $('timing-note').textContent = S.text.timing; $('timing-note').hidden = false; }
  const NI = S.summary && S.summary.nir;
  if (NI && S.text.nir) {
    $('nir-text').textContent = S.text.nir;
    const lab = { season: ['Season alone', '--straw'], camera_auto_wb: ['Camera colour, corrected', '--cam'], camera_ndvi: ['Camera near-infrared (NDVI)', '--cam'],
      camera_ndvi_plus_rgb: ['Camera NDVI + colour', '--cam'], sat_ir_view: ['Satellite infrared, same slope', '--sat'], sat_ir_site: ['Satellite infrared, at the site', '--sat'] };
    const s0 = NI.pooled.season.rmse;
    $('nir-table').querySelector('tbody').innerHTML = Object.entries(lab).filter(([k]) => NI.pooled[k]).map(([k, [l, c]]) => {
      const v = NI.pooled[k];
      return `<tr${k === 'camera_ndvi' ? ' class="hl"' : ''}><td><span class="chip" style="background:var(${c})"></span>${l}</td><td class="num">${k === 'season' ? '–' : v.cams_better + ' of ' + NI.cams}</td><td class="num">${v.rmse.toFixed(1)}</td><td class="num">${k === 'season' ? '–' : signed((v.rmse - s0) / s0, 1)}</td><td class="num">${k === 'season' ? '–' : v.anomaly_r.toFixed(2)}</td></tr>`;
    }).join('');
  } else { $('nir-block').hidden = true; }

  /* ---------------- explorer ---------------- */
  const sel = $('ex-select');
  S.cams.slice().sort((a, b) => a.name.localeCompare(b.name)).forEach((c) => { const o = document.createElement('option'); o.value = c.cam; o.textContent = c.name; o.dataset.sub = `${c.state}, ${c.veg}, ${c.years[0]}–${c.years[1]}`; sel.appendChild(o); });
  $('ex-count').textContent = T.cams + ' cameras';
  sel.addEventListener('change', () => selectCam(sel.value, false));
  const camCache = {};
  let CD = null, CS = null, unit = 0, exRoi = true;
  $('ex-roi').addEventListener('click', (e) => { exRoi = !exRoi; e.currentTarget.setAttribute('aria-pressed', String(exRoi)); drawExOverlay(); });
  async function selectCam(cam, scroll) {
    selCam = cam; sel.value = cam;
    drawMap(); drawBoard();
    CS = S.cams.find((c) => c.cam === cam);
    if (!camCache[cam]) camCache[cam] = await getJSON(`data/cam/${encodeURIComponent(cam)}.json`);
    CD = camCache[cam]; unit = 0;
    const im = $('ex-img'); im.src = CD.img; im.alt = `Master view of the ${CS.name} camera`;
    $('ex-photo').style.aspectRatio = `${CD.size[0]} / ${CD.size[1]}`;
    $('ex-photo-note').textContent = `The view every ${CS.frames.toLocaleString()} registered photos were mapped onto. Green blocks are the brush the camera measured, chosen automatically; amber outlines are rock, soil or road used to correct colour.`;
    const r = CS.res;
    $('ex-facts').innerHTML = `
      <div><span class="label">Ecosystem</span><b>${esc(CS.veg)}</b></div>
      <div><span class="label">Facing</span><b>${esc(CS.facing || '–')}</b></div>
      <div><span class="label">Photos registered</span><b>${CS.frames.toLocaleString()}</b></div>
      <div><span class="label">Archive used</span><b>${CS.years[0]}–${CS.years[1]}</b></div>
      <div><span class="label">Field samples scored</span><b>${CS.n.toLocaleString()} over ${CS.n_years} years</b></div>
      <div><span class="label">Sampling units</span><b>${CS.n_units}</b></div>
      <div class="wide2"><span class="label">Sampling sites</span><b>${CS.sites.map((s) => `${esc(s.name)} (${s.km} km)`).join(', ')}</b></div>
      <div class="wide2"><span class="label">Species sampled</span><b><i>${CS.species.map(esc).join(', ')}</i></b></div>`;
    const tbody = $('ex-table').querySelector('tbody'); tbody.innerHTML = '';
    S.sets.forEach((s) => {
      const v = r[s.key]; if (!v) return;
      const col = { cam: '--cam', sat: '--sat', straw: '--straw', both: '--ink-2' }[s.role];
      const tr = document.createElement('tr'); if (s.key === CAMSET) tr.className = 'hl';
      tr.innerHTML = `<td><span class="chip" style="background:var(${col})"></span>${esc(s.label)}</td><td class="num">${v.rmse.toFixed(1)}</td><td class="num">${s.key === 'season' ? '–' : signed(-v.skill, 1)}</td><td class="num">${s.key === 'season' ? '–' : v.anom.toFixed(2)}</td>`;
      tbody.appendChild(tr);
    });
    const ub = $('ex-units'); ub.innerHTML = '';
    CD.units.forEach((u, i) => {
      const b = document.createElement('button'); b.className = 'btn'; b.setAttribute('aria-pressed', String(i === unit));
      const [site, sp] = u.split(' | ');
      b.textContent = `${site}: ${sp.split(' ')[0][0]}. ${sp.split(' ').slice(1).join(' ')}`;
      b.addEventListener('click', () => { unit = i; [...ub.children].forEach((c, j) => c.setAttribute('aria-pressed', String(j === i))); drawExPred(); });
      ub.appendChild(b);
    });
    drawExOverlay(); drawCalendar(); drawExPred();
    if (scroll) document.getElementById('explore').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  function drawExOverlay() {
    if (!CD) return;
    const veg = [...CD.veg].map((c) => c === '1'), ref = [...CD.ref].map((c) => c === '1');
    drawBlocks($('ex-ov'), CD.grid[0], CD.grid[1], veg, ref, exRoi);
  }
  $('ex-img').addEventListener('load', drawExOverlay);
  const rampColor = (t) => { // straw -> pale -> green, 0..1
    const a = [194, 124, 14], m = [214, 208, 176], b = [46, 133, 64];
    const lerp = (p, q, k) => p.map((v, i) => Math.round(v + (q[i] - v) * k));
    return t < 0.5 ? lerp(a, m, t * 2) : lerp(m, b, (t - 0.5) * 2);
  };
  $('cal-ramp').style.background = `linear-gradient(90deg, rgb(${rampColor(0)}), rgb(${rampColor(0.5)}), rgb(${rampColor(1)}))`;
  function drawCalendar() {
    const cv = $('calendar'), cal = CD.calendar, ny = cal.rows.length;
    const W = cv.clientWidth || 800, rowH = Math.max(9, Math.min(16, Math.round(260 / ny))), H2 = ny * rowH, dpr = window.devicePixelRatio || 1;
    cv.style.height = H2 + 'px'; cv.width = W * dpr; cv.height = H2 * dpr;
    const g = cv.getContext('2d'); g.scale(dpr, dpr); g.clearRect(0, 0, W, H2);
    g.fillStyle = css('--panel'); g.fillRect(0, 0, W, H2);
    const dw = W / 366;
    cal.rows.forEach((row, yi) => {
      for (let d = 0; d < row.length; d++) {
        const ch = row[d]; if (ch === '.') continue;
        const c = rampColor(B64.indexOf(ch) / 63); g.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`;
        g.fillRect(d * dw, yi * rowH + 1, dw + 0.6, rowH - 2);
      }
    });
    g.strokeStyle = css('--ink'); g.lineWidth = 1.1; g.globalAlpha = 0.85;
    for (const s of CD.samples) {
      const t = new Date(toT(s.d)), yi = t.getUTCFullYear() - cal.years[0]; if (yi < 0 || yi >= ny) continue;
      const doy = Math.floor((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / DAY);
      g.beginPath(); g.arc((doy + 0.5) * dw, yi * rowH + rowH / 2, Math.max(2, rowH / 2 - 3.5), 0, Math.PI * 2); g.stroke();
    }
    g.globalAlpha = 1;
    $('cal-years').style.gridTemplateRows = `repeat(${ny}, ${rowH}px)`;
    $('cal-years').innerHTML = cal.years.map((y, i) => `<span style="line-height:${rowH}px">${(ny > 12 && i % 2) ? '' : y}</span>`).join('');
    cv.onpointermove = (e) => {
      const r = cv.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
      const yi = Math.floor(py / rowH), d = Math.floor(px / dw); if (yi < 0 || yi >= ny || d < 0 || d > 365) { $('cal-tip').hidden = true; return; }
      const y = cal.years[yi], t = Date.UTC(y, 0, 1) + d * DAY, ch = cal.rows[yi][d];
      let near = null; for (const s of CD.samples) { const dt = Math.abs(toT(s.d) - t); if (dt < 6 * DAY && (!near || dt < Math.abs(toT(near.d) - t))) near = s; }
      const tip = $('cal-tip'); tip.hidden = false; tip.style.left = (px + 50) + 'px'; tip.style.top = (yi * rowH) + 'px';
      tip.innerHTML = `${fmtDate(t)}, ${ch && ch !== '.' ? 'greenness ' + Math.round(B64.indexOf(ch) / 63 * 100) + '/100' : 'no clear photo'}` + (near ? `<br>${esc(CD.units[near.u].split(' | ')[0])}: measured ${Math.round(near.o)}%${near.c != null ? ', camera est. ' + Math.round(near.c) + '%' : ''}` : '');
    };
    cv.onpointerleave = () => { $('cal-tip').hidden = true; };
  }
  function drawExPred() {
    const pv = $('ex-pred');
    const rows = CD.samples.filter((r) => r.u === unit).map((r) => ({ ...r, t: toT(r.d) })).sort((a, b) => a.t - b.t);
    const w = pv.clientWidth || 900, h = 280, m = { l: 44, r: 12, t: 12, b: 26 };
    pv.setAttribute('viewBox', `0 0 ${w} ${h}`); pv.setAttribute('height', h); pv.innerHTML = '';
    if (!rows.length) return;
    const a = rows[0].t - 30 * DAY, b = rows[rows.length - 1].t + 30 * DAY;
    const vals = rows.flatMap((r) => [r.o, r.c, r.s, r.k]).filter((v) => v != null);
    const lo = Math.floor(Math.min(40, ...vals) / 20) * 20, hi = Math.ceil(Math.max(...vals) / 20) * 20;
    const x = (t) => m.l + (t - a) / (b - a) * (w - m.l - m.r), y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (h - m.t - m.b);
    const grid = el('g', { class: 'grid' }, pv);
    const step = hi - lo > 160 ? 40 : 20;
    for (let v = lo; v <= hi; v += step) { el('line', { x1: m.l, x2: w - m.r, y1: y(v), y2: y(v) }, grid); el('text', { x: 4, y: y(v) + 4 }, pv).textContent = v + '%'; }
    const span = (b - a) / (365 * DAY), yStep = Math.max(1, Math.ceil(span / (w / 70)));
    for (let yr = new Date(a).getUTCFullYear() + 1; yr <= new Date(b).getUTCFullYear(); yr++) { const xx = x(Date.UTC(yr, 0, 1)); el('line', { x1: xx, x2: xx, y1: m.t, y2: h - m.b }, grid); if (yr % yStep === 0) el('text', { x: xx + 3, y: h - 8 }, pv).textContent = yr; }
    if (lo < 60) el('line', { x1: m.l, x2: w - m.r, y1: y(60), y2: y(60), stroke: css('--crit'), 'stroke-width': 1 }, pv);
    for (const [k, col] of [['k', '--straw'], ['s', '--sat'], ['c', '--cam']]) {
      let d = '', prev = null;
      for (const r of rows) { if (r[k] == null) { prev = null; continue; } d += (prev && r.t - prev < 75 * DAY ? 'L' : 'M') + x(r.t).toFixed(1) + ',' + y(r[k]).toFixed(1); prev = r.t; }
      el('path', { d, fill: 'none', stroke: css(col), 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, pv);
    }
    for (const r of rows) el('circle', { cx: x(r.t), cy: y(r.o), r: 3.4, fill: css('--ink'), stroke: css('--paper'), 'stroke-width': 1.3 }, pv);
    const hit = el('rect', { x: m.l, y: m.t, width: w - m.l - m.r, height: h - m.t - m.b, fill: 'transparent' }, pv);
    const cross = el('line', { y1: m.t, y2: h - m.b, stroke: css('--ink-3'), 'stroke-width': 1, visibility: 'hidden' }, pv);
    hit.addEventListener('pointermove', (e) => {
      const r = pv.getBoundingClientRect(); const px = (e.clientX - r.left) / r.width * w; const t = a + (px - m.l) / (w - m.l - m.r) * (b - a);
      let best = rows[0]; for (const q of rows) if (Math.abs(q.t - t) < Math.abs(best.t - t)) best = q;
      cross.setAttribute('x1', x(best.t)); cross.setAttribute('x2', x(best.t)); cross.setAttribute('visibility', 'visible');
      const tip = $('ex-tip'); tip.hidden = false; tip.style.left = (x(best.t) / w * r.width) + 'px'; tip.style.top = (y(best.o) / h * r.height) + 'px';
      const f = (v) => (v != null ? Math.round(v) + '%' : '–');
      tip.innerHTML = `${fmtDate(best.t)}<br>measured ${f(best.o)}<br>camera ${f(best.c)}, satellite ${f(best.s)}<br>season alone ${f(best.k)}`;
    });
    hit.addEventListener('pointerleave', () => { $('ex-tip').hidden = true; cross.setAttribute('visibility', 'hidden'); });
  }

  /* ---------------- method cards ---------------- */
  const Hd = S.hard || {};
  $('hard-reg').textContent = Hd.reg_stat || `${pct(T.frames / Math.max(1, T.frames_total || T.frames))}`;
  $('hard-reg-text').innerHTML = Hd.reg_text || '';
  $('hard-roi').textContent = Hd.roi_stat || `${P.hand_vs_auto.auto_better} of ${P.hand_vs_auto.cams}`;
  $('hard-roi-text').innerHTML = Hd.roi_text || '';
  $('hard-wb').textContent = Hd.wb_stat || '';
  $('hard-wb-text').innerHTML = Hd.wb_text || '';
  const sb = $('segbar');
  const lab = document.createElement('div'); lab.className = 'label'; lab.style.display = 'flex'; lab.style.justifyContent = 'space-between';
  lab.innerHTML = `<span>San Bernardino NF camera, ${new Date(t0).getUTCFullYear()}</span><span>${new Date(t1).getUTCFullYear()}</span>`;
  const row = document.createElement('div'); row.className = 'seg-row';
  H.segments.forEach((s) => {
    const a = toT(s.start), b = toT(s.end); const i = document.createElement('i');
    i.style.left = (100 * (a - t0) / (t1 - t0)) + '%'; i.style.width = Math.max(0.4, 100 * (b - a) / (t1 - t0)) + '%';
    i.style.background = s.linked ? 'var(--cam)' : 'var(--ink-3)'; i.title = `${s.start} to ${s.end}: ${s.n} photos, ${s.linked ? 'joined to the master view' : 'could not be joined'}`;
    row.appendChild(i);
  });
  const moves = document.createElement('div'); moves.className = 'seg-row'; moves.style.height = '18px'; moves.style.background = 'transparent';
  (H.moves || []).forEach((mv) => { const i = document.createElement('i'); i.style.left = (100 * (toT(mv.d) - t0) / (t1 - t0)) + '%'; i.style.width = '2px'; i.style.background = 'var(--ink)'; i.title = `${mv.d}: view shifted ${mv.px} px`; moves.appendChild(i); });
  const sbl = document.createElement('div'); sbl.className = 'legend';
  sbl.innerHTML = '<span><i class="key-line" style="background:var(--cam);height:8px"></i>Tracked stretches, all joined back to one view</span><span><i class="key-line" style="background:var(--ink);width:2px;height:12px"></i>Days the camera moved</span>';
  sb.append(lab, row, moves, sbl);
  const rr = $('raw-reg');
  rr.innerHTML = (H.rawreg || []).map((p) => `<figure><img src="${p.raw}" alt="Photo as recorded on ${p.d}"><figcaption>As recorded, ${fmtDate(toT(p.d))}</figcaption></figure>`).join('') +
    `<figure><img src="assets/hero/raw_avg.jpg" alt="The three photos averaged without registration"><figcaption>Those three averaged as recorded: three hills, a smeared road.</figcaption></figure>
     <figure><img src="assets/hero/reg_avg.jpg" alt="The three photos averaged after registration"><figcaption>The same three averaged after registration: one hill, one road.</figcaption></figure>`;

  /* ---------------- live network ---------------- */
  const LC = { 10: ['Tree cover', '#2f7d3b'], 20: ['Shrubland', '#9a9a2c'], 30: ['Grassland', '#d9b44a'], 40: ['Cropland', '#c38d60'], 50: ['Built-up', '#b04a3b'], 60: ['Bare', '#a99a8a'], 80: ['Water', '#3b78c2'], 90: ['Wetland', '#3b9c9c'] };
  let camIdx = Math.max(0, L.cams.findIndex((c) => c.id === L.default));
  let mode = 'chg';
  const blocksCache = {};
  const liveOf = (c) => (LS && LS.cams && LS.cams[c.id]) || null;
  const anyLive = LS && LS.cams ? Object.values(LS.cams)[0] : null;
  $('net-span').textContent = L.cams.length + ' cameras' + (anyLive ? `, updated ${fmtDate(toT(anyLive.dates[anyLive.dates.length - 1]))}` : '');
  $('net-prose').innerHTML = `<p>The study cameras are mostly retired. The fire cameras on Southern California's ridgetops are not: HPWREN runs hundreds of them and posts a photo every minute. I fitted eight of them to the terrain by matching the skyline in each photo to a skyline rendered from a 30 m elevation model, solving for heading, tilt and roll plus one lens shared by the whole network (median skyline error ${(L.cams.map((c) => c.median_err_deg).sort((a, b) => a - b)[4]).toFixed(2)}°). That ties every 16-pixel block in the frame to a spot on the ground with a distance, a slope and a land-cover class.</p><p>Every morning a GitHub Action pulls yesterday's midday photos from each camera, measures every ground block and commits the numbers back to this site. The overlay shows which slopes have browned fastest over the last 90 days, a first look at where fuels are curing ahead of the rest.</p>`;
  const camList = $('cam-list');
  L.cams.forEach((c, i) => {
    const b = document.createElement('button'); b.className = 'cam-btn'; b.setAttribute('aria-pressed', String(i === camIdx));
    const a = c.yaw, half = c.hfov / 2;
    const p = (ang, r) => [17 + r * Math.sin(ang * Math.PI / 180), 17 - r * Math.cos(ang * Math.PI / 180)];
    const [x1, y1] = p(a - half, 14), [x2, y2] = p(a + half, 14);
    b.innerHTML = `<svg viewBox="0 0 34 34" aria-hidden="true"><circle cx="17" cy="17" r="15" fill="none" stroke="currentColor" stroke-opacity="0.35"/><path d="M17 17 L${x1.toFixed(1)} ${y1.toFixed(1)} A14 14 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)} Z" fill="currentColor" fill-opacity="0.75"/><text x="17" y="6.5" font-size="5" text-anchor="middle" fill="currentColor" font-family="monospace">N</text></svg><span>${esc(c.short)}<small>${esc(c.dir_label)}</small></span>`;
    b.addEventListener('click', () => { camIdx = i; [...camList.children].forEach((x, j) => x.setAttribute('aria-pressed', String(j === i))); loadCam(); });
    camList.appendChild(b);
  });
  document.querySelectorAll('#ov-modes .btn').forEach((b) => b.addEventListener('click', () => {
    mode = b.dataset.mode; document.querySelectorAll('#ov-modes .btn').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); renderLive();
  }));
  async function loadCam() {
    const c = L.cams[camIdx];
    if (!blocksCache[c.id]) { try { const B = await getJSON(c.blocks); B.uidx = []; B.usable.forEach((u, i) => { if (u) B.uidx.push(i); }); blocksCache[c.id] = B; } catch (e) { blocksCache[c.id] = null; } }
    const lv = liveOf(c), im = $('net-img');
    const want = lv && lv.latest ? lv.latest.url : c.img_oct;
    im.onerror = () => { if (im.getAttribute('src') !== c.img_oct) { im.src = c.img_oct; photoNote = 'median of late September and early October 2026 photos (live photo unavailable)'; renderLive(); } };
    photoNote = lv && lv.latest ? `midday photo from ${fmtDate(toT(lv.latest.date))}, straight from the HPWREN server` : 'median of late September and early October 2026 photos';
    if (im.getAttribute('src') !== want) im.src = want;
    renderLive(); drawNetChart();
  }
  let photoNote = '';
  function chgOf(c, B) {
    const lv = liveOf(c); if (!lv || !B) return null;
    const v = lv.change.filter((x) => x != null).slice().sort((a, b) => a - b), med = v.length ? v[Math.floor(v.length / 2)] : 0;
    const out = new Array(B.gw * B.gh).fill(null); B.uidx.forEach((i, k) => { if (lv.change[k] != null) out[i] = lv.change[k] - med; }); return out;
  }
  let chgScale = 20;
  function chgColor(v) {
    const t = Math.max(-1, Math.min(1, v / chgScale));
    const a = t < 0 ? [194, 124, 14] : [46, 133, 64], mid = [150, 150, 140], k = Math.abs(t);
    return `rgba(${Math.round(mid[0] + (a[0] - mid[0]) * k)},${Math.round(mid[1] + (a[1] - mid[1]) * k)},${Math.round(mid[2] + (a[2] - mid[2]) * k)},${0.2 + 0.6 * k})`;
  }
  function distColor(d) { if (d < 1000) return 'rgba(255,255,255,0.10)'; if (d < 3000) return 'rgba(80,160,255,0.22)'; if (d < 10000) return 'rgba(80,160,255,0.40)'; return 'rgba(40,80,200,0.55)'; }
  function renderLive() {
    const c = L.cams[camIdx], B = blocksCache[c.id], CH = chgOf(c, B), lv = liveOf(c);
    if (CH) { const a = CH.filter((v) => v != null).map(Math.abs).sort((x, y) => x - y); chgScale = a.length ? Math.max(4, a[Math.floor(a.length * 0.9)]) : 20; }
    $('net-img').alt = `${c.name}, ${photoNote}`;
    const cv = $('net-ov'), r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    cv.width = r.width * dpr; cv.height = r.height * dpr; const g = cv.getContext('2d'); g.scale(dpr, dpr); g.clearRect(0, 0, r.width, r.height);
    const key = $('ov-key'); key.innerHTML = '';
    if (B && mode !== 'none') {
      const bw = r.width / B.gw, bh = r.height / B.gh;
      for (let i = 0; i < B.gw * B.gh; i++) {
        if (!B.usable[i] && mode !== 'dist') continue;
        const d = B.dist[i]; if (d == null) continue;
        let col = null;
        if (mode === 'dist') col = distColor(d);
        else if (mode === 'lc') { const k = LC[B.lc[i]]; if (k) col = k[1] + '88'; }
        else if (mode === 'chg' && CH && CH[i] != null) col = chgColor(CH[i]);
        if (!col) continue;
        g.fillStyle = col; g.fillRect((i % B.gw) * bw, Math.floor(i / B.gw) * bh, bw + 0.3, bh + 0.3);
      }
      if (mode === 'dist') {
        g.strokeStyle = 'rgba(255,255,255,0.9)'; g.lineWidth = 1.5;
        for (const D of [1000, 3000, 10000]) for (let y = 0; y < B.gh; y++) for (let x = 0; x < B.gw - 1; x++) {
          const i = y * B.gw + x, a = B.dist[i], b2 = B.dist[i + 1], c2 = y < B.gh - 1 ? B.dist[i + B.gw] : null;
          if (a == null) continue;
          if (b2 != null && (a < D) !== (b2 < D)) { g.beginPath(); g.moveTo((x + 1) * bw, y * bh); g.lineTo((x + 1) * bw, (y + 1) * bh); g.stroke(); }
          if (c2 != null && (a < D) !== (c2 < D)) { g.beginPath(); g.moveTo(x * bw, (y + 1) * bh); g.lineTo((x + 1) * bw, (y + 1) * bh); g.stroke(); }
        }
        key.innerHTML = '<div class="scale"><span>Ground distance from the camera, from the terrain model: white lines at 1, 3 and 10 km; deeper blue is farther.</span></div>';
      } else if (mode === 'lc') {
        const present = new Set(B.lc.filter((v, i) => B.usable[i]));
        key.innerHTML = '<div class="lc-keys">' + Object.entries(LC).filter(([k]) => present.has(+k)).map(([, v]) => `<span><i style="background:${v[1]}"></i>${v[0]}</span>`).join('') + '<span>ESA WorldCover 10 m at each block\'s ground point</span></div>';
      } else if (mode === 'chg') {
        key.innerHTML = lv ? `<div class="scale"><span>dried faster</span><span class="ramp" style="background:linear-gradient(90deg, rgb(194,124,14), rgb(150,150,140), rgb(46,133,64))"></span><span>held up</span></div><div class="scale" style="margin-top:4px"><span>change in greenness from ${fmtShort(toT(lv.first_window[0]))}–${fmtShort(toT(lv.first_window[1]))} to ${fmtShort(toT(lv.last_window[0]))}–${fmtShort(toT(lv.last_window[1]))}, against the view as a whole: brown blocks dried faster than the rest, green ones held up</span></div>` : '<div class="scale"><span>Live numbers unavailable right now.</span></div>';
      }
    }
    const note = document.createElement('p'); note.className = 'note'; note.style.marginTop = '6px'; note.textContent = 'Photo: ' + photoNote + '.'; key.appendChild(note);
    drawLiveMap(c, B, CH);
    const lcTop = Object.entries(c.lc_counts).sort((a, b) => b[1] - a[1]).slice(0, 2).map(([k]) => k).join(', ');
    $('cam-stats').innerHTML = `<div><span class="label">Skyline fit</span><b>${c.median_err_deg.toFixed(2)}°</b></div>
      <div><span class="label">Facing</span><b>${Math.round(((c.yaw % 360) + 360) % 360)}°</b></div>
      <div><span class="label">Ground blocks</span><b>${c.n_blocks.toLocaleString()}</b></div>
      <div><span class="label">Mostly</span><b>${lcTop}</b></div>
      <div><span class="label">Days measured</span><b>${lv ? lv.n_days : '–'}</b></div>
      <div><span class="label">Last day</span><b>${lv ? fmtShort(toT(lv.dates[lv.dates.length - 1])) : '–'}</b></div>
      <div style="grid-column:1/-1"><span class="label">Site</span><b style="font-family:var(--body);font-weight:400;font-size:.92rem">${esc(c.name)}, ${c.elev} m</b></div>`;
  }
  const hsCache = {};
  function drawLiveMap(c, B, CH) {
    const cv = $('map'), r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    cv.width = r.width * dpr; cv.height = r.height * dpr; const g = cv.getContext('2d'); g.scale(dpr, dpr);
    const dark = getComputedStyle(document.documentElement).colorScheme.includes('dark');
    const src = dark ? c.hs_dark : c.hs_light, bd = c.bounds;
    const X = (lon) => (lon - bd.west) / (bd.east - bd.west) * r.width, Y = (lat) => (bd.north - lat) / (bd.north - bd.south) * r.height;
    const paint = (bg) => {
      g.clearRect(0, 0, r.width, r.height);
      if (bg) g.drawImage(bg, 0, 0, r.width, r.height);
      if (B) for (let i = 0; i < B.gw * B.gh; i++) {
        if (!B.usable[i] || B.lat[i] == null) continue;
        let col;
        if (mode === 'chg' && CH && CH[i] != null) col = chgColor(CH[i]);
        else if (mode === 'lc') { const k = LC[B.lc[i]]; col = k ? k[1] : null; }
        else col = dark ? 'rgba(230,235,228,0.55)' : 'rgba(24,33,27,0.5)';
        if (!col) continue;
        g.fillStyle = col; g.fillRect(X(B.lon[i]) - 1.5, Y(B.lat[i]) - 1.5, 3, 3);
      }
      const cx = X(c.lon), cy = Y(c.lat), R = r.width * 0.47;
      const a1 = (c.yaw - c.hfov / 2 - 90) * Math.PI / 180, a2 = (c.yaw + c.hfov / 2 - 90) * Math.PI / 180;
      g.strokeStyle = dark ? 'rgba(230,235,228,0.8)' : 'rgba(24,33,27,0.75)'; g.lineWidth = 1.2;
      g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + R * Math.cos(a1), cy + R * Math.sin(a1)); g.moveTo(cx, cy); g.lineTo(cx + R * Math.cos(a2), cy + R * Math.sin(a2)); g.stroke();
      g.fillStyle = dark ? '#E2E8E0' : '#18211B'; g.beginPath(); g.arc(cx, cy, 4.5, 0, Math.PI * 2); g.fill();
      const km = r.width / (2 * bd.radius_m / 1000);
      g.fillRect(12, r.height - 16, 2 * km, 2); g.font = '11px ' + css('--mono'); g.fillText('2 km', 12, r.height - 22);
      g.fillText('N ↑', r.width - 34, 18);
    };
    if (hsCache[src]) paint(hsCache[src]); else { const im = new Image(); im.onload = () => { hsCache[src] = im; paint(im); }; im.src = src; paint(null); }
  }
  function drawNetChart() {
    const sv = $('net-chart'), c = L.cams[camIdx], lv = liveOf(c);
    const w = sv.clientWidth || 900, h = 200, m = { l: 48, r: 12, t: 12, b: 26 };
    sv.setAttribute('viewBox', `0 0 ${w} ${h}`); sv.setAttribute('height', h); sv.innerHTML = '';
    const leg = $('net-legend'); leg.innerHTML = '';
    if (!lv) return;
    const COL = { tree: '#2f7d3b', shrub: '#9a9a2c', grass: '#d9b44a' };
    const ts = lv.dates.map(toT), a = ts[0], b = ts[ts.length - 1];
    const all = Object.values(lv.series).flat().filter((v) => v != null);
    const lo = Math.min(...all), hi = Math.max(...all), pad = (hi - lo) * 0.1 || 0.01;
    const x = (t) => m.l + (t - a) / Math.max(DAY, b - a) * (w - m.l - m.r), y = (v) => m.t + (1 - (v - lo + pad) / (hi - lo + 2 * pad)) * (h - m.t - m.b);
    const grid = el('g', { class: 'grid' }, sv);
    for (let k = 0; k <= 3; k++) { const v = lo - pad + k * (hi - lo + 2 * pad) / 3; el('line', { x1: m.l, x2: w - m.r, y1: y(v), y2: y(v) }, grid); el('text', { x: 2, y: y(v) + 4 }, sv).textContent = v.toFixed(3); }
    for (let t = Date.UTC(new Date(a).getUTCFullYear(), new Date(a).getUTCMonth() + 1, 1); t <= b; t = Date.UTC(new Date(t).getUTCFullYear(), new Date(t).getUTCMonth() + 1, 1)) { el('line', { x1: x(t), x2: x(t), y1: m.t, y2: h - m.b }, grid); el('text', { x: x(t) + 3, y: h - 8 }, sv).textContent = new Date(t).toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' }) + (new Date(t).getUTCMonth() === 0 || t === Date.UTC(new Date(a).getUTCFullYear(), new Date(a).getUTCMonth() + 1, 1) ? ' ' + new Date(t).getUTCFullYear() : ''); }
    for (const [k, vals] of Object.entries(lv.series)) {
      let d = '', prev = null;
      vals.forEach((v, i) => { if (v == null) { prev = null; return; } d += (prev != null && ts[i] - prev < 4 * DAY ? 'L' : 'M') + x(ts[i]).toFixed(1) + ',' + y(v).toFixed(1); prev = ts[i]; });
      el('path', { d, fill: 'none', stroke: COL[k], 'stroke-width': 2, 'stroke-linejoin': 'round' }, sv);
      leg.insertAdjacentHTML('beforeend', `<span><i class="key-line" style="background:${COL[k]}"></i>${k[0].toUpperCase() + k.slice(1)} blocks within 8 km (median greenness, GRVI)</span>`);
    }
    const hit = el('rect', { x: m.l, y: m.t, width: w - m.l - m.r, height: h - m.t - m.b, fill: 'transparent' }, sv);
    hit.addEventListener('pointermove', (e) => {
      const r = sv.getBoundingClientRect(); const px = (e.clientX - r.left) / r.width * w; const t = a + (px - m.l) / (w - m.l - m.r) * (b - a);
      let bi = 0; ts.forEach((q, i) => { if (Math.abs(q - t) < Math.abs(ts[bi] - t)) bi = i; });
      const tip = $('net-tip'); tip.hidden = false; tip.style.left = (x(ts[bi]) / w * r.width) + 'px'; tip.style.top = '20px';
      tip.innerHTML = fmtDate(ts[bi]) + Object.entries(lv.series).map(([k, v]) => `<br>${k} ${v[bi] != null ? v[bi].toFixed(3) : '–'}`).join('');
    });
    hit.addEventListener('pointerleave', () => { $('net-tip').hidden = true; });
  }

  /* ---------------- toolkit, limits, methods ---------------- */
  $('tk-code').innerHTML = `<span class="c"># install</span>
pip install "fuelgauge[geo,seg,eval] @ git+https://github.com/shourya0mehta/fuel-gauge"

<span class="c"># daily photos from one fixed camera -> registered colours</span>
fuelgauge register-archive photos/ out/mycam

<span class="c"># skyline + 30 m terrain -> pose and pixel-to-ground lookup</span>
fuelgauge calibrate mycam frame.jpg --lat 33.40 --lon -117.19 --elev 483

<span class="c"># in Python</span>
from fuelgauge import track, colour, rois, evaluate
res = track.track(frames, track.Matcher())     <span class="c"># keyframe tracking</span>
views = track.group_views(res, times)          <span class="c"># re-find the view after moves</span>
moves = track.sustained_moves(times, tx, ty)   <span class="c"># when was it bumped?</span>`;
  $('tk-mods').innerHTML = [
    ['track', 'Multi-year registration: keyframe tracking within stretches, then loop-closure linking across camera moves.'],
    ['terrain', 'Renders the skyline from a DEM (with earth curvature and refraction), fits camera pose and a shared fisheye lens, maps pixels to ground.'],
    ['camera', 'Fisheye camera model: pixel to azimuth and elevation and back.'],
    ['segment', 'SegFormer sky and ground masks through ONNX Runtime, no PyTorch needed.'],
    ['rois', 'Chooses the brush to measure and the rock and soil to white-balance against, with no hand-drawn masks.'],
    ['quality', 'Frame screening and a haze score from edge agreement with the master view.'],
    ['colour', 'Block colours, GCC and GRVI, white balance, causal smoothing.'],
    ['evaluate', 'Leave-one-year-out scoring against field fuel moisture, with a per-site seasonal baseline.'],
    ['sources', 'Readers for PhenoCam, HPWREN, Globe-LFMC and MODIS on Planetary Computer.'],
    ['coverage', 'Script: statewide terrain viewsheds for any list of camera positions, plus smoke-column line of sight to fire ignitions.'],
  ].map(([k, v]) => `<div><code>${k}</code><span>${v}</span></div>`).join('') + `<div><code>tests</code><span>${(S.text && S.text.tests) || 'Synthetic camera drift and re-aims, synthetic terrain pose recovery, and a check that no held-out year leaks into its own prediction.'}</span></div>`;
  const LIM = (S.text && S.text.limits) || [
    ['Distance', 'Field samples are taken up to 25 km from each camera, sometimes on a different slope and species from the brush in view. A closer match would raise every predictor\'s score, the camera\'s most of all.'],
    ['Colour only', 'Ordinary cameras record red, green and blue. Leaf water shows up most clearly in infrared, which only the satellite has here, and colour changes after a plant has already dried. Most PhenoCams also record near-infrared (12 of the 23 here), the obvious next test.'],
    ['Old archives', 'The study cameras are research cameras, mostly retired. The live fire cameras have no field samples close enough to score yet, so the live section shows change, not fuel moisture.'],
    ['Small samples', 'Crews sample every two to four weeks, so each camera has a few hundred samples over 5 to 16 years. Year-to-year results are noisy, which is why every number here is scored on held-out years.'],
  ];
  if (C) LIM.unshift(['Coverage assumptions', 'The map uses today\'s cameras against fires from 2020 to 2025. It assumes every site can pan a full circle and see 30 km, and ignores haze, night, trees by the mast and where each camera was pointed. Ignition points can be off by hundreds of metres.']);
  if ($('limits-grid')) $('limits-grid').innerHTML = LIM.map((l) => `<div><h3>${l[0]}</h3><p>${l[1]}</p></div>`).join('');
  $('methods-body').innerHTML = (S.text && S.text.methods) || `
    <p><b>Cameras.</b> PhenoCam Network midday photos (one per day) for every camera with Globe-LFMC field samples within 25 km, overlapping years only. HPWREN fire cameras for the live network, pulled from the public CDN.</p>
    <p><b>Registration.</b> SIFT features on contrast-equalised frames, 4-degree-of-freedom similarity transforms by RANSAC, keyframe tracking within stretches, new stretch after four lost frames, stretches joined by their clearest keyframes (at least 30 inliers). A camera moved to a new spot becomes a second view with its own calibration.</p>
    <p><b>Measurement.</b> 24-pixel blocks on the registered view. Vegetation from a SegFormer-B2 (ADE20K) label map plus each block's seasonal swing; reference blocks for white balance are covered, non-vegetation and seasonally flat. Daily index: GRVI = (G − R) / (G + R), clear days only (haze scored by edge agreement), trailing 90th percentile over a week then a trailing two-week mean.</p>
    <p><b>Scoring.</b> Ridge regression with one intercept and one set of day-of-year harmonics per sampling unit (site and species); predictors use the index level and its 30-day change. Leave-one-year-out; RMSE, R², anomaly correlation, years better than season alone.</p>
    <p><b>Satellite.</b> MODIS MCD43A4 v6.1 nadir reflectance (500 m, daily product sampled every 8 days, 3 × 3 pixel mean) at a point 1 km along each camera's view and at each sampling site; NDVI, NDII (with shortwave infrared) and green chromatic coordinate; 17-day rolling median.</p>
    <p><b>Live network.</b> Copernicus GLO-30 DEM panoramas with earth curvature and refraction (k = 0.13); skyline from SegFormer; bounded pose fit with a trimmed skyline loss; one equidistant fisheye lens fitted jointly across eight cameras. Land cover: ESA WorldCover 2021.</p>
    <p><b>Coverage.</b> ALERTCalifornia camera positions from the public camera map, grouped into sites. For each site, rays every 0.1° out to 30 km from a 10 m mast over the Copernicus 90 m DEM, with earth curvature and refraction; a cell is in view if no terrain rises above the line of sight. Ignitions: NIFC WFIGS incident locations, California wildfires 2020 to 2025; for fires of 10 acres or more, line of sight to points 100 m and 300 m above the ignition is tested from every site within 30 km.</p>
    <p><b>Near-infrared.</b> For the ten IR-capable cameras, the IR photo taken with each colour photo (or that day's midday IR photo) and both exposure settings from the archive's metadata. Each IR photo is warped with its colour photo's registration; camera NDVI per block follows Petach et al. (2014).</p>
    <p><b>Sources.</b></p>
    <ul>
      <li>PhenoCam Network, <a href="https://phenocam.nau.edu">phenocam.nau.edu</a> (Richardson et al. 2018, Scientific Data). Per-camera acknowledgements are in the repository.</li>
      <li>HPWREN camera network, <a href="https://hpwren.ucsd.edu">hpwren.ucsd.edu</a>, UC San Diego.</li>
      <li>Globe-LFMC 2.0 (Yebra et al. 2024, Scientific Data), compiled from the US National Fuel Moisture Database and others.</li>
      <li>MODIS MCD43A4 v6.1 and Copernicus DEM GLO-30 via Microsoft Planetary Computer; ESA WorldCover 10 m 2021.</li>
      <li>SegFormer-B2 fine-tuned on ADE20K (NVIDIA), ONNX export by Xenova on Hugging Face.</li>
      <li>ALERTCalifornia camera network, <a href="https://alertcalifornia.org">alertcalifornia.org</a> (UC San Diego with CAL FIRE).</li>
      <li>NIFC WFIGS wildland fire incident locations, National Interagency Fire Center.</li>
      <li>Petach, Toomey, Aubrecht and Richardson (2014), Agricultural and Forest Meteorology, for camera NDVI.</li>
    </ul>`;

  /* ---------------- boot ---------------- */
  function all() { drawTimeline(); drawHeroRoi(); drawMap(); drawBoard(); if (CD) { drawExOverlay(); drawCalendar(); drawExPred(); } renderLive(); drawNetChart(); }
  setTime(cur);
  drawTimeline(); drawMap(); drawBoard();
  await selectCam(selCam, false);
  loadCam();
  let rt = null; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(all, 140); });
  const mq = window.matchMedia('(prefers-color-scheme: dark)'); if (mq.addEventListener) mq.addEventListener('change', all);
  new MutationObserver(all).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
})();
