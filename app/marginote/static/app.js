/* Marginote — the app's screens. Plain JavaScript, no outside code: everything is served by your own server.
   Text from your books is always inserted as text (textContent), never as HTML. */
'use strict';

// ---------- small helpers ----------

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  let value;
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k === 'value') value = v;
    else if (k === 'style') Object.assign(el.style, v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (typeof v === 'boolean' || k === 'disabled' || k === 'checked' || k === 'selected') el[k] = v;
    else el.setAttribute(k, v === true ? '' : String(v));
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : String(kid));
  }
  if (value !== undefined) el.value = value;
  return el;
}

// replaceChildren() would write "null" for an empty slot; put() skips them
function put(el, ...kids) {
  el.replaceChildren(...kids.flat(Infinity).filter((k) => k != null && k !== false));
  return el;
}

const SVG_NS = 'http://www.w3.org/2000/svg';
const ICONS = {
  plus: 'M12 5v14M5 12h14',
  search: 'M10.5 4a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13zM20 20l-4.7-4.7',
  back: 'm15 18-6-6 6-6',
  left: 'm14 17-5-5 5-5',
  right: 'm10 7 5 5-5 5',
  close: 'M6 6l12 12M18 6 6 18',
  camera: 'M4 8h3l2-3h6l2 3h3v11H4zM12 10.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7z',
  image: 'M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15.5 8.5h.01',
  pen: 'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  zoomIn: 'M10.5 4a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13zM20 20l-4.7-4.7M10.5 8v5M8 10.5h5',
  zoomOut: 'M10.5 4a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13zM20 20l-4.7-4.7M8 10.5h5',
  check: 'm5 12 5 5 9-10',
};
function icon(name, size = 18) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  for (const [k, v] of Object.entries({ width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
    'stroke-width': name === 'more' ? 3 : 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' })) {
    svg.setAttribute(k, v);
  }
  const path = document.createElementNS(SVG_NS, 'path');
  path.setAttribute('d', ICONS[name]);
  svg.append(path);
  return svg;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function shortDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, '0')} ${MONTHS[d.getMonth()]}`;
}
function fullDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
const fold = (s) => (s || '').normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const isWide = () => window.matchMedia('(min-width: 960px)').matches;
const coarse = () => window.matchMedia('(pointer: coarse)').matches;

const prefs = {
  get(key, fallback) {
    try { const v = localStorage.getItem('marginote.' + key); return v == null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem('marginote.' + key, JSON.stringify(value)); } catch { /* private mode: not kept */ }
  },
};

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ---------- talking to the server ----------

class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function api(path, { method = 'GET', body, form } = {}) {
  const opts = { method, credentials: 'same-origin', headers: {} };
  if (form) opts.body = form;
  else if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  let res;
  try { res = await fetch(path, opts); } catch {
    throw new ApiError(0, 'Cannot reach your server. Is Tailscale on?');
  }
  const data = (res.headers.get('content-type') || '').includes('json') ? await res.json() : await res.text();
  if (res.status === 401 && path !== '/api/login') {
    if (!location.hash.startsWith('#/login')) {
      sessionStorage.setItem('marginote.after', location.hash);
      go('login');
    }
    throw new ApiError(401, 'Please log in');
  }
  if (!res.ok) {
    let msg = `Something went wrong (${res.status})`;
    if (typeof data?.detail === 'string') msg = data.detail;
    else if (Array.isArray(data?.detail)) msg = data.detail.map((d) => d.msg).join('; ');
    throw new ApiError(res.status, msg);
  }
  return data;
}

const store = {
  books: null,
  tags: null,
  async getBooks(force) {
    if (!this.books || force) this.books = await api('/api/books');
    return this.books;
  },
  async getTags(force) {
    if (!this.tags || force) this.tags = await api('/api/tags');
    return this.tags;
  },
  changed() { this.books = null; this.tags = null; refreshSide(); },
};

function currentBookId(books) {
  const last = prefs.get('captureBook', null);
  if (books.some((b) => b.id === last)) return last;
  return books.find((b) => b.status === 'reading')?.id ?? books[0]?.id ?? null;
}

// ---------- shared pieces ----------

const COVER_COLORS = ['#2f4858', '#5b3a29', '#33553c', '#4a3f6b', '#6b3a4a', '#3d5a73'];
function cover(book, size = '') {
  const placeholder = () => {
    let n = 0;
    for (const c of book.title || '') n = (n * 31 + c.charCodeAt(0)) >>> 0;
    const author = (book.authors || '').split(',')[0].trim().split(' ').pop();
    return h('div', { class: `cover ph ${size}`, style: { background: COVER_COLORS[n % COVER_COLORS.length] }, 'aria-hidden': 'true' },
      h('b', { text: book.title }), h('i', { text: author }));
  };
  if (!book.cover_url) return placeholder();
  const img = h('img', { class: `cover ${size}`, alt: '', loading: 'lazy',
    src: `${book.cover_url}?v=${encodeURIComponent(book.updated_at || '')}` });
  img.addEventListener('error', () => img.replaceWith(placeholder()));
  return img;
}

function withMarks(text) {
  // search results mark the matching words with \u0002 … \u0003
  const out = [];
  const parts = String(text).split(/(\u0002[^\u0003]*\u0003)/);
  for (const part of parts) {
    if (part.startsWith('\u0002')) out.push(h('mark', { text: part.slice(1, -1) }));
    else if (part) out.push(part);
  }
  return out;
}

function entryMeta(e, showBook) {
  const bits = [];
  if (showBook) bits.push(h('span', { class: 'book', text: e.book_title + (e.tags.length || e.note ? ' · ' : '') }));
  const tail = [];
  if (e.kind === 'thought') tail.push('[thought]');
  if (e.tags.length) tail.push(e.tags.map((t) => '#' + t.replace(/ /g, '-')).join(' '));
  if (e.note) tail.push('+note');
  bits.push(tail.join(' · '));
  return bits;
}

function entryRow(e, { showBook = false, fresh = false } = {}) {
  return h('a', { class: `entry-row${e.kind === 'thought' ? ' thought' : ''}${fresh ? ' fresh' : ''}`, href: `#/entry/${e.id}`, id: `e${e.id}` },
    h('span', { class: 'pg', text: e.page || '—' }),
    h('div', { class: 'body' },
      h('p', { class: 'txt' }, e.snippet ? withMarks(e.snippet) : e.text),
      h('span', { class: 'meta' }, entryMeta(e, showBook))));
}

function entryTable(entries, { showBook = true } = {}) {
  const rows = entries.map((e) => {
    const tr = h('tr', { onclick: () => go(`entry/${e.id}`) },
      h('td', { class: 'm', text: e.page || '—' }),
      h('td', { class: e.kind === 'thought' ? 'thought' : '' }, e.snippet ? withMarks(e.snippet) : e.text,
        e.note ? h('div', { class: 'note-line', text: '+ ' + e.note }) : null),
      showBook ? h('td', { text: e.book_title }) : null,
      h('td', { class: 'tags', text: e.tags.map((t) => '#' + t.replace(/ /g, '-')).join(' ') }),
      h('td', { class: 'm', text: fullDate(e.created_at) }));
    return tr;
  });
  return h('div', { class: 'table-wrap' },
    h('table', { class: 'grid' },
      h('thead', {}, h('tr', {},
        h('th', { style: { width: '56px' }, text: 'Pg' }), h('th', { text: 'Entry' }),
        showBook ? h('th', { style: { width: '200px' }, text: 'Book' }) : null,
        h('th', { style: { width: '150px' }, text: 'Tags' }), h('th', { style: { width: '104px' }, text: 'Added' }))),
      h('tbody', {}, rows)));
}

let toastTimer;
function toast(message, action) {
  document.querySelector('.toast')?.remove();
  clearTimeout(toastTimer);
  const el = h('div', { class: 'toast', role: 'status' }, h('span', { text: message }),
    action ? h('button', { type: 'button', onclick: () => { el.remove(); action.run(); } }, action.label) : null);
  document.body.append(el);
  toastTimer = setTimeout(() => el.remove(), action ? 9000 : 4000);
}

function errorBox(err, retry) {
  return h('div', { class: 'pad' },
    h('div', { class: 'error', role: 'alert', text: err.message || String(err) }),
    retry ? h('button', { class: 'btn', type: 'button', onclick: retry }, 'Try again') : null);
}

function backLink(label, fallback) {
  return h('a', { class: 'link-btn', href: '#/' + fallback, onclick: (ev) => {
    if (history.length > 1 && sessionStorage.getItem('marginote.nav')) { ev.preventDefault(); history.back(); }
  } }, icon('back', 20), label);
}

