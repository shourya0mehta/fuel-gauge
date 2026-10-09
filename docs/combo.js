/* Searchable dropdown that replaces a native <select data-combo>. The <select> stays in the page (hidden) as the
   source of truth: picking an item sets its value and fires 'change', and code that sets select.value directly
   is reflected in the button. Options may be added later; the list rebuilds itself. Each option can carry a
   second line in data-sub. Keyboard: type to filter, arrows to move, Enter to pick, Escape to close. */
(() => {
  'use strict';
  const valueDesc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
  let uid = 0;
  function upgrade(sel) {
    if (sel._combo) return;
    const id = 'cb' + (++uid);
    const wrap = document.createElement('div'); wrap.className = 'combo ' + (sel.dataset.comboClass || '');
    const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'combo-btn';
    btn.setAttribute('aria-haspopup', 'listbox'); btn.setAttribute('aria-expanded', 'false');
    if (sel.getAttribute('aria-label')) btn.setAttribute('aria-label', sel.getAttribute('aria-label'));
    btn.innerHTML = '<span class="combo-val"></span><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    const pop = document.createElement('div'); pop.className = 'combo-pop'; pop.hidden = true;
    pop.innerHTML = `<div class="combo-search"><svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10.5 10.5L14 14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg><input type="text" placeholder="${sel.dataset.placeholder || 'Search'}" aria-controls="${id}" autocomplete="off" spellcheck="false"></div><ul class="combo-list" role="listbox" id="${id}"></ul><p class="combo-empty" hidden>No matches</p>`;
    sel.after(wrap); wrap.append(btn, pop); sel.classList.add('combo-native'); sel.tabIndex = -1; sel.setAttribute('aria-hidden', 'true');
    const input = pop.querySelector('input'), list = pop.querySelector('ul'), empty = pop.querySelector('.combo-empty');
    let items = [], active = -1;
    const norm = (s) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

    function build() {
      list.innerHTML = '';
      items = [...sel.options].map((o, k) => {
        const li = document.createElement('li'); li.setAttribute('role', 'option'); li.id = `${id}-${k}`; li.dataset.value = o.value;
        li.innerHTML = `<span class="combo-main"></span>${o.dataset.sub ? '<span class="combo-sub"></span>' : ''}`;
        li.querySelector('.combo-main').textContent = o.textContent;
        if (o.dataset.sub) li.querySelector('.combo-sub').textContent = o.dataset.sub;
        li.addEventListener('mousedown', (e) => e.preventDefault());
        li.addEventListener('click', () => choose(k));
        li.addEventListener('mousemove', () => setActive(items.findIndex((it) => it.li === li)));
        list.appendChild(li);
        return { li, k, text: norm(o.textContent + ' ' + (o.dataset.sub || '')) };
      });
      sync();
    }
    function sync() {
      const o = sel.options[sel.selectedIndex];
      btn.querySelector('.combo-val').textContent = o ? o.textContent : (sel.dataset.placeholder || 'Choose');
      items.forEach((it) => it.li.setAttribute('aria-selected', String(it.k === sel.selectedIndex)));
    }
    function visible() { return items.filter((it) => !it.li.hidden); }
    function setActive(n) {
      const v = visible(); if (!v.length) { active = -1; return; }
      active = Math.max(0, Math.min(v.length - 1, n));
      v.forEach((it, j) => it.li.classList.toggle('active', j === active));
      input.setAttribute('aria-activedescendant', v[active].li.id);
      v[active].li.scrollIntoView({ block: 'nearest' });
    }
    function filter() {
      const q = norm(input.value.trim()).split(/\s+/).filter(Boolean);
      items.forEach((it) => { it.li.hidden = !q.every((w) => it.text.includes(w)); });
      empty.hidden = visible().length > 0;
      const v = visible(); const cur = v.findIndex((it) => it.k === sel.selectedIndex);
      setActive(cur >= 0 && !q.length ? cur : 0);
    }
    function open() {
      if (!pop.hidden) return;
      pop.hidden = false; wrap.classList.add('open'); btn.setAttribute('aria-expanded', 'true');
      const r = btn.getBoundingClientRect(); wrap.classList.toggle('up', innerHeight - r.bottom < 320 && r.top > 340);
      input.value = ''; filter(); input.focus({ preventScroll: true });
    }
    function close(focusBtn) {
      if (pop.hidden) return;
      pop.hidden = true; wrap.classList.remove('open'); btn.setAttribute('aria-expanded', 'false');
      if (focusBtn) btn.focus({ preventScroll: true });
    }
    function choose(k) {
      const changed = sel.selectedIndex !== k;
      valueDesc.set.call(sel, sel.options[k].value); sync(); close(true);
      if (changed) sel.dispatchEvent(new Event('change', { bubbles: true }));
    }
    btn.addEventListener('click', () => (pop.hidden ? open() : close()));
    btn.addEventListener('keydown', (e) => { if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); open(); } });
    input.addEventListener('input', filter);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); setActive(active + 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(active - 1); }
      else if (e.key === 'Enter') { e.preventDefault(); const v = visible()[active]; if (v) choose(v.k); }
      else if (e.key === 'Escape') { e.preventDefault(); close(true); }
      else if (e.key === 'Tab') close(false);
    });
    document.addEventListener('pointerdown', (e) => { if (!wrap.contains(e.target)) close(false); });
    // reflect programmatic changes and late-added options
    Object.defineProperty(sel, 'value', { configurable: true, get() { return valueDesc.get.call(this); }, set(v) { valueDesc.set.call(this, v); sync(); } });
    new MutationObserver(build).observe(sel, { childList: true });
    sel.addEventListener('change', sync);
    sel._combo = { sync, build };
    build();
  }
  const run = () => document.querySelectorAll('select[data-combo]').forEach(upgrade);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
  window.upgradeCombos = run;
})();
