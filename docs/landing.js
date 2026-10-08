/* Fuel Gauge landing page. Data: data/hero.skyline.json (skylines of four calibrated fire cameras), data/live.json and
   assets/live/<cam>_blocks.json (pixel-to-ground lookups), data/hero.json (registration record of one ridge camera),
   data/study.json and data/coverage.json (results). */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
  const getJSON = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(u); return r.json(); });
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const fmt = (n, d = 0) => Number(n).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d });
  const pct = (x) => Math.round(x * 100) + '%';
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const LC = { 10: ['Tree cover', '#2F7D3B'], 20: ['Shrubland', '#A3A033'], 30: ['Grassland', '#DDB64C'], 40: ['Cropland', '#C38D60'], 50: ['Built-up', '#B04A3B'], 60: ['Bare ground', '#A99A8A'], 80: ['Water', '#3B78C2'], 90: ['Wetland', '#3B9C9C'] };
  const COMPASS = ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west'];
  const facing = (a) => COMPASS[Math.round(((a % 360) + 360) % 360 / 45) % 8];

  /* copy buttons and tabs */
  document.querySelectorAll('[data-copy]').forEach((b) => b.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = 'Copied'; } catch (e) { b.textContent = 'Select and copy'; }
    setTimeout(() => { b.textContent = 'Copy'; }, 1600);
  }));
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  tabs.forEach((t) => t.addEventListener('click', () => tabs.forEach((x) => {
    const on = x === t; x.setAttribute('aria-selected', String(on)); $(x.getAttribute('aria-controls')).hidden = !on;
  })));

  /* registration compare slider */
  const cmp = $('compare');
  if (cmp) { const r = cmp.querySelector('input'); const set = () => cmp.style.setProperty('--cut', r.value + '%'); r.addEventListener('input', set); set(); }

  Promise.all([getJSON('data/hero.skyline.json'), getJSON('data/live.json'), getJSON('data/hero.json').catch(() => null),
    getJSON('data/study.json').catch(() => null), getJSON('data/coverage.json').catch(() => null), getJSON('data/cam/cucamongasouth.json').catch(() => null)])
    .then(([SK, L, H, S, C, CD]) => { instrument(SK, L); skylineChart(SK, L); geo(L); if (H) registration(H, S); if (CD) measureBlock(CD, S); if (S) evaluation(S); if (C) coverage(C); results(S, C); })
    .catch((e) => console.error(e));

  const blocksCache = {};
  const loadBlocks = (c) => blocksCache[c.id] || (blocksCache[c.id] = getJSON(c.blocks));

  /* ---------------- hero: a calibrated fire camera ---------------- */
  let heroCam = null; const listeners = [];
  function instrument(SK, L) {
    const ids = Object.keys(SK);
    const byId = Object.fromEntries(L.cams.map((c) => [c.id, c]));
    const sw = $('cam-switch');
    ids.forEach((id, i) => {
      const b = document.createElement('button'); b.type = 'button'; b.textContent = byId[id].short; b.setAttribute('aria-pressed', String(i === 0));
      b.addEventListener('click', () => { [...sw.children].forEach((x) => x.setAttribute('aria-pressed', String(x === b))); show(id, false); });
      sw.appendChild(b);
    });
    const frame = $('frame'), svg = $('frame-svg'), cv = $('frame-ov'), img = $('frame-img');
    let cur = null, B = null, hover = -1;

    function show(id, first) {
      const c = byId[id], s = SK[id]; heroCam = id; listeners.forEach((f) => f(id));
      img.src = c.img_oct; img.alt = `${c.name}, ${c.dir_label.toLowerCase()}, autumn 2026`;
      cur = { c, s }; B = null; hover = -1;
      drawSvg(first && !reduced); readout(); drawHover();
      $('frame-cap').textContent = `${c.name}, ${c.dir_label.toLowerCase()} from ${fmt(c.elev)} m. Solved pose: heading ${s.yaw.toFixed(1)}°, tilt ${s.pitch.toFixed(2)}°, roll ${s.roll.toFixed(2)}°. Median skyline disagreement ${s.err.toFixed(2)}°, about ${Math.max(1, Math.round(s.err / (s.hfov / s.w)))} pixel${Math.round(s.err / (s.hfov / s.w)) > 1 ? 's' : ''}. Hover or tap the hillside to read any spot off the terrain.`;
      loadBlocks(c).then((b) => { if (cur && cur.c.id === id) { B = b; drawContours(); readout(); } }).catch(() => {});
    }
    function cleanDetected(s) {
      // drop columns the robust fit trimmed (poles, trees by the mast): far from the predicted skyline
      const R = s.rendered; let j = 0; const out = [];
      for (const [u, v] of s.detected) {
        while (j < R.length - 2 && R[j + 1][0] < u) j++;
        const [u0, v0] = R[j], [u1, v1] = R[Math.min(j + 1, R.length - 1)];
        const pv = u1 === u0 ? v0 : v0 + (v1 - v0) * (u - u0) / (u1 - u0);
        out.push(Math.abs(v - pv) < 40 ? [u, v] : null);
      }
      return out;
    }
    const pathOf = (pts) => { let d = '', pen = false; for (const p of pts) { if (!p) { pen = false; continue; } d += (pen ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1); pen = true; } return d; };
    function drawSvg(animate) {
      const { s } = cur; svg.innerHTML = '';
      svg.setAttribute('viewBox', `0 0 ${s.w} ${s.h}`);
      const ruler = el('g', { class: 'ruler' }, svg);
      const ry = s.h - s.w * 9 / 16 + 56;
      el('line', { x1: 0, x2: s.w, y1: ry, y2: ry }, ruler).setAttribute('opacity', '0.5');
      s.ticks.forEach(([u, az]) => {
        el('line', { x1: u, x2: u, y1: ry - 16, y2: ry + 16 }, ruler);
        const t = el('text', { x: u + 6, y: ry - 22 }, ruler); t.textContent = `${((az % 360) + 360) % 360}°`;
      });
      for (let k = 0; k < s.ticks.length - 1; k++) { const u = (s.ticks[k][0] + s.ticks[k + 1][0]) / 2; el('line', { x1: u, x2: u, y1: ry - 6, y2: ry + 6 }, ruler); }
      el('g', { id: 'contours' }, svg);
      el('path', { class: 'sk-dem', d: pathOf(s.rendered) }, svg);
      const det = el('path', { class: 'sk-det', d: pathOf(cleanDetected(s)) }, svg);
      if (animate) {
        const len = det.getTotalLength ? det.getTotalLength() : 3000;
        det.style.setProperty('--len', String(Math.ceil(len) + 10)); det.setAttribute('pathLength', String(Math.ceil(len) + 10));
        det.classList.add('draw');
      }
    }
    function drawContours() {
      const g = svg.querySelector('#contours'); if (!g || !B) return; g.innerHTML = '';
      const { s } = cur, bw = s.w / B.gw, bh = s.h / B.gh;
      for (const D of [1000, 3000, 10000]) {
        let d = ''; let label = null;
        for (let y = 0; y < B.gh; y++) for (let x = 0; x < B.gw; x++) {
          const i = y * B.gw + x, a = B.dist[i]; if (a == null || !B.usable[i]) continue;
          const r = x < B.gw - 1 ? B.dist[i + 1] : null, dn = y < B.gh - 1 ? B.dist[i + B.gw] : null;
          if (r != null && B.usable[i + 1] && (a < D) !== (r < D)) d += `M${(x + 1) * bw},${y * bh}V${(y + 1) * bh}`;
          if (dn != null && B.usable[i + B.gw] && (a < D) !== (dn < D)) {
            d += `M${x * bw},${(y + 1) * bh}H${(x + 1) * bw}`;
            if (!label || Math.abs(x - B.gw * 0.62) < Math.abs(label[0] - B.gw * 0.62)) label = [x, y];
          }
        }
        el('path', { d, fill: 'none', stroke: '#FFFFFF', 'stroke-width': 1.4, 'stroke-opacity': 0.75, 'vector-effect': 'non-scaling-stroke' }, g);
        if (label) { const t = el('text', { class: 'contour-label', x: label[0] * bw + 4, y: (label[1] + 1) * bh - 8 }, g); t.textContent = `${D / 1000} km`; }
      }
    }
    function bearingAt(u) {
      const T = cur.s.ticks; let k = 0; while (k < T.length - 2 && T[k + 1][0] < u) k++;
      const [u0, a0] = T[k], [u1, a1] = T[k + 1]; return ((a0 + (a1 - a0) * (u - u0) / (u1 - u0)) % 360 + 360) % 360;
    }
    function readout() {
      const ro = $('readout'), { c, s } = cur;
      if (hover < 0 || !B || !B.usable[hover] || B.dist[hover] == null) {
        ro.innerHTML = `<div class="big">${c.short}</div><dl><dt>Heading</dt><dd>${s.yaw.toFixed(1)}°</dd><dt>Tilt</dt><dd>${s.pitch.toFixed(2)}°</dd><dt>Roll</dt><dd>${s.roll.toFixed(2)}°</dd><dt>Field of view</dt><dd>${s.hfov.toFixed(1)}°</dd><dt>Skyline error</dt><dd>${s.err.toFixed(2)}°</dd></dl><p class="hint" style="margin-top:8px">${B ? 'Point at the hillside to read the ground.' : 'Loading the ground lookup.'}</p>`;
        return;
      }
      const i = hover, x = i % B.gw, d = B.dist[i];
      const lc = LC[B.lc[i]];
      ro.innerHTML = `<div class="big">${d < 1000 ? fmt(d) + ' m' : fmt(d / 1000, 1) + ' km'} away</div><dl>
        <dt>Bearing</dt><dd>${bearingAt((x + 0.5) * s.w / B.gw).toFixed(1)}°</dd>
        <dt>Land cover</dt><dd>${lc ? lc[0] : 'unknown'}</dd>
        <dt>Slope faces</dt><dd>${B.aspect[i] != null ? facing(B.aspect[i]) : 'flat'}</dd>
        <dt>Ground point</dt><dd>${B.lat[i].toFixed(4)}, ${B.lon[i].toFixed(4)}</dd></dl>`;
    }
    // the photo is shown cropped from the top (object-position bottom): image height = width / 1.5
    const geom = (r) => { const ih = r.width * cur.s.h / cur.s.w; return { ih, off: ih - r.height }; };
    function drawHover() {
      const r = frame.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
      cv.width = r.width * dpr; cv.height = r.height * dpr; const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, r.width, r.height);
      if (!B || hover < 0 || !B.usable[hover]) return;
      const { ih, off } = geom(r), bw = r.width / B.gw, bh = ih / B.gh, x = hover % B.gw, y = Math.floor(hover / B.gw);
      g.strokeStyle = css('--signal'); g.lineWidth = 2.5; g.strokeRect(x * bw - 1, y * bh - off - 1, bw + 2, bh + 2);
    }
    const pick = (e) => {
      if (!B) return; const r = frame.getBoundingClientRect(), { ih, off } = geom(r);
      const x = Math.floor((e.clientX - r.left) / r.width * B.gw), y = Math.floor((e.clientY - r.top + off) / ih * B.gh);
      const i = x >= 0 && y >= 0 && x < B.gw && y < B.gh ? y * B.gw + x : -1;
      if (i !== hover) { hover = i; readout(); drawHover(); }
    };
    frame.addEventListener('pointermove', pick); frame.addEventListener('pointerdown', pick);
    frame.addEventListener('pointerleave', (e) => { if (e.pointerType === 'mouse') { hover = -1; readout(); drawHover(); } });
    window.addEventListener('resize', drawHover);
    show(ids[0], true);
  }

  /* ---------------- calibrate: skyline residuals ---------------- */
  function skylineChart(SK, L) {
    const sv = $('sky-chart'); if (!sv) return;
    const draw = (id) => {
      const s = SK[id], c = L.cams.find((x) => x.id === id);
      const w = sv.clientWidth || 640, h = 300, m = { l: 46, r: 10, t: 14, b: 30 }, mid = 168;
      sv.setAttribute('viewBox', `0 0 ${w} ${h}`); sv.setAttribute('height', h); sv.innerHTML = '';
      const degpp = s.hfov / s.w;
      const T = s.ticks; const bearing = (u) => { let k = 0; while (k < T.length - 2 && T[k + 1][0] < u) k++; const [u0, a0] = T[k], [u1, a1] = T[k + 1]; return a0 + (a1 - a0) * (u - u0) / (u1 - u0); };
      const b0 = bearing(0), b1 = bearing(s.w);
      const X = (u) => m.l + (bearing(u) - b0) / (b1 - b0) * (w - m.l - m.r);
      // upper panel: skylines as elevation above the frame centre, degrees
      const ev = (v) => (s.h / 2 - v) * degpp;
      const all = s.rendered.map((p) => ev(p[1])); const lo = Math.min(...all) - 0.6, hi = Math.max(...all) + 0.6;
      const Y = (a) => m.t + (1 - (a - lo) / (hi - lo)) * (mid - m.t - 18);
      const grid = el('g', { class: 'grid' }, sv);
      [lo + 0.6, (lo + hi) / 2, hi - 0.6].forEach((a) => { el('line', { x1: m.l, x2: w - m.r, y1: Y(a), y2: Y(a) }, grid); el('text', { x: 0, y: Y(a) + 4 }, sv).textContent = a.toFixed(1) + '°'; });
      const R = s.rendered; let j = 0; let dR = '', dD = '', pen = false; const res = [];
      R.forEach((p, k) => { dR += (k ? 'L' : 'M') + X(p[0]).toFixed(1) + ',' + Y(ev(p[1])).toFixed(1); });
      for (const [u, v] of s.detected) {
        while (j < R.length - 2 && R[j + 1][0] < u) j++;
        const [u0, v0] = R[j], [u1, v1] = R[Math.min(j + 1, R.length - 1)]; const pv = u1 === u0 ? v0 : v0 + (v1 - v0) * (u - u0) / (u1 - u0);
        res.push([u, (pv - v) * degpp, v]);
      }
      const cutoff = res.map((x) => Math.abs(x[1])).sort((a, b) => a - b)[Math.floor(res.length * 0.8)];
      res.forEach((x) => { x[3] = Math.abs(x[1]) <= cutoff; });
      res.forEach(([u, , v, ok]) => { if (ok) { dD += (pen ? 'L' : 'M') + X(u).toFixed(1) + ',' + Y(ev(v)).toFixed(1); pen = true; } else pen = false; });
      el('path', { d: dR, fill: 'none', stroke: css('--ink-2'), 'stroke-width': 1.5, 'stroke-dasharray': '4 4' }, sv);
      el('path', { d: dD, fill: 'none', stroke: css('--signal'), 'stroke-width': 2.2 }, sv);
      el('text', { x: m.l, y: m.t - 2 }, sv).textContent = 'Skyline height above the frame centre';
      // lower panel: residual, degrees
      const rr = Math.min(2, Math.max(0.5, Math.ceil(cutoff * 2.5 * 10) / 10)), Y2 = (r) => mid + 22 + (1 - (Math.max(-rr, Math.min(rr, r)) + rr) / (2 * rr)) * (h - m.b - mid - 22);
      el('text', { x: m.l, y: mid + 12 }, sv).textContent = 'Found minus predicted, degrees';
      [-rr / 2, 0, rr / 2].forEach((a) => { el('line', { x1: m.l, x2: w - m.r, y1: Y2(a), y2: Y2(a) }, grid); el('text', { x: 0, y: Y2(a) + 4 }, sv).textContent = (a > 0 ? '+' : '') + a.toFixed(2) + '°'; });
      el('rect', { x: m.l, y: Y2(s.err), width: w - m.l - m.r, height: Math.max(1, Y2(-s.err) - Y2(s.err)), fill: css('--signal'), 'fill-opacity': 0.12 }, sv);
      res.forEach(([u, r, , ok]) => el('circle', { cx: X(u), cy: Y2(r), r: ok ? 1.6 : 1.4, fill: ok ? css('--signal') : css('--slate'), 'fill-opacity': ok ? 0.9 : 0.5 }, sv));
      T.forEach(([u, az]) => { const t = el('text', { x: X(u), y: h - 8, 'text-anchor': 'middle' }, sv); t.textContent = `${((az % 360) + 360) % 360}°`; });
      const kept = res.filter((x) => x[3]).length;
      $('sky-cap').textContent = `${c.short}, ${c.dir_label.toLowerCase()}: the skyline found in the photo (orange) against the one rendered from the terrain after solving the pose (dashed), across ${Math.round(b1 - b0)}° of bearing. Below, the difference at each of ${res.length} image columns. The fit ignores the worst ${res.length - kept} (grey), where trees, buildings or the camera housing stand in front of the true skyline. Shaded band: the median error, ${s.err.toFixed(2)}°.`;
    };
    listeners.push(draw);
    if (heroCam) draw(heroCam);
    let t; window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => heroCam && draw(heroCam), 150); });
    const cams = L.cams.slice().sort((a, b) => a.median_err_deg - b.median_err_deg), mx = Math.max(...cams.map((c) => c.median_err_deg));
    $('errs').innerHTML = `<caption class="cap" style="caption-side:top;text-align:left;padding-bottom:6px">Median skyline error after fitting, all eight fire cameras, one shared lens</caption>` +
      cams.map((c) => `<tr><td>${c.short}</td><td><span class="bar" style="width:${Math.round(c.median_err_deg / mx * 120)}px"></span>${c.median_err_deg.toFixed(2)}°</td></tr>`).join('');
  }

  /* ---------------- georeference ---------------- */
  function geo(L) {
    const modeBox = $('geo-mode'); if (!modeBox) return;
    let mode = 'dist', idx = Math.max(0, L.cams.findIndex((c) => c.id === L.default));
    // camera picker joins the overlay buttons
    const sel = document.createElement('select'); sel.className = 'btn small'; sel.setAttribute('aria-label', 'Camera'); 
    L.cams.forEach((c, i) => { const o = document.createElement('option'); o.value = i; o.textContent = c.short; if (i === idx) o.selected = true; sel.appendChild(o); });
    sel.addEventListener('change', () => { idx = +sel.value; render(); });
    modeBox.parentNode.insertBefore(Object.assign(document.createElement('div'), { className: 'geo-controls' }), modeBox);
    const ctl = modeBox.previousSibling; ctl.style.cssText = 'display:flex;flex-wrap:wrap;gap:10px;align-items:center'; ctl.append(modeBox, sel);
    modeBox.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
      mode = b.dataset.mode; modeBox.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); render();
    }));
    const distCol = (d) => { const t = Math.min(1, Math.log10(Math.max(200, d) / 200) / Math.log10(150)); return `rgba(${Math.round(255 - 215 * t)},${Math.round(225 - 140 * t)},${Math.round(120 + 100 * t)},0.62)`; };
    const aspCol = (a) => { const t = (1 - Math.cos(a * Math.PI / 180)) / 2; return `rgba(${Math.round(60 + 182 * t)},${Math.round(110 - 26 * t)},${Math.round(200 - 173 * t)},0.6)`; };
    const colOf = (B, i) => {
      if (mode === 'dist') return distCol(B.dist[i]);
      if (mode === 'lc') { const k = LC[B.lc[i]]; return k ? k[1] + 'A6' : null; }
      return B.aspect[i] == null ? 'rgba(160,160,160,0.4)' : aspCol(B.aspect[i]);
    };
    const hs = {};
    async function render() {
      const c = L.cams[idx]; const img = $('geo-img');
      if (img.getAttribute('src') !== c.img_oct) { img.src = c.img_oct; img.alt = `${c.name}, ${c.dir_label.toLowerCase()}`; }
      let B; try { B = await loadBlocks(c); } catch (e) { return; }
      const cv = $('geo-ov'), r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
      cv.width = r.width * dpr; cv.height = r.height * dpr; const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0);
      const bw = r.width / B.gw, bh = r.height / B.gh;
      for (let i = 0; i < B.gw * B.gh; i++) { if (!B.usable[i] || B.dist[i] == null) continue; const col = colOf(B, i); if (!col) continue; g.fillStyle = col; g.fillRect((i % B.gw) * bw, Math.floor(i / B.gw) * bh, bw + 0.4, bh + 0.4); }
      // map
      const mc = $('geo-map'), mr = mc.getBoundingClientRect(); mc.width = mr.width * dpr; mc.height = mr.height * dpr; const m = mc.getContext('2d'); m.setTransform(dpr, 0, 0, dpr, 0, 0);
      const dark = matchMedia('(prefers-color-scheme: dark)').matches && document.documentElement.dataset.theme !== 'light';
      const src = dark ? c.hs_dark : c.hs_light, bd = c.bounds;
      const X = (lon) => (lon - bd.west) / (bd.east - bd.west) * mr.width, Y = (lat) => (bd.north - lat) / (bd.north - bd.south) * mr.height;
      const paint = (bg) => {
        m.clearRect(0, 0, mr.width, mr.height); if (bg) m.drawImage(bg, 0, 0, mr.width, mr.height);
        for (let i = 0; i < B.gw * B.gh; i++) { if (!B.usable[i] || B.lat[i] == null) continue; const col = colOf(B, i); if (!col) continue; m.fillStyle = col.replace(/,0\.\d+\)$/, ',0.95)').replace(/A6$/, ''); m.fillRect(X(B.lon[i]) - 1.6, Y(B.lat[i]) - 1.6, 3.2, 3.2); }
        const cx = X(c.lon), cy = Y(c.lat), R = mr.width * 0.47, a1 = (c.yaw - c.hfov / 2 - 90) * Math.PI / 180, a2 = (c.yaw + c.hfov / 2 - 90) * Math.PI / 180;
        m.strokeStyle = css('--ink'); m.globalAlpha = 0.7; m.lineWidth = 1.2; m.beginPath(); m.moveTo(cx, cy); m.lineTo(cx + R * Math.cos(a1), cy + R * Math.sin(a1)); m.moveTo(cx, cy); m.lineTo(cx + R * Math.cos(a2), cy + R * Math.sin(a2)); m.stroke(); m.globalAlpha = 1;
        m.fillStyle = css('--signal'); m.beginPath(); m.arc(cx, cy, 5, 0, Math.PI * 2); m.fill();
        const km = mr.width / (2 * bd.radius_m / 1000); m.fillStyle = css('--ink'); m.fillRect(12, mr.height - 16, 2 * km, 2); m.font = '12px ' + css('--font'); m.fillText('2 km', 12, mr.height - 22); m.fillText('N', mr.width - 20, 20);
      };
      if (hs[src]) paint(hs[src]); else { const im = new Image(); im.onload = () => { hs[src] = im; paint(im); }; im.src = src; paint(null); }
      const key = $('geo-key');
      if (mode === 'dist') key.innerHTML = `<span><i style="background:${distCol(300)}"></i>under 1 km</span><span><i style="background:${distCol(3000)}"></i>about 3 km</span><span><i style="background:${distCol(12000)}"></i>10 km and beyond</span>`;
      else if (mode === 'lc') { const present = new Set(B.lc.filter((v, i) => B.usable[i])); key.innerHTML = Object.entries(LC).filter(([k]) => present.has(+k)).map(([, v]) => `<span><i style="background:${v[1]}"></i>${v[0]}</span>`).join('') + '<span>ESA WorldCover 10 m</span>'; }
      else key.innerHTML = `<span><i style="background:${aspCol(0)}"></i>faces north, shaded</span><span><i style="background:${aspCol(90)}"></i>east or west</span><span><i style="background:${aspCol(180)}"></i>faces south, sun-baked</span>`;
      $('geo-cap').textContent = `${c.name}. Left: the photo with each 16-pixel ground block coloured. Right: the same ${fmt(c.n_blocks)} blocks placed on the map at the ground point their line of sight reaches, over shaded relief. The wedge is the camera's field of view.`;
    }
    render();
    let t; window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(render, 150); });
  }

  /* ---------------- register: segment record ---------------- */
  function registration(H, S) {
    const box = $('seg-track'); if (!box) return;
    const toT = (s) => Date.parse(s + 'T00:00:00Z');
    const t0 = toT(H.segments[0].start), t1 = toT(H.segments[H.segments.length - 1].end);
    const row = document.createElement('div'); row.className = 'row';
    H.segments.forEach((s) => { const i = document.createElement('i'); const a = toT(s.start), b = toT(s.end); i.style.left = (100 * (a - t0) / (t1 - t0)) + '%'; i.style.width = Math.max(0.4, 100 * (b - a) / (t1 - t0)) + '%'; i.title = `${s.start} to ${s.end}: ${fmt(s.n)} photos`; if (!s.linked) i.style.background = css('--slate'); row.appendChild(i); });
    const mv = document.createElement('div'); mv.className = 'moves';
    (H.moves || []).forEach((m) => { const i = document.createElement('i'); i.style.left = (100 * (toT(m.d) - t0) / (t1 - t0)) + '%'; i.title = `${m.d}: view shifted ${m.px} px`; mv.appendChild(i); });
    const ax = document.createElement('div'); ax.className = 'axis';
    const y0 = new Date(t0).getUTCFullYear(), y1 = new Date(t1).getUTCFullYear();
    for (let y = y0; y <= y1; y += 3) ax.insertAdjacentHTML('beforeend', `<span>${y}</span>`);
    const lab = document.createElement('p'); lab.className = 'cap';
    lab.innerHTML = `The same camera's ${fmt(H.counts.registered)} registered photos, ${y0} to ${y1}. Green bars are tracked stretches, all joined back to one view; orange ticks are the ${H.moves.length} days the camera was knocked or re-aimed.`;
    box.append(row, mv, ax, lab);
    if (S && S.totals) {
      const t = S.totals;
      $('reg-stats').innerHTML = `<div><b>${pct(t.frames / t.frames_ok)}</b><span>of ${fmt(t.frames_ok)} usable photos from ${t.cams} cameras locked onto a view</span></div><div><b>${t.moved}</b><span>cameras moved to a new mast, kept as second views</span></div><div><b>${(() => { const [a, b] = t.years_span.split('–'); return a + '–' + (b.length === 2 ? a.slice(0, 2) + b : b); })()}</b><span>photo records across ${S.totals.states} states</span></div>`;
    }
  }

  /* ---------------- measure: regions and 15 years of greenness ---------------- */
  function measureBlock(CD, S) {
    const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
    const img = $('roi-img'), cv = $('roi-ov');
    const [gw, gh] = typeof CD.grid === 'string' ? JSON.parse(CD.grid) : CD.grid;
    const draw = () => {
      const r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1; cv.width = r.width * dpr; cv.height = r.height * dpr;
      const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); const bw = r.width / gw, bh = r.height / gh;
      const fill = { veg: css('--field'), ref: css('--signal') };
      for (const k of ['veg', 'ref']) { g.fillStyle = fill[k]; g.globalAlpha = 0.55; [...CD[k]].forEach((v, i) => { if (v === '1') g.fillRect((i % gw) * bw, Math.floor(i / gw) * bh, bw, bh); }); }
      g.globalAlpha = 1;
    };
    if (img.complete && img.naturalWidth) draw(); else img.addEventListener('load', draw);
    window.addEventListener('resize', draw);
    const cv2 = $('green-chart'), cal = CD.calendar;
    const chart = () => {
      // one row per year, one column per day; straw = cured, green = flush
      const ny = cal.rows.length, lab = 40, w = cv2.clientWidth || 600, rowH = Math.max(10, Math.min(15, Math.floor(260 / ny))), top = 18, h = top + ny * rowH;
      const dpr = window.devicePixelRatio || 1; cv2.width = w * dpr; cv2.height = h * dpr; cv2.style.height = h + 'px';
      const g = cv2.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
      const cw = (w - lab) / 366, straw = [214, 176, 92], green = [24, 104, 72];
      g.fillStyle = css('--bg-2'); g.fillRect(lab, top, w - lab, ny * rowH);
      cal.rows.forEach((row, y) => {
        for (let d = 0; d < row.length; d++) {
          const ch = row[d]; if (ch === '.') continue;
          const k = B64.indexOf(ch) / 63;
          g.fillStyle = `rgb(${straw.map((c, j) => Math.round(c + (green[j] - c) * k)).join(',')})`;
          g.fillRect(lab + d * cw, top + y * rowH, cw + 0.6, rowH - 1);
        }
      });
      g.fillStyle = css('--slate'); g.font = '11px ' + css('--font'); g.textBaseline = 'middle';
      cal.years.forEach((y, i) => { if (i % 3 === 0 || i === ny - 1) g.fillText(String(y), 0, top + (i + 0.5) * rowH); });
      ['Jan', 'Apr', 'Jul', 'Oct'].forEach((m, j) => g.fillText(m, lab + [0, 90, 181, 273][j] * cw, 8));
    };
    chart(); let t; window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => { chart(); }, 150); });
    if (S && S.pooled && S.summary) {
      const hv = S.pooled.hand_vs_auto, p = S.summary.pooled;
      $('measure-stats').innerHTML = `<div><b>${hv.auto_better} of ${hv.cams}</b><span>cameras where automatic regions beat the network's hand-drawn ones</span></div><div><b>${p.camera_auto.anomaly_r.toFixed(2)} to ${p.camera_auto_wb.anomaly_r.toFixed(2)}</b><span>anomaly correlation with field fuel moisture before and after white balance</span></div>`;
    }
  }

  /* ---------------- evaluation ---------------- */
  function evaluation(S) {
    const p = S.summary.pooled, t = S.totals;
    const rows = [['season', 'Season alone'], ['camera_auto', 'Camera'], ['camera_auto_wb', 'Camera, white-balanced'], ['sat_ir_site', 'Satellite infrared at the sampling site'], ['camera_plus_sat_ir', 'Camera and satellite together']];
    const best = rows.slice(1).reduce((a, r) => (p[r[0]].anomaly_r > p[a].anomaly_r ? r[0] : a), 'camera_auto');
    $('score').innerHTML = `<thead><tr><th>Predictor, added to each site's seasonal cycle</th><th>Cameras where it beats season alone</th><th>Error, points of moisture</th><th>Anomaly correlation</th></tr></thead><tbody>` +
      rows.map(([k, l]) => `<tr${k === best ? ' class="hi"' : ''}><td>${l}</td><td>${k === 'season' ? '–' : `${p[k].cams_better} of ${p[k].cams}`}</td><td>${p[k].rmse.toFixed(1)}</td><td>${k === 'season' ? '0' : p[k].anomaly_r.toFixed(2)}</td></tr>`).join('') + '</tbody>';
    $('score-cap').textContent = `${fmt(t.samples)} held-out field samples of live fuel moisture from Globe-LFMC near ${t.cams} PhenoCam cameras in ${t.states} states, ${t.years_span}. Anomaly correlation asks whether a predictor knew a year was wetter or drier than usual.`;
    $('eval-text').textContent = `Run on 21 cameras, it showed that camera greenness matches the seasonal baseline (${p.camera_auto_wb.rmse.toFixed(1)} against ${p.season.rmse.toFixed(1)} points of error) while satellite infrared beats it at ${p.sat_ir_site.cams_better} of ${p.sat_ir_site.cams} cameras. Colour tracks greenness, and greenness lags moisture. That is a useful answer, and the harness that produced it works on any predictor you bring.`;
  }

  /* ---------------- coverage ---------------- */
  function coverage(C) {
    const s = C.siting, f = C.siting_fires, big = C.ignitions['1,000+ acres'];
    $('cov-stats').innerHTML = `<div><b>${pct(C.wild_seen)}</b><span>of California's wildland in line of sight of a camera, ${pct(C.wild_seen2)} of two</span></div>` +
      (big ? `<div><b>${pct(big.smoke300)}</b><span>of 1,000-acre fires since 2020 started where a camera could see a 300 m smoke column</span></div>` : '') +
      (s ? `<div><b>+${fmt(s.added_km2)} km²</b><span>of watched wildland from ten new sites picked out of ${fmt(s.candidates)} hilltops</span></div>` : '');
  }

  function results(S, C) {
    if (C && C.siting_fires) $('res-cov').textContent = `Line of sight from every ALERTCalifornia camera, checked against every wildfire from 2020 to 2025. ${pct(C.wild_seen)} of the state's wildland is in view; fires that started out of sight burned ${fmt(C.siting_fires.missed_acres / 1e6, 1)} million acres, and ten well-placed cameras would have seen ${pct(C.siting_fires.acres / C.siting_fires.missed_acres)} of that ground burn.`;
    if (S) $('res-study').textContent = `${fmt(S.totals.frames)} registered photos from PhenoCam cameras in ${S.totals.states} states, scored year by year against field measurements and MODIS.`;
  }
})();
