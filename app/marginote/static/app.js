/* Marginote — the app's screens. Plain JavaScript, no outside code: everything is served by your own server.
   Text you captured is always inserted as text (textContent), never as HTML. */
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
  book: 'M4 5c3-1 6-.5 8 1 2-1.5 5-2 8-1v14c-3-1-6-.5-8 1-2-1.5-5-2-8-1zM12 6v14',
  link: 'M10 14l4-4M8.5 11.5 6 14a3.5 3.5 0 0 0 4 4l2.5-2.5M15.5 12.5 18 10a3.5 3.5 0 0 0-4-4l-2.5 2.5',
  note: 'M6 3h9l4 4v14H6zM15 3v4h4M9 11h7M9 14h7M9 17h4',
  external: 'M9 5h10v10M19 5 7 17',
  paste: 'M9 3h6v4H9zM8 5H5v16h14V5h-3',
  inbox: 'M4 13h4l2 3h4l2-3h4M4 13l2-8h12l2 8v6H4z',
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
function plainDate(value) {   // '2026-10-02' -> '2 Oct 2026', '2026-10' -> 'Oct 2026'
  const m = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$/.exec(value || '');
  if (!m) return value || '';
  return [m[3] ? Number(m[3]) : null, m[2] ? MONTHS[Number(m[2]) - 1] : null, m[1]].filter(Boolean).join(' ');
}
function size(bytes) {
  if (!bytes) return '0 KB';
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}
const fold = (s) => (s || '').normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
const WORDS = { entry: 'entries', copy: 'copies', person: 'people', other: 'other' };
const plural = (n, word) => `${n} ${n === 1 ? word : WORDS[word] || word + 's'}`;
const isWide = () => window.matchMedia('(min-width: 960px)').matches;
const coarse = () => window.matchMedia('(pointer: coarse)').matches;
const kindName = (kind) => (kind === 'quote' ? 'quote' : 'comment');
const shorten = (text, n) => (text && text.length > n ? text.slice(0, n - 1).trimEnd() + '…' : text || '');
const surname = (p) => (p.sort_name || p.name).split(',')[0];
const joinDots = (parts) => parts.filter(Boolean).flatMap((x, k) => (k ? [' · ', x] : [x]));

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

// What each kind of source is called, what it is made by, and how to say where in it a passage is.
const KINDS = {
  book: { name: 'Book', several: 'books', maker: 'author', makerLabel: 'author(s)', publisher: 'publisher', where: 'page', photos: true },
  ebook: { name: 'Ebook', several: 'ebooks', maker: 'author', makerLabel: 'author(s)', publisher: 'publisher', where: 'page or chapter', photos: true },
  article: { name: 'Article', several: 'articles', maker: 'author', makerLabel: 'author(s)', publisher: 'site', where: null, link: true, dated: true },
  video: { name: 'Video', several: 'videos', maker: 'speaker', makerLabel: 'who speaks', publisher: 'channel', where: null, link: true, dated: true },
  podcast: { name: 'Podcast', several: 'podcasts', maker: 'speaker', makerLabel: 'who speaks', publisher: 'show', where: null, link: true, dated: true },
  talk: { name: 'Talk or class', several: 'talks', maker: 'speaker', makerLabel: 'who speaks', publisher: 'event or place', where: 'slide or part', photos: true, dated: true },
  other: { name: 'Other', several: 'other', maker: 'author', makerLabel: 'by', publisher: 'publisher or place', where: 'where', photos: true },
};
const kindOf = (s) => KINDS[s?.kind] || KINDS.book;
const makers = (s) => [...(s.people?.author || []), ...(s.people?.speaker || []), ...(s.people?.editor || [])];

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
      location.replace('#/login');
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

// Lists kept while you move around; forgotten after any change.
const store = {
  cache: {},
  async get(name, force) {
    if (!this.cache[name] || force) this.cache[name] = await api(`/api/${name}`);
    return this.cache[name];
  },
  sources(force) { return this.get('sources', force); },
  people(force) { return this.get('people', force); },
  topics(force) { return this.get('topics', force); },
  changed() { this.cache = {}; },
};

// ---------- navigation ----------
// The pages you went through, so "‹ Spinoza" takes you back to Spinoza's page and says so. A tab (Library,
// Entries, Notes…) starts afresh; a finished form is replaced by where it leads, never returned to.

const nav = {
  stack: (() => { try { return JSON.parse(sessionStorage.getItem('marginote.stack')) || []; } catch { return []; } })(),
  replacing: false,
  flash: {},           // a message for the next page: the entry just saved, a cover being looked for
  save() { try { sessionStorage.setItem('marginote.stack', JSON.stringify(this.stack)); } catch { /* not kept */ } },
  arrive(hash, root) {
    const top = this.stack[this.stack.length - 1];
    if (this.replacing) {
      this.replacing = false;
      this.stack.pop();
      const k = this.stack.findIndex((e) => e.hash === hash);
      if (k >= 0) this.stack = this.stack.slice(0, k + 1);
      else this.stack.push({ hash, label: '' });
    } else if (top && top.hash === hash) {
      return;
    } else if (root) {
      this.stack = [{ hash, label: '' }];
    } else {
      const k = this.stack.findIndex((e) => e.hash === hash);
      if (k >= 0) this.stack = this.stack.slice(0, k + 1);         // came back to a page already in the trail
      else this.stack.push({ hash, label: '' });
      if (this.stack.length > 40) this.stack.splice(1, 1);
    }
    this.save();
  },
  label(text) {
    const top = this.stack[this.stack.length - 1];
    if (top) { top.label = text; this.save(); }
  },
  prev() { return this.stack.length > 1 ? this.stack[this.stack.length - 2] : null; },
  back(fallback) { if (this.prev()) history.back(); else this.replace(fallback); },
  replace(path) {
    const target = '#/' + path;
    if (location.hash === target) { render(); return; }
    this.replacing = true;
    location.replace(target);
  },
  // after a form: back to the page it was opened from when that is where it leads, else replace the form
  finish(path) {
    const prev = this.prev();
    if (prev && prev.hash === '#/' + path) history.back();
    else this.replace(path);
  },
};

function go(path) { location.hash = '#/' + path; }

function backButton(fallback, fallbackLabel) {
  const prev = nav.prev();
  const label = prev?.label || fallbackLabel;
  return h('a', { class: 'link-btn back', href: prev ? prev.hash : '#/' + fallback, onclick: (ev) => { ev.preventDefault(); nav.back(fallback); } },
    icon('back', 20), h('span', { class: 'lbl', text: shorten(label, 22) }));
}

function cancelButton(fallback, text = 'Cancel') {
  return h('a', { class: 'link-btn', href: '#/' + fallback, onclick: (ev) => { ev.preventDefault(); nav.back(fallback); } }, text);
}

function bar(left, title, right) {
  return h('div', { class: 'bar' }, left || h('span', { class: 'spacer' }), h('span', { class: 'title', text: title || '' }),
    right || h('span', { class: 'spacer' }));
}

// ---------- shared pieces ----------