function tagInput(initial, allTags) {
  let tags = [...initial];
  const input = h('input', { type: 'text', placeholder: 'Add a tag', autocapitalize: 'none', autocomplete: 'off',
    autocorrect: 'off', spellcheck: 'false', enterkeyhint: 'done', 'aria-label': 'Add a tag' });
  const box = h('div', { class: 'tag-input', onclick: () => input.focus() });
  const sugg = h('div', { class: 'suggest' });
  const clean = (t) => t.replace(/^#+/, '').replace(/\s+/g, ' ').trim();
  function add(raw) {
    const t = clean(raw);
    if (t && !tags.some((x) => x.toLowerCase() === t.toLowerCase())) tags.push(t);
    draw();
  }
  function draw() {
    put(box, ...tags.map((t) => h('span', { class: 'chip' }, t,
      h('button', { type: 'button', 'aria-label': `Remove tag ${t}`, onclick: (ev) => {
        ev.stopPropagation(); tags = tags.filter((x) => x !== t); draw();
      } }, '×'))), input);
    drawSuggestions();
  }
  function drawSuggestions() {
    const q = fold(input.value);
    const list = allTags.filter((t) => !tags.includes(t.name) && (!q || fold(t.name).includes(q))).slice(0, 8);
    put(sugg, ...list.map((t) => h('button', {
      type: 'button',
      onpointerdown: (ev) => ev.preventDefault(),   // keep the keyboard open; do not add the half-typed word
      onclick: () => { input.value = ''; add(t.name); input.focus(); },
    }, '#' + t.name)));
  }
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' || ev.key === ',') { ev.preventDefault(); add(input.value); input.value = ''; drawSuggestions(); }
    else if (ev.key === 'Backspace' && !input.value && tags.length) { tags.pop(); draw(); }
  });
  input.addEventListener('input', () => {
    if (input.value.includes(',')) {
      const parts = input.value.split(',');
      input.value = parts.pop();
      parts.forEach(add);
    }
    drawSuggestions();
  });
  input.addEventListener('blur', () => { if (input.value.trim()) { add(input.value); input.value = ''; } });
  draw();
  return {
    el: h('div', { class: 'field' }, h('span', { text: 'Tags' }), box, sugg),
    get value() { if (input.value.trim()) { add(input.value); input.value = ''; } return tags; },
  };
}

// ---------- passage selection ----------
// Tap the first word, then the last. A tap goes to the nearest word on the nearest line, so a small word
// is easy to hit; the dots at each end can be dragged; the arrows move either end by one word.

function linesOf(words) {
  const map = new Map();
  for (const w of words) {
    let line = map.get(w.line);
    if (!line) { line = { words: [], top: Infinity, bottom: -Infinity, left: Infinity, right: -Infinity }; map.set(w.line, line); }
    line.words.push(w);
    line.top = Math.min(line.top, w.y); line.bottom = Math.max(line.bottom, w.y + w.h);
    line.left = Math.min(line.left, w.x); line.right = Math.max(line.right, w.x + w.w);
  }
  const lines = [...map.values()];
  for (const line of lines) line.words.sort((a, b) => a.i - b.i);
  lines.sort((a, b) => a.words[0].i - b.words[0].i);
  return lines;
}

