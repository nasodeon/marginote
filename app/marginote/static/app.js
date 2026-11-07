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
  camera: 'M4 8h3l2-3h6l2 3h3v11H4zM12 10.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7z',
  image: 'M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15.5 8.5h.01',
  pen: 'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  zoomIn: 'M10.5 4a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13zM20 20l-4.7-4.7M10.5 8v5M8 10.5h5',
  zoomOut: 'M10.5 4a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13zM20 20l-4.7-4.7M8 10.5h5',
};
function icon(name, size = 18) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  for (const [k, v] of Object.entries({ width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
    'stroke-width': name === 'more' ? 3 : 1.6, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' })) {
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
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}
function fullDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}
function dateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return `${fullDate(iso)}, ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
function size(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}
const fold = (s) => (s || '').normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
const WORDS = { entry: 'entries', copy: 'copies' };
const plural = (n, word) => `${n} ${n === 1 ? word : WORDS[word] || word + 's'}`;
const isWide = () => window.matchMedia('(min-width: 960px)').matches;
const coarse = () => window.matchMedia('(pointer: coarse)').matches;
const kindName = (kind) => (kind === 'quote' ? 'quote' : 'comment');

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
  changed() { this.books = null; this.tags = null; },
};

function currentBookId(books) {
  const last = prefs.get('captureBook', null);
  if (books.some((b) => b.id === last)) return last;
  return books[0]?.id ?? null;
}

// ---------- shared pieces ----------

function cover(book, size = '') {
  const placeholder = () => {
    const author = (book.authors || '').split(',')[0].trim().split(' ').pop();
    return h('div', { class: `cover ph ${size}`, 'aria-hidden': 'true' }, h('b', { text: book.title }), h('i', { text: author }));
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
  for (const part of String(text).split(/(\u0002[^\u0003]*\u0003)/)) {
    if (part.startsWith('\u0002')) out.push(h('mark', { text: part.slice(1, -1) }));
    else if (part) out.push(part);
  }
  return out;
}

function entryMeta(e, showBook) {
  const bits = [];
  if (showBook) bits.push(h('i', { text: e.book_title }));
  if (e.kind === 'comment') bits.push('comment');
  if (e.note) bits.push('note');
  const out = [];
  bits.forEach((b, k) => { if (k) out.push(' · '); out.push(b); });
  if (e.tags.length) {
    if (out.length) out.push(' · ');
    out.push(h('span', { class: 'tg', text: e.tags.map((t) => '#' + t.replace(/ /g, '-')).join(' ') }));
  }
  return out;
}

function entryRow(e, { showBook = false, fresh = false } = {}) {
  const meta = entryMeta(e, showBook);
  return h('a', { class: `entry-row${e.kind === 'comment' ? ' comment' : ''}${fresh ? ' fresh' : ''}`, href: `#/entry/${e.id}`, id: `e${e.id}` },
    h('span', { class: 'pg', text: e.page || '' }),
    h('div', { class: 'body' },
      h('p', { class: 'txt' }, e.snippet ? withMarks(e.snippet) : e.text),
      meta.length ? h('span', { class: 'meta' }, meta) : null));
}