function thumb(source, size = 'small') {
  const kind = source.kind || 'book';
  const wide = kind === 'video' || kind === 'podcast';
  const placeholder = () => {
    if (wide) return h('div', { class: `thumb-video ${size}`, 'aria-hidden': 'true' }, h('span', { class: 'play' }));
    if (kind === 'article') return h('div', { class: `cover ph article ${size}`, 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i'), h('i'));
    const who = makers(source)[0];
    return h('div', { class: `cover ph ${size}`, 'aria-hidden': 'true' }, h('b', { text: source.title }), h('i', { text: who ? surname(who) : '' }));
  };
  if (!source.cover_url) return h('span', { class: `slot ${size}` }, placeholder());
  const img = h('img', { class: `${wide ? 'thumb-video img' : 'cover'} ${size}`, alt: '', loading: 'lazy', src: source.cover_url });
  img.addEventListener('error', () => img.replaceWith(placeholder()));
  return h('span', { class: `slot ${size}` }, img);
}

function personLinks(list) {
  const out = [];
  list.forEach((p, k) => { if (k) out.push(k === list.length - 1 ? ' and ' : ', '); out.push(h('a', { class: 'plink', href: `#/person/${p.id}`, text: p.name })); });
  return out;
}

function topicLinks(list) {
  return h('div', { class: 'chips' }, list.map((t) => h('a', { class: 'chip', href: `#/topic/${t.id}`, text: t.name })));
}

function sourceLine(s) {
  // 'book · Frédéric Lordon' / 'video · Philosophie à voix haute'
  const who = makers(s).map((p) => p.name).join(', ');
  return joinDots([h('span', { class: 'sc', text: s.kind }), who || s.publisher || null, s.field ? h('i', { text: s.field }) : null]);
}

function sourceRow(s, { count = true, href = `#/source/${s.id}` } = {}) {
  return h('a', { class: 'book-row', href }, thumb(s),
    h('span', { class: 'main' }, h('span', { class: 't', text: s.title }), h('span', { class: 'a' }, sourceLine(s))),
    count ? h('span', { class: 'num w40', text: s.entry_count }) : null);
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

// the small grey line under an entry: what is not already obvious on the page it is shown on
function entryMeta(e, { showSource = false, source = null, person = null } = {}) {
  const bits = [];
  if (showSource) bits.push(h('i', { text: shorten(e.source.title, 48) }));
  if (e.words_by && e.words_by.id !== person) bits.push(h('span', { class: 'sc ink', text: `${surname(e.words_by)}, quoted` }));
  if (e.kind === 'comment') bits.push(h('span', { class: 'sc', text: 'comment' }));
  const about = e.about.filter((p) => p.id !== person && !(source && p.from_source));
  if (about.length) bits.push('about ' + about.map((p) => surname(p)).join(', '));
  if (e.note) bits.push('note');
  const topics = e.topics.filter((t) => !(source && t.from_source));
  if (topics.length) bits.push(h('span', { class: 'tg', text: topics.map((t) => t.name).join(' ') }));
  return joinDots(bits);
}

function where(e) {
  if (!e.page) return '';
  return /^\d/.test(e.page) || /^[ivxlcdm]+$/i.test(e.page) ? `p. ${e.page}` : e.page;
}

function entryRow(e, opts = {}) {
  const meta = entryMeta(e, opts);
  return h('a', { class: `entry-row${e.kind === 'comment' ? ' comment' : ''}${opts.fresh ? ' fresh' : ''}${opts.mark ? ' marked' : ''}`,
    href: `#/entry/${e.id}`, id: `e${e.id}` },
  h('span', { class: 'pg', text: e.page || '' }),
  h('div', { class: 'body' },
    h('p', { class: 'txt' }, e.snippet ? withMarks(e.snippet) : e.text),
    meta.length ? h('span', { class: 'meta' }, meta) : null));
}

function entryTable(entries, { showSource = true, fresh = null } = {}) {
  const rows = entries.map((e) => h('tr', { class: e.id === fresh ? 'fresh' : '', id: `e${e.id}`, onclick: () => go(`entry/${e.id}`) },
    h('td', { class: 'm', text: e.page || '' }),
    h('td', { class: e.kind === 'comment' ? 'comment' : '' }, e.snippet ? withMarks(e.snippet) : e.text,
      e.words_by ? h('span', { class: 'sub sc', text: `${surname(e.words_by)}, quoted` }) : null),
    showSource ? h('td', { class: 'it', text: e.source.title }) : null,
    h('td', { class: 'tags', text: e.topics.map((t) => t.name).join(' ') }),
    h('td', { class: 'm', text: fullDate(e.created_at) })));
  return h('div', { class: 'table-wrap' },
    h('table', { class: 'grid' },
      h('thead', {}, h('tr', {},
        h('th', { style: { width: '64px' }, text: 'where' }), h('th', { text: 'entry' }),
        showSource ? h('th', { style: { width: '200px' }, text: 'source' }) : null,
        h('th', { style: { width: '150px' }, text: 'topics' }), h('th', { style: { width: '110px' }, text: 'added' }))),
      h('tbody', {}, rows)));
}

function entryList(entries, opts = {}) {
  if (!entries.length) return null;
  if (isWide() && !opts.compact) return entryTable(entries, { showSource: opts.showSource, fresh: opts.fresh });
  return [h('div', { class: 'colhead' }, h('span', { class: 'w36', text: '' }), h('span', { style: { flex: 1 }, text: opts.head || 'entry' })),
    entries.map((e) => entryRow(e, { ...opts, fresh: e.id === opts.fresh })), h('div', { class: 'list-end' })];
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
function confirmDialog({ title, text, choices, extra }) {
  return new Promise((resolve) => {
    const dlg = h('dialog', { class: 'confirm', 'aria-labelledby': 'dlg-title' });
    const done = (value) => { dlg.close(); dlg.remove(); resolve(value); };
    put(dlg,
      h('h2', { id: 'dlg-title', text: title }),
      text ? h('p', { text }) : null,
      extra || null,
      h('div', { class: 'choices' },
        choices.map((c) => h('button', { type: 'button', class: `btn ${c.danger ? 'danger primary' : c.primary ? 'primary' : ''}`,
          onclick: () => done(typeof c.value === 'function' ? c.value() : c.value) }, c.label)),
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

function sectionHead(number, title, count) {
  return h('div', { class: 'section-head' }, h('h2', {}, number ? h('span', { class: 'num-sec', text: number }) : null, title),
    count != null ? h('span', { class: 'count', text: count }) : null);
}

// "3 more ›": the rest of a group, shown in place
function moreGroup(entries, first, rowOpts) {
  const wrap = h('div');
  const shown = entries.slice(0, first);
  const rest = entries.slice(first);
  put(wrap, shown.map((e) => entryRow(e, rowOpts)),
    rest.length ? h('button', { class: 'more-btn', type: 'button', onclick: () => put(wrap, entries.map((e) => entryRow(e, rowOpts))) },
      `${rest.length} more ›`) : null);
  return wrap;
}

// ---------- inputs for people and topics ----------
// Type a name: people and topics already in the library are offered; Enter (or the last line) adds a new one.

function chipInput({ label, initial = [], options, single = false, placeholder = 'add', newLabel, tt = false, id, quick = 0, onchange }) {
  let items = [...initial];
  let active = -1;
  let shown = [];
  const input = h('input', { type: 'text', id, placeholder, autocomplete: 'off', autocapitalize: tt ? 'none' : 'words',
    autocorrect: 'off', spellcheck: 'false', enterkeyhint: 'done', 'aria-label': label, role: 'combobox', 'aria-expanded': 'false' });
  const box = h('div', { class: 'tag-input', onclick: () => input.focus() });
  const list = h('div', { class: 'suggest-list', role: 'listbox', hidden: true });
  const quickRow = h('div', { class: 'suggest' });
  const has = (key) => items.some((i) => i.key === key);
  const changed = () => onchange?.(items);
  const matches = (o, q) => fold(o.label).includes(q) || (o.alt || []).some((a) => fold(a).includes(q));
  function add(item) {
    if (!item) return;
    if (!has(item.key)) { if (single) items = []; items.push(item); changed(); }
    input.value = '';
    active = -1;
    draw();
  }
  function addTyped() {
    const text = input.value.trim().replace(/^#+/, '');
    if (!text) return;
    const q = fold(text);
    const exact = options().find((o) => fold(o.label) === q || (o.alt || []).some((a) => fold(a) === q));
    add(exact || { key: 'new:' + q, label: text, value: text });
  }
  function drawList() {
    const q = fold(input.value.trim());
    if (!q || document.activeElement !== input) { list.hidden = true; input.setAttribute('aria-expanded', 'false'); return; }
    shown = options().filter((o) => !has(o.key) && matches(o, q)).slice(0, 6);
    const exists = options().some((o) => fold(o.label) === q);
    put(list,
      shown.map((o, k) => h('button', { type: 'button', role: 'option', class: k === active ? 'on' : '',
        onpointerdown: (ev) => ev.preventDefault(), onclick: () => add(o) }, h('span', { class: tt ? 'tt' : '', text: o.label }),
      o.sub ? h('span', { class: 'muted', text: o.sub }) : null)),
      exists ? null : h('button', { type: 'button', class: 'new', onpointerdown: (ev) => ev.preventDefault(), onclick: addTyped },
        `+ ${newLabel} “${input.value.trim()}”`));
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  }
  function drawQuick() {
    if (!quick) return;
    const q = fold(input.value.trim());
    put(quickRow, options().filter((o) => !has(o.key) && (!q || matches(o, q))).slice(0, quick).map((o) => h('button', {
      type: 'button', onpointerdown: (ev) => ev.preventDefault(), onclick: () => add(o) }, o.label)));
  }
  function draw() {
    put(box, items.map((i) => h('span', { class: `chip${tt ? '' : ' person'}` }, i.label,
      h('button', { type: 'button', 'aria-label': `Remove ${i.label}`, onclick: (ev) => {
        ev.stopPropagation(); items = items.filter((x) => x !== i); changed(); draw();
      } }, '×'))), single && items.length ? null : input);
    drawList();
    drawQuick();
  }
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' || (tt && ev.key === ',')) {
      ev.preventDefault();
      if (active >= 0 && shown[active]) add(shown[active]); else addTyped();
    } else if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      active = Math.max(-1, Math.min(shown.length - 1, active + (ev.key === 'ArrowDown' ? 1 : -1)));
      drawList();
    } else if (ev.key === 'Backspace' && !input.value && items.length) {
      items.pop(); changed(); draw();
    } else if (ev.key === 'Escape') {
      list.hidden = true;
    }
  });
  input.addEventListener('input', () => { active = -1; drawList(); drawQuick(); });
  input.addEventListener('focus', drawList);
  input.addEventListener('blur', () => { setTimeout(() => { if (input.value.trim()) addTyped(); list.hidden = true; }, 120); });
  draw();
  return {
    el: h('div', { class: 'field chip-field' }, h('label', { class: 'label', for: id, text: label }), box, list, quick ? quickRow : null),
    get value() { if (input.value.trim()) addTyped(); return items.map((i) => i.value); },
    get items() { return items; },
    set(list) { items = [...list]; draw(); },
  };
}

function personOption(p) {
  return { key: 'p' + p.id, label: p.name, value: p.id, alt: [p.sort_name, ...(p.aliases || [])],
    sub: p.entries != null ? `${p.sort_name} · ${plural(p.entries, 'entry')}` : p.sort_name };
}
const personItem = (p) => ({ key: 'p' + p.id, label: p.name, value: p.id });

function peopleInput(label, initial, allPeople, opts = {}) {
  return chipInput({ label, initial: initial.map(personItem), options: () => allPeople.map(personOption),
    newLabel: 'new person', placeholder: opts.placeholder || 'type a name', ...opts });
}

function topicsInput(label, initial, allTopics, opts = {}) {
  const byUse = [...allTopics].sort((a, b) => b.entries - a.entries);
  return chipInput({ label, tt: true, initial: initial.map((t) => ({ key: 't' + fold(t), label: t, value: t })),
    options: () => byUse.map((t) => ({ key: 't' + fold(t.name), label: t.name, value: t.name, sub: plural(t.entries, 'entry') })),
    newLabel: 'new topic', placeholder: 'add a topic', quick: 8, ...opts });
}

function kindSwitch(get, set, after) {
  const seg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Kind' });
  const draw = () => put(seg, ['quote', 'comment'].map((k) => h('button', { type: 'button', class: get() === k ? 'on' : '',
    'aria-pressed': get() === k ? 'true' : 'false', onclick: () => { set(k); draw(); after?.(); } }, k === 'quote' ? 'Quote' : 'Comment')));
  draw();
  return seg;
}

function segmented(label, choices, value, onpick) {
  const seg = h('div', { class: 'seg', role: 'group', 'aria-label': label });
  const draw = (v) => put(seg, choices.map(([k, text]) => h('button', { type: 'button', class: v === k ? 'on' : '',
    'aria-pressed': v === k ? 'true' : 'false', onclick: () => { draw(k); onpick(k); } }, text)));
  draw(value);
  return seg;
}

function filterRow(choices, value, onpick) {
  const row = h('div', { class: 'tools wrap' });
  const draw = (v) => put(row, choices.map(([k, text]) => h('button', { type: 'button', class: `filter${v === k ? ' on' : ''}`,
    'aria-pressed': v === k ? 'true' : 'false', onclick: () => { draw(k); onpick(k); } }, text)));
  draw(value);
  return row;
}

function field(id, label, attrs = {}, value = '') {
  const input = h('input', { class: 'input', id, value: value ?? '', ...attrs });
  return { input, el: h('label', { class: 'field', for: id }, h('span', { text: label }), input) };
}

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

async function deleteEntries(ids) {
  await api('/api/entries/delete', { method: 'POST', body: { ids } });
  store.changed();
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
      nav.replace(after && !after.startsWith('#/login') ? after.replace(/^#\/?/, '') : '');
    } catch (err) { msg.textContent = err.message; pw.select(); }
  } },
  h('h1', {}, 'Marginote'),
  h('input', { type: 'text', name: 'username', value: 'marginote', autocomplete: 'username', hidden: true, 'aria-hidden': 'true' }),
  h('label', { class: 'field', for: 'pw' }, h('span', { text: 'password' }), pw),
  h('button', { class: 'btn primary big', type: 'submit' }, 'Log in'), msg);
  setTimeout(() => pw.focus(), 50);
  return { el: form, bare: true };
}

// ----- the library: sources, people or topics -----

const LIBRARY_VIEWS = [['sources', 'Sources'], ['people', 'People'], ['topics', 'Topics']];

async function viewLibrary({ params }) {
  let view = params.get('view') || prefs.get('libraryView', 'sources');
  if (!LIBRARY_VIEWS.some(([k]) => k === view)) view = 'sources';
  const [sources, people, topics, inbox] = await Promise.all([store.sources(true), store.people(true), store.topics(true),
    api('/api/photos').catch(() => [])]);
  const q = h('input', { type: 'search', placeholder: 'Search the library', 'aria-label': 'Search the library', enterkeyhint: 'search' });
  const list = h('div', { class: 'library-list' });
  const tools = h('div');
  const counts = { sources: sources.length, people: people.length, topics: topics.length };
  const title = h('h1', {});

  function setView(v) {
    view = v;
    prefs.set('libraryView', v);
    history.replaceState(null, '', v === 'sources' ? '#/' : `#/?view=${v}`);
    const top = nav.stack[nav.stack.length - 1];
    if (top) { top.hash = location.hash; nav.save(); }
    draw();
  }

  function drawSources(needle) {
    const present = Object.keys(KINDS).filter((k) => sources.some((s) => s.kind === k));
    let medium = prefs.get('libraryMedium', '');
    if (medium && !present.includes(medium)) medium = '';
    let sort = prefs.get('librarySort', 'recent');
    const sortSel = h('select', { class: 'filter', 'aria-label': 'Order', onchange: () => { prefs.set('librarySort', sortSel.value); draw(); } },
      h('option', { value: 'recent' }, 'recent first'), h('option', { value: 'title' }, 'by title'), h('option', { value: 'added' }, 'by date added'));
    sortSel.value = sort;
    put(tools, present.length > 1 || sources.length > 6 ? h('div', { class: 'tools wrap' },
      present.length > 1 ? [['', 'all'], ...present.map((k) => [k, KINDS[k].several])].map(([k, text]) => h('button', {
        type: 'button', class: `filter${medium === k ? ' on' : ''}`, onclick: () => { prefs.set('libraryMedium', k); draw(); } }, text)) : null,
      h('span', { class: 'grow' }), sortSel) : null);
    let shown = sources.filter((s) => (!medium || s.kind === medium) && (!needle || fold(
      `${s.title} ${s.subtitle || ''} ${makers(s).map((p) => p.name).join(' ')} ${s.publisher || ''} ${s.field || ''}`).includes(needle)));
    if (sort === 'title') shown = [...shown].sort((a, b) => a.title.localeCompare(b.title));
    else if (sort === 'added') shown = [...shown].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    if (!sources.length) {
      return h('div', { class: 'empty' }, 'Nothing here yet.', h('a', { class: 'btn primary', href: '#/capture' }, 'Capture something'));
    }
    return [shown.length ? h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'source' }), h('span', { class: 'w40 r', text: 'entries' })) : null,
      shown.map((s) => sourceRow(s)), shown.length ? h('div', { class: 'list-end' }) : h('div', { class: 'empty', text: 'Nothing matches.' })];
  }

  function personSub(p) {
    return [
      p.works ? plural(p.works, 'work') : null,
      p.translated ? `translated ${p.translated}` : null,
      p.quoted_in ? `quoted in ${p.quoted_in}` : null,
      p.about_in ? `written about in ${p.about_in}` : null,
      p.notes ? plural(p.notes, 'note') : null,
    ].filter(Boolean).join(' · ');
  }

  function drawPeople(needle) {
    let which = prefs.get('peopleFilter', 'everyone');
    put(tools, people.length > 4 ? filterRow([['everyone', 'everyone'], ['authors', 'authors'], ['about', 'written about']], which,
      (k) => { prefs.set('peopleFilter', k); draw(); }) : null);
    const shown = people.filter((p) => (which === 'everyone' || (which === 'authors' ? p.works + p.translated > 0 : p.about_in > 0))
      && (!needle || fold(`${p.name} ${p.sort_name} ${(p.aliases || []).join(' ')}`).includes(needle)));
    if (!people.length) return h('div', { class: 'empty', text: 'People appear here as you add sources and say who they are about.' });
    const out = [h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'person' }), h('span', { class: 'w40 r', text: 'entries' }))];
    let letter = null;
    for (const p of shown) {
      const first = fold(p.sort_name).charAt(0).toUpperCase();
      if (first !== letter) { letter = first; out.push(h('div', { class: 'letter', text: letter })); }
      const [last, ...rest] = p.sort_name.split(',');
      out.push(h('a', { class: 'pick person-row', href: `#/person/${p.id}` },
        h('span', { class: 'main' }, h('span', {}, h('b', { text: last }), rest.length ? ',' + rest.join(',') : ''),
          h('span', { class: 'a', text: personSub(p) })),
        h('span', { class: 'num w40', text: p.entries })));
    }
    out.push(shown.length ? h('div', { class: 'list-end' }) : h('div', { class: 'empty', text: 'Nobody matches.' }));
    return out;
  }

  function drawTopics(needle) {
    const order = prefs.get('topicsOrder', 'name');
    put(tools, topics.length > 4 ? filterRow([['name', 'a–z'], ['use', 'most used'], ['notes', 'with notes']], order,
      (k) => { prefs.set('topicsOrder', k); draw(); }) : null);
    let shown = topics.filter((t) => (order !== 'notes' || t.notes) && (!needle || fold(t.name).includes(needle)));
    if (order === 'use') shown = [...shown].sort((a, b) => b.entries - a.entries);
    if (!topics.length) return h('div', { class: 'empty', text: 'Topics appear here as you add them to quotes, sources and notes.' });
    return [h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'topic' }), h('span', { class: 'w40 r', text: 'entries' })),
      shown.map((t) => h('a', { class: 'pick', href: `#/topic/${t.id}` },
        h('span', { class: 'main' }, h('span', { class: 't tt', text: t.name }),
          h('span', { class: 'a', text: [plural(t.sources, 'source'), t.notes ? plural(t.notes, 'note') : null].filter(Boolean).join(' · ') })),
        h('span', { class: 'num w40', text: t.entries }))),
      shown.length ? h('div', { class: 'list-end' }) : h('div', { class: 'empty', text: 'No topic matches.' })];
  }

  const seg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Show the library by' });
  function draw() {
    put(seg, LIBRARY_VIEWS.map(([k, text]) => h('button', { type: 'button', class: view === k ? 'on' : '', 'aria-pressed': view === k ? 'true' : 'false',
      onclick: () => setView(k) }, text)));
    put(title, 'Library', h('span', { class: 'count', text: counts[view] }));
    nav.label(LIBRARY_VIEWS.find(([k]) => k === view)[1]);
    const needle = fold(q.value.trim());
    put(list, view === 'people' ? drawPeople(needle) : view === 'topics' ? drawTopics(needle) : drawSources(needle),
      needle.length > 1 ? h('a', { class: 'more-btn', href: `#/entries?q=${encodeURIComponent(q.value.trim())}` },
        `Quotes and comments containing “${q.value.trim()}” ›`) : null);
  }
  q.addEventListener('input', draw);
  draw();
  const el = h('div', {},
    h('header', { class: 'top' },
      h('div', { class: 'top-row' }, title,
        h('div', { class: 'icons' },
          h('a', { class: 'icon-btn narrow-only', href: '#/settings', 'aria-label': 'Settings' }, icon('more', 22)),
          h('a', { class: 'icon-btn', href: '#/source/new', 'aria-label': 'Add a source' }, icon('plus', 22)))),
      seg,
      inbox.length ? h('a', { class: 'filter ink', href: '#/inbox' }, `inbox · ${plural(inbox.length, 'page')} to sort`) : null,
      h('label', { class: 'search' }, icon('search', 16), q),
      tools),
    list);
  return { el, nav: 'library' };
}

// ----- a source -----