function joinWords(words) {
  let out = '';
  words.forEach((w, k) => {
    if (k === 0) { out = w.text; return; }
    const prev = words[k - 1];
    if (prev.line !== w.line && /[-‐‑¬]$/.test(prev.text) && prev.text.length > 1) out = out.slice(0, -1) + w.text;
    else out += ' ' + w.text;
  });
  return out.replace(/\s+([,.)\]…”])/g, '$1').replace(/([“(\[])\s+/g, '$1').trim();
}

function makeSelector(photo, { start = null, end = null, onChange = () => {}, startMode = null } = {}) {
  const words = [];
  for (const w of photo.words) words[w.i] = w;
  const lines = linesOf(photo.words);
  const last = words.length - 1;
  let s = start, e = end;
  let phase = s != null && e != null ? 'range' : 'none';
  let mode = startMode || prefs.get('selectMode', 'photo');
  let zoom = 1;

  const hint = h('span', { class: 'sel-hint' });
  const photoBtn = h('button', { type: 'button', onclick: () => setMode('photo') }, 'Photo');
  const textBtn = h('button', { type: 'button', onclick: () => setMode('text') }, 'Large text');
  const zoomBtn = h('button', { class: 'icon-btn plain', type: 'button', 'aria-label': 'Zoom in', onclick: toggleZoom }, icon('zoomIn', 20));
  const modes = h('div', { class: 'sel-modes' },
    h('div', { class: 'seg', role: 'group', 'aria-label': 'Select on' }, photoBtn, textBtn), zoomBtn, hint);

  const img = h('img', { src: photo.image_url, alt: 'Photo of the page', draggable: 'false' });
  const wordLayer = h('div', { class: 'layer', 'aria-hidden': 'true' });
  const markLayer = h('div', { class: 'layer', 'aria-hidden': 'true' });
  const startDot = h('div', { class: 'handle start', title: 'Drag to move the start' });
  const endDot = h('div', { class: 'handle end', title: 'Drag to move the end' });
  const stage = h('div', { class: 'photo-stage' }, img, wordLayer, markLayer, startDot, endDot);
  const scroller = h('div', { class: 'photo-scroll' }, stage);
  const textPane = h('div', { class: 'text-pick' });
  const root = h('div', { class: 'selector' }, modes, scroller, textPane);

  const pct = (v, total) => `${(v / total) * 100}%`;
  const box = (x, y, w, hgt) => ({ left: pct(x, photo.width), top: pct(y, photo.height), width: pct(w, photo.width), height: pct(hgt, photo.height) });

  wordLayer.append(...photo.words.map((w) => h('div', { class: 'wb', style: box(w.x, w.y, w.w, w.h) })));
  const buttons = [];
  textPane.append(h('div', { class: 'flow' }, lines.flatMap((line) => line.words).map((w) => {
    const b = h('button', { type: 'button', class: 'tw', onclick: () => tap(w.i) }, w.text);
    buttons[w.i] = b;
    return b;
  })));

  function sizeStage() {
    // fit the page to the screen width on a phone, to the screen height on a computer; zoom doubles it
    const fitHeight = Math.max(320, window.innerHeight - 190);
    const byHeight = (fitHeight * photo.width) / photo.height;
    stage.style.width = isWide() ? `${Math.round(byHeight * zoom)}px` : `${100 * zoom}%`;
  }

  function nearest(x, y, loose) {
    let best = null, bestD = Infinity;
    for (const line of lines) {
      const dy = y < line.top ? line.top - y : y > line.bottom ? y - line.bottom : 0;
      const dx = x < line.left ? line.left - x : x > line.right ? x - line.right : 0;
      const d = dy + dx * 0.3 + Math.abs(y - (line.top + line.bottom) / 2) * 0.01;
      if (d < bestD) { bestD = d; best = line; }
    }
    if (!best || (!loose && bestD > (best.bottom - best.top) * 1.5)) return null;
    let word = null, wd = Infinity;
    for (const w of best.words) {
      const d = x < w.x ? w.x - x : x > w.x + w.w ? x - (w.x + w.w) : 0;
      if (d < wd) { wd = d; word = w; }
    }
    return word ? word.i : null;
  }

  function toPhoto(clientX, clientY) {
    const r = stage.getBoundingClientRect();
    return { x: ((clientX - r.left) / r.width) * photo.width, y: ((clientY - r.top) / r.height) * photo.height };
  }

  function tap(i) {
    if (phase === 'one') { e = i; if (e < s) [s, e] = [e, s]; phase = 'range'; }
    else { s = e = i; phase = 'one'; }
    update();
  }

  // taps on the photo (a drag scrolls instead)
  let down = null;
  stage.addEventListener('pointerdown', (ev) => {
    if (ev.target.closest('.handle')) return;
    down = { x: ev.clientX, y: ev.clientY };
  });
  stage.addEventListener('pointerup', (ev) => {
    if (!down) return;
    const moved = Math.hypot(ev.clientX - down.x, ev.clientY - down.y);
    down = null;
    if (moved > 10) return;
    const p = toPhoto(ev.clientX, ev.clientY);
    const i = nearest(p.x, p.y, false);
    if (i != null) tap(i);
  });
  stage.addEventListener('pointercancel', () => { down = null; });

  // dragging the dots
  let dragging = null;
  for (const [dot, which] of [[startDot, 'start'], [endDot, 'end']]) {
    dot.addEventListener('pointerdown', (ev) => {
      ev.preventDefault(); ev.stopPropagation();
      dot.setPointerCapture(ev.pointerId);
      dragging = which;
    });
    dot.addEventListener('pointermove', (ev) => {
      if (!dragging) return;
      const lift = ev.pointerType === 'touch' ? 34 : 0;   // aim just above the finger, so the word stays visible
      const p = toPhoto(ev.clientX, ev.clientY - lift);
      const i = nearest(p.x, p.y, true);
      if (i == null) return;
      if (dragging === 'start') s = i; else e = i;
      if (s > e) { [s, e] = [e, s]; dragging = dragging === 'start' ? 'end' : 'start'; }
      phase = 'range';
      update();
    });
    const stop = () => { dragging = null; };
    dot.addEventListener('pointerup', stop);
    dot.addEventListener('pointercancel', stop);
  }

  function drawMarks() {
    put(markLayer);
    const show = s != null && mode === 'photo';
    startDot.hidden = endDot.hidden = !show;
    if (!show) return;
    const rects = new Map();
    for (let k = s; k <= e; k++) {
      const w = words[k];
      if (!w) continue;
      const r = rects.get(w.line) || { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
      r.x0 = Math.min(r.x0, w.x); r.y0 = Math.min(r.y0, w.y);
      r.x1 = Math.max(r.x1, w.x + w.w); r.y1 = Math.max(r.y1, w.y + w.h);
      rects.set(w.line, r);
    }
    for (const r of rects.values()) markLayer.append(h('div', { class: 'hl', style: box(r.x0 - 2, r.y0 - 2, r.x1 - r.x0 + 4, r.y1 - r.y0 + 4) }));
    const a = words[s], b = words[e];
    const scale = stage.clientHeight / photo.height || 0.2;
    startDot.style.left = pct(a.x, photo.width);
    startDot.style.top = `calc(${pct(a.y, photo.height)} - 12px)`;
    startDot.style.setProperty('--stem', `${Math.max(8, a.h * scale + 3)}px`);
    endDot.style.left = pct(b.x + b.w, photo.width);
    endDot.style.top = `calc(${pct(b.y + b.h, photo.height)} + 12px)`;
    endDot.style.setProperty('--stem', `${Math.max(8, b.h * scale + 3)}px`);
  }

  function markText() {
    buttons.forEach((b, i) => {
      if (!b) return;
      const inside = s != null && i >= s && i <= e;
      b.classList.toggle('in', inside);
      b.classList.toggle('edge', inside && (i === s || i === e));
      b.setAttribute('aria-pressed', inside ? 'true' : 'false');
    });
  }

  function update() {
    drawMarks();
    markText();
    hint.textContent = phase === 'none' ? 'Tap the first word' : phase === 'one' ? 'Now tap the last word'
      : mode === 'text' ? 'Arrows below adjust it' : coarse() ? 'Drag the dots to adjust' : 'Tap again to start over';
    onChange({ start: s, end: e, phase, text: s == null ? '' : joinWords(words.slice(s, e + 1).filter(Boolean)) });
  }

  function setMode(m, remember = true) {
    mode = m;
    if (remember) prefs.set('selectMode', m);
    photoBtn.classList.toggle('on', m === 'photo'); textBtn.classList.toggle('on', m === 'text');
    scroller.hidden = m !== 'photo'; textPane.hidden = m !== 'text'; zoomBtn.hidden = m !== 'photo';
    update();
    if (m === 'text' && s != null) buttons[s]?.scrollIntoView({ block: 'center' });
  }

  function toggleZoom() {
    zoom = zoom === 1 ? 2 : 1;
    put(zoomBtn, icon(zoom === 1 ? 'zoomIn' : 'zoomOut', 20));
    zoomBtn.setAttribute('aria-label', zoom === 1 ? 'Zoom in' : 'Zoom out');
    sizeStage();
    requestAnimationFrame(() => {
      drawMarks();
      const target = s != null ? words[s] : null;
      if (target) {
        scroller.scrollLeft = (target.x / photo.width) * stage.clientWidth - scroller.clientWidth / 3;
        scroller.scrollTop = (target.y / photo.height) * stage.clientHeight - scroller.clientHeight / 3;
      }
    });
  }

  function nudge(which, step) {
    if (s == null) return;
    if (which === 'start') s = Math.min(Math.max(0, s + step), e);
    else e = Math.max(Math.min(last, e + step), s);
    phase = 'range';
    update();
  }

  img.addEventListener('load', () => drawMarks());
  const onResize = debounce(() => { sizeStage(); drawMarks(); }, 150);
  window.addEventListener('resize', onResize);
  sizeStage();
  setMode(mode, false);

  return {
    el: root,
    nudge,
    get range() { return s == null ? null : { start: s, end: e }; },
    destroy() { window.removeEventListener('resize', onResize); },
  };
}

function nudgeBar(sel) {
  const pair = (label, which) => h('span', { class: 'nudge' }, label,
    h('button', { type: 'button', 'aria-label': `Move the ${which} one word back`, onclick: () => sel.nudge(which, -1) }, icon('left')),
    h('button', { type: 'button', 'aria-label': `Move the ${which} one word on`, onclick: () => sel.nudge(which, 1) }, icon('right')));
  return h('div', { class: 'nudges' }, pair('Start', 'start'), pair('End', 'end'));
}

// ---------- screens ----------

async function viewLogin() {
  const pw = h('input', { class: 'input', type: 'password', id: 'pw', autocomplete: 'current-password', required: true });
  const msg = h('div', { class: 'note-line', role: 'alert' });
  const form = h('form', { class: 'login', onsubmit: async (ev) => {
    ev.preventDefault();
    msg.textContent = '';
    try {
      await api('/api/login', { method: 'POST', body: { password: pw.value } });
      const after = sessionStorage.getItem('marginote.after');
      sessionStorage.removeItem('marginote.after');
      store.changed();
      location.hash = after && !after.startsWith('#/login') ? after : '#/';
    } catch (err) { msg.textContent = err.message; pw.select(); }
  } },
  h('h1', { class: 'brand' }, 'Marginote'),
  h('input', { type: 'text', name: 'username', value: 'marginote', autocomplete: 'username', hidden: true, 'aria-hidden': 'true' }),
  h('label', { class: 'field', for: 'pw' }, h('span', { text: 'Password' }), pw),
  h('button', { class: 'btn primary big', type: 'submit' }, 'Log in'), msg);
  setTimeout(() => pw.focus(), 50);
  return { el: form, bare: true };
}

async function viewBooks({ params }) {
  const [books, tags] = await Promise.all([store.getBooks(), store.getTags()]);
  let sort = prefs.get('booksSort', 'last_entry');
  let status = prefs.get('booksStatus', 'all');
  const current = currentBookId(books);
  const total = books.reduce((n, b) => n + b.entry_count, 0);
  const SORTS = { last_entry: 'sort: last quote ↓', title: 'sort: title', added: 'sort: added ↓' };
  const STATUSES = ['all', 'reading', 'paused', 'finished'];

  const q = h('input', { type: 'search', placeholder: 'Filter books or search quotes', 'aria-label': 'Filter books or search quotes',
    value: params.get('q') || '', enterkeyhint: 'search' });
  const sortBtn = h('button', { class: 'btn small', type: 'button', onclick: () => {
    const keys = Object.keys(SORTS); sort = keys[(keys.indexOf(sort) + 1) % keys.length]; prefs.set('booksSort', sort); draw();
  } });
  const statusBtn = h('button', { class: 'btn small', type: 'button', onclick: () => {
    status = STATUSES[(STATUSES.indexOf(status) + 1) % STATUSES.length]; prefs.set('booksStatus', status); draw();
  } });
  const list = h('div');
  const found = h('section');

  function draw() {
    sortBtn.textContent = SORTS[sort];
    statusBtn.textContent = `status: ${status}`;
    const needle = fold(q.value.trim());
    let shown = books.filter((b) => (status === 'all' || b.status === status)
      && (!needle || fold(`${b.title} ${b.subtitle || ''} ${b.authors || ''}`).includes(needle)));
    const key = { last_entry: (b) => b.last_entry_at || b.created_at, added: (b) => b.created_at }[sort];
    shown = [...shown].sort(sort === 'title' ? (a, b) => a.title.localeCompare(b.title) : (a, b) => (key(a) < key(b) ? 1 : -1));
    put(list, 
      h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'Title · author' }),
        h('span', { class: 'w40', style: { textAlign: 'right' }, text: 'Qts' }), h('span', { class: 'w64', style: { textAlign: 'right' }, text: 'Last' })),
      ...shown.map((b) => h('a', { class: `book-row${b.id === current ? ' current' : ''}`, href: `#/book/${b.id}` },
        h('span', { class: 'main' },
          h('span', { class: 't' }, b.id === current ? h('span', { class: 'dot', 'aria-hidden': 'true' }) : null, h('span', { text: b.title })),
          h('span', { class: 'a', text: [b.authors, b.status].filter(Boolean).join(' · ') })),
        h('span', { class: 'num w40', text: b.entry_count }),
        h('span', { class: 'num w64 muted', text: shortDate(b.last_entry_at) }))));
    if (!books.length) {
      put(list, h('div', { class: 'empty' }, h('span', { text: 'No books yet. Add the book you are reading, then capture your first quote.' }),
        h('a', { class: 'btn primary', href: '#/book/new' }, icon('plus'), 'Add a book')));
    } else if (!shown.length) {
      list.append(h('div', { class: 'empty', text: needle ? 'No book matches; quotes that match are below.' : 'No book with this status.' }));
    }
  }

  const searchQuotes = debounce(async () => {
    const text = q.value.trim();
    history.replaceState(null, '', text ? `#/?q=${encodeURIComponent(text)}` : '#/');
    if (text.length < 2) { put(found, ); return; }
    try {
      const hits = await api(`/api/search?q=${encodeURIComponent(text)}&limit=30`);
      if (q.value.trim() !== text) return;
      put(found, 
        h('div', { class: 'colhead' }, h('span', { text: `Quotes matching “${text}”` }), h('span', { style: { flex: 1, textAlign: 'right' }, text: hits.length })),
        ...hits.map((e) => entryRow(e, { showBook: true })),
        hits.length ? null : h('div', { class: 'empty', text: 'No quote or note contains these words.' }));
    } catch (err) { put(found, errorBox(err)); }
  }, 250);
  q.addEventListener('input', () => { draw(); searchQuotes(); });

  draw();
  if (q.value) searchQuotes();
  const el = h('div', {},
    h('header', { class: 'top' },
      h('div', { class: 'top-row' },
        h('h1', {}, 'Books', h('span', { class: 'count', text: books.length })),
        h('div', { style: { display: 'flex', gap: '8px' } },
          h('a', { class: 'icon-btn narrow-only', href: '#/settings', 'aria-label': 'Settings' }, icon('more')),
          h('a', { class: 'icon-btn', href: '#/book/new', 'aria-label': 'Add a book' }, icon('plus')))),
      h('label', { class: 'search' }, icon('search', 16), q),
      h('div', { class: 'tools' }, sortBtn, statusBtn, h('span', { class: 'grow', text: plural(total, 'entry').replace('entrys', 'entries') }))),
    list, found,
    tags.length ? h('section', { class: 'pad narrow-only' }, h('h2', { class: 'section-title', text: 'Top tags' }),
      h('div', { class: 'chips' }, tags.slice(0, 12).map((t) => h('a', { class: 'chip', href: `#/quotes?tag=${encodeURIComponent(t.name)}` },
        t.name, h('span', { class: 'n', text: t.count }))))) : null);
  return { el, nav: 'books' };
}