function entryTable(entries, { showBook = true } = {}) {
  const rows = entries.map((e) => h('tr', { onclick: () => go(`entry/${e.id}`) },
    h('td', { class: 'm', text: e.page || '' }),
    h('td', { class: e.kind === 'comment' ? 'comment' : '' }, e.snippet ? withMarks(e.snippet) : e.text),
    showBook ? h('td', { class: 'it', text: e.book_title }) : null,
    h('td', { class: 'tags', text: e.tags.map((t) => '#' + t.replace(/ /g, '-')).join(' ') }),
    h('td', { class: 'm', text: fullDate(e.created_at) })));
  return h('div', { class: 'table-wrap' },
    h('table', { class: 'grid' },
      h('thead', {}, h('tr', {},
        h('th', { style: { width: '56px' }, text: 'p.' }), h('th', { text: 'entry' }),
        showBook ? h('th', { style: { width: '200px' }, text: 'book' }) : null,
        h('th', { style: { width: '150px' }, text: 'tags' }), h('th', { style: { width: '110px' }, text: 'added' }))),
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

// A confirmation with explicit choices. Resolves to the chosen value, or null if cancelled.
function confirmDialog({ title, text, choices }) {
  return new Promise((resolve) => {
    const dlg = h('dialog', { class: 'confirm', 'aria-labelledby': 'dlg-title' });
    const done = (value) => { dlg.close(); dlg.remove(); resolve(value); };
    put(dlg,
      h('h2', { id: 'dlg-title', text: title }),
      text ? h('p', { text }) : null,
      h('div', { class: 'choices' },
        choices.map((c) => h('button', { type: 'button', class: `btn ${c.danger ? 'danger primary' : ''}`, onclick: () => done(c.value) }, c.label)),
        h('button', { type: 'button', class: 'btn plain', onclick: () => done(null) }, 'Cancel')));
    dlg.addEventListener('cancel', (ev) => { ev.preventDefault(); done(null); });
    document.body.append(dlg);
    dlg.showModal();
  });
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
  const input = h('input', { type: 'text', placeholder: 'add a tag', autocapitalize: 'none', autocomplete: 'off',
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
    put(box, tags.map((t) => h('span', { class: 'chip' }, '#' + t,
      h('button', { type: 'button', 'aria-label': `Remove tag ${t}`, onclick: (ev) => {
        ev.stopPropagation(); tags = tags.filter((x) => x !== t); draw();
      } }, '×'))), input);
    drawSuggestions();
  }
  function drawSuggestions() {
    const q = fold(input.value);
    const list = allTags.filter((t) => !tags.includes(t.name) && (!q || fold(t.name).includes(q))).slice(0, 8);
    put(sugg, list.map((t) => h('button', {
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
    el: h('div', { class: 'field' }, h('span', { text: 'tags' }), box, sugg),
    get value() { if (input.value.trim()) { add(input.value); input.value = ''; } return tags; },
  };
}

function kindSwitch(get, set, after) {
  const seg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Kind' });
  const draw = () => put(seg, ['quote', 'comment'].map((k) => h('button', { type: 'button', class: get() === k ? 'on' : '',
    'aria-pressed': get() === k ? 'true' : 'false', onclick: () => { set(k); draw(); after?.(); } }, k === 'quote' ? 'Quote' : 'Comment')));
  draw();
  return seg;
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

  const photoBtn = h('button', { type: 'button', onclick: () => setMode('photo') }, 'Photo');
  const textBtn = h('button', { type: 'button', onclick: () => setMode('text') }, 'Large text');
  const zoomBtn = h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Zoom in', onclick: toggleZoom }, icon('zoomIn', 22));
  const modes = h('div', { class: 'sel-modes' }, h('div', { class: 'seg', role: 'group', 'aria-label': 'Select on' }, photoBtn, textBtn), zoomBtn);

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
    put(zoomBtn, icon(zoom === 1 ? 'zoomIn' : 'zoomOut', 22));
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
  return h('div', { class: 'nudges' }, pair('start', 'start'), pair('end', 'end'));
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
  h('h1', {}, 'Marginote'),
  h('input', { type: 'text', name: 'username', value: 'marginote', autocomplete: 'username', hidden: true, 'aria-hidden': 'true' }),
  h('label', { class: 'field', for: 'pw' }, h('span', { text: 'password' }), pw),
  h('button', { class: 'btn primary big', type: 'submit' }, 'Log in'), msg);
  setTimeout(() => pw.focus(), 50);
  return { el: form, bare: true };
}

async function viewBooks({ params }) {
  const [books, inbox] = await Promise.all([store.getBooks(true), api('/api/photos')]);   // fresh: covers found later show up
  let sort = prefs.get('booksSort', 'last_entry');
  let subject = prefs.get('booksSubject', '');
  const subjects = [...new Set(books.map((b) => b.subject).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  if (subject && !subjects.includes(subject)) subject = '';
  const SORTS = { last_entry: 'recent first', title: 'by title', added: 'by date added' };

  const q = h('input', { type: 'search', placeholder: 'Search', 'aria-label': 'Search books and quotes',
    value: params.get('q') || '', enterkeyhint: 'search' });
  const sortSel = h('select', { class: 'filter', 'aria-label': 'Sort by', onchange: () => { sort = sortSel.value; prefs.set('booksSort', sort); draw(); } },
    Object.entries(SORTS).map(([k, label]) => h('option', { value: k }, label)));
  sortSel.value = sort;
  const subjectSel = subjects.length ? h('select', { class: 'filter', 'aria-label': 'Subject', onchange: () => {
    subject = subjectSel.value; prefs.set('booksSubject', subject); draw();
  } }, h('option', { value: '' }, 'all subjects'), subjects.map((s) => h('option', { value: s }, s))) : null;
  if (subjectSel) subjectSel.value = subject;
  const list = h('div');
  const found = h('section');

  function draw() {
    const needle = fold(q.value.trim());
    let shown = books.filter((b) => (!subject || b.subject === subject)
      && (!needle || fold(`${b.title} ${b.subtitle || ''} ${b.authors || ''} ${b.subject || ''}`).includes(needle)));
    const key = { last_entry: (b) => b.last_entry_at || b.created_at, added: (b) => b.created_at }[sort];
    shown = [...shown].sort(sort === 'title' ? (a, b) => a.title.localeCompare(b.title) : (a, b) => (key(a) < key(b) ? 1 : -1));
    if (!books.length) {
      put(list, h('div', { class: 'empty' }, 'No books yet.', h('a', { class: 'btn primary', href: '#/book/new' }, 'Add a book')));
      return;
    }
    put(list,
      shown.length ? h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'title' }),
        h('span', { class: 'w40', style: { textAlign: 'right' }, text: 'qts' }), h('span', { class: 'w64', style: { textAlign: 'right' }, text: 'last' })) : null,
      shown.map((b) => h('a', { class: 'book-row', href: `#/book/${b.id}` },
        cover(b, 'small'),
        h('span', { class: 'main' },
          h('span', { class: 't', text: b.title }),
          h('span', { class: 'a' }, b.authors || '', b.subject ? [b.authors ? ' · ' : '', h('i', { text: b.subject })] : null)),
        h('span', { class: 'num w40', text: b.entry_count }),
        h('span', { class: 'num w64 muted', text: b.last_entry_at ? shortDate(b.last_entry_at) : '' }))),
      shown.length ? h('div', { class: 'list-end' }) : null);
  }

  const searchQuotes = debounce(async () => {
    const text = q.value.trim();
    history.replaceState(null, '', text ? `#/?q=${encodeURIComponent(text)}` : '#/');
    if (text.length < 2) { put(found); return; }
    try {
      const hits = await api(`/api/search?q=${encodeURIComponent(text)}&limit=30`);
      if (q.value.trim() !== text) return;
      put(found, hits.length
        ? [h('div', { class: 'colhead' }, h('span', { text: 'quotes' }), h('span', { style: { flex: 1, textAlign: 'right' }, text: hits.length })),
          hits.map((e) => entryRow(e, { showBook: true })), h('div', { class: 'list-end' })]
        : h('div', { class: 'empty', text: 'No quote contains these words.' }));
    } catch (err) { put(found, errorBox(err)); }
  }, 250);
  q.addEventListener('input', () => { draw(); searchQuotes(); });

  draw();
  if (q.value) searchQuotes();
  const el = h('div', {},
    h('header', { class: 'top' },
      h('div', { class: 'top-row' },
        h('h1', {}, 'Books', h('span', { class: 'count', text: books.length })),
        h('div', { style: { display: 'flex' } },
          h('a', { class: 'icon-btn narrow-only', href: '#/settings', 'aria-label': 'Settings' }, icon('more', 22)),
          h('a', { class: 'icon-btn', href: '#/book/new', 'aria-label': 'Add a book' }, icon('plus', 22)))),
      inbox.length ? h('a', { class: 'filter', href: '#/inbox', style: { color: 'var(--ink)', alignSelf: 'flex-start' } },
        `inbox · ${plural(inbox.length, 'page')} to sort`) : null,
      h('label', { class: 'search' }, icon('search', 16), q),
      books.length ? h('div', { class: 'tools half' }, sortSel, subjectSel) : null),
    list, found);
  return { el, nav: 'books' };
}

async function deleteEntries(ids) {
  await api('/api/entries/delete', { method: 'POST', body: { ids } });
  store.changed();
}

async function viewBook({ args: [id], params }) {
  const order = prefs.get('bookOrder', 'page');
  const [book, entries] = await Promise.all([api(`/api/books/${id}`), api(`/api/books/${id}/entries?order=${order}`)]);
  let tag = params.get('tag') || '';
  let selecting = false;
  const chosen = new Set();
  const fresh = Number(params.get('fresh')) || null;
  const bookTags = [...new Set(entries.flatMap((e) => e.tags))].sort((a, b) => a.localeCompare(b));
  const q = h('input', { type: 'search', placeholder: 'Search in this book', 'aria-label': 'Search in this book', enterkeyhint: 'search' });
  const list = h('div');
  const selectBar = h('div', { class: 'select-bar', hidden: true });
  const tagSelect = h('select', { class: 'filter', 'aria-label': 'Tag', onchange: () => { tag = tagSelect.value; draw(); } },
    h('option', { value: '' }, 'all tags'), bookTags.map((t) => h('option', { value: t }, '#' + t)));
  tagSelect.value = tag;
  const flip = () => { prefs.set('bookOrder', order === 'page' ? 'date' : 'page'); render(); };
  const orderBtn = h('button', { type: 'button', class: 'filter', onclick: flip }, order === 'page' ? 'by page' : 'by date');

  const shownEntries = () => {
    const needle = fold(q.value.trim());
    return entries.filter((e) => (!tag || e.tags.includes(tag))
      && (!needle || fold(`${e.text} ${e.note || ''} ${e.tags.join(' ')} ${e.page || ''}`).includes(needle)));
  };

  function drawSelectBar() {
    const shown = shownEntries();
    put(selectBar,
      h('span', { class: 'grow', text: chosen.size ? `${chosen.size} selected` : 'Tap the entries to delete' }),
      h('button', { type: 'button', class: 'btn small', onclick: () => {
        const all = shown.every((e) => chosen.has(e.id));
        shown.forEach((e) => (all ? chosen.delete(e.id) : chosen.add(e.id)));
        draw();
      } }, shown.length && shown.every((e) => chosen.has(e.id)) ? 'None' : 'All'),
      h('button', { type: 'button', class: 'btn small danger primary', disabled: !chosen.size, onclick: async () => {
        const n = chosen.size;
        const ok = await confirmDialog({ title: `Delete ${plural(n, 'entry')}?`, text: 'This cannot be undone.',
          choices: [{ label: `Delete ${plural(n, 'entry')}`, value: true, danger: true }] });
        if (!ok) return;
        try { await deleteEntries([...chosen]); toast(`${plural(n, 'entry')} deleted`); render(); } catch (err) { toast(err.message); }
      } }, 'Delete'),
      h('button', { type: 'button', class: 'btn small plain', onclick: () => { selecting = false; chosen.clear(); draw(); } }, 'Done'));
  }

  function draw() {
    const shown = shownEntries();
    selectBar.hidden = !selecting;
    if (selecting) {
      drawSelectBar();
      put(list, h('div', {}, shown.map((e) => {
        const box = h('input', { type: 'checkbox', checked: chosen.has(e.id), 'aria-label': 'Select', onchange: () => {
          if (box.checked) chosen.add(e.id); else chosen.delete(e.id);
          drawSelectBar();
        } });
        return h('label', { class: `entry-row${e.kind === 'comment' ? ' comment' : ''}` }, h('span', { class: 'check' }, box),
          h('div', { class: 'body' }, h('p', { class: 'txt' }, e.text), h('span', { class: 'meta', text: e.page ? `p. ${e.page}` : '' })));
      })), h('div', { class: 'list-end' }));
      return;
    }
    put(list,
      shown.length ? (isWide() ? entryTable(shown, { showBook: false })
        : [h('div', { class: 'colhead' }, h('span', { class: 'w36', text: 'p.' }), h('span', { style: { flex: 1 }, text: 'entry' })),
          shown.map((e) => entryRow(e, { fresh: e.id === fresh })), h('div', { class: 'list-end' })]) : null,
      !shown.length && entries.length ? h('div', { class: 'empty', text: 'Nothing matches.' }) : null,
      !entries.length ? h('div', { class: 'empty' }, h('a', { class: 'btn primary', href: `#/capture?book=${book.id}` }, 'Capture a quote')) : null);
  }
  q.addEventListener('input', draw);

  const removeBook = async () => {
    const n = entries.length;
    const choice = await confirmDialog({
      title: `Delete “${book.title}”?`,
      text: n ? `It has ${plural(n, 'entry')}. This cannot be undone.` : 'This cannot be undone.',
      choices: [
        { label: n ? `Delete the book and its ${plural(n, 'entry')}` : 'Delete the book', value: 'book', danger: true },
        n ? { label: `Delete only its ${plural(n, 'entry')}`, value: 'entries' } : null,
      ].filter(Boolean),
    });
    try {
      if (choice === 'book') {
        await api(`/api/books/${book.id}`, { method: 'DELETE' });
        store.changed();
        toast('Book deleted');
        go('');
      } else if (choice === 'entries') {
        await deleteEntries(entries.map((e) => e.id));
        toast(`${plural(n, 'entry')} deleted`);
        render();
      }
    } catch (err) { toast(err.message); }
  };

  draw();
  if (fresh) setTimeout(() => document.getElementById(`e${fresh}`)?.scrollIntoView({ block: 'center' }), 50);

  const coverEl = h('span', {}, cover(book, isWide() ? 'large' : ''));
  if (params.get('cover') === '1' && !book.has_cover) {
    (async () => {   // the cover is searched in the background: check for up to a minute
      for (let k = 0; k < 20; k++) {
        await new Promise((r) => setTimeout(r, 3000));
        if (!coverEl.isConnected) return;
        const b = await api(`/api/books/${id}`).catch(() => null);
        if (b?.has_cover) { put(coverEl, cover(b, isWide() ? 'large' : '')); store.changed(); return; }
      }
    })();
  }
  const details = [book.publisher, book.year, book.edition, book.translator ? `transl. ${book.translator}` : null].filter(Boolean).join(', ');
  const counts = [plural(book.quote_count, 'quote'), book.comment_count ? plural(book.comment_count, 'comment') : null,
    bookTags.length ? plural(bookTags.length, 'tag') : null].filter(Boolean).join(' · ');
  const el = h('div', {},
    h('div', { class: 'bar' }, backLink('Books', ''), h('a', { class: 'link-btn', href: `#/book/${id}/edit` }, 'Edit')),
    h('header', { class: 'top', style: { paddingTop: '6px' } },
      h('div', { class: 'book-head' }, coverEl,
        h('div', { class: 'info' },
          h('h1', { text: book.title }),
          book.subtitle ? h('span', { class: 'it', text: book.subtitle }) : null,
          book.authors ? h('span', { class: 'by', text: book.authors }) : null,
          details || book.subject ? h('span', { class: 'meta' }, details, details && book.subject ? ' · ' : '', book.subject ? h('i', { text: book.subject }) : null) : null,
          h('span', { class: 'counts', text: counts }),
          h('div', { class: 'actions' },
            h('a', { class: 'btn primary small', href: `#/capture?book=${book.id}` }, '+ Quote'),
            entries.length ? h('a', { class: 'btn small', href: `/api/books/${book.id}/export.md`, download: '' }, 'Export') : null,
            entries.length ? h('button', { class: 'btn small', type: 'button', onclick: () => { selecting = true; draw(); } }, 'Select') : null))),
      entries.length ? h('label', { class: 'search' }, icon('search', 16), q) : null,
      entries.length ? h('div', { class: 'tools' }, orderBtn, bookTags.length ? tagSelect : null) : null),
    list,
    selectBar,
    h('div', { class: 'pad' }, h('button', { class: 'btn small danger', type: 'button', style: { alignSelf: 'flex-start' }, onclick: removeBook }, 'Delete this book…')));
  return { el, nav: 'books' };
}

async function viewQuotes({ params }) {
  const [books, tags] = await Promise.all([store.getBooks(), store.getTags()]);
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
  const q = h('input', { type: 'search', placeholder: 'Search', 'aria-label': 'Search quotes', value: f.q, enterkeyhint: 'search' });
  q.addEventListener('input', debounce(() => setFilter('q', q.value.trim()), 400));
  const select = (key, label, options) => {
    const s = h('select', { class: 'filter', 'aria-label': label, onchange: () => setFilter(key, s.value) }, options);
    s.value = f[key];
    return s;
  };
  const filters = h('div', { class: 'tools' },
    select('book', 'Book', [h('option', { value: '' }, 'all books'), books.map((b) => h('option', { value: String(b.id) }, b.title))]),
    tags.length ? select('tag', 'Tag', [h('option', { value: '' }, 'all tags'), tags.map((t) => h('option', { value: t.name }, `#${t.name} (${t.count})`))]) : null,
    select('kind', 'Type', [h('option', { value: '' }, 'all types'), h('option', { value: 'quote' }, 'quotes'), h('option', { value: 'comment' }, 'comments')]),
    f.tag || f.book || f.kind || f.q ? h('a', { class: 'filter', href: '#/quotes' }, 'clear') : null);

  const list = h('div');
  function draw() {
    put(list,
      entries.length ? (isWide() ? entryTable(entries) : [h('div', { class: 'colhead' }, h('span', { class: 'w36', text: 'p.' }), h('span', { text: 'entry' })),
        entries.map((e) => entryRow(e, { showBook: !f.book })), h('div', { class: 'list-end' })]) : null,
      entries.length ? null : h('div', { class: 'empty', text: f.q || f.tag || f.book || f.kind ? 'Nothing matches.' : 'No quotes yet.' }),
      more ? h('div', { class: 'pad' }, h('button', { class: 'btn', type: 'button', onclick: async () => { offset += PAGE; await load(true); draw(); } }, 'Show more')) : null);
  }
  draw();
  const el = h('div', {},
    h('header', { class: 'top' },
      h('div', { class: 'top-row' }, h('h1', {}, 'Quotes', h('span', { class: 'count', text: entries.length + (more ? '+' : '') }))),
      h('label', { class: 'search' }, icon('search', 16), q), filters),
    list);
  if (f.q) setTimeout(() => { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 30);
  return { el, nav: 'quotes' };
}

async function viewTags() {
  const tags = await store.getTags(true);
  let byName = prefs.get('tagsByName', false);
  const list = h('div');
  const toggle = h('button', { class: 'filter', type: 'button', onclick: () => { byName = !byName; prefs.set('tagsByName', byName); draw(); } });
  function draw() {
    toggle.textContent = byName ? 'sorted by name' : 'sorted by use';
    const shown = [...tags].sort(byName ? (a, b) => a.name.localeCompare(b.name) : (a, b) => b.count - a.count);
    put(list,
      tags.length ? h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'tag' }), h('span', { text: 'entries' })) : null,
      shown.map((t) => h('a', { class: 'pick', href: `#/quotes?tag=${encodeURIComponent(t.name)}` },
        h('span', { class: 'main' }, h('span', { class: 't tt', text: '#' + t.name })),
        h('span', { class: 'num muted', text: t.count }))),
      tags.length ? h('div', { class: 'list-end' }) : h('div', { class: 'empty', text: 'No tags yet.' }));
  }
  draw();
  return {
    el: h('div', {}, h('header', { class: 'top' }, h('div', { class: 'top-row' }, h('h1', {}, 'Tags', h('span', { class: 'count', text: tags.length }))),
      tags.length ? h('div', { class: 'tools' }, toggle) : null), list),
    nav: 'tags',
  };
}

async function viewEntry({ args: [id] }) {
  const e = await api(`/api/entries/${id}`);
  const book = await api(`/api/books/${e.book_id}`);
  const del = async () => {
    const ok = await confirmDialog({ title: `Delete this ${kindName(e.kind)}?`, text: 'This cannot be undone.',
      choices: [{ label: `Delete the ${kindName(e.kind)}`, value: true, danger: true }] });
    if (!ok) return;
    try {
      await deleteEntries([e.id]);
      toast(`${e.kind === 'quote' ? 'Quote' : 'Comment'} deleted`);
      go(`book/${e.book_id}`);
    } catch (err) { toast(err.message); }
  };
  const copy = async () => {
    const cite = [book.authors, book.title].filter(Boolean).join(', ') + (e.page ? `, p. ${e.page}` : '');
    try { await navigator.clipboard.writeText(`${e.text}\n— ${cite}`); toast('Copied'); } catch { toast('Copying is not allowed here'); }
  };
  const el = h('div', {},
    h('div', { class: 'bar' }, backLink('Back', `book/${e.book_id}`), h('a', { class: 'link-btn', href: `#/entry/${id}/edit` }, 'Edit')),
    h('article', { class: 'entry-page' },
      h('a', { class: 'book-link', href: `#/book/${book.id}` }, cover(book, 'small'),
        h('span', {}, h('span', { class: 't', text: book.title }), book.authors ? [h('br'), h('span', { class: 'muted', text: book.authors })] : null)),
      h('div', { class: 'kv' }, e.page ? h('span', { text: `p. ${e.page}` }) : null, e.kind === 'comment' ? h('span', { class: 'it', text: 'comment' }) : null,
        h('span', { text: fullDate(e.created_at) })),
      h('p', { class: `quote-env${e.kind === 'comment' ? ' comment-text' : ''}`, lang: book.language || null, text: e.text }),
      e.note ? h('p', { class: 'note-p' }, h('b', { text: 'Note.' }), e.note) : null,
      e.tags.length ? h('div', { class: 'chips' }, e.tags.map((t) => h('a', { class: 'chip', href: `#/quotes?tag=${encodeURIComponent(t)}` }, '#' + t))) : null,
      h('div', { class: 'row-btns' },
        h('a', { class: 'btn small', href: `#/entry/${id}/edit` }, 'Edit'),
        e.photo_id ? h('a', { class: 'btn small', href: `#/entry/${id}/photo` }, 'Photo') : null,
        h('button', { class: 'btn small', type: 'button', onclick: copy }, 'Copy'),
        h('button', { class: 'btn small danger', type: 'button', onclick: del }, 'Delete…'))));
  return { el, nav: 'quotes' };
}

async function viewEntryEdit({ args: [id] }) {
  const [e, books, tags] = await Promise.all([api(`/api/entries/${id}`), store.getBooks(), store.getTags()]);
  let kind = e.kind;
  const text = h('textarea', { class: 'textarea', rows: 6, id: 'f-text', value: e.text });
  const page = h('input', { class: 'input', id: 'f-page', value: e.page || '', inputmode: 'text', style: { width: '90px' } });
  const note = h('textarea', { class: 'textarea', rows: 3, id: 'f-note', value: e.note || '' });
  const bookSel = h('select', { class: 'select', id: 'f-book' }, books.map((b) => h('option', { value: String(b.id) }, b.title)));
  bookSel.value = String(e.book_id);
  const tagsIn = tagInput(e.tags, tags);
  const textLabel = h('span', { text: kind === 'quote' ? 'passage' : 'comment' });
  const kindSeg = kindSwitch(() => kind, (k) => { kind = k; }, () => { textLabel.textContent = kind === 'quote' ? 'passage' : 'comment'; });
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
      h('span', { class: 'title', text: 'Edit' }), h('button', { class: 'link-btn strong', type: 'submit' }, 'Save')),
    h('div', { class: 'details' },
      kindSeg,
      h('label', { class: 'field', for: 'f-text' }, textLabel, text),
      h('div', { class: 'two' }, h('label', { class: 'field', for: 'f-page' }, h('span', { text: 'page' }), page),
        h('label', { class: 'field', for: 'f-book', style: { flex: 1, minWidth: 0 } }, h('span', { text: 'book' }), bookSel)),
      h('label', { class: 'field', for: 'f-note' }, h('span', { text: 'note' }), note),
      tagsIn.el,
      e.photo_id ? h('a', { class: 'btn small', href: `#/entry/${id}/photo`, style: { alignSelf: 'flex-start' } }, 'Change the selection on the photo') : null,
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
    preview.textContent = r.text || 'Tap the first word, then the last.';
    preview.classList.toggle('empty', !r.text);
    saveBtn.disabled = !range || (r.start === e.word_start && r.end === e.word_end);
  } });
  saveBtn.addEventListener('click', async () => {
    const ok = await confirmDialog({ title: 'Use this selection?', text: 'The saved text is replaced by the words selected on the photo.',
      choices: [{ label: 'Replace the text', value: true }] });
    if (!ok) return;
    try {
      await api(`/api/entries/${id}`, { method: 'PATCH', body: { word_start: range.start, word_end: range.end } });
      store.changed();
      toast('Selection saved');
      go(`entry/${id}`);
    } catch (err) { toast(err.message); }
  });
  const el = h('div', { style: { display: 'flex', flexDirection: 'column', height: '100dvh' } },
    h('div', { class: 'bar' }, h('a', { class: 'link-btn', href: `#/entry/${id}` }, icon('back', 20), 'Back'),
      h('span', { class: 'title', text: e.page ? `p. ${e.page}` : '' }), h('span', { style: { width: '60px' } })),
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
      el: h('div', {}, h('div', { class: 'bar' }, backLink('Cancel', ''), h('span', { class: 'title' }), h('span', { style: { width: '60px' } })),
        h('div', { class: 'empty' }, 'Add a book first.', h('a', { class: 'btn primary', href: '#/book/new?then=capture' }, 'Add a book'))),
      bare: true,
    };
  }
  const fromInbox = params.get('photo');
  let photo = null;
  if (fromInbox) {
    photo = await api(`/api/photos/${encodeURIComponent(fromInbox)}`);
    if (photo.status !== 'ready') { toast('This page is still being read'); go('inbox'); return null; }
  }
  const wanted = Number(params.get('book')) || photo?.book_id;
  let book = books.find((b) => b.id === wanted) || books.find((b) => b.id === currentBookId(books));
  const waiting = fromInbox ? [] : await api('/api/photos').catch(() => []);
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
    const drop = h('div', { class: 'drop wide-only' }, 'or drop a photo here');
    for (const t of ['dragenter', 'dragover']) drop.addEventListener(t, (ev) => { ev.preventDefault(); drop.classList.add('over'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('over'));
    drop.addEventListener('drop', (ev) => { ev.preventDefault(); drop.classList.remove('over'); const f = ev.dataTransfer.files[0]; if (f) send(f); });
    put(root,
      bar(cancel(), ''),
      h('div', { class: 'capture-start' },
        h('div', { class: 'book-choice' }, cover(book, 'small'),
          h('div', { class: 'main' }, h('div', { class: 't', text: book.title }), book.authors ? h('div', { class: 'muted', text: book.authors }) : null),
          h('button', { class: 'btn small', type: 'button', onclick: stepPickBook }, 'Change')),
        errorMessage ? h('div', { class: 'error', role: 'alert', text: errorMessage }) : null,
        coarse()
          ? [h('label', { class: 'btn primary big file-btn' }, icon('camera', 20), 'Take a photo', fileInput(true)),
            h('label', { class: 'btn big file-btn' }, icon('image', 20), 'Choose a photo', fileInput(false))]
          : [h('label', { class: 'btn primary big file-btn' }, icon('image', 20), 'Choose a photo', fileInput(false)), drop],
        h('button', { class: 'btn big', type: 'button', onclick: stepLater }, icon('image', 20), 'Several pages, sort later'),
        h('button', { class: 'btn big', type: 'button', onclick: () => stepDetails(null) }, icon('pen', 20), 'Type it'),
        waiting.length ? h('a', { class: 'filter', href: '#/inbox', style: { color: 'var(--ink)' } }, `inbox · ${plural(waiting.length, 'page')} to sort`) : null));
  }

  function stepLater() {
    cleanup();
    const sent = h('div', { class: 'sent' });
    let count = 0;
    const counter = h('p', { class: 'note-line' });
    const queue = [];
    let busy = false;
    async function pump() {
      if (busy) return;
      busy = true;
      while (queue.length) {
        const { file, row } = queue.shift();
        const state = row.querySelector('.state');
        try {
          const form = new FormData();
          form.append('file', await shrinkPhoto(file));
          await api(`/api/photos?later=true&book_id=${book.id}`, { method: 'POST', form });
          state.textContent = 'sent';
          count += 1;
          counter.textContent = `${plural(count, 'page')} sent. They are read on the server; sort them from the inbox.`;
        } catch (err) { state.textContent = err.message; state.classList.add('bad'); }
      }
      busy = false;
    }
    const add = (files) => {
      for (const file of files) {
        const row = h('div', { class: 'sent-row' }, h('img', { src: URL.createObjectURL(file), alt: '' }), h('span', { class: 'state', text: 'sending…' }));
        sent.prepend(row);
        queue.push({ file, row });
      }
      pump();
    };
    const input = (camera) => h('input', { type: 'file', accept: 'image/*', multiple: !camera, capture: camera ? 'environment' : null,
      'aria-label': camera ? 'Take a photo' : 'Choose photos', onchange: (ev) => { add([...ev.target.files]); ev.target.value = ''; } });
    put(root,
      bar(h('a', { class: 'link-btn', href: '#/inbox' }, 'Inbox'), book.title, h('a', { class: 'link-btn strong', href: `#/book/${book.id}` }, 'Done')),
      h('div', { class: 'capture-start' },
        h('div', { class: 'book-choice' }, cover(book, 'small'),
          h('div', { class: 'main' }, h('div', { class: 't', text: book.title }), book.authors ? h('div', { class: 'muted', text: book.authors }) : null)),
        coarse() ? h('label', { class: 'btn primary big file-btn' }, icon('camera', 20), 'Take a photo', input(true)) : null,
        h('label', { class: `btn big file-btn${coarse() ? '' : ' primary'}` }, icon('image', 20), 'Choose photos', input(false)),
        counter, sent));
  }

  function stepPickBook() {
    cleanup();
    const q = h('input', { type: 'search', placeholder: 'Find a book', 'aria-label': 'Find a book' });
    const list = h('div');
    const draw = () => {
      const needle = fold(q.value.trim());
      put(list, books.filter((b) => !needle || fold(`${b.title} ${b.authors || ''}`).includes(needle)).map((b) =>
        h('button', { type: 'button', class: `pick${b.id === book.id ? ' on' : ''}`, onclick: () => { book = b; prefs.set('captureBook', b.id); stepStart(); } },
          cover(b, 'small'), h('span', { class: 'main' }, h('span', { class: 't', text: b.title }), h('span', { class: 'a', text: b.authors || '' })))));
    };
    q.addEventListener('input', draw);
    draw();
    put(root,
      bar(h('button', { class: 'link-btn', type: 'button', onclick: () => stepStart() }, icon('back', 20), 'Back'), 'Book'),
      h('div', { class: 'pad' }, h('label', { class: 'search' }, icon('search', 16), q),
        h('a', { class: 'btn small', href: '#/book/new?then=capture', style: { alignSelf: 'flex-start' } }, '+ New book')),
      list);
  }

  async function send(file) {
    put(root, bar(cancel(), book.title),
      h('div', { class: 'capture-start' }, h('div', { class: 'status-line', role: 'status' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }),
        'Reading the page…')));
    try {
      const small = await shrinkPhoto(file);
      const form = new FormData();
      form.append('file', small);
      photo = await api('/api/photos', { method: 'POST', form });
      capture.last = { photo, bookId: book.id };
      if (!photo.words.length) { stepStart('No text found on this photo. Take it again, closer.'); return; }
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
      preview.textContent = r.text || 'Tap the first word, then the last.';
      preview.classList.toggle('empty', !r.text);
      next.disabled = !range;
      next.textContent = r.phase === 'none' ? 'Next' : `Next · ${plural(r.end - r.start + 1, 'word')}`;
    } });
    put(root,
      bar(fromInbox ? h('a', { class: 'link-btn', href: '#/inbox' }, icon('back', 20), 'Inbox')
        : h('button', { class: 'link-btn', type: 'button', onclick: () => stepStart() }, icon('back', 20), 'Retake'), book.title,
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
    const text = h('textarea', { class: 'textarea', rows: fromPhoto ? 5 : 6, id: 'c-text', value: selectedText || '' });
    const page = h('input', { class: 'input', id: 'c-page', value: photo?.detected_page || '', inputmode: 'text', style: { width: '90px' } });
    const note = h('textarea', { class: 'textarea', rows: 2, id: 'c-note' });
    const tagsIn = tagInput([], tags);
    const bookSel = h('select', { class: 'select', id: 'c-book' }, books.map((b) => h('option', { value: String(b.id) }, b.title)));
    bookSel.value = String(book.id);
    const textLabel = h('span', { text: 'passage' });
    const kindSeg = kindSwitch(() => kind, (k) => { kind = k; }, () => { textLabel.textContent = kind === 'quote' ? 'passage' : 'comment'; });
    const saveBtn = h('button', { class: 'btn primary big', type: 'submit' }, 'Save');
    const save = async (ev) => {
      ev.preventDefault();
      if (!text.value.trim()) { text.focus(); toast('The text is empty'); return; }
      saveBtn.disabled = true;
      try {
        const bookId = Number(bookSel.value);
        const body = { book_id: bookId, kind, text: text.value, page: page.value, note: note.value, tags: tagsIn.value };
        if (fromPhoto) Object.assign(body, { photo_id: photo.id, word_start: range.start, word_end: range.end });
        const e = await api('/api/entries', { method: 'POST', body });
        prefs.set('captureBook', bookId);
        store.changed();
        if (fromInbox) {
          go('inbox');
          toast('Saved', { label: 'Another from this page', run: () => go('capture', { photo: photo.id }) });
        } else {
          go(`book/${bookId}`, { fresh: e.id });
          toast('Saved', fromPhoto ? { label: 'Another from this page', run: () => go('capture', { again: 1 }) } : null);
        }
      } catch (err) { saveBtn.disabled = false; toast(err.message); }
    };
    put(root, h('form', { onsubmit: save, style: { display: 'flex', flexDirection: 'column', flex: 1 } },
      bar(fromPhoto ? h('button', { class: 'link-btn', type: 'button', onclick: stepSelect }, icon('back', 20), 'Passage')
        : h('button', { class: 'link-btn', type: 'button', onclick: () => (photo ? stepSelect() : stepStart()) }, icon('back', 20), 'Back'), book.title),
      h('div', { class: 'details', style: { flex: 1 } },
        fromPhoto ? null : kindSeg,
        h('label', { class: 'field', for: 'c-text' }, textLabel, text),
        h('div', { class: 'two' },
          h('label', { class: 'field', for: 'c-page' }, h('span', { text: 'page' }), page),
          h('label', { class: 'field', for: 'c-book', style: { flex: 1, minWidth: 0 } }, h('span', { text: 'book' }), bookSel)),
        h('label', { class: 'field', for: 'c-note' }, h('span', { text: 'note' }), note),
        tagsIn.el),
      h('div', { class: 'save-bar' }, saveBtn)));
    if (!fromPhoto) setTimeout(() => text.focus(), 50);
  }

  if (fromInbox) {
    stepSelect();
  } else if (params.get('again') && capture.last) {
    photo = capture.last.photo;
    book = books.find((b) => b.id === capture.last.bookId) || book;
    stepSelect();
  } else {
    stepStart();
  }
  return { el: root, bare: true, cleanup };
}