async function viewSource({ args: [id] }) {
  const order = prefs.get('sourceOrder', 'page');
  const [source, entries] = await Promise.all([api(`/api/sources/${id}`), api(`/api/sources/${id}/entries?order=${order}`)]);
  nav.label(shorten(source.title, 24));
  const k = kindOf(source);
  const fresh = nav.flash.entry || null;
  const coverPending = nav.flash.cover === source.id;
  nav.flash = {};
  let selecting = false;
  const chosen = new Set();
  const q = h('input', { type: 'search', placeholder: 'Search here', 'aria-label': 'Search in this source', enterkeyhint: 'search' });
  const list = h('div');
  const selectBar = h('div', { class: 'select-bar', hidden: true });
  const orderBtn = k.where ? h('button', { type: 'button', class: 'filter', onclick: () => {
    prefs.set('sourceOrder', order === 'page' ? 'date' : 'page'); render();
  } }, order === 'page' ? `by ${k.where === 'page' ? 'page' : 'place'}` : 'by date') : null;

  const shownEntries = () => {
    const needle = fold(q.value.trim());
    return entries.filter((e) => !needle || fold(`${e.text} ${e.note || ''} ${e.topics.map((t) => t.name).join(' ')} ${e.page || ''}`).includes(needle));
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
      put(list, shown.map((e) => {
        const box = h('input', { type: 'checkbox', checked: chosen.has(e.id), 'aria-label': 'Select', onchange: () => {
          if (box.checked) chosen.add(e.id); else chosen.delete(e.id);
          drawSelectBar();
        } });
        return h('label', { class: `entry-row${e.kind === 'comment' ? ' comment' : ''}` }, h('span', { class: 'check' }, box),
          h('div', { class: 'body' }, h('p', { class: 'txt' }, e.text), h('span', { class: 'meta', text: where(e) })));
      }), h('div', { class: 'list-end' }));
      return;
    }
    put(list,
      entryList(shown, { showSource: false, source: source.id, fresh, head: k.link ? 'quotes and comments' : 'entry' }),
      !shown.length && entries.length ? h('div', { class: 'empty', text: 'Nothing matches.' }) : null,
      !entries.length ? h('div', { class: 'empty' }, 'Nothing captured from it yet.',
        h('a', { class: 'btn primary', href: `#/capture?source=${source.id}` }, '+ Capture')) : null);
  }
  q.addEventListener('input', draw);

  const removeSource = async () => {
    const n = entries.length;
    const choice = await confirmDialog({
      title: `Delete “${source.title}”?`,
      text: n ? `It has ${plural(n, 'entry')}. This cannot be undone.` : 'This cannot be undone.',
      choices: [
        { label: n ? `Delete it and its ${plural(n, 'entry')}` : 'Delete it', value: 'all', danger: true },
        n ? { label: `Delete only its ${plural(n, 'entry')}`, value: 'entries' } : null,
      ].filter(Boolean),
    });
    try {
      if (choice === 'all') {
        await api(`/api/sources/${source.id}`, { method: 'DELETE' });
        store.changed();
        toast('Deleted');
        nav.back('');
      } else if (choice === 'entries') {
        await deleteEntries(entries.map((e) => e.id));
        toast(`${plural(n, 'entry')} deleted`);
        render();
      }
    } catch (err) { toast(err.message); }
  };

  draw();
  if (fresh) setTimeout(() => document.getElementById(`e${fresh}`)?.scrollIntoView({ block: 'center' }), 60);

  const wide = source.kind === 'video' || source.kind === 'podcast';
  const coverEl = h('span', { class: wide ? 'video-cover' : '' }, thumb(source, wide ? 'hero' : isWide() ? 'large' : ''));
  if (coverPending && !source.has_cover) {
    (async () => {   // the cover is looked for in the background: check for up to a minute
      for (let n = 0; n < 20; n++) {
        await new Promise((r) => setTimeout(r, 3000));
        if (!coverEl.isConnected) return;
        const s = await api(`/api/sources/${id}`).catch(() => null);
        if (s?.has_cover) { put(coverEl, thumb(s, wide ? 'hero' : isWide() ? 'large' : '')); store.changed(); return; }
      }
    })();
  }
  const people = source.people;
  const details = joinDots([h('span', { class: 'sc', text: source.kind }), source.publisher,
    source.date ? plainDate(source.date) : source.year, source.edition, source.field ? h('i', { text: source.field }) : null]);
  const counts = [plural(source.quote_count, 'quote'), source.comment_count ? plural(source.comment_count, 'comment') : null].join(' · ').replace(/ · $/, '');
  const info = h('div', { class: 'info' },
    h('h1', { text: source.title }),
    source.subtitle ? h('span', { class: 'it', text: source.subtitle }) : null,
    makers(source).length ? h('span', { class: 'by' }, personLinks(makers(source))) : null,
    people.translator.length ? h('span', { class: 'meta' }, 'translated by ', personLinks(people.translator)) : null,
    h('span', { class: 'meta' }, details),
    people.about.length ? h('span', { class: 'meta' }, 'about ', personLinks(people.about)) : null,
    source.topics.length ? topicLinks(source.topics) : null,
    entries.length ? h('span', { class: 'counts', text: counts }) : null,
    h('div', { class: 'actions' },
      h('a', { class: 'btn primary small', href: `#/capture?source=${source.id}` }, '+ Capture'),
      source.url ? h('a', { class: 'btn small', href: source.url, target: '_blank', rel: 'noopener noreferrer' },
        k.link && source.kind !== 'article' ? `Open the ${source.kind}` : 'Open the link', icon('external', 14)) : null,
      entries.length ? h('a', { class: 'btn small', href: `/api/sources/${source.id}/export.md`, download: '' }, 'Export') : null,
      entries.length ? h('button', { class: 'btn small', type: 'button', onclick: () => { selecting = true; draw(); } }, 'Select') : null));
  const el = h('div', {},
    bar(backButton('', 'Library'), '', h('a', { class: 'link-btn', href: `#/source/${id}/edit` }, 'Edit')),
    h('header', { class: 'top', style: { paddingTop: '6px' } },
      wide ? [coverEl, h('div', { class: 'book-head' }, info)] : h('div', { class: 'book-head' }, coverEl, info),
      entries.length > 5 ? h('label', { class: 'search' }, icon('search', 16), q) : null,
      entries.length > 1 && orderBtn ? h('div', { class: 'tools' }, orderBtn) : null),
    list,
    selectBar,
    h('div', { class: 'pad' }, h('button', { class: 'btn small danger', type: 'button', style: { alignSelf: 'flex-start' }, onclick: removeSource },
      `Delete this ${k.name.toLowerCase()}…`)));
  return { el, nav: 'library' };
}

// ----- a person -----

const SECTION_TITLES = { works: 'Works', translated: 'Translations', quoted: 'Quoted elsewhere' };

function noteBlock(n, { full = false, here = null } = {}) {
  const also = [...n.people.filter((p) => p.id !== here?.person).map((p) => surname(p)),
    ...n.topics.filter((t) => t.id !== here?.topic).map((t) => t.name)];
  return h('a', { class: `note-block${full ? ' full' : ''}`, href: `#/note/${n.id}` },
    n.title ? h('b', { class: 'note-title', text: n.title }) : null,
    h('p', { class: 'note-text', text: n.text }),
    h('span', { class: 'meta' }, joinDots([fullDate(n.updated_at), also.length ? `also on ${also.join(', ')}` : null])));
}

async function viewPerson({ args: [id] }) {
  const data = await api(`/api/people/${id}`);
  const p = data.person;
  nav.label(surname(p));
  let medium = '';
  const media = {};
  for (const sec of data.sections) for (const g of sec.groups) media[g.source.kind] = (media[g.source.kind] || 0) + Math.max(1, g.entries.length);
  const body = h('div');
  const aside = h('div', { class: 'aside' });

  function draw() {
    const parts = [];
    const notes = data.notes.length ? [sectionHead(isWide() ? null : 1, 'Notes', data.notes.length),
      data.notes.map((note) => noteBlock(note, { here: { person: p.id } }))] : null;
    for (const sec of data.sections) {
      const groups = sec.groups.filter((g) => !medium || g.source.kind === medium);
      if (!groups.length) continue;
      const total = groups.reduce((a, g) => a + g.entries.length, 0);
      const title = sec.key === 'about' ? `About ${surname(p)}` : SECTION_TITLES[sec.key];
      parts.push(sectionHead(null, title, [plural(groups.length, 'source'), total ? plural(total, 'entry') : null].filter(Boolean).join(' · ')));
      for (const g of groups) {
        parts.push(sourceRow(g.source, { count: false }));
        if (g.entries.length) parts.push(moreGroup(g.entries, 3, { person: p.id, source: g.source.id }));
      }
    }
    // section numbers follow the order on screen: notes first on a phone, beside on a computer
    let k = notes && !isWide() ? 1 : 0;
    for (const el of parts) if (el.classList?.contains('section-head')) el.querySelector('h2').prepend(h('span', { class: 'num-sec', text: ++k }));
    if (isWide()) {
      put(body, parts.length ? [parts, h('div', { class: 'list-end' })] : h('div', { class: 'empty', text: 'Nothing about this person yet.' }));
      put(aside, notes || h('div', { class: 'note-line', text: 'No notes on them yet.' }));
    } else {
      put(body, notes, parts, parts.length ? h('div', { class: 'list-end' }) : null,
        !parts.length && !notes ? h('div', { class: 'empty', text: 'Nothing about this person yet.' }) : null);
    }
  }
  draw();
  const kinds = Object.keys(media);
  const counts = [p.works ? plural(p.works, 'work') : null, p.translated ? `translated ${p.translated}` : null,
    p.quoted_in ? `quoted in ${plural(p.quoted_in, 'source')}` : null, p.about_in ? `written about in ${p.about_in}` : null,
    plural(p.entries, 'entry')].filter(Boolean).join(' · ');
  const el = h('div', {},
    bar(backButton('?view=people', 'People'), '', h('a', { class: 'link-btn', href: `#/person/${id}/edit` }, 'Edit')),
    h('header', { class: 'top', style: { paddingTop: '6px' } },
      h('h1', { text: p.sort_name }),
      p.dates ? h('span', { class: 'meta', text: p.dates }) : null,
      h('span', { class: 'meta', text: counts }),
      p.aliases.length ? h('span', { class: 'meta it', text: `Also written: ${p.aliases.join(', ')}` }) : null,
      h('div', { class: 'actions' },
        h('a', { class: 'btn small', href: `#/note/new?person=${p.id}` }, '+ Note'),
        h('a', { class: 'btn small', href: `#/capture?about=${p.id}` }, `+ Capture about ${surname(p)}`)),
      kinds.length > 1 ? filterRow([['', 'all'], ...kinds.map((m) => [m, `${KINDS[m].several} ${media[m]}`])], '', (m) => { medium = m; draw(); }) : null),
    h('div', { class: 'two-col' }, body, isWide() ? aside : null));
  return { el, nav: 'library' };
}

// ----- a topic -----

async function viewTopic({ args: [id] }) {
  const data = await api(`/api/topics/${id}`);
  const t = data.topic;
  nav.label(shorten(t.name, 24));
  let by = prefs.get('topicGroup', 'person');
  const body = h('div');
  function groups() {
    const map = new Map();
    for (const e of data.entries) {
      let key; let label; let href = null;
      if (by === 'person') { key = e.by ? 'p' + e.by.id : 'none'; label = e.by ? e.by.sort_name : 'No author'; href = e.by ? `#/person/${e.by.id}` : null; }
      else if (by === 'source') { key = 's' + e.source.id; label = e.source.title; href = `#/source/${e.source.id}`; }
      else { key = e.created_at.slice(0, 7); label = plainDate(key); }
      if (!map.has(key)) map.set(key, { label, href, entries: [] });
      map.get(key).entries.push(e);
    }
    const list = [...map.values()];
    if (by !== 'date') list.sort((a, b) => b.entries.length - a.entries.length || a.label.localeCompare(b.label));
    return list;
  }
  function draw() {
    put(body, groups().map((g) => [
      h('div', { class: 'group-head' }, g.href ? h('a', { href: g.href, text: g.label }) : h('span', { text: g.label }), h('span', { class: 'count', text: g.entries.length })),
      moreGroup(g.entries, 3, { showSource: by !== 'source', person: by === 'person' ? Number(g.href?.split('/').pop()) : null })]),
    data.entries.length ? h('div', { class: 'list-end' }) : null);
  }
  draw();
  let n = 0;
  const el = h('div', {},
    bar(backButton('?view=topics', 'Topics'), '', h('a', { class: 'link-btn', href: `#/topic/${id}/edit` }, 'Edit')),
    h('header', { class: 'top', style: { paddingTop: '6px' } },
      h('h1', { text: t.name }),
      h('span', { class: 'meta', text: [plural(t.sources, 'source'), plural(data.people.length, 'person'), plural(t.entries, 'entry')].join(' · ') }),
      data.people.length ? h('div', { class: 'chips' }, h('span', { class: 'label', text: 'people' }),
        data.people.slice(0, 12).map((pp) => h('a', { class: 'chip serif', href: `#/person/${pp.id}` }, surname(pp), h('span', { class: 'n', text: pp.count })))) : null,
      data.related.length ? h('div', { class: 'chips' }, h('span', { class: 'label', text: 'often with' }),
        data.related.map((r) => h('a', { class: 'chip', href: `#/topic/${r.id}` }, r.name, h('span', { class: 'n', text: r.count })))) : null,
      h('div', { class: 'actions' },
        h('a', { class: 'btn small', href: `#/note/new?topic=${t.id}` }, '+ Note'),
        h('a', { class: 'btn small', href: `#/capture?topic=${t.id}` }, '+ Capture'))),
    data.notes.length ? [sectionHead(++n, 'Notes', data.notes.length), data.notes.map((note) => noteBlock(note, { full: true, here: { topic: t.id } }))] : null,
    data.entries.length ? [sectionHead(++n, 'Entries', data.entries.length),
      h('div', { class: 'tools pad-x' }, h('span', { class: 'label', text: 'group by' }),
        segmented('Group entries by', [['person', 'person'], ['source', 'source'], ['date', 'date']], by, (k) => { by = k; prefs.set('topicGroup', k); draw(); })),
      body] : h('div', { class: 'empty', text: 'No quote or comment on this topic yet.' }));
  return { el, nav: 'library' };
}

// ----- all quotes and comments -----

async function viewEntries({ params }) {
  const f = { q: params.get('q') || '', kind: params.get('kind') || '', medium: params.get('medium') || '' };
  let entries = [];
  let offset = 0;
  let more = false;
  const PAGE = 200;
  async function load(append) {
    if (f.q) {
      let hits = await api(`/api/search?q=${encodeURIComponent(f.q)}&limit=500`);
      hits = hits.filter((e) => (!f.kind || e.kind === f.kind) && (!f.medium || e.source.kind === f.medium));
      entries = hits; more = false;
    } else {
      const qs = new URLSearchParams({ limit: PAGE, offset });
      if (f.kind) qs.set('kind', f.kind);
      if (f.medium) qs.set('medium', f.medium);
      const page = await api(`/api/entries?${qs}`);
      entries = append ? entries.concat(page) : page;
      more = page.length === PAGE;
    }
  }
  await load(false);
  nav.label('Entries');
  const setFilter = (key, value) => {
    f[key] = value;
    const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v));
    history.replaceState(null, '', `#/entries${qs.toString() ? '?' + qs : ''}`);
    const top = nav.stack[nav.stack.length - 1];
    if (top) { top.hash = location.hash; nav.save(); }
    offset = 0;
    load(false).then(draw).catch((err) => put(list, errorBox(err)));
  };
  const q = h('input', { type: 'search', placeholder: 'Search words, people, topics', 'aria-label': 'Search quotes and comments', value: f.q, enterkeyhint: 'search' });
  q.addEventListener('input', debounce(() => setFilter('q', q.value.trim()), 350));
  const kindSel = h('select', { class: 'filter', 'aria-label': 'Type', onchange: () => setFilter('kind', kindSel.value) },
    h('option', { value: '' }, 'quotes and comments'), h('option', { value: 'quote' }, 'quotes'), h('option', { value: 'comment' }, 'comments'));
  kindSel.value = f.kind;
  const mediumSel = h('select', { class: 'filter', 'aria-label': 'From', onchange: () => setFilter('medium', mediumSel.value) },
    h('option', { value: '' }, 'from everything'), Object.entries(KINDS).map(([k, v]) => h('option', { value: k }, `from ${v.several}`)));
  mediumSel.value = f.medium;
  const list = h('div');
  const count = h('span', { class: 'count' });
  function draw() {
    count.textContent = entries.length + (more ? '+' : '');
    put(list,
      entryList(entries, { showSource: true }),
      entries.length ? null : h('div', { class: 'empty', text: f.q || f.kind || f.medium ? 'Nothing matches.' : 'No quotes yet.' }),
      more ? h('div', { class: 'pad' }, h('button', { class: 'btn', type: 'button', onclick: async () => { offset += PAGE; await load(true); draw(); } }, 'Show more')) : null);
  }
  draw();
  const el = h('div', {},
    h('header', { class: 'top' },
      h('div', { class: 'top-row' }, h('h1', {}, 'Entries', count)),
      h('label', { class: 'search' }, icon('search', 16), q),
      h('div', { class: 'tools half' }, kindSel, mediumSel)),
    list);
  if (f.q) setTimeout(() => { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 30);
  return { el, nav: 'entries' };
}

// ----- one quote or comment -----

function citation(e, source) {
  const who = e.words_by ? `${e.words_by.name}, quoted in ` : '';
  const by = makers(source).map((p) => p.name).join(', ');
  const place = where(e);
  return `${who}${by ? by + ', ' : ''}${source.title}${source.year ? ` (${source.year})` : source.date ? ` (${plainDate(source.date)})` : ''}${place ? ', ' + place : ''}`;
}