async function viewBook({ args: [id], params }) {
  const order = prefs.get('bookOrder', 'page');
  const [book, entries] = await Promise.all([api(`/api/books/${id}`), api(`/api/books/${id}/entries?order=${order}`)]);
  let tag = params.get('tag') || '';
  const fresh = Number(params.get('fresh')) || null;
  const bookTags = [...new Set(entries.flatMap((e) => e.tags))].sort((a, b) => a.localeCompare(b));
  const q = h('input', { type: 'search', placeholder: 'Search in this book', 'aria-label': 'Search in this book', enterkeyhint: 'search' });
  const list = h('div');
  const tagSelect = h('select', { class: isWide() ? 'btn small' : null, 'aria-label': 'Show tag', onchange: () => { tag = tagSelect.value; draw(); } },
    h('option', { value: '' }, 'tag: all'), bookTags.map((t) => h('option', { value: t }, '#' + t)));
  tagSelect.value = tag;
  const orderBtn = h('button', { type: 'button', class: 'w36', style: { textAlign: 'left', whiteSpace: 'nowrap' },
    text: order === 'page' ? 'Pg ↑' : 'New ↓', 'aria-label': order === 'page' ? 'Sorted by page; sort by date' : 'Sorted by date; sort by page',
    onclick: () => { prefs.set('bookOrder', order === 'page' ? 'date' : 'page'); render(); } });

  function draw() {
    const needle = fold(q.value.trim());
    const shown = entries.filter((e) => (!tag || e.tags.includes(tag))
      && (!needle || fold(`${e.text} ${e.note || ''} ${e.tags.join(' ')} ${e.page || ''}`).includes(needle)));
    put(list, 
      isWide() ? (shown.length ? entryTable(shown, { showBook: false }) : null) : h('div', {}, shown.map((e) => entryRow(e, { fresh: e.id === fresh }))),
      shown.length ? null : h('div', { class: 'empty' }, entries.length ? 'Nothing matches.' : h('span', { text: 'No quotes from this book yet.' }),
        entries.length ? null : h('a', { class: 'btn primary', href: `#/capture?book=${book.id}` }, icon('camera'), 'Capture a quote')));
  }
  q.addEventListener('input', draw);
  draw();
  if (fresh) setTimeout(() => document.getElementById(`e${fresh}`)?.scrollIntoView({ block: 'center' }), 50);

  const coverEl = h('span', {}, cover(book, isWide() ? 'large' : ''));
  if (params.get('cover') === '1' && !book.has_cover) {
    (async () => {
      for (let k = 0; k < 8; k++) {
        await new Promise((r) => setTimeout(r, 1500));
        if (!coverEl.isConnected) return;
        const b = await api(`/api/books/${id}`).catch(() => null);
        if (b?.has_cover) { put(coverEl, cover(b, isWide() ? 'large' : '')); store.changed(); return; }
      }
    })();
  }
  const details = [book.authors, book.publisher, book.year, book.edition, book.language].filter(Boolean).join(' · ');
  const el = h('div', {},
    h('div', { class: 'bar' }, backLink('Books', ''), h('a', { class: 'link-btn', href: `#/book/${id}/edit` }, 'Edit')),
    h('header', { class: 'top', style: { paddingTop: '4px' } },
      h('div', { class: 'book-head' }, coverEl,
        h('div', { class: 'info' },
          h('h1', { text: book.title }),
          book.subtitle ? h('span', { class: 'muted', text: book.subtitle }) : null,
          details ? h('span', { class: 'meta', text: details }) : null,
          h('span', { class: 'counts', text: `${plural(book.quote_count, 'quote')} · ${plural(book.thought_count, 'thought')} · ${plural(bookTags.length, 'tag')}` }),
          h('div', { class: 'row-btns', style: { marginTop: '4px' } },
            h('a', { class: 'btn primary small', href: `#/capture?book=${book.id}` }, '+ Quote'),
            entries.length ? h('a', { class: 'btn small', href: `/api/books/${book.id}/export.md`, download: '' }, 'Export') : null))),
      entries.length ? h('label', { class: 'search' }, icon('search', 16), q) : null),
    entries.length && !isWide() ? h('div', { class: 'colhead' }, orderBtn, h('span', { style: { flex: 1 }, text: 'Entry' }), tagSelect) : null,
    entries.length && isWide() ? h('div', { class: 'tools', style: { padding: '12px 32px' } },
      h('button', { class: 'btn small', type: 'button', onclick: orderBtn.onclick || (() => orderBtn.click()) }, order === 'page' ? 'sort: page ↑' : 'sort: added ↓'),
      tagSelect) : null,
    list);
  return { el, nav: 'books' };
}

