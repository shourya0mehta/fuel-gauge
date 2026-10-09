/* Fuel Gauge landing page.
   Data: data/hero.skyline.json (skylines of four calibrated fire cameras), data/live.json + assets/live/<cam>_blocks.json
   (pixel-to-ground lookups), live/summary.json (daily measurements), data/hero.json (alignment record of one ridge camera),
   data/cam/cucamongasouth.json (regions + daily calendar), data/study.json and data/coverage.json (results).
   Live frames come straight from HPWREN's real-time CDN and refresh every minute. */
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
  const RT = (id) => `https://cdn.hpwren.ucsd.edu/RT/${id}.jpg?m=${Math.floor(Date.now() / 60000)}`;

  /* when an element scrolls into view, run fn once */
  const io = 'IntersectionObserver' in window ? new IntersectionObserver((ents) => ents.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add('in'); const f = e.target._onIn; if (f) { e.target._onIn = null; f(); } io.unobserve(e.target); }
  }), { threshold: 0.25 }) : null;
  const onView = (node, fn) => { if (!node) return; if (!io || reduced) { node.classList.add('in'); if (fn) fn(); return; } node._onIn = fn; io.observe(node); };
  document.querySelectorAll('.reveal:not(.in)').forEach((n) => onView(n));

  /* on phones, technique lists start folded */
  if (matchMedia('(max-width: 700px)').matches) document.querySelectorAll('.hood[open]').forEach((d) => d.removeAttribute('open'));

  /* nav border on scroll */
  const nav = $('nav'); const onScroll = () => nav.classList.toggle('scrolled', scrollY > 8); addEventListener('scroll', onScroll, { passive: true }); onScroll();

  /* copy */
  document.querySelectorAll('[data-copy]').forEach((b) => b.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = 'Copied'; } catch (e) { b.textContent = 'Select it'; }
    setTimeout(() => { b.textContent = 'Copy'; }, 1600);
  }));

  /* typed headline */
  (() => {
    const t = $('typed'); if (!t || reduced) return;
    const words = ['fire lookout', 'webcam', 'PhenoCam', 'ridge camera', 'trail camera'];
    let w = 0, i = words[0].length, del = true;
    const tick = () => {
      const word = words[w];
      if (del) { i--; t.textContent = word.slice(0, i); if (i === 0) { del = false; w = (w + 1) % words.length; } setTimeout(tick, 45); }
      else { i++; t.textContent = words[w].slice(0, i); if (i === words[w].length) { del = true; setTimeout(tick, 2400); } else setTimeout(tick, 75); }
    };
    setTimeout(tick, 2600);
  })();

  /* count-up numbers */
  document.querySelectorAll('[data-count]').forEach((b) => onView(b.parentElement, () => {
    if (reduced) return;
    const to = +b.dataset.count, dec = +b.dataset.dec || 0, suf = b.dataset.suffix || '', t0 = performance.now(), D = 1400;
    const step = (now) => { const k = Math.min(1, (now - t0) / D), e = 1 - Math.pow(1 - k, 3); b.textContent = fmt(to * e, dec) + suf; if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }));

  /* step rail: progress and active step */
  (() => {
    const steps = [...document.querySelectorAll('.step')], links = [...document.querySelectorAll('.rail a')], fill = $('rail-fill'), box = document.querySelector('.steps');
    if (!steps.length) return;
    const upd = () => {
      const mid = innerHeight * 0.4; let act = 0;
      steps.forEach((s, k) => { if (s.getBoundingClientRect().top < mid) act = k; });
      links.forEach((a, k) => { a.classList.toggle('active', k === act); a.classList.toggle('done', k < act); });
      const r = box.getBoundingClientRect(); const p = Math.max(0, Math.min(1, (mid - r.top) / r.height));
      if (fill) fill.style.height = (p * 100).toFixed(1) + '%';
    };
    addEventListener('scroll', upd, { passive: true }); addEventListener('resize', upd); upd();
  })();

  /* alignment compare: sweeps by itself until touched */
  (() => {
    const cmp = $('compare'); if (!cmp) return;
    const r = cmp.querySelector('input'); let auto = !reduced, t0 = performance.now(), visible = false;
    const set = (v) => { cmp.style.setProperty('--cut', v + '%'); };
    r.addEventListener('input', () => { auto = false; set(r.value); });
    cmp.addEventListener('pointerdown', () => { auto = false; });
    if ('IntersectionObserver' in window) new IntersectionObserver((e) => { visible = e[0].isIntersecting; }).observe(cmp);
    const loop = (now) => { if (auto && visible) { const v = 50 + 32 * Math.sin((now - t0) / 1300); set(v.toFixed(1)); r.value = v; } if (auto) requestAnimationFrame(loop); };
    set(50); if (auto) requestAnimationFrame(loop);
  })();

  Promise.all([getJSON('data/hero.skyline.json'), getJSON('data/live.json'), getJSON('live/summary.json').catch(() => null), getJSON('data/hero.json').catch(() => null),
    getJSON('data/study.json').catch(() => null), getJSON('data/coverage.json').catch(() => null), getJSON('data/cam/cucamongasouth.json').catch(() => null)])
    .then(([SK, L, LS, H, S, C, CD]) => {
      const parts = [() => instrument(SK, L), () => pixelDemo(L), () => skylineChart(SK, L), () => geo(L), () => H && registration(H, S),
        () => CD && measureBlock(CD, S), () => C && coverage(C), () => results(S, C), () => live(L, LS), () => terminal()];
      parts.forEach((f) => { try { f(); } catch (e) { console.error(e); } });
    })
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
    const frame = $('frame'), svg = $('frame-svg'), cv = $('frame-ov'), img = $('frame-img'), xh = $('xhair'), pip = $('pip'), pipImg = $('pip-img');
    let cur = null, B = null, hover = -1, userHover = false, tourIdx = 0, tourPts = [], showLive = false, tel = null;

    function show(id, first) {
      const c = byId[id], s = SK[id]; heroCam = id; listeners.forEach((f) => f(id));
      showLive = false; img.src = c.img_oct; img.alt = `${c.name}, ${c.dir_label.toLowerCase()}, autumn 2026 composite`;
      pipImg.src = RT(id); pipImg.onerror = () => { pip.hidden = true; }; pip.hidden = false;
      $('cb-name').textContent = c.short + (c.dir_label ? ' ' + c.dir_label.replace('Looking ', '').replace(/^\w/, (m) => m.toUpperCase()) : '');
      $('cb-sub').textContent = c.name.split(' - ').pop();
      cur = { c, s }; B = null; hover = -1; tourPts = [];
      drawSvg(first && !reduced); readout(); drawHover(); telemetry(s);
      $('frame-cap').textContent = `${c.name}, ${c.dir_label.toLowerCase()} from ${fmt(c.elev)} m. Orange is the skyline Fuel Gauge found in the photo; dashed white is the skyline a terrain model predicts once the pose is solved. Hover anywhere on the hillside to read the ground.`;
      loadBlocks(c).then((b) => {
        if (!cur || cur.c.id !== id) return;
        B = b; drawContours();
        // tour: a spread of usable blocks, near to far
        const u = []; for (let i = 0; i < B.gw * B.gh; i++) if (B.usable[i] && B.dist[i] != null && B.lat[i] != null) u.push(i);
        u.sort((a, z) => B.dist[a] - B.dist[z]);
        tourPts = [0.12, 0.55, 0.3, 0.85, 0.7, 0.2].map((q) => u[Math.floor(q * (u.length - 1))]);
        readout();
      }).catch(() => {});
    }
    function telemetry(s) {
      const box = $('telemetry');
      const vals = [['Heading', s.yaw, 1, '°'], ['Tilt', s.pitch, 2, '°'], ['Roll', s.roll, 2, '°'], ['Field of view', s.hfov, 1, '°'], ['Skyline error', s.err, 2, '°']];
      if (!box.children.length) box.innerHTML = vals.map((v, k) => `<div${k === 4 ? ' class="hi"' : ''}><span>${v[0]}</span><b>–</b></div>`).join('');
      const bs = box.querySelectorAll('b'); const from = tel || vals.map(() => 0); const t0 = performance.now();
      const step = (now) => { const k = reduced ? 1 : Math.min(1, (now - t0) / 900), e = 1 - Math.pow(1 - k, 3);
        vals.forEach((v, j) => { bs[j].textContent = (from[j] + (v[1] - from[j]) * e).toFixed(v[2]) + v[3]; }); if (k < 1) requestAnimationFrame(step); };
      requestAnimationFrame(step); tel = vals.map((v) => v[1]);
    }
    pip.addEventListener('click', () => {
      showLive = !showLive; const c = cur.c;
      img.style.opacity = 0;
      setTimeout(() => { img.src = showLive ? RT(c.id) : c.img_oct; pipImg.src = showLive ? c.img_oct : RT(c.id); img.style.opacity = 1; }, 200);
      pip.querySelector('.pip-tag').innerHTML = showLive ? 'Daylight composite' : '<span class="pulse"></span>Feed right now';
      pip.setAttribute('aria-label', showLive ? 'Show the daylight composite in the main view' : 'Show the live feed in the main view');
    });
    setInterval(() => { if (!cur) return; const u = RT(cur.c.id); if (showLive) img.src = u; else pipImg.src = u; }, 60000);

    function cleanDetected(s) {
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
      const r = frame.getBoundingClientRect(); const visH = s.w * r.height / r.width;
      const ruler = el('g', { class: 'ruler' + (animate ? ' fadein' : '') }, svg);
      const ry = s.h - visH + 54;
      el('line', { x1: 0, x2: s.w, y1: ry, y2: ry }, ruler).setAttribute('opacity', '0.5');
      s.ticks.forEach(([u, az]) => {
        el('line', { x1: u, x2: u, y1: ry - 14, y2: ry + 14 }, ruler);
        const t = el('text', { x: u + 6, y: ry - 20 }, ruler); t.textContent = `${((az % 360) + 360) % 360}°`;
      });
      for (let k = 0; k < s.ticks.length - 1; k++) { const u = (s.ticks[k][0] + s.ticks[k + 1][0]) / 2; el('line', { x1: u, x2: u, y1: ry - 6, y2: ry + 6 }, ruler); }
      el('g', { id: 'contours', class: animate ? 'fadein' : '' }, svg);
      el('path', { class: 'sk-dem', d: pathOf(s.rendered) }, svg);
      const det = el('path', { class: 'sk-det', d: pathOf(cleanDetected(s)) }, svg);
      if (animate) {
        const len = det.getTotalLength ? det.getTotalLength() : 3000;
        det.style.setProperty('--len', String(Math.ceil(len) + 10)); det.classList.add('draw');
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
        el('path', { d, fill: 'none', stroke: '#FFFFFF', 'stroke-width': 1.3, 'stroke-opacity': 0.6, 'vector-effect': 'non-scaling-stroke' }, g);
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
        ro.innerHTML = `<div class="big">${c.short}</div><dl><dt>Pose solved from</dt><dd>skyline only</dd><dt>Ground blocks</dt><dd>${fmt(c.n_blocks)}</dd><dt>Elevation</dt><dd>${fmt(c.elev)} m</dd></dl><p class="hint">${B ? 'Hover the hillside to read the ground' : 'Loading the ground lookup'}</p>`;
        return;
      }
      const i = hover, x = i % B.gw, d = B.dist[i], lc = LC[B.lc[i]];
      ro.innerHTML = `<div class="big">${d < 1000 ? fmt(d) : fmt(d / 1000, 1)} <small>${d < 1000 ? 'm' : 'km'} away</small></div><dl>
        <dt>Bearing</dt><dd>${bearingAt((x + 0.5) * s.w / B.gw).toFixed(1)}°</dd>
        <dt>Land cover</dt><dd>${lc ? lc[0] : 'unknown'}</dd>
        <dt>Slope faces</dt><dd>${B.aspect[i] != null ? facing(B.aspect[i]) : 'flat'}</dd>
        <dt>Ground point</dt><dd>${B.lat[i].toFixed(4)}, ${B.lon[i].toFixed(4)}</dd></dl>`;
    }
    const geom = (r) => { const ih = r.width * cur.s.h / cur.s.w; return { ih, off: ih - r.height }; };
    function drawHover() {
      const r = frame.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
      cv.width = r.width * dpr; cv.height = r.height * dpr; const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, r.width, r.height);
      if (!B || hover < 0 || !B.usable[hover]) { xh.classList.remove('on'); return; }
      const { ih, off } = geom(r), bw = r.width / B.gw, bh = ih / B.gh, x = hover % B.gw, y = Math.floor(hover / B.gw);
      g.fillStyle = 'rgba(255,91,31,.28)'; g.fillRect(x * bw, y * bh - off, bw, bh);
      xh.style.transform = `translate(${(x + 0.5) * bw}px, ${(y + 0.5) * bh - off}px)`; xh.classList.add('on');
    }
    const pick = (e) => {
      if (!B) return; userHover = true; const r = frame.getBoundingClientRect(), { ih, off } = geom(r);
      const x = Math.floor((e.clientX - r.left) / r.width * B.gw), y = Math.floor((e.clientY - r.top + off) / ih * B.gh);
      const i = x >= 0 && y >= 0 && x < B.gw && y < B.gh ? y * B.gw + x : -1;
      if (i !== hover) { hover = i; xh.style.transition = 'opacity .2s'; readout(); drawHover(); }
    };
    frame.addEventListener('pointermove', (e) => { if (e.target.closest('.pip')) return; pick(e); });
    frame.addEventListener('pointerdown', (e) => { if (e.target.closest('.pip')) return; pick(e); });
    frame.addEventListener('pointerleave', (e) => { if (e.pointerType === 'mouse') { userHover = false; xh.style.transition = ''; } });
    addEventListener('resize', () => { if (cur) { drawSvg(false); drawContours(); drawHover(); } });
    // auto tour: the crosshair visits ground points by itself until someone takes over
    if (!reduced) setInterval(() => { if (userHover || !B || !tourPts.length || document.hidden) return; hover = tourPts[tourIdx++ % tourPts.length]; readout(); drawHover(); }, 2600);
    show(ids[0], true);
  }

  /* ---------------- pixel -> measurement ---------------- */
  function pixelDemo(L) {
    const c = L.cams.find((x) => x.id === L.default) || L.cams[0];
    const im = new Image(); im.src = c.img_oct;
    Promise.all([loadBlocks(c), new Promise((res) => { im.onload = res; im.onerror = res; })]).then(([B]) => {
      const cvs = document.createElement('canvas'); cvs.width = B.gw; cvs.height = B.gh; const g = cvs.getContext('2d');
      let px = null; try { g.drawImage(im, 0, 0, B.gw, B.gh); px = g.getImageData(0, 0, B.gw, B.gh).data; } catch (e) { px = null; }
      const u = []; for (let i = 0; i < B.gw * B.gh; i++) if (B.usable[i] && B.dist[i] != null && B.lat[i] != null && B.rel[i] != null && LC[B.lc[i]]) u.push(i);
      const rels = u.map((i) => B.rel[i]).sort((a, b) => a - b);
      const pickN = [0.15, 0.5, 0.82, 0.33, 0.67, 0.05].map((q) => u[Math.floor(q * (u.length - 1))]);
      const T = (L.cams.find((x) => x.id === c.id));
      let k = 0;
      const show = () => {
        const i = pickN[k++ % pickN.length];
        const rgb = px ? [px[i * 4], px[i * 4 + 1], px[i * 4 + 2]] : [122, 106, 85];
        $('pd-swatch').style.backgroundColor = `rgb(${rgb.join(',')})`;
        $('pd-rgb').textContent = `rgb(${rgb.join(', ')})`;
        const browner = Math.round(100 * rels.filter((v) => v > B.rel[i]).length / rels.length);
        const lines = [['distance_m', fmt(B.dist[i]).replace(/,/g, '')], ['lat', B.lat[i].toFixed(5)], ['lon', B.lon[i].toFixed(5)], ['land_cover', `"${LC[B.lc[i]][0].toLowerCase()}"`],
          ['slope_faces', `"${B.aspect[i] != null ? facing(B.aspect[i]) : 'flat'}"`], ['browner_than_pct', browner], ['camera', `"${T.short.toLowerCase().replace(/\s+/g, '-')}"`]];
        const pre = $('pd-json'); pre.innerHTML = '{\n';
        let j = 0;
        const add = () => {
          if (j < lines.length) { const [kk, v] = lines[j]; pre.innerHTML += `  <span class="k">"${kk}"</span>: <span class="v">${v}</span>${j < lines.length - 1 ? ',' : ''}\n`; j++; setTimeout(add, reduced ? 0 : 110); }
          else pre.innerHTML += '}';
        };
        add();
      };
      onView($('pixel-demo'), () => { show(); if (!reduced) setInterval(() => { if (!document.hidden) show(); }, 4200); });
    });
  }

  /* ---------------- calibrate: skyline residuals ---------------- */
  function skylineChart(SK, L) {
    const sv = $('sky-chart'); if (!sv) return;
    const draw = (id) => {
      const s = SK[id], c = L.cams.find((x) => x.id === id);
      const w = sv.clientWidth || 640, h = 300, m = { l: 50, r: 10, t: 16, b: 30 }, mid = 168;
      sv.setAttribute('viewBox', `0 0 ${w} ${h}`); sv.setAttribute('height', h); sv.innerHTML = '';
      const degpp = s.hfov / s.w;
      const T = s.ticks; const bearing = (u) => { let k = 0; while (k < T.length - 2 && T[k + 1][0] < u) k++; const [u0, a0] = T[k], [u1, a1] = T[k + 1]; return a0 + (a1 - a0) * (u - u0) / (u1 - u0); };
      const b0 = bearing(0), b1 = bearing(s.w);
      const X = (u) => m.l + (bearing(u) - b0) / (b1 - b0) * (w - m.l - m.r);
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
      el('path', { d: dR, fill: 'none', stroke: css('--ink'), 'stroke-width': 1.4, 'stroke-dasharray': '4 4', opacity: 0.55 }, sv);
      const clipId = 'skyclip' + id.replace(/\W/g, '');
      const clip = el('rect', { x: 0, y: 0, width: sv.dataset.seen ? w : 0, height: h }, el('clipPath', { id: clipId }, el('defs', {}, sv)));
      const fg = el('g', { 'clip-path': `url(#${clipId})` }, sv);
      el('path', { d: dD, fill: 'none', stroke: css('--signal'), 'stroke-width': 2.4, 'stroke-linejoin': 'round' }, fg);
      el('text', { x: m.l, y: m.t - 4 }, sv).textContent = 'skyline height above frame centre';
      const rr = Math.min(2, Math.max(0.5, Math.ceil(cutoff * 2.5 * 10) / 10)), Y2 = (r) => mid + 22 + (1 - (Math.max(-rr, Math.min(rr, r)) + rr) / (2 * rr)) * (h - m.b - mid - 22);
      el('text', { x: m.l, y: mid + 12 }, sv).textContent = 'found minus predicted';
      [-rr / 2, 0, rr / 2].forEach((a) => { el('line', { x1: m.l, x2: w - m.r, y1: Y2(a), y2: Y2(a) }, grid); el('text', { x: 0, y: Y2(a) + 4 }, sv).textContent = (a > 0 ? '+' : '') + a.toFixed(2) + '°'; });
      el('rect', { x: m.l, y: Y2(s.err), width: w - m.l - m.r, height: Math.max(1, Y2(-s.err) - Y2(s.err)), fill: css('--signal'), 'fill-opacity': 0.14 }, sv);
      res.forEach(([u, r, , ok]) => { if (Math.abs(r) <= rr) el('circle', { cx: X(u), cy: Y2(r), r: ok ? 1.7 : 1.4, fill: ok ? css('--signal') : '#B5B5B0' }, fg); });
      T.forEach(([u, az]) => { const t = el('text', { x: X(u), y: h - 8, 'text-anchor': 'middle' }, sv); t.textContent = `${((az % 360) + 360) % 360}°`; });
      const kept = res.filter((x) => x[3]).length;
      $('sky-cap').textContent = `${c.short}: the skyline found in the photo (orange) against the one the terrain predicts after solving the pose (dashed), over ${Math.round(b1 - b0)}° of bearing. Below, the gap at each of ${res.length} columns; the fit ignores the worst ${res.length - kept} (grey), where trees or buildings stand in front of the true skyline. Median error ${s.err.toFixed(2)}°.`;
      if (!sv.dataset.seen) {
        sv.dataset.seen = '1';
        onView(sv.parentElement, () => { if (reduced) { clip.setAttribute('width', w); return; } const t0 = performance.now(); const step = (now) => { const k = Math.min(1, (now - t0) / 1600), e = 1 - Math.pow(1 - k, 3); const cr = sv.querySelector('clipPath rect'); if (cr) cr.setAttribute('width', (w * e).toFixed(1)); if (k < 1) requestAnimationFrame(step); }; requestAnimationFrame(step); });
      }
    };
    listeners.push(draw);
    if (heroCam) draw(heroCam);
    let t; addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => heroCam && draw(heroCam), 150); });
    const cams = L.cams.slice().sort((a, b) => a.median_err_deg - b.median_err_deg), mx = Math.max(...cams.map((c) => c.median_err_deg));
    const box = $('errs');
    box.innerHTML = cams.map((c) => `<div><span>${c.short}</span><b>${c.median_err_deg.toFixed(2)}°</b><i style="--w:${Math.round(c.median_err_deg / mx * 100)}%"></i></div>`).join('');
    onView(box);
  }

  /* ---------------- map: overlays and a line-of-sight sweep ---------------- */
  function geo(L) {
    const modeBox = $('geo-mode'), sel = $('geo-cam'); if (!modeBox) return;
    let mode = 'dist', idx = Math.max(0, L.cams.findIndex((c) => c.id === L.default)), B = null, c = null, bg = null, visible = false, t0 = 0, anim = 0;
    L.cams.forEach((cc, i) => { const o = document.createElement('option'); o.value = i; o.textContent = cc.short; o.dataset.sub = `${cc.dir_label}, ${cc.name.split(' - ').pop()}, skyline fit ${cc.median_err_deg.toFixed(2)}°`; if (i === idx) o.selected = true; sel.appendChild(o); });
    sel.addEventListener('change', () => { idx = +sel.value; load(); });
    modeBox.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
      mode = b.dataset.mode; modeBox.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); photo(); key();
    }));
    const distCol = (d, a = 0.62) => { const t = Math.min(1, Math.log10(Math.max(200, d) / 200) / Math.log10(150)); return `rgba(${Math.round(255 - 225 * t)},${Math.round(196 - 120 * t)},${Math.round(120 + 40 * t)},${a})`; };
    const aspCol = (asp, a = 0.6) => { const t = (1 - Math.cos(asp * Math.PI / 180)) / 2; return `rgba(${Math.round(70 + 185 * t)},${Math.round(90 + 1 * t)},${Math.round(160 - 129 * t)},${a})`; };
    const colOf = (i, a) => {
      if (mode === 'dist') return distCol(B.dist[i], a);
      if (mode === 'lc') { const k = LC[B.lc[i]]; return k ? k[1] + (a > 0.9 ? '' : 'A6') : null; }
      return B.aspect[i] == null ? 'rgba(160,160,160,0.4)' : aspCol(B.aspect[i], a);
    };
    async function load() {
      c = L.cams[idx]; const img = $('geo-img');
      img.src = c.img_oct; img.alt = `${c.name}, ${c.dir_label.toLowerCase()}`;
      try { B = await loadBlocks(c); } catch (e) { return; }
      bg = null; const im = new Image(); im.onload = () => { bg = im; }; im.src = c.hs_light;
      t0 = performance.now(); photo(); key();
      $('geo-cap').textContent = `${c.name}. Left: every ${16}-pixel ground block in the photo, coloured. Right: the same ${fmt(c.n_blocks)} blocks traced along their lines of sight and dropped onto the map, over shaded relief.`;
      if (!anim) anim = requestAnimationFrame(frame);
    }
    function photo() {
      if (!B) return;
      const cv = $('geo-ov'), r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
      cv.width = r.width * dpr; cv.height = r.height * dpr; const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0);
      const bw = r.width / B.gw, bh = r.height / B.gh;
      for (let i = 0; i < B.gw * B.gh; i++) { if (!B.usable[i] || B.dist[i] == null) continue; const col = colOf(i, 0.6); if (!col) continue; g.fillStyle = col; g.fillRect((i % B.gw) * bw, Math.floor(i / B.gw) * bh, bw + 0.4, bh + 0.4); }
    }
    function key() {
      const k = $('geo-key'); if (!B) return;
      if (mode === 'dist') k.innerHTML = `<span><i style="background:${distCol(300, 1)}"></i>under 1 km</span><span><i style="background:${distCol(3000, 1)}"></i>about 3 km</span><span><i style="background:${distCol(15000, 1)}"></i>10 km and beyond</span>`;
      else if (mode === 'lc') { const present = new Set(B.lc.filter((v, i) => B.usable[i])); k.innerHTML = Object.entries(LC).filter(([kk]) => present.has(+kk)).map(([, v]) => `<span><i style="background:${v[1]}"></i>${v[0]}</span>`).join('') + '<span>from ESA WorldCover 10 m</span>'; }
      else k.innerHTML = `<span><i style="background:${aspCol(0, 1)}"></i>faces north, shaded</span><span><i style="background:${aspCol(90, 1)}"></i>east or west</span><span><i style="background:${aspCol(180, 1)}"></i>faces south, sun-baked</span>`;
    }
    // sweep: a beam crosses the field of view and drops each block onto the map as it passes
    function frame(now) {
      anim = requestAnimationFrame(frame);
      if (!B || !visible || document.hidden) return;
      const mc = $('geo-map'), mr = mc.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
      if (mc.width !== Math.round(mr.width * dpr)) { mc.width = mr.width * dpr; mc.height = mr.height * dpr; }
      const m = mc.getContext('2d'); m.setTransform(dpr, 0, 0, dpr, 0, 0);
      const bd = c.bounds, W = mr.width, Hh = mr.height;
      const X = (lon) => (lon - bd.west) / (bd.east - bd.west) * W, Y = (lat) => (bd.north - lat) / (bd.north - bd.south) * Hh;
      const cx = X(c.lon), cy = Y(c.lat), R = Math.hypot(W, Hh);
      const a1 = c.yaw - c.hfov / 2, a2 = c.yaw + c.hfov / 2, period = 4200;
      const k = reduced ? 1 : ((now - t0) % period) / period, first = reduced || now - t0 > period;
      const sweep = a1 + (a2 - a1) * k;
      m.clearRect(0, 0, W, Hh); if (bg) m.drawImage(bg, 0, 0, W, Hh); else { m.fillStyle = css('--bg-2'); m.fillRect(0, 0, W, Hh); }
      const toRad = (a) => (a - 90) * Math.PI / 180;
      m.fillStyle = 'rgba(255,255,255,.35)'; m.beginPath(); m.moveTo(cx, cy); m.arc(cx, cy, R, toRad(a1), toRad(a2)); m.closePath(); m.fill();
      for (let i = 0; i < B.gw * B.gh; i++) {
        if (!B.usable[i] || B.lat[i] == null) continue;
        const x = X(B.lon[i]), y = Y(B.lat[i]);
        let az = Math.atan2(x - cx, cy - y) * 180 / Math.PI; az = ((az - a1) % 360 + 360) % 360 + a1;
        if (!first && az > sweep) continue;
        const col = colOf(i, 0.95); if (!col) continue;
        const fresh = !reduced && Math.abs(az - sweep) < 6;
        m.fillStyle = fresh ? css('--signal') : col; const sz = fresh ? 4 : 3.2;
        m.fillRect(x - sz / 2, y - sz / 2, sz, sz);
      }
      if (!reduced) {
        const g = m.createRadialGradient(cx, cy, 0, cx, cy, R * 0.8); g.addColorStop(0, 'rgba(255,91,31,.55)'); g.addColorStop(1, 'rgba(255,91,31,0)');
        m.fillStyle = g; m.beginPath(); m.moveTo(cx, cy); m.arc(cx, cy, R, toRad(sweep - 7), toRad(sweep)); m.closePath(); m.fill();
        m.strokeStyle = css('--signal'); m.lineWidth = 2; m.beginPath(); m.moveTo(cx, cy); m.lineTo(cx + R * Math.cos(toRad(sweep)), cy + R * Math.sin(toRad(sweep))); m.stroke();
      }
      m.fillStyle = css('--ink'); m.beginPath(); m.arc(cx, cy, 6, 0, Math.PI * 2); m.fill(); m.fillStyle = css('--signal'); m.beginPath(); m.arc(cx, cy, 3.5, 0, Math.PI * 2); m.fill();
      const km = W / (2 * bd.radius_m / 1000); m.fillStyle = css('--ink'); m.fillRect(12, Hh - 16, 2 * km, 2); m.font = '500 12px ' + css('--mono'); m.fillText('2 km', 12, Hh - 22); m.fillText('N', W - 20, 22);
    }
    if ('IntersectionObserver' in window) new IntersectionObserver((e) => { visible = e[0].isIntersecting; if (visible && B) t0 = performance.now(); }).observe($('geo-map')); else visible = true;
    load();
    let t; addEventListener('resize', () => { clearTimeout(t); t = setTimeout(photo, 150); });
  }

  /* ---------------- align: segment record ---------------- */
  function registration(H, S) {
    const box = $('seg-track'); if (!box) return;
    const toT = (s) => Date.parse(s + 'T00:00:00Z');
    const t0 = toT(H.segments[0].start), t1 = toT(H.segments[H.segments.length - 1].end);
    const row = document.createElement('div'); row.className = 'row';
    H.segments.forEach((s, k) => { const i = document.createElement('i'); const a = toT(s.start), b = toT(s.end); i.style.left = (100 * (a - t0) / (t1 - t0)) + '%'; i.style.width = Math.max(0.4, 100 * (b - a) / (t1 - t0)) + '%'; i.style.transitionDelay = (k * 0.12) + 's'; i.title = `${s.start} to ${s.end}: ${fmt(s.n)} photos`; if (!s.linked) i.style.background = css('--slate'); row.appendChild(i); });
    const mv = document.createElement('div'); mv.className = 'moves';
    (H.moves || []).forEach((m, k) => { const i = document.createElement('i'); i.style.left = (100 * (toT(m.d) - t0) / (t1 - t0)) + '%'; i.style.transitionDelay = (0.8 + k * 0.05) + 's'; i.title = `${m.d}: view shifted ${m.px} px`; mv.appendChild(i); });
    const ax = document.createElement('div'); ax.className = 'axis';
    const y0 = new Date(t0).getUTCFullYear(), y1 = new Date(t1).getUTCFullYear();
    for (let y = y0; y <= y1; y += 3) ax.insertAdjacentHTML('beforeend', `<span>${y}</span>`);
    const lab = document.createElement('p'); lab.className = 'cap';
    lab.innerHTML = `The same camera's ${fmt(H.counts.registered)} aligned photos, ${y0} to ${y1}. Black bars are tracked stretches, all joined back to one view. Orange ticks mark the ${H.moves.length} times the camera was knocked or re-aimed.`;
    box.append(row, mv, ax, lab); onView(box);
    if (S && S.totals) {
      const t = S.totals;
      $('reg-stats').innerHTML = `<div><b>${pct(t.frames / t.frames_ok)}</b><span>of ${fmt(t.frames_ok)} usable photos from ${t.cams} cameras locked onto a view</span></div><div><b>${t.moved} of ${t.cams}</b><span>cameras were moved to a new mast and kept as a second view</span></div><div><b>${H.moves.length}</b><span>bumps and re-aims caught on this one camera</span></div>`;
    }
  }

  /* ---------------- measure: regions and 15 years of greenness ---------------- */
  function measureBlock(CD, S) {
    const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
    const img = $('roi-img'), cv = $('roi-ov');
    const [gw, gh] = typeof CD.grid === 'string' ? JSON.parse(CD.grid) : CD.grid;
    const cells = []; for (const k of ['veg', 'ref']) [...CD[k]].forEach((v, i) => { if (v === '1') cells.push([k, i, Math.random()]); });
    cells.sort((a, b) => a[2] - b[2]);
    let shown = reduced ? cells.length : 0;
    const draw = () => {
      const r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1; cv.width = r.width * dpr; cv.height = r.height * dpr;
      const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); const bw = r.width / gw, bh = r.height / gh;
      const fill = { veg: css('--field'), ref: css('--signal') };
      g.globalAlpha = 0.6;
      for (let n = 0; n < shown; n++) { const [k, i] = cells[n]; g.fillStyle = fill[k]; g.fillRect((i % gw) * bw + 0.5, Math.floor(i / gw) * bh + 0.5, bw - 1, bh - 1); }
      g.globalAlpha = 1;
    };
    const run = () => { const t0 = performance.now(); const step = (now) => { shown = Math.min(cells.length, Math.floor((now - t0) / 1400 * cells.length)); draw(); if (shown < cells.length) requestAnimationFrame(step); }; requestAnimationFrame(step); };
    if (img.complete && img.naturalWidth) draw(); else img.addEventListener('load', draw);
    addEventListener('resize', draw);
    const cv2 = $('green-chart'), cal = CD.calendar; let rowsShown = reduced ? cal.rows.length : 0;
    const chart = () => {
      const ny = cal.rows.length, lab = 38, w = cv2.clientWidth || 600, rowH = Math.max(11, Math.min(17, Math.floor(280 / ny))), top = 18, h = top + ny * rowH;
      const dpr = window.devicePixelRatio || 1; cv2.width = w * dpr; cv2.height = h * dpr; cv2.style.height = h + 'px';
      const g = cv2.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
      const cw = (w - lab) / 366, straw = [214, 176, 92], green = [24, 104, 72];
      g.fillStyle = css('--bg-2'); g.fillRect(lab, top, w - lab, ny * rowH);
      cal.rows.slice(0, rowsShown).forEach((row, y) => {
        for (let d = 0; d < row.length; d++) {
          const ch = row[d]; if (ch === '.') continue;
          const k = B64.indexOf(ch) / 63;
          g.fillStyle = `rgb(${straw.map((cc, j) => Math.round(cc + (green[j] - cc) * k)).join(',')})`;
          g.fillRect(lab + d * cw, top + y * rowH, cw + 0.6, rowH - 2);
        }
      });
      g.fillStyle = css('--slate'); g.font = '11px ' + css('--mono'); g.textBaseline = 'middle';
      cal.years.forEach((y, i) => { if (i % 3 === 0 || i === ny - 1) g.fillText(String(y), 0, top + (i + 0.5) * rowH); });
      ['Jan', 'Apr', 'Jul', 'Oct'].forEach((m, j) => g.fillText(m, lab + [0, 90, 181, 273][j] * cw, 8));
    };
    chart(); let t; addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => { chart(); }, 150); });
    onView($('roi-img').parentElement, () => {
      run();
      const t0 = performance.now(); const step = (now) => { rowsShown = Math.min(cal.rows.length, Math.floor((now - t0) / 110)); chart(); if (rowsShown < cal.rows.length) requestAnimationFrame(step); };
      if (!reduced) requestAnimationFrame(step);
    });
    if (S && S.pooled && S.summary) {
      const hv = S.pooled.hand_vs_auto, p = S.summary.pooled;
      $('measure-stats').innerHTML = `<div><b>${hv.auto_better} of ${hv.cams}</b><span>cameras where automatic regions beat the network's hand-drawn masks</span></div><div><b>+${Math.round((p.camera_auto_wb.anomaly_r / p.camera_auto.anomaly_r - 1) * 100)}%</b><span>more year-to-year signal after white balance (anomaly r ${p.camera_auto.anomaly_r.toFixed(2)} to ${p.camera_auto_wb.anomaly_r.toFixed(2)})</span></div>`;
    }
  }

  /* ---------------- scale: coverage map ---------------- */
  function coverage(C) {
    const s = C.siting, big = C.ignitions['1,000+ acres'], M = C.map, sv = $('cov-ov');
    if (M && sv) {
      sv.setAttribute('viewBox', `0 0 ${M.w} ${M.h}`);
      const P = (lat, lon) => [(lon - M.west) / M.res, (M.north - lat) / M.res];
      (s ? s.picks : []).forEach((p, k) => { const [x, y] = P(p.lat, p.lon); el('rect', { class: 'cov-dia', x: x - 7, y: y - 7, width: 14, height: 14, transform: `rotate(45 ${x} ${y})` }, sv); });
      (C.unseen_large || []).filter((f) => f.smoke300 === 0).slice(0, 6).forEach((f, k) => {
        const [x, y] = P(f.lat, f.lon);
        el('circle', { class: 'cov-ring', cx: x, cy: y, r: 16, style: `animation-delay:${k * 0.4}s` }, sv);
        el('circle', { class: 'cov-dot', cx: x, cy: y, r: 6 }, sv);
        if (k < 3) { const t = el('text', { class: 'cov-lab', x: x + 14, y: y + 5 }, sv); t.textContent = `${f.name}, ${f.year}`; }
      });
    }
    const box = $('cov-stats');
    box.innerHTML = `<div><b>${pct(C.wild_seen)}</b><span>of California's wildland in line of sight of at least one camera; ${pct(C.wild_seen2)} of two</span></div>` +
      (big ? `<div><b>${pct(1 - big.smoke300)}</b><span>of 1,000-acre fires since 2020 started where no camera could see a 300 m smoke column</span></div>` : '') +
      (s ? `<div><b>+${fmt(s.added_km2)} km²</b><span>of watched wildland from ten new sites, picked from ${fmt(s.candidates)} hilltops</span></div>` : '');
  }

  /* ---------------- results ---------------- */
  function results(S, C) {
    if (C) {
      const big = C.ignitions['1,000+ acres'];
      if (big) $('res-cov-num').textContent = pct(1 - big.smoke300);
      $('res-cov').textContent = `Lines of sight from all ${fmt(C.cameras)} ALERTCalifornia cameras, checked against every wildfire from 2020 to 2025. The big fires that started out of view, including the SCU Lightning Complex and the Claremont Fire, burned ${big ? fmt(big.acres_nosmoke / 1e6, 1) : '1.4'} million acres.`;
      if (C.siting_fires) {
        const f = C.siting_fires; $('res-site-num').textContent = pct(f.acres / f.missed_acres);
        $('res-site').textContent = `A greedy search over ${fmt(f.candidates)} hilltops picked ten sites that would have seen smoke from ${f.fires} of the ${f.missed_fires} fires no camera could see: ${fmt(f.acres / 1e6, 2)} million of their ${fmt(f.missed_acres / 1e6, 2)} million acres.`;
      }
    }
    if (S && S.summary) {
      const p = S.summary.pooled, nir = S.summary.nir && S.summary.nir.pooled;
      $('res-bench').textContent = `We scored the cameras against ${fmt(S.totals.samples)} field samples of live fuel moisture, one held-out year at a time. Colour alone does not beat the calendar yet; satellite infrared does. The harness ships with the package, ready for the next signal.`;
      const rows = [['Camera colour', p.camera_auto_wb.anomaly_r, 'var(--ink)'], ...(nir && nir.camera_ndvi ? [['Camera near-infrared', nir.camera_ndvi.anomaly_r, '#9A9A95']] : []), ['Satellite infrared', p.sat_ir_site.anomaly_r, 'var(--signal)']];
      const mx = Math.max(...rows.map((r) => r[1]));
      const bx = $('bench-bars');
      bx.innerHTML = rows.map(([l, v, col]) => `<div><span>${l}</span><i style="--w:${Math.max(2, v / mx * 100)}%;--c:${col}"></i><b>${v.toFixed(2)}</b></div>`).join('') + '<p class="cap" style="margin-top:2px">Anomaly correlation: does it know a year was unusually wet or dry?</p>';
      onView(bx);
    }
  }

  /* ---------------- live network ---------------- */
  function live(L, LS) {
    const grid = $('live-grid'); if (!grid) return;
    const clock = () => { const t = new Date().toLocaleTimeString('en-US', { timeZone: 'America/Los_Angeles', hour: 'numeric', minute: '2-digit', second: '2-digit' }); $('clock').textContent = t; };
    clock(); setInterval(clock, 1000);
    const any = LS && LS.cams ? Object.values(LS.cams)[0] : null;
    if (any) $('live-updated').textContent = 'Measured daily, latest through ' + new Date(any.dates[any.dates.length - 1] + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const loaded = {};
    const caHour = () => +new Date().toLocaleString('en-US', { timeZone: 'America/Los_Angeles', hour: 'numeric', hour12: false });
    const day = () => { const hr = caHour(); return hr >= 7 && hr < 19; };
    const note = $('live-night');
    if (note) note.hidden = day();
    L.cams.forEach((c) => {
      const ch = c.change || {}; const worst = Object.entries(ch).sort((a, b) => a[1].delta - b[1].delta)[0];
      const a = document.createElement('a'); a.className = 'cam'; a.href = 'research.html#live';
      a.innerHTML = `<div class="cam-media"><img alt="Live frame from ${c.name}" loading="lazy"><span class="live-tag"><span class="pulse"></span>LIVE</span><span class="age">now</span></div>
        <div class="cam-body"><b>${c.short}</b><span>${c.dir_label}, skyline fit ${c.median_err_deg.toFixed(2)}°</span><em>${worst && worst[1].delta < 0 ? 'Browning fastest: ' + worst[0] : 'Holding green across the view'}</em></div>`;
      const im = a.querySelector('img'), age = a.querySelector('.age'), tag = a.querySelector('.live-tag');
      const daylight = () => { im.src = c.img_oct; age.textContent = 'daytime view'; tag.innerHTML = 'NIGHT AT THE RIDGE'; loaded[c.id] = 0; };
      im.onerror = () => { im.onerror = null; daylight(); };
      im.onload = () => { if (im.src.includes('/RT/')) loaded[c.id] = Date.now(); };
      if (day()) im.src = RT(c.id); else daylight();
      grid.appendChild(a);
      setInterval(() => { if (loaded[c.id]) { const s = Math.round((Date.now() - loaded[c.id]) / 1000); age.textContent = s < 5 ? 'now' : s + 's ago'; } }, 1000);
      setInterval(() => { if (document.hidden || !day()) return; const n = new Image(); n.onload = () => { im.src = n.src; tag.innerHTML = '<span class="pulse"></span>LIVE'; }; n.src = RT(c.id); }, 60000);
    });
  }

  /* ---------------- terminal ---------------- */
  function terminal() {
    const pre = $('term-body'); if (!pre) return;
    const script = [
      ['$', 'pip install "fuelgauge[geo,seg] @ git+https://github.com/shourya0mehta/fuel-gauge"'],
      ['ok', 'Successfully installed fuelgauge-0.3.0'],
      ['$', 'fuelgauge run sangabriel/ out/sangabriel'],
      ['o', '1052 of 1052 photos dated, 2008-05-21 to 2016-03-23'],
      ['o', 'track 1052/1052 segments 15'],
      ['o', 'segments 15, views [[14], [2, 7, 9, 11]]'],
      ['o', '1052 frames, 934 pass checks, 750 registered'],
      ['ok', '831 days measured over 2 view(s); wrote out/sangabriel_daily.csv and out/sangabriel_regions.png'],
      ['$', 'fuelgauge calibrate rm-e frame.jpg --lat 33.4008 --lon -117.1905 --elev 483 --yaw 90'],
      ['ok', '{"camera": {"yaw": 90.33, "pitch": -0.86, "roll": 0.2, "hfov": 101.15, "k1": 0.08}}'],
      ['$', 'fuelgauge viewshed cameras.csv coverage.tif'],
    ];
    const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
    const render = (lines, cursor) => { pre.innerHTML = lines.map(([k, t]) => k === '$' ? `<span class="pr">$</span> ${esc(t)}` : `<span class="${k}">${esc(t)}</span>`).join('\n') + (cursor ? '<span class="cur"></span>' : ''); };
    if (reduced) { render(script, true); return; }
    render([], true);
    onView($('term'), () => {
      const done = []; let li = 0;
      const next = () => {
        if (li >= script.length) { render(done, true); return; }
        const [k, t] = script[li++];
        if (k === '$') { let c = 0; const type = () => { c += 2; render(done.concat([[k, t.slice(0, c)]]), true); if (c < t.length) setTimeout(type, 18); else { done.push([k, t]); setTimeout(next, 350); } }; type(); }
        else { done.push([k, t]); render(done, true); setTimeout(next, k === 'ok' ? 500 : 260); }
      };
      next();
    });
  }
})();