async function viewEntry({ args: [id] }) {
  const e = await api(`/api/entries/${id}`);
  const source = await api(`/api/sources/${e.source.id}`);
  nav.label(e.kind === 'quote' ? 'Quote' : 'Comment');
  const del = async () => {
    const ok = await confirmDialog({ title: `Delete this ${kindName(e.kind)}?`, text: 'This cannot be undone.',
      choices: [{ label: `Delete the ${kindName(e.kind)}`, value: true, danger: true }] });
    if (!ok) return;
    try {
      await deleteEntries([e.id]);
      toast(`${e.kind === 'quote' ? 'Quote' : 'Comment'} deleted`);
      nav.back(`source/${e.source.id}`);
    } catch (err) { toast(err.message); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(`${e.text}\n— ${citation(e, source)}`); toast('Copied with its reference'); } catch { toast('Copying is not allowed here'); }
  };
  const linkLabel = source.kind === 'article' && e.kind === 'quote' ? 'Open at this passage' : source.kind === 'article' ? 'Open the article' : `Open the ${source.kind}`;
  const el = h('div', {},
    bar(backButton(`source/${e.source.id}`, shorten(source.title, 24)), '', h('a', { class: 'link-btn', href: `#/entry/${id}/edit` }, 'Edit')),
    h('article', { class: 'entry-page' },
      h('a', { class: 'book-link', href: `#/source/${source.id}` }, thumb(source),
        h('span', {}, h('span', { class: 't', text: source.title }), makers(source).length ? [h('br'), h('span', { class: 'muted', text: makers(source).map((p) => p.name).join(', ') })] : null)),
      h('div', { class: 'kv' }, joinDots([where(e) || null, e.kind === 'comment' ? h('i', { text: 'comment' }) : null, fullDate(e.created_at)])),
      e.words_by ? h('p', { class: 'words-by' }, h('span', { class: 'sc', text: 'words of ' }), h('a', { class: 'plink', href: `#/person/${e.words_by.id}`, text: e.words_by.name }),
        `, quoted by ${makers(source).map((p) => p.name).join(', ') || 'the source'}`) : null,
      h('p', { class: `quote-env${e.kind === 'comment' ? ' comment-text' : ''}`, lang: source.language || null, text: e.text }),
      e.note ? h('p', { class: 'note-p' }, h('b', { text: 'Note.' }), e.note) : null,
      e.about.length ? h('p', { class: 'kv-line' }, h('span', { class: 'label', text: 'about ' }), personLinks(e.about)) : null,
      e.topics.length ? topicLinks(e.topics) : null,
      e.link ? h('a', { class: 'btn small', href: e.link, target: '_blank', rel: 'noopener noreferrer', style: { alignSelf: 'flex-start' } }, linkLabel, icon('external', 14)) : null,
      e.notes?.length ? h('div', { class: 'kv-line' }, h('span', { class: 'label', text: 'in your notes ' }),
        e.notes.flatMap((n, k) => [k ? ', ' : '', h('a', { class: 'plink', href: `#/note/${n.id}`, text: n.title })])) : null,
      h('p', { class: 'cite muted', text: citation(e, source) }),
      h('div', { class: 'row-btns' },
        h('a', { class: 'btn small', href: `#/entry/${id}/edit` }, 'Edit'),
        e.photo_id ? h('a', { class: 'btn small', href: `#/entry/${id}/photo` }, 'Photo') : null,
        h('button', { class: 'btn small', type: 'button', onclick: copy }, 'Copy'),
        h('a', { class: 'btn small', href: `#/note/new?entry=${e.id}` }, '+ Note'),
        h('button', { class: 'btn small danger', type: 'button', onclick: del }, 'Delete…'))));
  return { el, nav: 'entries' };
}

// the fields shared by capture and editing: who, about whom, topics, note
function entryFields({ source, sources, people, topics, entry = null, about = null, topicNames = null, onSourceChange }) {
  let touchedAbout = false;
  let touchedTopics = false;
  const k = kindOf(source);
  const page = h('input', { class: 'input', id: 'f-page', value: entry?.page || '', inputmode: 'text', style: { width: '110px' } });
  const pageLabel = h('span', { text: k.where || 'where' });
  const sourceSel = h('select', { class: 'select', id: 'f-source' }, sources.map((s) => h('option', { value: String(s.id) }, shorten(s.title, 60))));
  sourceSel.value = String(source.id);
  const wordsBy = peopleInput('words of (when not the author’s)', entry?.words_by ? [entry.words_by] : [], people,
    { single: true, id: 'f-by', placeholder: 'a quote within the quote' });
  const aboutIn = peopleInput('about', about || entry?.about || source.people.about, people,
    { id: 'f-about', placeholder: 'who it is about', onchange: () => { touchedAbout = true; } });
  const topicsIn = topicsInput('topics', topicNames || (entry ? entry.topics.map((t) => t.name) : source.topics.map((t) => t.name)), topics,
    { id: 'f-topics', onchange: () => { touchedTopics = true; } });
  if (about) touchedAbout = true;
  if (topicNames) touchedTopics = true;
  const note = h('textarea', { class: 'textarea', rows: 3, id: 'f-note', value: entry?.note || '' });
  const pageRow = h('div', { class: 'two' },
    h('label', { class: 'field', for: 'f-page' }, pageLabel, page),
    h('label', { class: 'field grow', for: 'f-source' }, h('span', { text: 'source' }), sourceSel));
  sourceSel.addEventListener('change', () => {
    const s = sources.find((x) => String(x.id) === sourceSel.value);
    pageLabel.textContent = kindOf(s).where || 'where';
    onSourceChange?.(s);
  });
  return {
    els: [pageRow, h('label', { class: 'field', for: 'f-note' }, h('span', { text: 'your note' }), note), aboutIn.el, topicsIn.el, wordsBy.el],
    focusNote: () => note.focus(),
    about: () => aboutIn.value,
    topics: () => topicsIn.value,
    values() {
      const out = { page: page.value, note: note.value, source_id: Number(sourceSel.value) };
      const by = wordsBy.value;
      out.words_by = by.length ? by[0] : null;
      if (touchedAbout || entry) out.about = aboutIn.value;
      if (touchedTopics || entry) out.topics = topicsIn.value;
      return out;
    },
  };
}

async function viewEntryEdit({ args: [id] }) {
  const [e, sources, people, topics] = await Promise.all([api(`/api/entries/${id}`), store.sources(), store.people(), store.topics()]);
  const source = sources.find((s) => s.id === e.source.id) || await api(`/api/sources/${e.source.id}`);
  nav.label('Edit');
  let kind = e.kind;
  const text = h('textarea', { class: 'textarea', rows: 6, id: 'f-text', value: e.text });
  const textLabel = h('span', { text: kind === 'quote' ? 'passage' : 'comment' });
  const kindSeg = kindSwitch(() => kind, (k) => { kind = k; }, () => { textLabel.textContent = kind === 'quote' ? 'passage' : 'comment'; });
  const fields = entryFields({ source, sources, people, topics, entry: e });
  const msg = h('div', { class: 'note-line', role: 'alert' });
  const save = async (ev) => {
    ev.preventDefault();
    try {
      await api(`/api/entries/${id}`, { method: 'PATCH', body: { ...fields.values(), text: text.value, kind } });
      store.changed();
      toast('Saved');
      nav.finish(`entry/${id}`);
    } catch (err) { msg.textContent = err.message; }
  };
  const el = h('form', { onsubmit: save },
    bar(cancelButton(`entry/${id}`), 'Edit', h('button', { class: 'link-btn strong', type: 'submit' }, 'Save')),
    h('div', { class: 'details' },
      kindSeg,
      h('label', { class: 'field', for: 'f-text' }, textLabel, text),
      fields.els,
      e.photo_id ? h('a', { class: 'btn small', href: `#/entry/${id}/photo`, style: { alignSelf: 'flex-start' } }, 'Change the selection on the photo') : null,
      msg,
      h('button', { class: 'btn primary big', type: 'submit' }, 'Save')));
  return { el, bare: !isWide(), nav: 'entries' };
}

async function viewEntryPhoto({ args: [id] }) {
  const e = await api(`/api/entries/${id}`);
  if (!e.photo_id) { nav.replace(`entry/${id}`); return null; }
  const photo = await api(`/api/photos/${e.photo_id}`);
  nav.label('Photo');
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
      choices: [{ label: 'Replace the text', value: true, primary: true }] });
    if (!ok) return;
    try {
      await api(`/api/entries/${id}`, { method: 'PATCH', body: { word_start: range.start, word_end: range.end } });
      store.changed();
      toast('Selection saved');
      nav.back(`entry/${id}`);
    } catch (err) { toast(err.message); }
  });
  const el = h('div', { class: 'fill-screen' },
    bar(backButton(`entry/${id}`, 'Quote'), e.page ? where(e) : ''),
    sel.el,
    h('div', { class: 'sel-sheet' }, preview, nudgeBar(sel), saveBtn));
  return { el, bare: true, cleanup: () => sel.destroy() };
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

// ----- capture: choose what you are reading or watching, then a photo, a link or typed text -----

const capture = { last: null };   // the photo just used, to take another passage from it

// What another app shared or what was copied: a passage, a link, or both. Apple Books adds where the passage
// is from ("Extrait de" then the title and the author); links to a book shop or a reader are left out.
const SHOP_HOSTS = /(^|\.)(amazon\.[a-z.]+|a\.co|amzn\.to|kindle\.[a-z.]+|books\.apple\.com|itunes\.apple\.com|apple\.co|play\.google\.com|kobo\.com)$/i;
const BOOKS_CITE = /^(Extrait de|Extrait du livre|Excerpt From|Excerpt from|Extracto de|Auszug aus|Estratto da)\b\s*:?\s*(.*)$/;
const COPYRIGHT_LINE = /droits d.auteur|copyright|urheberrecht|derechos de autor|diritti d.autore/i;
function parseShared(raw) {
  let text = String(raw || '').replace(/\r\n?/g, '\n').replace(/ /g, ' ');
  let url = null;
  for (const m of text.match(/https?:\/\/[^\s<>"«»“”]+/gi) || []) {
    let host = '';
    try { host = new URL(m.replace(/[.,;:!?)\]]+$/, '')).hostname; } catch { continue; }
    if (!url && !SHOP_HOSTS.test(host)) url = m.replace(/[.,;:!?)\]]+$/, '');
  }
  text = text.replace(/https?:\/\/[^\s<>"«»“”]+/gi, '');
  const lines = text.split('\n');
  let book = null;
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const m = lines[i].trim().match(BOOKS_CITE);
    if (!m) continue;
    const rest = m[2].trim();
    if (rest) {
      // older form: "Extrait de: Rousseau, Jean-Jacques. « Les Confessions ». Apple Books."
      const q = rest.match(/^(.*?)\.?\s*[«“"]\s*(.+?)\s*[»”"]/);
      book = q ? { author: q[1].trim(), title: q[2].replace(/[.,]$/, '').trim() } : { author: '', title: rest.replace(/\.?\s*(Apple Books|iBooks)\.?$/i, '').trim() };
    } else {
      const after = lines.slice(i + 1).map((l) => l.trim()).filter((l) => l && !COPYRIGHT_LINE.test(l));
      book = { title: after[0] || '', author: after[1] || '' };
    }
    lines.length = i;
    break;
  }
  text = lines.join('\n').trim();
  // the quotation marks put around a passage
  const pair = text.match(/^([«“"„])\s*([\s\S]*?)\s*([»”"“])$/);
  const closes = { '«': '»', '“': '”', '"': '"', '„': '“' };
  if (pair && closes[pair[1]] === pair[3] && !pair[2].includes(pair[1])) text = pair[2];
  if (book && !book.title) book = null;
  return { text, url, book };
}

// the page title that Safari shares with a selection, when it came along with the passage
function withoutTitle(text, ...titles) {
  const same = (a, b) => {
    const x = fold(a).replace(/\s+/g, ' ').trim();
    const y = fold(b).replace(/\s+/g, ' ').trim();
    return x && y && x.length < 300 && (x === y || (Math.min(x.length, y.length) > 8 && (x.includes(y) || y.includes(x))));
  };
  const lines = (text || '').split('\n');
  for (const end of ['first', 'last']) {
    const i = end === 'first' ? 0 : lines.length - 1;
    if (lines.length > 1 && titles.some((t) => t && same(lines[i], t))) lines.splice(i, 1);
    else if (lines.length === 1 && titles.some((t) => t && same(lines[0], t))) lines.length = 0;
  }
  return lines.join('\n').trim();
}

// "Les Confessions" and "Les Confessions (Édition intégrale)" are the same book
function sameTitle(a, b) {
  const key = (t) => fold(t).replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
  const x = key(a);
  const y = key(b);
  if (!x || !y) return false;
  if (x === y) return true;
  const [short, long] = x.length < y.length ? [x, y] : [y, x];
  return short.length >= 6 && long.startsWith(short + ' ');
}

// once saved, going back to the shared address does not offer the same passage again
function finishShared() {
  try {
    const kept = JSON.parse(sessionStorage.getItem('marginote.shared') || 'null');
    if (kept?.raw) sessionStorage.setItem('marginote.sharedSaved', kept.raw);
    sessionStorage.removeItem('marginote.shared');
  } catch { /* nothing kept */ }
}

// the shared text, read from the address as it is ("+" is kept as "+")
function sharedParam() {
  const m = location.hash.match(/[?&]share=([^&]*)/);
  if (!m) return null;
  try { return decodeURIComponent(m[1]); } catch { return m[1]; }
}

function sourceChoice(s, change) {
  return h('div', { class: 'book-choice' }, thumb(s),
    h('div', { class: 'main' }, h('div', { class: 't', text: s.title }), h('div', { class: 'muted' }, sourceLine(s))),
    change ? h('button', { class: 'btn small', type: 'button', onclick: change }, 'Change') : null);
}