async function viewQuotes({ params }) {
  const books = await store.getBooks();
  const tags = await store.getTags();
  const f = { q: params.get('q') || '', tag: params.get('tag') || '', book: params.get('book') || '', kind: params.get('kind') || '' };
  let entries = [];
  let offset = 0;
  let more = false;
  const PAGE = 200;

  async function load(append) {
    if (f.q) {
      let hits = await api(`/api/search?q=${encodeURIComponent(f.q)}&limit=500${f.book ? `&book_id=${f.book}` : ''}`);
      hits = hits.filter((e) => (!f.tag || e.tags.includes(f.tag)) && (!f.kind || e.kind === f.kind));
      entries = hits; more = false;
    } else {
      const qs = new URLSearchParams({ limit: PAGE, offset });
      if (f.tag) qs.set('tag', f.tag);
      if (f.book) qs.set('book_id', f.book);
      if (f.kind) qs.set('kind', f.kind);
      const page = await api(`/api/entries?${qs}`);
      entries = append ? entries.concat(page) : page;
      more = page.length === PAGE;
    }
  }
  await load(false);

  const setFilter = (key, value) => {
    f[key] = value;
    const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v));
    location.hash = `#/quotes${qs.toString() ? '?' + qs : ''}`;
  };
  const q = h('input', { type: 'search', placeholder: 'Search text, notes, books', 'aria-label': 'Search quotes', value: f.q, enterkeyhint: 'search' });
  q.addEventListener('input', debounce(() => setFilter('q', q.value.trim()), 400));
  const select = (key, label, options) => {
    const s = h('select', { class: 'btn small', 'aria-label': label, onchange: () => setFilter(key, s.value) }, options);
    s.value = f[key];
    return s;
  };
  const filters = h('div', { class: 'tools' },
    select('tag', 'Tag', [h('option', { value: '' }, 'tag: all'), tags.map((t) => h('option', { value: t.name }, `#${t.name} (${t.count})`))]),
    select('book', 'Book', [h('option', { value: '' }, 'book: all'), books.map((b) => h('option', { value: String(b.id) }, b.title))]),
    select('kind', 'Kind', [h('option', { value: '' }, 'kind: all'), h('option', { value: 'quote' }, 'quotes'), h('option', { value: 'thought' }, 'thoughts')]),
    f.tag || f.book || f.kind || f.q ? h('a', { class: 'btn small', href: '#/quotes' }, 'clear') : null);

  const list = h('div');
  function draw() {
    put(list, 
      isWide() ? (entries.length ? entryTable(entries) : null) : h('div', {}, entries.map((e) => entryRow(e, { showBook: !f.book }))),
      entries.length ? null : h('div', { class: 'empty', text: f.q || f.tag || f.book || f.kind ? 'Nothing matches these filters.' : 'No quotes yet.' }),
      more ? h('div', { class: 'pad' }, h('button', { class: 'btn', type: 'button', onclick: async () => { offset += PAGE; await load(true); draw(); } }, 'Show more')) : null);
  }
  draw();
  const el = h('div', {},
    h('header', { class: 'top' },
      h('div', { class: 'top-row' }, h('h1', {}, 'Quotes', h('span', { class: 'count', text: entries.length + (more ? '+' : '') })),
        h('a', { class: 'btn primary wide-only', href: '#/capture' }, '+ New entry')),
      h('label', { class: 'search' }, icon('search', 16), q), filters),
    list);
  if (f.q) setTimeout(() => { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 30);
  return { el, nav: 'quotes' };
}

async function viewTags() {
  const tags = await store.getTags(true);
  let byName = prefs.get('tagsByName', false);
  const list = h('div');
  const toggle = h('button', { class: 'btn small', type: 'button', onclick: () => { byName = !byName; prefs.set('tagsByName', byName); draw(); } });
  function draw() {
    toggle.textContent = byName ? 'sort: name' : 'sort: count ↓';
    const shown = [...tags].sort(byName ? (a, b) => a.name.localeCompare(b.name) : (a, b) => b.count - a.count);
    put(list, ...shown.map((t) => h('a', { class: 'pick', href: `#/quotes?tag=${encodeURIComponent(t.name)}` },
      h('span', { class: 'main' }, h('span', { class: 't mono', text: '#' + t.name })),
      h('span', { class: 'num muted', text: t.count }))));
    if (!tags.length) list.append(h('div', { class: 'empty', text: 'No tags yet. Add tags when you save a quote.' }));
  }
  draw();
  return {
    el: h('div', {}, h('header', { class: 'top' }, h('div', { class: 'top-row' }, h('h1', {}, 'Tags', h('span', { class: 'count', text: tags.length }))),
      h('div', { class: 'tools' }, toggle)), list),
    nav: 'tags',
  };
}

async function viewEntry({ args: [id] }) {
  const e = await api(`/api/entries/${id}`);
  const book = await api(`/api/books/${e.book_id}`);
  const del = async () => {
    if (!confirm(`Delete this ${e.kind}? This cannot be undone.`)) return;
    try {
      await api(`/api/entries/${id}`, { method: 'DELETE' });
      store.changed();
      toast(`${e.kind === 'quote' ? 'Quote' : 'Thought'} deleted`);
      go(`book/${e.book_id}`);
    } catch (err) { toast(err.message); }
  };
  const copy = async () => {
    const cite = [book.authors, book.title].filter(Boolean).join(', ') + (e.page ? `, p. ${e.page}` : '');
    try { await navigator.clipboard.writeText(`${e.text}\n— ${cite}`); toast('Copied with its reference'); } catch { toast('Copying is not allowed here'); }
  };
  const el = h('div', {},
    h('div', { class: 'bar' }, backLink('Back', `book/${e.book_id}`), h('a', { class: 'link-btn', href: `#/entry/${id}/edit` }, 'Edit')),
    h('div', { class: 'pad' },
      h('a', { class: 'book-link', href: `#/book/${book.id}` }, cover(book, 'small'),
        h('span', {}, h('span', { class: 't', text: book.title }), h('br'), h('span', { class: 'muted', text: book.authors || '' }))),
      h('div', { class: 'kv' }, h('span', { text: e.page ? `p. ${e.page}` : 'no page' }), h('span', { text: e.kind }), h('span', { text: `added ${fullDate(e.created_at)}` })),
      h('p', { class: `quote-big${e.kind === 'thought' ? ' thought-text' : ''}`, text: e.text }),
      e.note ? h('div', { class: 'note-box', text: e.note }) : null,
      e.tags.length ? h('div', { class: 'chips' }, e.tags.map((t) => h('a', { class: 'chip', href: `#/quotes?tag=${encodeURIComponent(t)}` }, '#' + t))) : null,
      h('div', { class: 'row-btns' },
        h('a', { class: 'btn', href: `#/entry/${id}/edit` }, icon('pen', 16), 'Edit'),
        e.photo_id ? h('a', { class: 'btn', href: `#/entry/${id}/photo` }, icon('image', 16), 'Photo') : null,
        h('button', { class: 'btn', type: 'button', onclick: copy }, 'Copy'),
        h('button', { class: 'btn danger', type: 'button', onclick: del }, 'Delete'))));
  return { el, nav: 'quotes' };
}

async function viewEntryEdit({ args: [id] }) {
  const [e, books, tags] = await Promise.all([api(`/api/entries/${id}`), store.getBooks(), store.getTags()]);
  let kind = e.kind;
  const text = h('textarea', { class: 'textarea', rows: 6, id: 'f-text', value: e.text });
  const page = h('input', { class: 'input', id: 'f-page', value: e.page || '', inputmode: 'text', style: { width: '110px' } });
  const note = h('textarea', { class: 'textarea', rows: 3, id: 'f-note', value: e.note || '' });
  const bookSel = h('select', { class: 'select', id: 'f-book' }, books.map((b) => h('option', { value: String(b.id) }, b.title)));
  bookSel.value = String(e.book_id);
  const tagsIn = tagInput(e.tags, tags);
  const kindSeg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Kind' });
  const drawKind = () => put(kindSeg, ...['quote', 'thought'].map((k) =>
    h('button', { type: 'button', class: kind === k ? 'on' : '', onclick: () => { kind = k; drawKind(); } }, k === 'quote' ? 'Quote' : 'Thought')));
  drawKind();
  const msg = h('div', { class: 'note-line', role: 'alert' });
  const save = async (ev) => {
    ev.preventDefault();
    try {
      await api(`/api/entries/${id}`, { method: 'PATCH', body: {
        text: text.value, page: page.value, note: note.value, book_id: Number(bookSel.value), kind, tags: tagsIn.value } });
      store.changed();
      toast('Saved');
      go(`entry/${id}`);
    } catch (err) { msg.textContent = err.message; }
  };
  const el = h('form', { onsubmit: save },
    h('div', { class: 'bar' }, h('a', { class: 'link-btn', href: `#/entry/${id}` }, 'Cancel'),
      h('span', { class: 'title', text: 'Edit' }), h('button', { class: 'link-btn', type: 'submit', style: { fontWeight: 600 } }, 'Save')),
    h('div', { class: 'details' },
      kindSeg,
      h('label', { class: 'field', for: 'f-text' }, h('span', { text: kind === 'quote' ? 'Passage' : 'Thought' }), text),
      h('div', { class: 'two' }, h('label', { class: 'field', for: 'f-page' }, h('span', { text: 'Page' }), page),
        h('label', { class: 'field', for: 'f-book', style: { flex: 1, minWidth: 0 } }, h('span', { text: 'Book' }), bookSel)),
      h('label', { class: 'field', for: 'f-note' }, h('span', { text: 'Your note' }), note),
      tagsIn.el,
      e.photo_id ? h('a', { class: 'btn', href: `#/entry/${id}/photo` }, icon('image', 16), 'Change the selection on the photo') : null,
      msg,
      h('button', { class: 'btn primary big', type: 'submit' }, 'Save')));
  return { el, bare: !isWide(), nav: 'quotes' };
}