async function viewInbox() {
  const photos = await api('/api/photos');
  const done = async (p) => {
    if (p.entry_count) {
      await api(`/api/photos/${p.id}`, { method: 'PATCH', body: { queued: false } }).catch((err) => toast(err.message));
      render();
      return;
    }
    const ok = await confirmDialog({ title: 'Remove this page?', text: 'No quote was saved from it. The photo is deleted.',
      choices: [{ label: 'Remove the photo', value: true, danger: true }] });
    if (!ok) return;
    await api(`/api/photos/${p.id}`, { method: 'DELETE' }).catch((err) => toast(err.message));
    render();
  };
  const reading = photos.some((p) => p.status === 'reading');
  if (reading) {   // check again until every page is read
    const mark = location.hash;
    setTimeout(() => { if (location.hash === mark) render(); }, 3000);
  }
  const el = h('div', {},
    h('header', { class: 'top' }, h('div', { class: 'top-row' }, h('h1', {}, 'Inbox', h('span', { class: 'count', text: photos.length })))),
    photos.length ? [h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'pages to sort' })),
      photos.map((p) => h('div', { class: 'inbox-row' },
        h('img', { class: 'thumb', src: p.thumb_url, alt: '', loading: 'lazy' }),
        h('div', { class: 'main' },
          h('span', { class: 't', text: p.book_title || 'No book' }),
          h('span', { class: 'a' }, [
            p.detected_page ? `p. ${p.detected_page}` : null,
            p.status === 'reading' ? h('i', { text: 'being read…' }) : null,
            p.status === 'failed' ? h('i', { class: 'bad', text: 'could not be read' }) : null,
            p.entry_count ? plural(p.entry_count, 'quote') + ' saved' : null,
            fullDate(p.created_at),
          ].filter(Boolean).flatMap((x, k) => (k ? [' · ', x] : [x]))),
          h('div', { class: 'actions' },
            p.status === 'ready' ? h('a', { class: 'btn primary small', href: `#/capture?photo=${p.id}` }, 'Sort') : null,
            h('button', { class: 'btn small', type: 'button', onclick: () => done(p) }, p.entry_count ? 'Done' : 'Remove…'))))),
      h('div', { class: 'list-end' })]
      : h('div', { class: 'empty' }, 'Nothing to sort.', h('a', { class: 'btn', href: '#/capture' }, 'Capture')));
  return { el, nav: 'inbox' };
}