async function viewCapture({ params }) {
  const [sources, people, topics] = await Promise.all([store.sources(), store.people(), store.topics()]);
  nav.label('Capture');
  const root = h('div', { class: 'capture' });
  let selector = null;
  const cleanup = () => { selector?.destroy(); selector = null; };
  const aboutPreset = params.get('about') ? people.filter((p) => String(p.id) === params.get('about')) : null;
  const topicPreset = params.get('topic') ? topics.filter((t) => String(t.id) === params.get('topic')).map((t) => t.name) : null;
  const carry = [aboutPreset ? `about=${params.get('about')}` : '', topicPreset ? `topic=${params.get('topic')}` : ''].filter(Boolean).join('&');
  const fromInbox = params.get('photo');
  let source = null;
  let photo = null;
  let range = null;
  let startedHere = false;     // whether "Back" leads to the first screen of this capture
  let shared = null;           // a passage shared from another app or pasted, waiting for its source
  let sharedFromStart = false;

  const leave = (left) => left || cancelButton('');
  const backTo = (fn, label = 'Back') => h('button', { class: 'link-btn', type: 'button', onclick: () => fn() }, icon('back', 20), label);
  const home = () => (shared ? stepShared(shared) : stepStart());
  const keepShared = (sh = shared) => { try { sessionStorage.setItem('marginote.shared', JSON.stringify(sh)); } catch { /* not kept */ } };
  const sharedCarry = () => (shared ? (keepShared(), '&shared=1') : '');

  // a passage and/or a link: a link goes to the page's form, a passage alone asks where it is from
  function takeShared(sh, fromStart = false) {
    if (!sh.text && !sh.url) { stepPaste('Nothing to keep in what was shared.'); return; }
    sharedFromStart = fromStart;
    if (sh.url) { keepShared(sh); stepLink(sh.url, '', sh.text, Boolean(sh.raw)); return; }
    shared = sh;
    keepShared();
    stepShared(sh);
  }

  function stepStart() {
    cleanup();
    startedHere = true;
    shared = null;
    const recent = sources.slice(0, 4);
    const paste = async () => {
      let text = '';
      try { text = await navigator.clipboard.readText(); } catch { /* not allowed: paste it by hand */ }
      if (text.trim()) takeShared(parseShared(text), true); else stepPaste();
    };
    const newRow = (ic, title, sub, onclick) => h('button', { type: 'button', class: 'pick', onclick },
      h('span', { class: 'slot small icon-slot' }, icon(ic, 26)), h('span', { class: 'main' }, h('span', { class: 't', text: title }), h('span', { class: 'a', text: sub })));
    put(root,
      bar(leave(), 'Capture'),
      h('div', { class: 'capture-start' },
        h('h1', { class: 'ask', text: 'What are you reading or watching?' }),
        aboutPreset?.length ? h('p', { class: 'note-line' }, `About ${aboutPreset[0].name}.`) : null,
        topicPreset?.length ? h('p', { class: 'note-line' }, `On ${topicPreset[0]}.`) : null,
        h('button', { class: 'btn', type: 'button', onclick: paste, style: { alignSelf: 'flex-start' } }, icon('paste', 18), 'Paste what you copied')),
      recent.length ? [h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'continue' })),
        recent.map((s) => h('button', { type: 'button', class: 'pick', onclick: () => { startedHere = true; stepSource(s); } }, thumb(s),
          h('span', { class: 'main' }, h('span', { class: 't', text: s.title }), h('span', { class: 'a' }, sourceLine(s))))),
        sources.length > recent.length ? h('button', { type: 'button', class: 'more-btn', onclick: () => stepPick((s) => stepSource(s)) }, 'Something else from the library ›') : null] : null,
      h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'something new' })),
      newRow('book', 'Book or ebook', 'Photo of a page or a screenshot; the book from its ISBN or back cover',
        () => go(`source/new?kind=book&then=capture${carry ? '&' + carry : ''}`)),
      newRow('link', 'Link', 'Article, video or podcast: paste the link, or share it from the app', () => stepLink('')),
      newRow('pen', 'Something else', 'A talk, a class, a film: type its title and who gave it',
        () => go(`source/new?kind=talk&then=capture${carry ? '&' + carry : ''}`)),
      newRow('note', 'Note', 'Your own thoughts on a person or a topic', () => go(`note/new${carry ? '?' + carry.replace('about=', 'person=') : ''}`)),
      h('div', { class: 'list-end' }),
      h('div', { class: 'pad' }, h('button', { class: 'btn', type: 'button', style: { alignSelf: 'flex-start' }, onclick: () => stepLater(null) },
        icon('inbox', 18), 'Photos to sort later')));
  }

  function stepPick(then, back) {
    cleanup();
    const q = h('input', { type: 'search', placeholder: 'Find a source', 'aria-label': 'Find a source' });
    const list = h('div');
    const draw = () => {
      const needle = fold(q.value.trim());
      put(list, sources.filter((s) => !needle || fold(`${s.title} ${makers(s).map((p) => p.name).join(' ')} ${s.publisher || ''}`).includes(needle)).map((s) =>
        h('button', { type: 'button', class: `pick${s.id === source?.id ? ' on' : ''}`, onclick: () => then(s) }, thumb(s),
          h('span', { class: 'main' }, h('span', { class: 't', text: s.title }), h('span', { class: 'a' }, sourceLine(s))))));
    };
    q.addEventListener('input', draw);
    draw();
    put(root,
      bar(back ? backTo(back) : source || startedHere ? backTo(() => (source ? stepSource(source) : home())) : leave(), 'Source'),
      h('div', { class: 'pad' }, h('label', { class: 'search' }, icon('search', 16), q),
        h('a', { class: 'btn small', href: `#/source/new?then=capture${carry ? '&' + carry : ''}${sharedCarry()}`, style: { alignSelf: 'flex-start' } }, '+ New source')),
      list);
    setTimeout(() => q.focus(), 50);
  }

  function stepSource(s) {
    cleanup();
    source = s;
    prefs.set('captureSource', s.id);
    const k = kindOf(s);
    if (!k.photos) { stepDetails(null); return; }
    const fileInput = (useCamera) => h('input', { type: 'file', accept: 'image/*', capture: useCamera ? 'environment' : null,
      'aria-label': useCamera ? 'Take a photo' : 'Choose a photo', onchange: (ev) => { const f = ev.target.files[0]; if (f) send(f); } });
    const drop = h('div', { class: 'drop wide-only' }, 'or drop a photo or a screenshot here');
    for (const t of ['dragenter', 'dragover']) drop.addEventListener(t, (ev) => { ev.preventDefault(); drop.classList.add('over'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('over'));
    drop.addEventListener('drop', (ev) => { ev.preventDefault(); drop.classList.remove('over'); const f = ev.dataTransfer.files[0]; if (f) send(f); });
    put(root,
      bar(startedHere ? backTo(home) : leave(), ''),
      h('div', { class: 'capture-start' },
        sourceChoice(s, () => stepPick((x) => stepSource(x))),
        root.dataset.error ? h('div', { class: 'error', role: 'alert', text: root.dataset.error }) : null,
        coarse()
          ? [h('label', { class: 'btn primary big file-btn' }, icon('camera', 20), 'Take a photo', fileInput(true)),
            h('label', { class: 'btn big file-btn' }, icon('image', 20), s.kind === 'ebook' ? 'Choose a screenshot' : 'Choose a photo', fileInput(false))]
          : [h('label', { class: 'btn primary big file-btn' }, icon('image', 20), 'Choose a photo or a screenshot', fileInput(false)), drop],
        h('button', { class: 'btn big', type: 'button', onclick: () => stepLater(s) }, icon('inbox', 20), 'Several pages, sort later'),
        h('button', { class: 'btn big', type: 'button', onclick: () => stepDetails(null) }, icon('pen', 20), 'Type it')));
    delete root.dataset.error;
  }

  function stepLater(s) {
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
          await api(`/api/photos?later=true${s ? `&source_id=${s.id}` : ''}`, { method: 'POST', form });
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
      bar(s ? backTo(() => stepSource(s)) : startedHere ? backTo(home) : leave(), 'Sort later',
        h('a', { class: 'link-btn strong', href: '#/inbox', onclick: (ev) => { ev.preventDefault(); nav.replace('inbox'); } }, 'Done')),
      h('div', { class: 'capture-start' },
        s ? sourceChoice(s) : h('p', { class: 'note-line', text: 'You choose the source of each page when you sort it.' }),
        coarse() ? h('label', { class: 'btn primary big file-btn' }, icon('camera', 20), 'Take a photo', input(true)) : null,
        h('label', { class: `btn big file-btn${coarse() ? '' : ' primary'}` }, icon('image', 20), 'Choose photos', input(false)),
        counter, sent));
  }

  // what was copied, pasted by hand when the browser does not let the app read it
  function stepPaste(msg = '') {
    cleanup();
    root.classList.remove('fill-screen');
    const area = h('textarea', { class: 'textarea', rows: 8, id: 'p-text' });
    const say = h('div', { class: 'note-line', role: 'alert', text: msg });
    const next = (ev) => {
      ev.preventDefault();
      const sh = parseShared(area.value);
      if (!sh.text && !sh.url) { say.textContent = 'Paste a passage or a link.'; area.focus(); return; }
      takeShared(sh, true);
    };
    put(root, h('form', { class: 'fill-form', onsubmit: next },
      bar(backTo(stepStart), 'Paste'),
      h('div', { class: 'details' },
        h('label', { class: 'field', for: 'p-text' }, h('span', { text: 'a passage, a link, or both' }), area),
        h('p', { class: 'note-line', text: coarse() ? 'Touch the box, then Paste.' : 'Click the box and paste (Ctrl+V).' }),
        say),
      h('div', { class: 'save-bar' }, h('button', { class: 'btn primary big', type: 'submit' }, 'Next'))));
    setTimeout(() => area.focus(), 50);
  }

  // a passage shared from another app, or pasted: which source is it from?
  function stepShared(sh) {
    cleanup();
    root.classList.remove('fill-screen');
    source = null;
    const useSource = (s) => { source = s; prefs.set('captureSource', s.id); stepDetails(sh.text); };
    const row = (ic, title, sub, onclick) => h('button', { type: 'button', class: 'pick', onclick },
      h('span', { class: 'slot small icon-slot' }, icon(ic, 26)),
      h('span', { class: 'main' }, h('span', { class: 't', text: title }), sub ? h('span', { class: 'a', text: sub }) : null));
    const sourcePick = (s, on) => h('button', { type: 'button', class: `pick${on ? ' on' : ''}`, onclick: () => useSource(s) }, thumb(s),
      h('span', { class: 'main' }, h('span', { class: 't', text: s.title }), h('span', { class: 'a' }, sourceLine(s))));
    const b = sh.book;   // the book Apple Books names under the passage
    const match = b ? sources.find((s) => sameTitle(s.title, b.title)) : null;
    const createBook = async (ev) => {
      const btn = ev.currentTarget;
      btn.disabled = true;
      try {
        const s = await api('/api/sources', { method: 'POST', body: { kind: 'ebook', title: b.title, people: { author: b.author ? [b.author] : [] } } });
        store.changed();
        sources.unshift(s);
        useSource(s);
      } catch (err) { btn.disabled = false; toast(err.message); }
    };
    const recent = sources.filter((s) => s !== match).slice(0, 4);
    put(root,
      bar(sharedFromStart ? backTo(stepStart) : leave(), 'Shared'),
      h('div', { class: 'capture-start' },
        h('h1', { class: 'ask', text: 'Where is it from?' }),
        h('blockquote', { class: 'shared-text', text: shorten(sh.text, 420) })),
      b ? [h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'named with the passage' })),
        match ? sourcePick(match, true) : row('book', `New ebook: ${b.title}`, b.author || 'From Apple Books', createBook)] : null,
      recent.length ? [h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'recent' })),
        recent.map((s) => sourcePick(s)),
        sources.length > recent.length ? h('button', { type: 'button', class: 'more-btn', onclick: () => stepPick(useSource, () => stepShared(sh)) }, 'Something else from the library ›') : null] : null,
      h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'something new' })),
      row('link', 'A web page, a video or a podcast', 'Paste its link; the passage is kept with it', () => stepLink('', '', sh.text)),
      row('book', 'A book, a talk, anything else', 'Type its title and who wrote it',
        () => go(`source/new?kind=${b ? 'ebook' : 'book'}&then=capture${carry ? '&' + carry : ''}${sharedCarry()}`)),
      row('note', 'Your own note', 'Keep it as a note on a person or a topic', () => go(`note/new?shared=1${carry ? '&' + carry.replace('about=', 'person=') : ''}`)),
      h('div', { class: 'list-end' }));
  }

  async function send(file) {
    put(root, bar(leave(), source.title),
      h('div', { class: 'capture-start' }, h('div', { class: 'status-line', role: 'status' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }),
        'Reading the page…')));
    try {
      const form = new FormData();
      form.append('file', await shrinkPhoto(file));
      photo = await api(`/api/photos?source_id=${source.id}`, { method: 'POST', form });
      capture.last = { photo, sourceId: source.id };
      if (!photo.words.length) { root.dataset.error = 'No text found on this photo. Take it again, closer.'; stepSource(source); return; }
      range = null;
      stepSelect();
    } catch (err) { if (err.status !== 401) { root.dataset.error = err.message; stepSource(source); } }
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
      bar(fromInbox ? cancelButton('inbox', 'Inbox') : backTo(() => stepSource(source), 'Retake'), source.title,
        h('button', { class: 'link-btn', type: 'button', onclick: () => stepDetails(null, true) }, 'Type')),
      selector.el,
      h('div', { class: 'sel-sheet' }, preview, nudgeBar(selector), next));
    root.classList.add('fill-screen');
  }

  function stepDetails(selectedText, typedWithPhoto) {
    cleanup();
    root.classList.remove('fill-screen');
    const fromPhoto = Boolean(photo && selectedText != null && !typedWithPhoto);
    const k = kindOf(source);
    let kind = fromPhoto || !(source.kind === 'video' || source.kind === 'podcast') ? 'quote' : 'comment';
    const text = h('textarea', { class: 'textarea', rows: fromPhoto ? 5 : 6, id: 'c-text', value: selectedText || '' });
    const textLabel = h('span', { text: kind === 'quote' ? 'passage' : 'comment' });
    const kindSeg = kindSwitch(() => kind, (x) => { kind = x; }, () => { textLabel.textContent = kind === 'quote' ? 'passage' : 'comment'; });
    const fields = entryFields({ source, sources, people, topics, about: aboutPreset?.length ? [...source.people.about, ...aboutPreset.filter((p) => !source.people.about.some((a) => a.id === p.id))] : null,
      topicNames: topicPreset?.length ? [...new Set([...source.topics.map((t) => t.name), ...topicPreset])] : null });
    const saveBtn = h('button', { class: 'btn primary big', type: 'submit' }, 'Save');
    const save = async (ev) => {
      ev.preventDefault();
      if (!text.value.trim()) { text.focus(); toast('The text is empty'); return; }
      saveBtn.disabled = true;
      try {
        const body = { ...fields.values(), kind, text: text.value };
        if (fromPhoto) Object.assign(body, { photo_id: photo.id, word_start: range.start, word_end: range.end });
        const e = await api('/api/entries', { method: 'POST', body });
        prefs.set('captureSource', body.source_id);
        store.changed();
        if (fromInbox) {
          nav.replace('inbox');
          toast('Saved', { label: 'Another from this page', run: () => go(`capture?photo=${photo.id}`) });
        } else {
          if (shared) finishShared();
          nav.flash = { entry: e.id };
          nav.finish(`source/${body.source_id}`);
          toast('Saved', fromPhoto ? { label: 'Another from this page', run: () => go('capture?again=1') } : null);
        }
      } catch (err) { saveBtn.disabled = false; toast(err.message); }
    };
    const back = fromPhoto ? backTo(stepSelect, 'Passage') : photo && typedWithPhoto ? backTo(stepSelect) : shared ? backTo(home)
      : k.photos ? backTo(() => stepSource(source)) : startedHere ? backTo(home) : leave();
    put(root, h('form', { onsubmit: save, class: 'fill-form' },
      bar(back, shorten(source.title, 32)),
      h('div', { class: 'details' },
        k.link && !photo ? sourceChoice(source, shared
          ? () => { shared.text = text.value; stepPick((s) => { source = s; stepDetails(shared.text); }, () => stepDetails(shared.text)); }
          : () => stepPick((s) => { source = s; stepSource(s); })) : null,
        fromPhoto ? null : kindSeg,
        h('label', { class: 'field', for: 'c-text' }, textLabel, text),
        source.url && !photo ? h('a', { class: 'filter ink', href: source.url, target: '_blank', rel: 'noopener noreferrer' }, `open the ${source.kind === 'article' ? 'article' : source.kind} ›`) : null,
        fields.els),
      h('div', { class: 'save-bar' }, saveBtn)));
    const pageInput = document.getElementById('f-page');
    if (pageInput && photo?.detected_page && fromPhoto && !pageInput.value) pageInput.value = photo.detected_page;
    if (!fromPhoto && !selectedText) setTimeout(() => text.focus(), 50);
  }

  // a link shared from another app, the bookmark, or pasted: the page is read, then the quote is saved with it
  async function stepLink(url, title = '', quoted = '', fromShortcut = false) {
    cleanup();
    root.classList.remove('fill-screen');
    if (!url) {
      const input = h('input', { class: 'input', type: 'url', id: 'l-url', placeholder: 'https://…', autocapitalize: 'none', autocorrect: 'off', inputmode: 'url' });
      const msg = h('div', { class: 'note-line', role: 'alert' });
      put(root, h('form', { onsubmit: (ev) => { ev.preventDefault(); if (input.value.trim()) stepLink(input.value.trim(), title, quoted); else msg.textContent = 'Paste or type a link'; } },
        bar(startedHere || shared ? backTo(home) : leave(), 'Link'),
        h('div', { class: 'details' },
          quoted ? h('blockquote', { class: 'shared-text', text: shorten(quoted, 300) }) : null,
          h('label', { class: 'field', for: 'l-url' }, h('span', { text: 'link to the article, video or podcast' }), input),
          h('div', { class: 'row-btns' },
            h('button', { class: 'btn small', type: 'button', onclick: async () => {
              try { input.value = (await navigator.clipboard.readText()).trim(); } catch { msg.textContent = 'Pasting is not allowed here: long-press the field and choose Paste.'; }
            } }, 'Paste')),
          msg,
          h('button', { class: 'btn primary big', type: 'submit' }, 'Next'))));
      setTimeout(() => input.focus(), 50);
      return;
    }
    put(root, bar(leave(), 'Link'), h('div', { class: 'capture-start' },
      h('div', { class: 'status-line', role: 'status' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }), 'Reading the page…')));
    let info;
    try {
      info = await api('/api/lookup/link', { method: 'POST', body: { url } });
    } catch (err) {
      if (err.status === 401) return;
      info = { url, kind: 'article', title: null, site: null, people: [], date: null, note: err.message };
    }
    if (info.existing) source = sources.find((s) => s.id === info.existing.id) || await api(`/api/sources/${info.existing.id}`);
    // Safari shares the page title along with the selection
    quoted = withoutTitle(quoted, title, info.title, info.existing ? source.title : null);
    if (fromShortcut && !info.existing && !info.title && !title) {
      // the page could not be read: its title is then the short first line Safari sent
      const lines = quoted.split('\n');
      if (lines.length > 1 && lines[0].trim().length <= 160) { title = lines[0].trim(); quoted = lines.slice(1).join('\n').trim(); }
    }
    if (info.existing) {
      linkForm(null, quoted, info.note);
    } else {
      linkForm(info, quoted, info.note, title);
    }
  }

  function linkForm(info, quoted, note, pageTitle) {
    // info: details of a new source to create; null when the link is already in the library (source is set)
    let kind = quoted ? 'quote' : 'comment';
    let sourceKind = info?.kind || source?.kind;
    const text = h('textarea', { class: 'textarea', rows: 5, id: 'c-text', value: quoted || '' });
    const textLabel = h('span', { text: kind === 'quote' ? 'passage' : 'comment' });
    const kindSeg = kindSwitch(() => kind, (x) => { kind = x; }, () => { textLabel.textContent = kind === 'quote' ? 'passage' : 'comment'; });
    const title = field('l-title', 'title', { required: true }, info ? info.title || pageTitle || '' : '');
    const site = field('l-site', 'site', {}, info?.site || '');
    const date = field('l-date', 'date', { placeholder: '2026-10-02', inputmode: 'numeric' }, info?.date || '');
    const makersIn = peopleInput('author(s)', [], people, { id: 'l-makers' });
    for (const name of info?.people || []) makersIn.items.push({ key: 'new:' + fold(name), label: name, value: name });
    makersIn.set(makersIn.items);
    const setKind = (k2) => {
      sourceKind = k2;
      site.el.firstChild.textContent = KINDS[k2].publisher;
      makersIn.el.querySelector('.label').textContent = KINDS[k2].makerLabel;
    };
    const pseudo = source || { id: 0, kind: sourceKind, people: { about: [] }, topics: [] };
    const fields = entryFields({ source: pseudo, sources: source ? sources : [{ ...pseudo, title: 'this new source' }], people, topics,
      about: aboutPreset?.length ? aboutPreset : null, topicNames: topicPreset?.length ? topicPreset : null });
    const saveBtn = h('button', { class: 'btn primary big', type: 'submit' }, 'Save');
    const save = async (ev) => {
      ev.preventDefault();
      if (!text.value.trim()) { text.focus(); toast('The text is empty'); return; }
      if (info && !title.input.value.trim()) { title.input.focus(); toast('Give it a title'); return; }
      saveBtn.disabled = true;
      try {
        let sid = source?.id;
        const values = fields.values();
        delete values.page;
        if (!source) {
          // a new article or video: whom and what it is about are said of it, so its later quotes follow
          const s = await api('/api/sources', { method: 'POST', body: {
            kind: sourceKind, title: title.input.value, url: info.url, publisher: site.input.value, date: date.input.value,
            language: info.language, cover_url: info.image_url,
            people: { [KINDS[sourceKind].maker]: makersIn.value, about: fields.about() }, topics: fields.topics(),
          } });
          sid = s.id;
          delete values.about;
          delete values.topics;
        }
        const e = await api('/api/entries', { method: 'POST', body: { ...values, source_id: sid, kind, text: text.value } });
        store.changed();
        finishShared();
        nav.flash = { entry: e.id, cover: info?.image_url ? sid : null };
        nav.replace(`source/${sid}`);
        toast('Saved');
      } catch (err) { saveBtn.disabled = false; toast(err.message); }
    };
    if (info) setKind(sourceKind);
    put(root, h('form', { onsubmit: save, class: 'fill-form' },
      bar(startedHere || shared ? backTo(home) : leave(), source ? 'In your library' : 'New source'),
      h('div', { class: 'details' },
        note ? h('div', { class: 'note-line', role: 'status', text: `${note}. Type the details in.` }) : null,
        source ? sourceChoice(source) : [
          segmented('Kind of source', [['article', 'Article'], ['video', 'Video'], ['podcast', 'Podcast']], sourceKind, setKind),
          title.el,
          h('div', { class: 'two' }, h('div', { class: 'grow' }, site.el), h('div', { style: { width: '130px' } }, date.el)),
          makersIn.el,
          h('p', { class: 'note-line link-line', text: info.url })],
        h('hr', { class: 'rule' }),
        kindSeg,
        h('label', { class: 'field', for: 'c-text' }, textLabel, text),
        fields.els.slice(1)),
      h('div', { class: 'save-bar' }, saveBtn)));
    if (!quoted) setTimeout(() => text.focus(), 50);
  }

  if (fromInbox) {
    photo = await api(`/api/photos/${encodeURIComponent(fromInbox)}`);
    if (photo.status !== 'ready') { toast('This page is still being read'); nav.replace('inbox'); return null; }
    source = sources.find((s) => s.id === photo.source_id);
    if (source) stepSelect();
    else stepPick(async (s) => { source = s; await api(`/api/photos/${photo.id}`, { method: 'PATCH', body: { source_id: s.id } }).catch(() => null); stepSelect(); });
  } else if (params.has('share')) {
    // from the iPhone Shortcut: whatever another app shared (a passage, a link, or both)
    const raw = sharedParam();
    let saved = null;
    try { saved = sessionStorage.getItem('marginote.sharedSaved'); } catch { /* none */ }
    if (raw && raw === saved) stepStart();
    else takeShared({ ...parseShared(raw), raw });
  } else if (params.get('u') || params.get('url')) {
    stepLink(params.get('u') || params.get('url'), params.get('t') || '', params.get('q') || '');
  } else if (params.get('again') && capture.last) {
    photo = capture.last.photo;
    source = sources.find((s) => s.id === capture.last.sourceId);
    if (source) stepSelect(); else stepStart();
  } else if (params.get('source')) {
    const s = sources.find((x) => String(x.id) === params.get('source')) || await api(`/api/sources/${params.get('source')}`);
    try { shared = params.get('shared') ? JSON.parse(sessionStorage.getItem('marginote.shared')) : null; } catch { shared = null; }
    if (shared?.text) { source = s; stepDetails(shared.text); } else { shared = null; stepSource(s); }
  } else {
    stepStart();
  }
  return { el: root, bare: true, cleanup };
}