async function viewEntryPhoto({ args: [id] }) {
  const e = await api(`/api/entries/${id}`);
  if (!e.photo_id) { go(`entry/${id}`); return null; }
  const photo = await api(`/api/photos/${e.photo_id}`);
  const preview = h('p', { class: 'sel-preview' });
  const saveBtn = h('button', { class: 'btn primary', type: 'button', disabled: true }, 'Use this selection');
  let range = null;
  const sel = makeSelector(photo, { start: e.word_start, end: e.word_end, startMode: 'photo', onChange: (r) => {
    range = r.phase === 'none' ? null : r;
    preview.textContent = r.text || 'Tap the first word of the passage.';
    preview.classList.toggle('empty', !r.text);
    saveBtn.disabled = !range || (r.start === e.word_start && r.end === e.word_end);
  } });
  saveBtn.addEventListener('click', async () => {
    if (!confirm('Replace the saved text with the words selected on the photo?')) return;
    try {
      await api(`/api/entries/${id}`, { method: 'PATCH', body: { word_start: range.start, word_end: range.end } });
      store.changed();
      toast('Selection saved');
      go(`entry/${id}`);
    } catch (err) { toast(err.message); }
  });
  const el = h('div', { class: 'selector-page', style: { display: 'flex', flexDirection: 'column', height: '100dvh' } },
    h('div', { class: 'bar' }, h('a', { class: 'link-btn', href: `#/entry/${id}`, onclick: () => sel.destroy() }, icon('back', 20), 'Back'),
      h('span', { class: 'title', text: e.page ? `Page ${e.page}` : 'Photo' }), h('span', { style: { width: '60px' } })),
    sel.el,
    h('div', { class: 'sel-sheet' }, preview, nudgeBar(sel), saveBtn));
  return { el, bare: true, cleanup: () => sel.destroy() };
}

// ----- capture: book → photo → passage → note and tags → save -----

const capture = { last: null };   // the photo just used, to take another passage from it

function shrinkPhoto(file) {
  // Shrink on the phone before sending: a 3–8 MB photo becomes about 0.5 MB, uploads fast, and carries no
  // location, camera or date data. Falls back to the original file if the browser cannot decode it.
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      try {
        const scale = Math.min(1, 2400 / Math.max(img.naturalWidth, img.naturalHeight));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(img.naturalWidth * scale);
        canvas.height = Math.round(img.naturalHeight * scale);
        canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);
        canvas.toBlob((blob) => resolve(blob ? new File([blob], 'page.jpg', { type: 'image/jpeg' }) : file), 'image/jpeg', 0.9);
      } catch { resolve(file); }
    };
    img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
    img.src = url;
  });
}

