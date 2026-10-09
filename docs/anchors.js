/* In-page links that land where they should. Sticky bars (the nav, and the section bar on the research page) are
   measured, not guessed, and while charts and images are still filling in, the target is re-aligned until the
   page settles or the reader starts scrolling on their own. */
(() => {
  'use strict';
  // sticky bars that span the page width (the side rail on wide screens does not count)
  // (the step rail only sticks inside the tour, so it counts only for targets there)
  const sticky = (target) => ['#nav', '.subnav', '.rail'].map((s) => document.querySelector(s)).filter(Boolean)
    .filter((el) => !el.classList.contains('rail') || (target && el.parentElement.contains(target)))
    .reduce((h, el) => h + (getComputedStyle(el).position === 'sticky' && el.offsetWidth > innerWidth * 0.8 ? el.offsetHeight : 0), 0);
  const offset = (target) => sticky(target) + 18;
  const setPad = () => { document.documentElement.style.scrollPaddingTop = offset() + 'px'; };
  const targetOf = (hash) => { try { return hash && hash.length > 1 ? document.getElementById(decodeURIComponent(hash.slice(1))) : null; } catch (e) { return null; } };
  const topOf = (el) => el.getBoundingClientRect().top + scrollY - offset(el);
  let follow = null;
  const stop = () => { if (follow) { follow.disconnect(); follow = null; } };
  ['wheel', 'touchstart', 'keydown', 'pointerdown'].forEach((t) => addEventListener(t, (e) => { if (!(t === 'pointerdown' && e.target.closest('a[href*="#"]'))) stop(); }, { passive: true }));
  function go(el, smooth) {
    stop(); setPad();
    scrollTo({ top: topOf(el), behavior: smooth ? 'smooth' : 'instant' });
    // keep the target pinned while content above it is still loading
    if ('ResizeObserver' in window) {
      let last = 0; const until = performance.now() + 4000;
      follow = new ResizeObserver(() => {
        if (performance.now() > until) return stop();
        const want = topOf(el); if (Math.abs(want - scrollY) > 3 && performance.now() - last > 60) { last = performance.now(); scrollTo({ top: want, behavior: 'instant' }); }
      });
      follow.observe(document.body);
      setTimeout(stop, 4000);
    }
    if (smooth) setTimeout(() => { if (follow) { const want = topOf(el); if (Math.abs(want - scrollY) > 3) scrollTo({ top: want, behavior: 'instant' }); } }, 900);
  }
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[href]'); if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey) return;
    const url = new URL(a.href, location.href);
    if (url.pathname !== location.pathname || !url.hash) return;
    const el = targetOf(url.hash); if (!el) return;
    e.preventDefault(); history.pushState(null, '', url.hash); go(el, !matchMedia('(prefers-reduced-motion: reduce)').matches);
  });
  addEventListener('popstate', () => { const el = targetOf(location.hash); if (el) go(el, false); });
  addEventListener('resize', setPad);
  setPad();
  if (location.hash) {
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
    const land = () => { const el = targetOf(location.hash); if (el) go(el, false); };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', land); else land();
    addEventListener('load', () => { if (follow || !scrollY) land(); });
  }
})();