async function viewInbox() {
  const photos = await api('/api/photos');
  nav.label('Inbox');
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
  if (photos.some((p) => p.status === 'reading')) {   // check again until every page is read
    const mark = location.hash;
    setTimeout(() => { if (location.hash === mark) render(); }, 3000);
  }
  const el = h('div', {},
    h('header', { class: 'top' }, h('div', { class: 'top-row' }, h('h1', {}, 'Inbox', h('span', { class: 'count', text: photos.length })))),
    photos.length ? [h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'pages to sort' })),
      photos.map((p) => h('div', { class: 'inbox-row' },
        h('img', { class: 'thumb', src: p.thumb_url, alt: '', loading: 'lazy' }),
        h('div', { class: 'main' },
          h('span', { class: 't', text: p.source_title || 'No source yet' }),
          h('span', { class: 'a' }, joinDots([
            p.detected_page ? `p. ${p.detected_page}` : null,
            p.status === 'reading' ? h('i', { text: 'being read…' }) : null,
            p.status === 'failed' ? h('i', { class: 'bad', text: 'could not be read' }) : null,
            p.entry_count ? plural(p.entry_count, 'quote') + ' saved' : null,
            fullDate(p.created_at),
          ])),
          h('div', { class: 'actions' },
            p.status === 'ready' ? h('a', { class: 'btn primary small', href: `#/capture?photo=${p.id}` }, 'Sort') : null,
            h('button', { class: 'btn small', type: 'button', onclick: () => done(p) }, p.entry_count ? 'Done' : 'Remove…'))))),
      h('div', { class: 'list-end' })]
      : h('div', { class: 'empty' }, 'Nothing to sort.', h('a', { class: 'btn', href: '#/capture' }, 'Capture')));
  return { el, nav: 'inbox' };
}

// ----- adding or editing a source -----