async function viewBookForm({ args: [id], params }) {
  const editing = id != null;
  const [book, books] = await Promise.all([editing ? api(`/api/books/${id}`) : {}, store.getBooks()]);
  const field = (key, label, attrs = {}) => {
    const input = h('input', { class: 'input', id: `b-${key}`, value: book[key] ?? '', ...attrs });
    return { input, el: h('label', { class: 'field', for: `b-${key}` }, h('span', { text: label }), input) };
  };
  const isbn = field('isbn', 'isbn', { inputmode: 'numeric', autocomplete: 'off' });
  const title = field('title', 'title', { required: true, autocapitalize: 'sentences' });
  const subtitle = field('subtitle', 'subtitle');
  const authors = field('authors', 'author(s)');
  const subjects = [...new Set(books.map((b) => b.subject).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  const subject = field('subject', 'type or subject', { list: 'subjects', autocomplete: 'off', autocapitalize: 'sentences' });
  const translator = field('translator', 'translator');
  const publisher = field('publisher', 'publisher');
  const edition = field('edition', 'edition');
  const year = field('year', 'year', { inputmode: 'numeric' });
  const language = h('select', { class: 'select', id: 'b-language' },
    h('option', { value: '' }, '—'), h('option', { value: 'fr' }, 'French'), h('option', { value: 'en' }, 'English'), h('option', { value: 'other' }, 'Other'));
  language.value = ['fr', 'en', ''].includes(book.language || '') ? (book.language || '') : 'other';
  const msg = h('div', { class: 'note-line', role: 'status' });

  const lookUp = async (prefix = '') => {
    msg.textContent = `${prefix}Looking up…`;
    try {
      const found = await api(`/api/lookup/isbn/${encodeURIComponent(isbn.input.value)}`);
      for (const [k, f] of Object.entries({ title, subtitle, authors, publisher, year, translator })) if (found[k]) f.input.value = found[k];
      if (found.language) language.value = ['fr', 'en'].includes(found.language) ? found.language : 'other';
      msg.textContent = `${prefix}Found on ${found.source}.`;
    } catch (err) { msg.textContent = prefix + err.message; }
  };
  const lookupBtn = h('button', { class: 'btn small', type: 'button', onclick: () => lookUp() }, 'Look up');
  const backCover = h('input', { type: 'file', accept: 'image/*', capture: 'environment', 'aria-label': 'Photo of the back cover',
    onchange: async (ev) => {
      const f = ev.target.files[0];
      ev.target.value = '';
      if (!f) return;
      msg.textContent = 'Reading the barcode…';
      try {
        const form = new FormData();
        form.append('file', await shrinkPhoto(f));
        const r = await api('/api/lookup/isbn-photo', { method: 'POST', form });
        isbn.input.value = r.isbn;
        await lookUp(r.found_by === 'barcode' ? 'Barcode read. ' : 'ISBN read. ');
      } catch (err) { msg.textContent = err.message; }
    } });
  const scanBtn = h('label', { class: 'btn small file-btn' }, icon('camera', 16), 'Back cover', backCover);

  const payload = () => {
    const y = year.input.value.trim();
    const lang = language.value === 'other' ? (book.language && !['fr', 'en'].includes(book.language) ? book.language : null) : language.value || null;
    return { title: title.input.value, subtitle: subtitle.input.value, authors: authors.input.value, subject: subject.input.value,
      translator: translator.input.value, publisher: publisher.input.value, edition: edition.input.value,
      year: y ? Number(y) : null, isbn: isbn.input.value, language: lang };
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
        toast('Saved');
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
      h('span', { class: 'label', text: 'cover' }),
      h('button', { class: 'btn small', type: 'button', onclick: async () => {
        coverMsg.textContent = 'Looking for a cover…';
        try {
          const b = await api(`/api/books/${id}/cover/fetch`, { method: 'POST' });
          put(coverSlot, cover(b, 'large'));
          coverMsg.textContent = 'Cover found.';
          store.changed();
        } catch (err) { coverMsg.textContent = err.message; }
      } }, 'Find online'),
      h('label', { class: 'btn small file-btn' }, 'Use my photo', own), coverMsg));
  }

  const el = h('form', { onsubmit: save },
    h('datalist', { id: 'subjects' }, subjects.map((s) => h('option', { value: s }))),
    h('div', { class: 'bar' }, h('a', { class: 'link-btn', href: editing ? `#/book/${id}` : (params.get('then') === 'capture' ? '#/capture' : '#/') }, 'Cancel'),
      h('span', { class: 'title', text: editing ? 'Edit book' : 'New book' }),
      h('button', { class: 'link-btn strong', type: 'submit' }, 'Save')),
    h('div', { class: 'details' },
      coverBox,
      h('div', { class: 'two' }, h('div', { style: { flex: 1, minWidth: 0 } }, isbn.el), lookupBtn, scanBtn),
      title.el, subtitle.el, authors.el, subject.el,
      h('div', { class: 'two' }, h('div', { style: { flex: 1 } }, publisher.el), h('div', { style: { width: '90px' } }, year.el)),
      h('div', { class: 'two' }, h('div', { style: { flex: 1 } }, edition.el), h('div', { style: { flex: 1 } }, translator.el)),
      h('label', { class: 'field', for: 'b-language' }, h('span', { text: 'language' }), language),
      msg,
      h('button', { class: 'btn primary big', type: 'submit' }, editing ? 'Save' : 'Add the book')));
  if (!editing) setTimeout(() => isbn.input.focus(), 50);
  return { el, bare: !isWide(), nav: 'books' };
}