async function viewCapture({ params }) {
  const [books, tags] = await Promise.all([store.getBooks(), store.getTags()]);
  if (!books.length) {
    return {
      el: h('div', {}, h('div', { class: 'bar' }, backLink('Cancel', ''), h('span', { class: 'title', text: 'Capture' }), h('span', { style: { width: '60px' } })),
        h('div', { class: 'empty' }, 'First add the book you are reading.', h('a', { class: 'btn primary', href: '#/book/new?then=capture' }, icon('plus'), 'Add a book'))),
      bare: true,
    };
  }
  const wanted = Number(params.get('book'));
  let book = books.find((b) => b.id === wanted) || books.find((b) => b.id === currentBookId(books));
  let photo = null;
  let range = null;
  let selector = null;
  const root = h('div', { class: 'capture', style: { display: 'flex', flexDirection: 'column', minHeight: '100dvh' } });
  const cleanup = () => selector?.destroy();

  const bar = (left, title, right) => h('div', { class: 'bar' }, left, h('span', { class: 'title', text: title }), right || h('span', { style: { width: '60px' } }));
  const cancel = () => h('a', { class: 'link-btn', href: book ? `#/book/${book.id}` : '#/' }, 'Cancel');

  function stepStart(errorMessage) {
    cleanup();
    const fileInput = (useCamera) => h('input', { type: 'file', accept: 'image/*', capture: useCamera ? 'environment' : null,
      'aria-label': useCamera ? 'Take a photo' : 'Choose a photo', onchange: (ev) => { const f = ev.target.files[0]; if (f) send(f); } });
    const drop = h('div', { class: 'drop wide-only' }, 'Or drop a photo of the page here');
    for (const t of ['dragenter', 'dragover']) drop.addEventListener(t, (ev) => { ev.preventDefault(); drop.classList.add('over'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('over'));
    drop.addEventListener('drop', (ev) => { ev.preventDefault(); drop.classList.remove('over'); const f = ev.dataTransfer.files[0]; if (f) send(f); });
    put(root, 
      bar(cancel(), 'Capture'),
      h('div', { class: 'capture-start' },
        h('span', { class: 'label', text: 'What are you reading?' }),
        h('div', { class: 'book-choice' }, cover(book, 'small'),
          h('div', { class: 'main' }, h('div', { class: 't', text: book.title }), h('div', { class: 'muted', text: book.authors || '' })),
          h('button', { class: 'btn small', type: 'button', onclick: stepPickBook }, 'Change')),
        errorMessage ? h('div', { class: 'error', role: 'alert', text: errorMessage }) : null,
        coarse()
          ? [h('label', { class: 'btn primary big file-btn' }, icon('camera', 20), 'Take a photo of the page', fileInput(true)),
            h('label', { class: 'btn big file-btn' }, icon('image', 20), 'Choose from your photos', fileInput(false))]
          : [h('label', { class: 'btn primary big file-btn' }, icon('image', 20), 'Choose a photo of the page', fileInput(false)), drop],
        h('button', { class: 'btn big', type: 'button', onclick: () => stepDetails(null) }, icon('pen', 20), 'Type a quote or a thought'),
        h('p', { class: 'note-line', text: 'Tip: hold the phone straight above the page, the whole page in the frame, and keep your thumb in the margin.' })));
  }

  function stepPickBook() {
    cleanup();
    const q = h('input', { type: 'search', placeholder: 'Find a book', 'aria-label': 'Find a book' });
    const list = h('div');
    const draw = () => {
      const needle = fold(q.value.trim());
      put(list, ...books.filter((b) => !needle || fold(`${b.title} ${b.authors || ''}`).includes(needle)).map((b) =>
        h('button', { type: 'button', class: `pick${b.id === book.id ? ' on' : ''}`, onclick: () => { book = b; prefs.set('captureBook', b.id); stepStart(); } },
          cover(b, 'small'), h('span', { class: 'main' }, h('span', { class: 't', text: b.title }), h('span', { class: 'a', text: b.authors || '' })),
          h('span', { class: 'num muted', text: b.entry_count }))));
    };
    q.addEventListener('input', draw);
    draw();
    put(root, 
      bar(h('button', { class: 'link-btn', type: 'button', onclick: () => stepStart() }, icon('back', 20), 'Back'), 'What are you reading?'),
      h('div', { class: 'pad' }, h('label', { class: 'search' }, icon('search', 16), q),
        h('a', { class: 'btn', href: '#/book/new?then=capture' }, icon('plus'), 'Add a new book')),
      list);
  }

  async function send(file) {
    put(root, bar(cancel(), book.title),
      h('div', { class: 'capture-start' }, h('div', { class: 'status-line', role: 'status' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }),
        'Reading the page… usually 3 to 5 seconds')));
    try {
      const small = await shrinkPhoto(file);
      const form = new FormData();
      form.append('file', small);
      photo = await api('/api/photos', { method: 'POST', form });
      capture.last = { photo, bookId: book.id };
      if (!photo.words.length) { stepStart('No text was found on this photo. Take it again, closer and straight above the page.'); return; }
      range = null;
      stepSelect();
    } catch (err) { if (err.status !== 401) stepStart(err.message); }
  }

  function stepSelect() {
    cleanup();
    const preview = h('p', { class: 'sel-preview empty' });
    const next = h('button', { class: 'btn primary big', type: 'button', disabled: true, onclick: async () => {
      try {
        const sel = await api(`/api/photos/${photo.id}/select`, { method: 'POST', body: { start: range.start, end: range.end } });
        stepDetails(sel.text);
      } catch (err) { toast(err.message); }
    } }, 'Next');
    selector = makeSelector(photo, { start: range?.start, end: range?.end, onChange: (r) => {
      range = r.phase === 'none' ? null : { start: r.start, end: r.end };
      preview.textContent = r.text || 'Tap the first word of the passage, then the last one.';
      preview.classList.toggle('empty', !r.text);
      next.disabled = !range;
      next.textContent = r.phase === 'none' ? 'Next' : `Next · ${plural(r.end - r.start + 1, 'word')}`;
    } });
    put(root, 
      bar(h('button', { class: 'link-btn', type: 'button', onclick: () => stepStart() }, icon('back', 20), 'Retake'), book.title,
        h('button', { class: 'link-btn', type: 'button', onclick: () => stepDetails(null, true) }, 'Type')),
      selector.el,
      h('div', { class: 'sel-sheet' }, preview, nudgeBar(selector), next));
    root.style.height = '100dvh';
  }

  function stepDetails(selectedText, typedWithPhoto) {
    cleanup();
    root.style.height = '';
    const fromPhoto = Boolean(photo && selectedText != null && !typedWithPhoto);
    let kind = 'quote';
    const text = h('textarea', { class: 'textarea', rows: fromPhoto ? 5 : 6, id: 'c-text', value: selectedText || '',
      placeholder: fromPhoto ? '' : 'Type the passage, or your thought' });
    const detected = photo?.detected_page || '';
    const page = h('input', { class: 'input', id: 'c-page', value: detected, inputmode: 'text', style: { width: '96px' }, placeholder: '—' });
    const note = h('textarea', { class: 'textarea', rows: 2, id: 'c-note', placeholder: 'What it makes you think of (optional)' });
    const tagsIn = tagInput([], tags);
    const kindSeg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Kind' });
    const textLabel = h('span');
    const drawKind = () => {
      put(kindSeg, ...['quote', 'thought'].map((k) => h('button', { type: 'button', class: kind === k ? 'on' : '', onclick: () => { kind = k; drawKind(); } },
        k === 'quote' ? 'Quote' : 'Thought')));
      textLabel.textContent = kind === 'quote' ? (fromPhoto ? 'Passage · fix any misread word' : 'Passage') : 'Your thought';
    };
    drawKind();
    const saveBtn = h('button', { class: 'btn primary big', type: 'submit' }, `Save to ${book.title}`);
    const save = async (ev) => {
      ev.preventDefault();
      if (!text.value.trim()) { text.focus(); toast('The passage is empty'); return; }
      saveBtn.disabled = true;
      try {
        const body = { book_id: book.id, kind, text: text.value, page: page.value, note: note.value, tags: tagsIn.value };
        if (fromPhoto) Object.assign(body, { photo_id: photo.id, word_start: range.start, word_end: range.end });
        const e = await api('/api/entries', { method: 'POST', body });
        prefs.set('captureBook', book.id);
        store.changed();
        go(`book/${book.id}`, { fresh: e.id });
        toast('Saved', fromPhoto ? { label: 'Another from this page', run: () => go('capture', { again: 1 }) } : null);
      } catch (err) { saveBtn.disabled = false; toast(err.message); }
    };
    put(root, h('form', { onsubmit: save, style: { display: 'flex', flexDirection: 'column', flex: 1 } },
      bar(fromPhoto ? h('button', { class: 'link-btn', type: 'button', onclick: stepSelect }, icon('back', 20), 'Passage')
        : h('button', { class: 'link-btn', type: 'button', onclick: () => (photo ? stepSelect() : stepStart()) }, icon('back', 20), 'Back'), book.title),
      h('div', { class: 'details', style: { flex: 1 } },
        fromPhoto ? null : kindSeg,
        h('label', { class: 'field', for: 'c-text' }, textLabel, text),
        h('div', { class: 'two' },
          h('label', { class: 'field', for: 'c-page' }, h('span', { text: 'Page' }), page),
          detected ? h('span', { class: 'found' }, icon('check', 16), 'Read from the photo; edit if wrong') : null),
        h('label', { class: 'field', for: 'c-note' }, h('span', { text: 'Your note' }), note),
        tagsIn.el),
      h('div', { class: 'save-bar' }, saveBtn)));
    if (!fromPhoto) setTimeout(() => text.focus(), 50);
  }

  if (params.get('again') && capture.last) {
    photo = capture.last.photo;
    book = books.find((b) => b.id === capture.last.bookId) || book;
    stepSelect();
  } else {
    stepStart();
  }
  return { el: root, bare: true, cleanup };
}

async function viewBookForm({ args: [id], params }) {
  const editing = id != null;
  const book = editing ? await api(`/api/books/${id}`) : {};
  const field = (key, label, attrs = {}) => {
    const input = h('input', { class: 'input', id: `b-${key}`, value: book[key] ?? '', ...attrs });
    return { input, el: h('label', { class: 'field', for: `b-${key}`, style: attrs.wrapStyle }, h('span', { text: label }), input) };
  };
  const isbn = field('isbn', 'ISBN (back cover)', { inputmode: 'numeric', autocomplete: 'off', placeholder: '978…' });
  const title = field('title', 'Title', { required: true, autocapitalize: 'sentences' });
  const subtitle = field('subtitle', 'Subtitle');
  const authors = field('authors', 'Author(s)', { placeholder: 'e.g. Henri Poincaré' });
  const translator = field('translator', 'Translator');
  const publisher = field('publisher', 'Publisher');
  const edition = field('edition', 'Edition');
  const year = field('year', 'Year', { inputmode: 'numeric' });
  const language = h('select', { class: 'select', id: 'b-language' },
    h('option', { value: '' }, '—'), h('option', { value: 'fr' }, 'French'), h('option', { value: 'en' }, 'English'), h('option', { value: 'other' }, 'Other'));
  language.value = ['fr', 'en', ''].includes(book.language || '') ? (book.language || '') : 'other';
  const status = h('select', { class: 'select', id: 'b-status' },
    h('option', { value: 'reading' }, 'Reading'), h('option', { value: 'paused' }, 'Paused'), h('option', { value: 'finished' }, 'Finished'));
  status.value = book.status || 'reading';
  const msg = h('div', { class: 'note-line', role: 'status' });

  const lookupBtn = h('button', { class: 'btn', type: 'button', onclick: async () => {
    msg.textContent = 'Looking up…';
    try {
      const found = await api(`/api/lookup/isbn/${encodeURIComponent(isbn.input.value)}`);
      for (const [k, f] of Object.entries({ title, subtitle, authors, publisher, year })) if (found[k]) f.input.value = found[k];
      if (found.language) language.value = ['fr', 'en'].includes(found.language) ? found.language : 'other';
      msg.textContent = `Found on ${found.source}. Check the details, then save.`;
    } catch (err) { msg.textContent = err.message; }
  } }, 'Look up');

  const payload = () => {
    const y = year.input.value.trim();
    const lang = language.value === 'other' ? (book.language && !['fr', 'en'].includes(book.language) ? book.language : null) : language.value || null;
    return { title: title.input.value, subtitle: subtitle.input.value, authors: authors.input.value, translator: translator.input.value,
      publisher: publisher.input.value, edition: edition.input.value, year: y ? Number(y) : null, isbn: isbn.input.value,
      language: lang, status: status.value };
  };
  const save = async (ev) => {
    ev.preventDefault();
    msg.textContent = '';
    const body = payload();
    if (body.year != null && !Number.isInteger(body.year)) { msg.textContent = 'The year must be a number'; return; }
    try {
      if (editing) {
        await api(`/api/books/${id}`, { method: 'PATCH', body });
        store.changed();
        toast('Book saved');
        go(`book/${id}`);
      } else {
        const b = await api('/api/books', { method: 'POST', body });
        store.changed();
        prefs.set('captureBook', b.id);
        if (params.get('then') === 'capture') go('capture', { book: b.id });
        else go(`book/${b.id}`, b.cover_pending ? { cover: 1 } : null);
      }
    } catch (err) { msg.textContent = err.message; }
  };

  let coverBox = null;
  if (editing) {
    const coverSlot = h('span', {}, cover(book, 'large'));
    const coverMsg = h('div', { class: 'note-line', role: 'status' });
    const own = h('input', { type: 'file', accept: 'image/*', 'aria-label': 'Use my own photo of the cover', onchange: async (ev) => {
      const f = ev.target.files[0];
      if (!f) return;
      coverMsg.textContent = 'Sending…';
      try {
        const form = new FormData();
        form.append('file', await shrinkPhoto(f));
        const b = await api(`/api/books/${id}/cover`, { method: 'POST', form });
        put(coverSlot, cover(b, 'large'));
        coverMsg.textContent = 'Cover saved.';
        store.changed();
      } catch (err) { coverMsg.textContent = err.message; }
    } });
    coverBox = h('div', { class: 'cover-box' }, coverSlot, h('div', { class: 'info' },
      h('span', { class: 'label', text: 'Cover' }),
      h('button', { class: 'btn', type: 'button', onclick: async () => {
        coverMsg.textContent = 'Looking for a cover online…';
        try {
          const b = await api(`/api/books/${id}/cover/fetch`, { method: 'POST' });
          put(coverSlot, cover(b, 'large'));
          coverMsg.textContent = 'Cover found.';
          store.changed();
        } catch (err) { coverMsg.textContent = err.message; }
      } }, 'Find a cover online'),
      h('label', { class: 'btn file-btn' }, 'Use my own photo', own), coverMsg));
  }

  const remove = async () => {
    const n = book.entry_count;
    if (!confirm(n ? `Delete “${book.title}” and its ${plural(n, 'entry').replace('entrys', 'entries')}? This cannot be undone.` : `Delete “${book.title}”?`)) return;
    try {
      await api(`/api/books/${id}`, { method: 'DELETE' });
      store.changed();
      toast('Book deleted');
      go('');
    } catch (err) { toast(err.message); }
  };

  const el = h('form', { onsubmit: save },
    h('div', { class: 'bar' }, h('a', { class: 'link-btn', href: editing ? `#/book/${id}` : (params.get('then') === 'capture' ? '#/capture' : '#/') }, 'Cancel'),
      h('span', { class: 'title', text: editing ? 'Edit book' : 'Add a book' }),
      h('button', { class: 'link-btn', type: 'submit', style: { fontWeight: 600 } }, 'Save')),
    h('div', { class: 'details' },
      coverBox,
      h('div', { class: 'two' }, h('div', { style: { flex: 1, minWidth: 0 } }, isbn.el), lookupBtn),
      editing ? null : h('p', { class: 'note-line', text: 'With an ISBN, the details and the cover are filled in for you. Without one, type the title and author; the cover is searched by title.' }),
      title.el, subtitle.el, authors.el,
      h('div', { class: 'two' }, h('div', { style: { flex: 1 } }, publisher.el), h('div', { style: { width: '96px' } }, year.el)),
      h('div', { class: 'two' }, h('div', { style: { flex: 1 } }, edition.el), h('div', { style: { flex: 1 } }, translator.el)),
      h('div', { class: 'two' },
        h('label', { class: 'field', for: 'b-language', style: { flex: 1 } }, h('span', { text: 'Language' }), language),
        h('label', { class: 'field', for: 'b-status', style: { flex: 1 } }, h('span', { text: 'Status' }), status)),
      msg,
      h('button', { class: 'btn primary big', type: 'submit' }, editing ? 'Save' : 'Add the book'),
      editing ? h('button', { class: 'btn danger', type: 'button', onclick: remove, style: { alignSelf: 'flex-start' } }, 'Delete this book') : null));
  if (!editing) setTimeout(() => isbn.input.focus(), 50);
  return { el, bare: !isWide(), nav: 'books' };
}

async function viewSettings() {
  const health = await api('/api/health');
  const backupMsg = h('span', { class: 'note-line', role: 'status' });
  const rows = [
    ['App', health.version],
    ['Text recognition', health.tesseract ? `Tesseract ${health.tesseract} · ${health.ocr_languages.join(', ')}` : 'missing'],
    ['Page straightening', health.straighten_pages ? 'on' : 'off'],
    ['Online book lookups', health.lookups_enabled ? 'on' : 'off'],
  ];
  const el = h('div', {},
    h('header', { class: 'top' }, h('div', { class: 'top-row' }, h('h1', {}, 'Settings'))),
    h('div', { class: 'pad' },
      h('div', { class: 'kv', style: { flexDirection: 'column', gap: '6px' } }, rows.map(([k, v]) => h('span', {}, `${k}: `, h('b', { text: v })))),
      h('div', { class: 'row-btns' },
        h('button', { class: 'btn', type: 'button', onclick: async () => {
          try { const r = await api('/api/backup', { method: 'POST' }); backupMsg.textContent = `Saved ${r.file} in data/backups.`; } catch (err) { backupMsg.textContent = err.message; }
        } }, 'Back up now'),
        h('a', { class: 'btn', href: '/docs', target: '_blank', rel: 'noopener' }, 'API documentation'),
        h('button', { class: 'btn danger', type: 'button', onclick: async () => {
          await api('/api/logout', { method: 'POST' }).catch(() => null);
          store.changed();
          go('login');
        } }, 'Log out')),
      backupMsg,
      h('p', { class: 'note-line', text: 'On iPhone: in Safari, tap Share, then Add to Home Screen, to open Marginote like an app.' })));
  return { el, nav: 'settings' };
}

// ---------- shell and navigation ----------

const sideTags = h('div', { class: 'chips' });
function refreshSide() {
  if (!isWide() || !document.body.contains(sideTags)) return;
  store.getTags().then((tags) => {
    put(sideTags, ...tags.slice(0, 16).map((t) => h('a', { class: 'chip', href: `#/quotes?tag=${encodeURIComponent(t.name)}` },
      t.name, h('span', { class: 'n', text: t.count }))));
  }).catch(() => {});
}

function buildShell() {
  const link = (nav, href, label) => h('a', { href, dataset: { nav } }, label);
  const side = h('aside', { class: 'side' },
    h('a', { href: '#/', class: 'brand', style: { color: 'inherit', textDecoration: 'none' } }, 'Marginote ', h('small', {}, '/ index')),
    h('a', { class: 'btn primary', href: '#/capture' }, '+ Capture'),
    h('nav', { 'aria-label': 'Main' }, link('books', '#/', 'Books'), link('quotes', '#/quotes', 'Quotes'), link('tags', '#/tags', 'Tags'),
      link('settings', '#/settings', 'Settings')),
    h('div', { style: { display: 'flex', flexDirection: 'column', gap: '8px' } }, h('h2', { class: 'section-title', text: 'Tags' }), sideTags));
  const tabbar = h('nav', { class: 'tabbar', 'aria-label': 'Main' },
    link('books', '#/', 'Books'), link('quotes', '#/quotes', 'Quotes'), link('tags', '#/tags', 'Tags'),
    h('span', { class: 'tab-capture' }, h('a', { class: 'btn primary', href: '#/capture', style: { height: '40px', padding: '0 12px', fontSize: '13px' } }, '+ Capture')));
  const main = h('main', { class: 'view', id: 'view' });
  put(document.body, h('div', { class: 'app', id: 'app' }, side, main, tabbar));
}

const ROUTES = [
  [/^$/, viewBooks],
  [/^login$/, viewLogin],
  [/^book\/new$/, viewBookForm],
  [/^book\/(\d+)$/, viewBook],
  [/^book\/(\d+)\/edit$/, viewBookForm],
  [/^quotes$/, viewQuotes],
  [/^tags$/, viewTags],
  [/^entry\/(\d+)$/, viewEntry],
  [/^entry\/(\d+)\/edit$/, viewEntryEdit],
  [/^entry\/(\d+)\/photo$/, viewEntryPhoto],
  [/^capture$/, viewCapture],
  [/^settings$/, viewSettings],
];

function go(path, params) {
  const qs = params ? '?' + new URLSearchParams(params) : '';
  const target = `#/${path}${qs}`;
  if (location.hash === target) render();
  else location.hash = target;
}

let renderCount = 0;
let cleanupCurrent = null;
async function render() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, qs] = raw.split('?');
  const params = new URLSearchParams(qs || '');
  const n = ++renderCount;
  const view = document.getElementById('view');
  const route = ROUTES.find(([re]) => re.test(path));
  if (!route) { go(''); return; }
  const args = path.match(route[0]).slice(1);
  try {
    const result = await route[1]({ params, args: args.length ? args : [undefined] });
    if (n !== renderCount || !result) return;
    cleanupCurrent?.();
    cleanupCurrent = result.cleanup || null;
    document.getElementById('app').classList.toggle('bare', Boolean(result.bare));
    for (const a of document.querySelectorAll('[data-nav]')) a.classList.toggle('on', a.dataset.nav === result.nav);
    put(view, result.el);
    if (!params.get('fresh')) window.scrollTo(0, 0);
  } catch (err) {
    if (n !== renderCount || err.status === 401) return;
    put(view, errorBox(err, render));
  }
}

window.addEventListener('hashchange', () => { sessionStorage.setItem('marginote.nav', '1'); render(); });
window.matchMedia('(min-width: 960px)').addEventListener('change', () => { refreshSide(); render(); });

(async function start() {
  buildShell();
  try {
    const me = await api('/api/me');
    if (!me.logged_in) { sessionStorage.setItem('marginote.after', location.hash); location.replace('#/login'); }
    else refreshSide();
  } catch { /* shown by render */ }
  render();
})();