async function viewSourceForm({ args: [id], params }) {
  const editing = id != null;
  const [source, sources, people, topics] = await Promise.all([editing ? api(`/api/sources/${id}`) : null, store.sources(), store.people(), store.topics()]);
  nav.label(editing ? 'Edit' : 'New source');
  let kind = source?.kind || (KINDS[params.get('kind')] ? params.get('kind') : 'book');
  let coverUrl = null;
  const s = source || { people: { author: [], speaker: [], translator: [], editor: [], about: [] }, topics: [] };
  const aboutPreset = params.get('about') ? people.filter((p) => String(p.id) === params.get('about')) : [];
  const topicPreset = params.get('topic') ? topics.filter((t) => String(t.id) === params.get('topic')).map((t) => t.name) : [];
  const carry = ['about', 'topic', 'shared'].filter((k) => params.get(k)).map((k) => `&${k}=${params.get(k)}`).join('');
  const isbn = field('s-isbn', 'isbn', { inputmode: 'numeric', autocomplete: 'off' }, s.isbn);
  const url = field('s-url', 'link', { type: 'url', inputmode: 'url', autocapitalize: 'none', autocorrect: 'off', placeholder: 'https://…' }, s.url);
  const title = field('s-title', 'title', { required: true, autocapitalize: 'sentences' }, s.title);
  const subtitle = field('s-subtitle', 'subtitle', {}, s.subtitle);
  const fields = [...new Set(sources.map((x) => x.field).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  const fieldIn = field('s-field', 'kind of work', { list: 'fields', autocomplete: 'off', autocapitalize: 'sentences', placeholder: 'Philosophie, Roman, Histoire…' }, s.field);
  const publisher = field('s-publisher', 'publisher', {}, s.publisher);
  const edition = field('s-edition', 'edition', {}, s.edition);
  const year = field('s-year', 'year', { inputmode: 'numeric' }, s.year);
  const date = field('s-date', 'date', { inputmode: 'numeric', placeholder: '2026-10-02' }, s.date);
  const makersIn = peopleInput('author(s)', [...s.people.author, ...s.people.speaker], people, { id: 's-makers' });
  const translators = peopleInput('translator(s)', s.people.translator, people, { id: 's-translators' });
  const editors = peopleInput('editor(s)', s.people.editor, people, { id: 's-editors' });
  const about = peopleInput('about (people)', [...s.people.about, ...aboutPreset.filter((p) => !s.people.about.some((a) => a.id === p.id))], people,
    { id: 's-about', placeholder: 'who it is about' });
  const topicsIn = topicsInput('topics', [...new Set([...s.topics.map((t) => t.name), ...topicPreset])], topics, { id: 's-topics' });
  const language = h('select', { class: 'select', id: 's-language' },
    h('option', { value: '' }, '—'), h('option', { value: 'fr' }, 'French'), h('option', { value: 'en' }, 'English'), h('option', { value: 'other' }, 'Other'));
  language.value = ['fr', 'en', ''].includes(s.language || '') ? (s.language || '') : 'other';
  const msg = h('div', { class: 'note-line', role: 'status' });
  const found = (existing) => (existing && existing.id !== s.id ? [' Already in your library: ', h('a', { class: 'plink', href: `#/source/${existing.id}`, text: existing.title })] : []);

  const lookUp = async (prefix = '') => {
    put(msg, `${prefix}Looking up…`);
    try {
      const f = await api(`/api/lookup/isbn/${encodeURIComponent(isbn.input.value)}`);
      for (const [key, input] of Object.entries({ title, subtitle, publisher, year })) if (f[key]) input.input.value = f[key];
      if (f.people?.author?.length) makersIn.set(f.people.author.map((n) => ({ key: 'new:' + fold(n), label: n, value: n })));
      if (f.people?.translator?.length) translators.set(f.people.translator.map((n) => ({ key: 'new:' + fold(n), label: n, value: n })));
      if (f.language) language.value = ['fr', 'en'].includes(f.language) ? f.language : 'other';
      put(msg, `${prefix}Found on ${f.source}.`, found(f.existing));
    } catch (err) { put(msg, prefix + err.message); }
  };
  const readPage = async () => {
    put(msg, 'Reading the page…');
    try {
      const f = await api('/api/lookup/link', { method: 'POST', body: { url: url.input.value } });
      url.input.value = f.url;
      if (f.note) { put(msg, `${f.note}. Type the details in.`, found(f.existing)); return; }
      if (!editing && KINDS[f.kind]) { kind = f.kind; layout(); }
      if (f.title) title.input.value = f.title;
      if (f.site) publisher.input.value = f.site;
      if (f.date) date.input.value = f.date;
      if (f.people?.length) makersIn.set(f.people.map((n) => ({ key: 'new:' + fold(n), label: n, value: n })));
      if (f.language) language.value = ['fr', 'en'].includes(f.language) ? f.language : 'other';
      coverUrl = f.image_url;
      put(msg, 'Details read from the page.', found(f.existing));
    } catch (err) { put(msg, err.message); }
  };
  const backCover = h('input', { type: 'file', accept: 'image/*', capture: 'environment', 'aria-label': 'Photo of the back cover',
    onchange: async (ev) => {
      const f = ev.target.files[0];
      ev.target.value = '';
      if (!f) return;
      put(msg, 'Reading the barcode…');
      try {
        const form = new FormData();
        form.append('file', await shrinkPhoto(f));
        const r = await api('/api/lookup/isbn-photo', { method: 'POST', form });
        isbn.input.value = r.isbn;
        await lookUp(r.found_by === 'barcode' ? 'Barcode read. ' : 'ISBN read. ');
      } catch (err) { put(msg, err.message); }
    } });
  const isbnRow = h('div', { class: 'two' }, h('div', { class: 'grow' }, isbn.el),
    h('button', { class: 'btn small', type: 'button', onclick: () => lookUp() }, 'Look up'),
    h('label', { class: 'btn small file-btn' }, icon('camera', 16), 'Back cover', backCover));
  const urlRow = h('div', { class: 'two' }, h('div', { class: 'grow' }, url.el), h('button', { class: 'btn small', type: 'button', onclick: readPage }, 'Read the page'));
  const editionBox = h('div', { class: 'grow' }, edition.el);
  const bookOnly = [subtitle.el, translators.el, editors.el, editionBox];
  const yearBox = h('div', { style: { width: '110px' } }, year.el);
  const dateBox = h('div', { style: { width: '130px' } }, date.el);
  const kindSeg = h('div', { class: 'kind-picker', role: 'group', 'aria-label': 'Kind of source' });

  function layout() {
    const k = KINDS[kind];
    put(kindSeg, Object.entries(KINDS).map(([key, v]) => h('button', { type: 'button', class: key === kind ? 'on' : '', 'aria-pressed': key === kind ? 'true' : 'false',
      onclick: () => { kind = key; layout(); } }, v.name)));
    isbnRow.hidden = !(kind === 'book' || kind === 'ebook');
    urlRow.hidden = !(k.link || source?.url || kind === 'ebook');
    for (const el of bookOnly) el.hidden = !(kind === 'book' || kind === 'ebook');
    yearBox.hidden = Boolean(k.dated);
    dateBox.hidden = !k.dated;
    publisher.el.firstChild.textContent = k.publisher;
    makersIn.el.querySelector('.label').textContent = k.makerLabel;
  }
  layout();

  const payload = () => {
    const y = year.input.value.trim();
    const lang = language.value === 'other' ? (s.language && !['fr', 'en'].includes(s.language) ? s.language : null) : language.value || null;
    const k = KINDS[kind];
    const roles = { author: k.maker === 'author' ? makersIn.value : [], speaker: k.maker === 'speaker' ? makersIn.value : [], about: about.value };
    if (kind === 'book' || kind === 'ebook') Object.assign(roles, { translator: translators.value, editor: editors.value });
    return { kind, title: title.input.value, subtitle: subtitle.input.value, publisher: publisher.input.value, edition: edition.input.value,
      year: !k.dated && y ? Number(y) : null, date: k.dated ? date.input.value : null, isbn: isbnRow.hidden ? null : isbn.input.value,
      url: url.input.value, language: lang, field: fieldIn.input.value, people: roles, topics: topicsIn.value };
  };
  const save = async (ev) => {
    ev.preventDefault();
    put(msg);
    const body = payload();
    if (body.year != null && !Number.isInteger(body.year)) { put(msg, 'The year must be a number'); return; }
    try {
      if (editing) {
        await api(`/api/sources/${id}`, { method: 'PATCH', body });
        store.changed();
        toast('Saved');
        nav.finish(`source/${id}`);
      } else {
        const created = await api('/api/sources', { method: 'POST', body: { ...body, cover_url: coverUrl } });
        store.changed();
        if (params.get('then') === 'capture') nav.replace(`capture?source=${created.id}${carry}`);
        else {
          nav.flash = { cover: created.cover_pending ? created.id : null };
          nav.replace(`source/${created.id}`);
        }
      }
    } catch (err) { put(msg, err.message); }
  };

  let coverBox = null;
  if (editing) {
    const coverSlot = h('span', {}, thumb(source, 'large'));
    const coverMsg = h('div', { class: 'note-line', role: 'status' });
    const own = h('input', { type: 'file', accept: 'image/*', 'aria-label': 'Use my own picture', onchange: async (ev) => {
      const f = ev.target.files[0];
      if (!f) return;
      coverMsg.textContent = 'Sending…';
      try {
        const form = new FormData();
        form.append('file', await shrinkPhoto(f));
        const b = await api(`/api/sources/${id}/cover`, { method: 'POST', form });
        put(coverSlot, thumb(b, 'large'));
        coverMsg.textContent = 'Picture saved.';
        store.changed();
      } catch (err) { coverMsg.textContent = err.message; }
    } });
    coverBox = h('div', { class: 'cover-box' }, coverSlot, h('div', { class: 'info' },
      h('span', { class: 'label', text: kind === 'video' || kind === 'podcast' ? 'picture' : 'cover' }),
      h('button', { class: 'btn small', type: 'button', onclick: async () => {
        coverMsg.textContent = 'Looking online…';
        try {
          const b = await api(`/api/sources/${id}/cover/fetch`, { method: 'POST' });
          put(coverSlot, thumb(b, 'large'));
          coverMsg.textContent = 'Found.';
          store.changed();
        } catch (err) { coverMsg.textContent = err.message; }
      } }, 'Find online'),
      h('label', { class: 'btn small file-btn' }, 'Use my picture', own), coverMsg));
  }

  const el = h('form', { onsubmit: save },
    h('datalist', { id: 'fields' }, fields.map((x) => h('option', { value: x }))),
    bar(cancelButton(editing ? `source/${id}` : ''), editing ? 'Edit' : 'New source', h('button', { class: 'link-btn strong', type: 'submit' }, 'Save')),
    h('div', { class: 'details' },
      kindSeg,
      coverBox,
      isbnRow, urlRow,
      msg,
      title.el, subtitle.el,
      makersIn.el, translators.el,
      about.el, topicsIn.el,
      h('div', { class: 'two' }, h('div', { class: 'grow' }, publisher.el), yearBox, dateBox),
      fieldIn.el,
      h('div', { class: 'two' }, editionBox, h('label', { class: 'field grow', for: 's-language' }, h('span', { text: 'language' }), language)),
      editors.el,
      h('button', { class: 'btn primary big', type: 'submit' }, editing ? 'Save' : 'Add it')));
  if (!editing) setTimeout(() => (isbnRow.hidden ? (urlRow.hidden ? title.input : url.input) : isbn.input).focus(), 50);
  return { el, bare: !isWide(), nav: 'library' };
}

// ----- editing a person or a topic -----

async function viewPersonForm({ args: [id] }) {
  const [data, people] = await Promise.all([api(`/api/people/${id}`), store.people(true)]);
  const p = data.person;
  nav.label('Edit');
  const name = field('p-name', 'name, as usually written', { required: true }, p.name);
  const sort = field('p-sort', 'in an index', {}, p.sort_name);
  const dates = field('p-dates', 'dates', { placeholder: '1632–1677' }, p.dates);
  const aliases = h('textarea', { class: 'textarea', rows: 3, id: 'p-aliases', value: p.aliases.join('\n') });
  const msg = h('div', { class: 'note-line', role: 'alert' });
  const save = async (ev) => {
    ev.preventDefault();
    try {
      await api(`/api/people/${id}`, { method: 'PATCH', body: { name: name.input.value, sort_name: sort.input.value, dates: dates.input.value,
        aliases: aliases.value.split('\n') } });
      store.changed();
      toast('Saved');
      nav.finish(`person/${id}`);
    } catch (err) { msg.textContent = err.message; }
  };
  const others = people.filter((x) => x.id !== p.id);
  const mergeSel = h('select', { class: 'select', id: 'p-merge' }, h('option', { value: '' }, '—'),
    others.map((x) => h('option', { value: String(x.id) }, `${x.sort_name}${x.entries ? ` (${plural(x.entries, 'entry')})` : ''}`)));
  const merge = async () => {
    const other = others.find((x) => String(x.id) === mergeSel.value);
    if (!other) { msg.textContent = 'Choose who this is'; return; }
    const keep = await confirmDialog({ title: 'The same person?', text: `${p.name} and ${other.name} become one. Which name stays? The other is kept as another spelling.`,
      choices: [{ label: other.name, value: 'other', primary: true }, { label: p.name, value: 'this' }] });
    if (!keep) return;
    try {
      const [from, into] = keep === 'other' ? [p.id, other.id] : [other.id, p.id];
      await api(`/api/people/${from}/merge`, { method: 'POST', body: { into } });
      store.changed();
      toast('Merged');
      nav.replace(`person/${into}`);
    } catch (err) { msg.textContent = err.message; }
  };
  const remove = async () => {
    const ok = await confirmDialog({ title: `Remove ${p.name}?`, text: 'They are taken off every source, quote and note. Those stay.',
      choices: [{ label: 'Remove this person', value: true, danger: true }] });
    if (!ok) return;
    try {
      await api(`/api/people/${id}`, { method: 'DELETE' });
      store.changed();
      nav.replace('?view=people');
    } catch (err) { msg.textContent = err.message; }
  };
  const el = h('form', { onsubmit: save },
    bar(cancelButton(`person/${id}`), 'Edit person', h('button', { class: 'link-btn strong', type: 'submit' }, 'Save')),
    h('div', { class: 'details' },
      name.el, sort.el, dates.el,
      h('label', { class: 'field', for: 'p-aliases' }, h('span', { text: 'other spellings, one per line' }), aliases),
      msg,
      h('button', { class: 'btn primary big', type: 'submit' }, 'Save'),
      h('hr', { class: 'rule' }),
      h('label', { class: 'field', for: 'p-merge' }, h('span', { text: 'the same person as' }), mergeSel),
      h('button', { class: 'btn small', type: 'button', style: { alignSelf: 'flex-start' }, onclick: merge }, 'Merge…'),
      h('button', { class: 'btn small danger', type: 'button', style: { alignSelf: 'flex-start' }, onclick: remove }, 'Remove this person…')));
  return { el, bare: !isWide(), nav: 'library' };
}

async function viewTopicForm({ args: [id] }) {
  const data = await api(`/api/topics/${id}`);
  nav.label('Edit');
  const name = field('t-name', 'name', { required: true, autocapitalize: 'none' }, data.topic.name);
  const msg = h('div', { class: 'note-line', role: 'alert' });
  const save = async (ev) => {
    ev.preventDefault();
    try {
      const t = await api(`/api/topics/${id}`, { method: 'PATCH', body: { name: name.input.value } });
      store.changed();
      toast(t.id !== Number(id) ? `Merged into ${t.name}` : 'Saved');
      if (t.id !== Number(id)) nav.replace(`topic/${t.id}`); else nav.finish(`topic/${id}`);
    } catch (err) { msg.textContent = err.message; }
  };
  const remove = async () => {
    const ok = await confirmDialog({ title: `Remove the topic ${data.topic.name}?`, text: 'It is taken off every quote, source and note. Those stay.',
      choices: [{ label: 'Remove the topic', value: true, danger: true }] });
    if (!ok) return;
    try { await api(`/api/topics/${id}`, { method: 'DELETE' }); store.changed(); nav.replace('?view=topics'); } catch (err) { msg.textContent = err.message; }
  };
  const el = h('form', { onsubmit: save },
    bar(cancelButton(`topic/${id}`), 'Edit topic', h('button', { class: 'link-btn strong', type: 'submit' }, 'Save')),
    h('div', { class: 'details' }, name.el,
      h('p', { class: 'note-line', text: 'Giving it the name of another topic merges the two.' }),
      msg,
      h('button', { class: 'btn primary big', type: 'submit' }, 'Save'),
      h('button', { class: 'btn small danger', type: 'button', style: { alignSelf: 'flex-start' }, onclick: remove }, 'Remove this topic…')));
  return { el, bare: !isWide(), nav: 'library' };
}

// ----- your notes -----

async function viewNotes({ params }) {
  let q = params.get('q') || '';
  let notes = await api(`/api/notes${q ? `?q=${encodeURIComponent(q)}` : ''}`);
  nav.label('Notes');
  const list = h('div');
  const input = h('input', { type: 'search', placeholder: 'Search your notes', 'aria-label': 'Search your notes', value: q, enterkeyhint: 'search' });
  const draw = () => put(list, notes.length ? [notes.map((n) => noteBlock(n)), h('div', { class: 'list-end' })]
    : h('div', { class: 'empty' }, q ? 'No note contains these words.' : 'Your own thoughts on a person or a topic go here.',
      q ? null : h('a', { class: 'btn primary', href: '#/note/new' }, 'Write a note')));
  input.addEventListener('input', debounce(async () => {
    q = input.value.trim();
    history.replaceState(null, '', q ? `#/notes?q=${encodeURIComponent(q)}` : '#/notes');
    const top = nav.stack[nav.stack.length - 1];
    if (top) { top.hash = location.hash; nav.save(); }
    try { notes = await api(`/api/notes${q ? `?q=${encodeURIComponent(q)}` : ''}`); draw(); } catch (err) { put(list, errorBox(err)); }
  }, 300));
  draw();
  const el = h('div', {},
    h('header', { class: 'top' },
      h('div', { class: 'top-row' }, h('h1', {}, 'Notes', h('span', { class: 'count', text: notes.length })),
        h('a', { class: 'icon-btn', href: '#/note/new', 'aria-label': 'Write a note' }, icon('plus', 22))),
      h('label', { class: 'search' }, icon('search', 16), input)),
    h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'note · most recent first' })),
    list);
  return { el, nav: 'notes' };
}

async function viewNote({ args: [id] }) {
  const n = await api(`/api/notes/${id}`);
  nav.label(shorten(n.title || 'Note', 24));
  const del = async () => {
    const ok = await confirmDialog({ title: 'Delete this note?', text: 'This cannot be undone.', choices: [{ label: 'Delete the note', value: true, danger: true }] });
    if (!ok) return;
    try { await api(`/api/notes/${id}`, { method: 'DELETE' }); store.changed(); toast('Note deleted'); nav.back('notes'); } catch (err) { toast(err.message); }
  };
  const el = h('div', {},
    bar(backButton('notes', 'Notes'), '', h('a', { class: 'link-btn', href: `#/note/${id}/edit` }, 'Edit')),
    h('article', { class: 'entry-page note-page' },
      n.title ? h('h1', { text: n.title }) : null,
      h('div', { class: 'kv' }, joinDots([fullDate(n.created_at), n.updated_at !== n.created_at ? `changed ${fullDate(n.updated_at)}` : null])),
      h('p', { class: 'note-body', text: n.text }),
      n.people.length ? h('p', { class: 'kv-line' }, h('span', { class: 'label', text: 'on ' }), personLinks(n.people)) : null,
      n.topics.length ? topicLinks(n.topics) : null,
      n.entries.length ? [h('div', { class: 'colhead flush' }, h('span', { text: 'refers to' })), n.entries.map((e) => entryRow(e, { showSource: true }))] : null,
      h('div', { class: 'row-btns' },
        h('a', { class: 'btn small', href: `#/note/${id}/edit` }, 'Edit'),
        h('button', { class: 'btn small danger', type: 'button', onclick: del }, 'Delete…'))));
  return { el, nav: 'notes' };
}