async function viewSettings() {
  const [health, backups] = await Promise.all([api('/api/health'), api('/api/backup/status')]);
  const backupMsg = h('span', { class: 'note-line', role: 'status' });
  const last = backups.copies[0];
  const table = (rows) => h('table', { class: 'grid settings' }, h('tbody', {}, rows.map(([k, v]) => h('tr', {}, h('td', { text: k }), h('td', { class: 'm', text: v })))));
  const el = h('div', {},
    h('header', { class: 'top' }, h('div', { class: 'top-row' }, h('h1', {}, 'Settings'))),
    h('div', { class: 'pad' },
      h('h2', { class: 'section-title', text: 'Backups' }),
      table([
        ['Last copy', last ? dateTime(last.written_at) : 'none yet'],
        ['Copies kept', `${backups.copies.length} of ${backups.kept}`],
        ['Next copy', dateTime(backups.next)],
        ['Database', size(backups.database_bytes)],
        ['Photos', `${backups.photos.count} · ${size(backups.photos.bytes)}`],
        ['Covers', `${backups.covers.count} · ${size(backups.covers.bytes)}`],
      ]),
      h('p', { class: 'note-line', text: 'Copies of the database are kept in data/backups. Photos and covers are files: back up the whole data folder from the NAS.' }),
      h('div', { class: 'row-btns' },
        h('button', { class: 'btn small', type: 'button', onclick: async () => {
          try { await api('/api/backup', { method: 'POST' }); toast('Copy made'); render(); } catch (err) { backupMsg.textContent = err.message; }
        } }, 'Back up now'),
        h('a', { class: 'btn small', href: '/api/backup/download', download: '' }, 'Download everything (.zip)')),
      backupMsg,
      h('h2', { class: 'section-title', text: 'App' }),
      table([
        ['Version', health.version],
        ['Text recognition', health.tesseract ? `Tesseract ${health.tesseract} (${health.ocr_languages.join(', ')})` : 'missing'],
        ['Page straightening', health.straighten_pages ? 'on' : 'off'],
        ['Barcode reader', health.barcode_reader ? 'on' : 'off'],
        ['Online book lookups', health.lookups_enabled ? 'on' : 'off'],
      ]),
      h('div', { class: 'row-btns' },
        h('a', { class: 'btn small', href: '/docs', target: '_blank', rel: 'noopener' }, 'API'),
        h('button', { class: 'btn small', type: 'button', onclick: async () => {
          await api('/api/logout', { method: 'POST' }).catch(() => null);
          store.changed();
          go('login');
        } }, 'Log out'))));
  return { el, nav: 'settings' };
}