async function viewNoteForm({ args: [id], params }) {
  const editing = id != null;
  const [note, people, topics] = await Promise.all([editing ? api(`/api/notes/${id}`) : null, store.people(), store.topics()]);
  nav.label(editing ? 'Edit' : 'New note');
  const n = note || { title: '', text: '', people: [], topics: [], entries: [] };
  if (!editing) {
    const person = people.find((p) => String(p.id) === params.get('person'));
    const topic = topics.find((t) => String(t.id) === params.get('topic'));
    if (person) n.people = [person];
    if (topic) n.topics = [topic];
    if (params.get('shared')) {
      try { n.text = JSON.parse(sessionStorage.getItem('marginote.shared'))?.text || ''; } catch { /* nothing kept */ }
    }
    if (params.get('entry')) {
      const e = await api(`/api/entries/${params.get('entry')}`).catch(() => null);
      if (e) {
        n.entries = [e];
        if (!n.people.length) n.people = e.about.length ? e.about : e.by ? [e.by] : [];
        if (!n.topics.length) n.topics = e.topics;
      }
    }
  }
  let linked = [...n.entries];
  const title = field('n-title', 'title, if you want one', {}, n.title);
  const text = h('textarea', { class: 'textarea note-input', rows: 10, id: 'n-text', value: n.text });
  const peopleIn = peopleInput('people', n.people, people, { id: 'n-people', placeholder: 'who it is about' });
  const topicsIn = topicsInput('topics', n.topics.map((t) => t.name), topics, { id: 'n-topics' });
  const linkedBox = h('div');
  const finder = h('div', { class: 'finder', hidden: true });
  const findInput = h('input', { type: 'search', placeholder: 'Words of the quote, its source, a person', 'aria-label': 'Find a quote or comment' });
  const found = h('div');
  findInput.addEventListener('input', debounce(async () => {
    const q = findInput.value.trim();
    if (q.length < 2) { put(found); return; }
    try {
      const hits = await api(`/api/search?q=${encodeURIComponent(q)}&limit=12`);
      put(found, hits.filter((e) => !linked.some((x) => x.id === e.id)).map((e) => h('button', { type: 'button', class: 'pick',
        onclick: () => { linked.push(e); drawLinked(); finder.hidden = true; findInput.value = ''; put(found); } },
      h('span', { class: 'main' }, h('span', { class: 'txt2', text: shorten(e.text, 140) }), h('span', { class: 'a', text: `${e.source.title}${e.page ? ', ' + where(e) : ''}` })))));
    } catch (err) { put(found, errorBox(err)); }
  }, 300));
  put(finder, h('label', { class: 'search' }, icon('search', 16), findInput), found);
  function drawLinked() {
    put(linkedBox, linked.map((e) => h('div', { class: 'linked-row' },
      h('span', { class: 'main' }, h('span', { class: 'txt2', text: shorten(e.text, 110) }), h('span', { class: 'a', text: `${e.source.title}${e.page ? ', ' + where(e) : ''}` })),
      h('button', { type: 'button', class: 'x', 'aria-label': 'Remove this reference', onclick: () => { linked = linked.filter((x) => x !== e); drawLinked(); } }, '×'))));
  }
  drawLinked();
  const msg = h('div', { class: 'note-line', role: 'alert' });
  const save = async (ev) => {
    ev.preventDefault();
    if (!text.value.trim()) { text.focus(); msg.textContent = 'The note is empty'; return; }
    const body = { title: title.input.value, text: text.value, people: peopleIn.value, topics: topicsIn.value, entries: linked.map((e) => e.id) };
    try {
      if (editing) {
        await api(`/api/notes/${id}`, { method: 'PATCH', body });
        store.changed();
        toast('Saved');
        nav.finish(`note/${id}`);
      } else {
        const created = await api('/api/notes', { method: 'POST', body });
        store.changed();
        if (params.get('shared')) finishShared();
        toast('Note saved');
        if (nav.prev() && (params.get('person') || params.get('topic') || params.get('entry'))) nav.back(`note/${created.id}`);
        else nav.replace(`note/${created.id}`);
      }
    } catch (err) { msg.textContent = err.message; }
  };
  const el = h('form', { onsubmit: save },
    bar(cancelButton(editing ? `note/${id}` : 'notes'), editing ? 'Edit note' : 'New note', h('button', { class: 'link-btn strong', type: 'submit' }, 'Save')),
    h('div', { class: 'details' },
      title.el,
      h('label', { class: 'field', for: 'n-text' }, h('span', { text: 'note' }), text),
      topicsIn.el, peopleIn.el,
      h('div', { class: 'field' }, h('span', { class: 'label', text: 'refers to (optional)' }), linkedBox,
        h('button', { type: 'button', class: 'btn small', style: { alignSelf: 'flex-start', marginTop: '6px' },
          onclick: () => { finder.hidden = !finder.hidden; if (!finder.hidden) findInput.focus(); } }, '+ Link a quote or comment'), finder),
      h('p', { class: 'note-line', text: 'Shown at the top of the page of each topic and person it is on.' }),
      msg,
      h('button', { class: 'btn primary big', type: 'submit' }, 'Save')));
  if (!editing) setTimeout(() => text.focus(), 50);
  return { el, bare: !isWide(), nav: 'notes' };
}

// ----- settings -----

function bookmarklet() {
  const target = `${location.origin}/#/capture?u=`;
  return 'javascript:(()=>{const q=String(getSelection()).trim().slice(0,4000);'
    + `window.open('${target}'+encodeURIComponent(location.href)+'&t='+encodeURIComponent(document.title)+'&q='+encodeURIComponent(q),'_blank')})()`;
}

// what the iPhone Shortcut opens, followed by what was shared
function shareAddress() { return `${location.origin}/#/capture?share=`; }

async function viewSettings() {
  const [health, backups] = await Promise.all([api('/api/health'), api('/api/backup/status')]);
  nav.label('Settings');
  const backupMsg = h('span', { class: 'note-line', role: 'status' });
  const daily = backups.copies.filter((c) => c.kind === 'daily');
  const upgrades = backups.copies.filter((c) => c.kind === 'before upgrade');
  const table = (rows) => h('table', { class: 'grid settings' }, h('tbody', {}, rows.map(([k, v]) => h('tr', {}, h('td', { text: k }), h('td', { class: 'm', text: v })))));
  const copyBtn = (text, label) => h('button', { class: 'btn small', type: 'button', style: { alignSelf: 'flex-start' }, onclick: async () => {
    try { await navigator.clipboard.writeText(text); toast('Copied'); } catch { toast('Copying is not allowed here: select the text and copy it'); }
  } }, label);
  const steps = (items) => h('ol', { class: 'steps' }, items.map((i) => h('li', {}, i)));
  const el = h('div', {},
    h('header', { class: 'top' }, h('div', { class: 'top-row' }, h('h1', {}, 'Settings'))),
    h('div', { class: 'pad settings-page' },
      h('h2', { class: 'section-title', text: 'Backups' }),
      table([
        ['Last copy', daily[0] ? dateTime(daily[0].written_at) : 'none yet'],
        ['Copies kept', `${daily.length}: the last ${backups.kept} days, and the first of each of the last ${backups.monthly} months`],
        ['Next copy', dateTime(backups.next)],
        ['Before upgrades', upgrades.length ? upgrades.map((c) => c.file).join(', ') : 'none'],
      ]),
      h('p', { class: 'note-line', text: 'Copies of the database are zips in data/backups on the NAS. Photos and covers are plain files: your NAS snapshots keep them.' }),
      h('div', { class: 'row-btns' },
        h('button', { class: 'btn small', type: 'button', onclick: async () => {
          try { await api('/api/backup', { method: 'POST' }); toast('Copy made'); render(); } catch (err) { backupMsg.textContent = err.message; }
        } }, 'Back up now'),
        h('a', { class: 'btn small', href: '/api/backup/download', download: '' }, 'Download everything (.zip)')),
      backupMsg,
      h('h2', { class: 'section-title', text: 'Space used' }),
      table([
        ['Database', size(backups.database_bytes)],
        ['Page photos', `${backups.photos.count} · ${size(backups.photos.bytes)}`],
        ['Covers and pictures', `${backups.covers.count} · ${size(backups.covers.bytes)}`],
        ['Backups', `${backups.backups.count} · ${size(backups.backups.bytes)}`],
      ]),
      h('h2', { class: 'section-title', text: 'Sending from other apps' }),
      h('h3', { class: 'sub-title', text: 'On a computer: a bookmark' }),
      h('p', {}, 'Drag this button to your bookmarks bar, once. Then select text on any page and click the bookmark: the page opens here, with the passage, its link and its title filled in.'),
      h('a', { class: 'btn small bookmarklet', href: bookmarklet(), onclick: (ev) => { ev.preventDefault(); toast('Drag it to the bookmarks bar'); } }, '→ Marginote'),
      h('h3', { class: 'sub-title', text: 'On the iPhone: « Marginote » in every app’s Share menu' }),
      h('p', {}, 'A shortcut made once in Apple’s Shortcuts app (Raccourcis). Then select text in any app (Safari, Notes, Mail, Books, a PDF…), tap Partager, then Marginote: this app opens with the passage and asks where it is from. A link shared on its own (YouTube, Podcasts, an article) opens its form here.'),
      steps([
        'In Raccourcis, tap + (top right). Tap the name at the top, « Renommer », and type Marginote.',
        'Tap ⓘ (at the bottom, or in the menu under the name) and turn on « Dans la feuille de partage » (« Afficher dans la feuille de partage » on older iPhones), then OK. A first line appears: « Recevoir … ». Tap the blue word after « Recevoir », tap « Effacer », tick only « Texte » and « URL », then OK.',
        'Add the action « Texte » (search box at the bottom). Touch inside its box and tap « Entrée du raccourci » in the bar above the keyboard.',
        'Add the action that encodes text for an address: search « encod » and choose « Encoder l’URL » (it may be worded slightly differently). It takes the Texte above by itself; leave it on « Encoder ».',
        'Add the action « URL ». Paste the address below in its box, then, right after it with no space, tap the result of the encoding step in the bar above the keyboard.',
        'Add the action « Ouvrir les URL », then OK (top right).',
      ]),
      h('pre', { class: 'code', text: shareAddress() }),
      copyBtn(shareAddress(), 'Copy the address'),
      h('p', { class: 'note-line', text: 'Done when: in Notes, you select a sentence, tap Partager (behind › in the small menu if needed), scroll down to Marginote, and this app opens on « Where is it from? » with your sentence. The first time, iOS asks whether the shortcut may open the address: Autoriser.' }),
      h('p', { class: 'note-line', text: 'It opens in Safari: log in there once (the app on the Home Screen keeps its own login), with Tailscale on. To find Marginote at the top of the Share menu: « Modifier les actions… » at its bottom, then add it to Favoris.' }),
      h('p', { class: 'note-line', text: 'An app without Partager in its menu (Kindle): Copy the passage, then here, Capture › Paste what you copied.' }),
      h('h2', { class: 'section-title', text: 'App' }),
      table([
        ['Version', health.version],
        ['Text recognition', health.tesseract ? `Tesseract ${health.tesseract} (${health.ocr_languages.join(', ')})` : 'missing'],
        ['Page straightening', health.straighten_pages ? 'on' : 'off'],
        ['Barcode reader', health.barcode_reader ? 'on' : 'off'],
        ['Online lookups', health.lookups_enabled ? 'on' : 'off'],
      ]),
      h('div', { class: 'row-btns' },
        h('a', { class: 'btn small', href: '/docs', target: '_blank', rel: 'noopener' }, 'API'),
        h('button', { class: 'btn small', type: 'button', onclick: async () => {
          await api('/api/logout', { method: 'POST' }).catch(() => null);
          store.changed();
          nav.replace('login');
        } }, 'Log out'))));
  return { el, nav: 'settings' };
}

// ---------- shell and navigation ----------

function buildShell() {
  const link = (navKey, href, label, cls = '') => h('a', { href, class: cls, dataset: { nav: navKey } }, label);
  const side = h('aside', { class: 'side' },
    h('a', { href: '#/', class: 'brand' }, 'Marginote'),
    h('a', { class: 'btn primary', href: '#/capture' }, '+ Capture'),
    h('nav', { 'aria-label': 'Main' },
      link('library', '#/', 'Library'),
      h('div', { class: 'sub' }, link('lib-sources', '#/?view=sources', 'Sources'), link('lib-people', '#/?view=people', 'People'),
        link('lib-topics', '#/?view=topics', 'Topics')),
      link('entries', '#/entries', 'Entries'), link('notes', '#/notes', 'Notes'),
      link('inbox', '#/inbox', 'Inbox'), link('settings', '#/settings', 'Settings')));
  const tabbar = h('nav', { class: 'tabbar', 'aria-label': 'Main' },
    link('library', '#/', 'Library'), link('entries', '#/entries', 'Entries'), link('notes', '#/notes', 'Notes'),
    h('span', { class: 'tab-capture' }, h('a', { class: 'btn primary', href: '#/capture' }, '+ Capture')));
  const main = h('main', { class: 'view', id: 'view' });
  put(document.body, h('div', { class: 'app', id: 'app' }, side, main, tabbar));
}

const ROUTES = [
  [/^$/, viewLibrary, true],
  [/^login$/, viewLogin, true],
  [/^source\/new$/, viewSourceForm],
  [/^source\/(\d+)$/, viewSource],
  [/^source\/(\d+)\/edit$/, viewSourceForm],
  [/^person\/(\d+)$/, viewPerson],
  [/^person\/(\d+)\/edit$/, viewPersonForm],
  [/^topic\/(\d+)$/, viewTopic],
  [/^topic\/(\d+)\/edit$/, viewTopicForm],
  [/^entries$/, viewEntries, true],
  [/^entry\/(\d+)$/, viewEntry],
  [/^entry\/(\d+)\/edit$/, viewEntryEdit],
  [/^entry\/(\d+)\/photo$/, viewEntryPhoto],
  [/^notes$/, viewNotes, true],
  [/^note\/new$/, viewNoteForm],
  [/^note\/(\d+)$/, viewNote],
  [/^note\/(\d+)\/edit$/, viewNoteForm],
  [/^capture$/, viewCapture, (params) => ![...params.keys()].length],
  [/^inbox$/, viewInbox, true],
  [/^settings$/, viewSettings, true],
  // addresses of version 0.4, from bookmarks or the home screen
  [/^book\/(\d+)$/, ({ args: [id] }) => { nav.replace(`source/${id}`); return null; }],
  [/^quotes$/, () => { nav.replace('entries'); return null; }],
  [/^tags$/, () => { nav.replace('?view=topics'); return null; }],
];

let renderCount = 0;
let cleanupCurrent = null;
async function render() {
  const raw = location.hash.replace(/^#\/?/, '');
  const cut = raw.indexOf('?');
  const path = cut < 0 ? raw : raw.slice(0, cut);
  const params = new URLSearchParams(cut < 0 ? '' : raw.slice(cut + 1));
  const n = ++renderCount;
  const view = document.getElementById('view');
  const route = ROUTES.find(([re]) => re.test(path));
  if (!route) { nav.replace(''); return; }
  const root = typeof route[2] === 'function' ? route[2](params) : Boolean(route[2]);
  nav.arrive('#/' + raw, root);
  const args = path.match(route[0]).slice(1);
  try {
    const result = await route[1]({ params, args: args.length ? args : [undefined] });
    if (n !== renderCount || !result) return;
    cleanupCurrent?.();
    cleanupCurrent = result.cleanup || null;
    document.getElementById('app').classList.toggle('bare', Boolean(result.bare));
    const libView = path === '' ? (params.get('view') || prefs.get('libraryView', 'sources')) : null;
    for (const a of document.querySelectorAll('[data-nav]')) {
      a.classList.toggle('on', a.dataset.nav === result.nav || (libView && a.dataset.nav === `lib-${libView}`));
    }
    put(view, result.el);
    window.scrollTo(0, 0);
  } catch (err) {
    if (n !== renderCount || err.status === 401) return;
    put(view, h('div', {}, bar(backButton('', 'Library'), ''), errorBox(err, render)));
  }
}

window.addEventListener('hashchange', render);
let wasWide = isWide();
window.matchMedia('(min-width: 960px)').addEventListener('change', () => {
  // the layout changes between phone and computer; forms keep what was typed, so they are left alone
  if (isWide() !== wasWide && !document.querySelector('form .details')) render();
  wasWide = isWide();
});

(async function start() {
  buildShell();
  try {
    const me = await api('/api/me');
    if (!me.logged_in) { sessionStorage.setItem('marginote.after', location.hash); nav.replace('login'); return; }
  } catch { /* shown by render */ }
  render();
})();