// ---------- shell and navigation ----------

function buildShell() {
  const link = (nav, href, label) => h('a', { href, dataset: { nav } }, label);
  const side = h('aside', { class: 'side' },
    h('a', { href: '#/', class: 'brand' }, 'Marginote'),
    h('a', { class: 'btn primary', href: '#/capture' }, '+ Capture'),
    h('nav', { 'aria-label': 'Main' }, link('books', '#/', 'Books'), link('quotes', '#/quotes', 'Quotes'), link('tags', '#/tags', 'Tags'),
      link('inbox', '#/inbox', 'Inbox'), link('settings', '#/settings', 'Settings')));
  const tabbar = h('nav', { class: 'tabbar', 'aria-label': 'Main' },
    link('books', '#/', 'Books'), link('quotes', '#/quotes', 'Quotes'), link('tags', '#/tags', 'Tags'),
    h('span', { class: 'tab-capture' }, h('a', { class: 'btn primary', href: '#/capture', style: { minHeight: '38px', padding: '0 12px', fontSize: '16px' } }, '+ Capture')));
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
  [/^inbox$/, viewInbox],
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
window.matchMedia('(min-width: 960px)').addEventListener('change', () => render());

(async function start() {
  buildShell();
  try {
    const me = await api('/api/me');
    if (!me.logged_in) { sessionStorage.setItem('marginote.after', location.hash); location.replace('#/login'); }
  } catch { /* shown by render */ }
  render();
})();
