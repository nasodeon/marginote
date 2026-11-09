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
  class: 'M3 4h18v12H3zM9 20l2-4M15 20l-2-4M7 8h7M7 11h4',
  said: 'M4 5h16v11h-9l-5 4v-4H4z',
  inbox: 'M4 13h4l2 3h4l2-3h4M4 13l2-8h12l2 8v6H4z',
  download: 'M12 4v11M7 10l5 5 5-5M5 20h14',
  pdf: 'M6 3h9l4 4v14H6zM15 3v4h4M9 17v-5h1.5a1.5 1.5 0 0 1 0 3H9',
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
const WORDS = { entry: 'entries', copy: 'copies', person: 'people', other: 'other', class: 'classes' };
const plural = (n, word) => `${n} ${n === 1 ? word : WORDS[word] || word + 's'}`;
const isWide = () => window.matchMedia('(min-width: 960px)').matches;
const coarse = () => window.matchMedia('(pointer: coarse)').matches;
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
// notesFirst: mostly your own notes on it (a video, a class), so capture starts on Note and its page shows them first.
const KINDS = {
  book: { name: 'Book', several: 'books', maker: 'author', makerLabel: 'author(s)', publisher: 'publisher', where: 'page', photos: true },
  ebook: { name: 'Ebook', several: 'ebooks', maker: 'author', makerLabel: 'author(s)', publisher: 'publisher', where: 'page or chapter', photos: true },
  article: { name: 'Article', several: 'articles', maker: 'author', makerLabel: 'author(s)', publisher: 'site', where: null, link: true, dated: true },
  video: { name: 'Video', several: 'videos', maker: 'speaker', makerLabel: 'who speaks', publisher: 'channel', where: null, link: true, dated: true, notesFirst: true },
  podcast: { name: 'Podcast', several: 'podcasts', maker: 'speaker', makerLabel: 'who speaks', publisher: 'show', where: null, link: true, dated: true, notesFirst: true },
  class: { name: 'Class', several: 'classes', maker: 'speaker', makerLabel: 'teacher(s)', publisher: 'school or university', where: 'session', photos: true, notesFirst: true },
  talk: { name: 'Talk', several: 'talks', maker: 'speaker', makerLabel: 'who speaks', publisher: 'event or place', where: 'slide or part', photos: true, dated: true },
  other: { name: 'Other', several: 'other', maker: 'author', makerLabel: 'by', publisher: 'publisher or place', where: 'where', photos: true },
};
// a scientific article (a DOI, an arXiv number or a journal) is quoted by page, like a book
const isPaper = (s) => s?.kind === 'article' && Boolean(s.doi || s.arxiv || s.journal || s.pages);
const PAPER = { ...KINDS.article, where: 'page' };
const kindOf = (s) => (isPaper(s) ? PAPER : KINDS[s?.kind] || KINDS.book);
const makers = (s) => [...(s.people?.author || []), ...(s.people?.speaker || []), ...(s.people?.editor || [])];
// every author is kept; in a line, more than three are 'the first et al.'
const shortNames = (list) => (list.length > 3 ? `${list[0]} et al.` : list.join(', '));
// 'Revue d’exemple 12 (3), p. 45–56', or 'arXiv:2401.01234' for a preprint
function inJournal(s) {
  if (s.journal) {
    const vol = [s.volume, s.issue ? `(${s.issue})` : null].filter(Boolean).join(' ');
    const pages = s.pages ? (/^\d/.test(s.pages) ? `p.\u00a0${s.pages}` : s.pages).replace(/[–-]/g, '\u2060–\u2060') : null;   // kept on one line
    return [[s.journal, vol].filter(Boolean).join(' '), pages].filter(Boolean).join(', ');
  }
  return s.arxiv ? `arXiv:${s.arxiv}` : null;
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
  // 'book · Frédéric Lordon' / 'video · Philosophie à voix haute' / 'class · Jeanne Dupont · 2026'
  const who = shortNames(makers(s).map((p) => p.name));
  return joinDots([h('span', { class: 'sc', text: s.kind }), who || s.publisher || null, s.kind === 'class' && s.year ? String(s.year) : null,
    s.field ? h('i', { text: s.field }) : null]);
}

function sourceRow(s, { count = true, href = `#/source/${s.id}` } = {}) {
  return h('a', { class: 'book-row', href }, thumb(s),
    h('span', { class: 'main' }, h('span', { class: 't', text: s.title }), h('span', { class: 'a' }, sourceLine(s))),
    count ? h('span', { class: 'num w40', text: (s.quote_count || 0) + (s.note_count || 0) }) : null);
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
  if (!e.source) {
    // words someone said: who (unless on their page) and where or when
    bits.push(h('span', { class: 'sc ink', text: e.by && e.by.id !== person ? `${surname(e.by)}, said` : 'said' }));
    if (e.page) bits.push(h('i', { text: shorten(e.page, 48) }));
  } else {
    if (showSource) bits.push(h('i', { text: shorten(e.source.title, 48) }));
    if (e.words_by && e.words_by.id !== person) bits.push(h('span', { class: 'sc ink', text: `${surname(e.words_by)}, quoted` }));
  }
  const about = e.about.filter((p) => p.id !== person && !(source && p.from_source));
  if (about.length) bits.push('about ' + about.map((p) => surname(p)).join(', '));
  if (e.note) bits.push('comment');
  const topics = e.topics.filter((t) => !(source && t.from_source));
  if (topics.length) bits.push(h('span', { class: 'tg', text: topics.map((t) => t.name).join(' ') }));
  return joinDots(bits);
}

function where(e) {
  if (!e.page || !e.source) return '';
  return placeText(e.page);
}
const placeText = (place) => (!place ? '' : /^\d/.test(place) || /^[ivxlcdm]+$/i.test(place) ? `p. ${place}` : place);

function entryRow(e, opts = {}) {
  const meta = entryMeta(e, opts);
  return h('a', { class: `entry-row${opts.fresh ? ' fresh' : ''}${opts.mark ? ' marked' : ''}`,
    href: `#/entry/${e.id}`, id: `e${e.id}` },
  h('span', { class: 'pg', text: e.source ? e.page || '' : '' }),
  h('div', { class: 'body' },
    h('p', { class: 'txt' }, e.snippet ? withMarks(e.snippet) : e.text),
    meta.length ? h('span', { class: 'meta' }, meta) : null));
}

function entryTable(entries, { showSource = true, fresh = null } = {}) {
  const rows = entries.map((e) => h('tr', { class: e.id === fresh ? 'fresh' : '', id: `e${e.id}`, onclick: () => go(`entry/${e.id}`) },
    h('td', { class: 'm', text: e.source ? e.page || '' : '' }),
    h('td', {}, e.snippet ? withMarks(e.snippet) : e.text,
      e.source && e.words_by ? h('span', { class: 'sub sc', text: `${surname(e.words_by)}, quoted` }) : null,
      e.note ? h('span', { class: 'sub', text: shorten(e.note, 90) }) : null),
    showSource ? h('td', { class: 'it' }, e.source ? e.source.title : [h('span', { class: 'sc', text: 'said ' }), e.by?.name || '',
      e.page ? `, ${e.page}` : '']) : null,
    h('td', { class: 'tags', text: e.topics.map((t) => t.name).join(' ') }),
    h('td', { class: 'm', text: fullDate(e.created_at) })));
  return h('div', { class: 'table-wrap' },
    h('table', { class: 'grid' },
      h('thead', {}, h('tr', {},
        h('th', { style: { width: '64px' }, text: 'where' }), h('th', { text: 'quote' }),
        showSource ? h('th', { style: { width: '200px' }, text: 'source' }) : null,
        h('th', { style: { width: '150px' }, text: 'topics' }), h('th', { style: { width: '110px' }, text: 'added' }))),
      h('tbody', {}, rows)));
}

function entryList(entries, opts = {}) {
  if (!entries.length) return null;
  if (isWide() && !opts.compact) return entryTable(entries, { showSource: opts.showSource, fresh: opts.fresh });
  return [opts.head === false ? null : h('div', { class: 'colhead' }, h('span', { class: 'w36', text: '' }), h('span', { style: { flex: 1 }, text: opts.head || 'quote' })),
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

function chipInput({ label, initial = [], options, single = false, placeholder = 'add', newLabel, tt = false, id, quick = 0, onchange, allowNew = true, chipClass = null }) {
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
    if (!allowNew && !exact) { add(options().find((o) => !has(o.key) && matches(o, q))); input.value = ''; return; }
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
      exists || !allowNew ? null : h('button', { type: 'button', class: 'new', onpointerdown: (ev) => ev.preventDefault(), onclick: addTyped },
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
    put(box, items.map((i) => h('span', { class: `chip ${chipClass || (tt ? '' : 'person')}` }, i.label,
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
    sub: p.entries != null ? `${p.sort_name} · ${plural(p.entries, 'quote')}` : p.sort_name };
}
const personItem = (p) => ({ key: 'p' + p.id, label: p.name, value: p.id });

function peopleInput(label, initial, allPeople, opts = {}) {
  return chipInput({ label, initial: initial.map(personItem), options: () => allPeople.map(personOption),
    newLabel: 'new person', placeholder: opts.placeholder || 'type a name', ...opts });
}

// the books, videos, classes… a note is on: chosen from the library
function sourcesInput(label, initial, allSources, opts = {}) {
  const item = (src) => ({ key: 's' + src.id, label: src.title, value: src.id });
  return chipInput({ label, initial: initial.map(item), allowNew: false, placeholder: 'find a source', chipClass: 'source',
    options: () => allSources.map((src) => ({ ...item(src), sub: [src.kind, makers(src).map((p) => p.name).join(', ')].filter(Boolean).join(' · ') })),
    ...opts });
}

function topicsInput(label, initial, allTopics, opts = {}) {
  const byUse = [...allTopics].sort((a, b) => b.entries - a.entries);
  return chipInput({ label, tt: true, initial: initial.map((t) => ({ key: 't' + fold(t), label: t, value: t })),
    options: () => byUse.map((t) => ({ key: 't' + fold(t.name), label: t.name, value: t.name, sub: plural(t.entries, 'quote') })),
    newLabel: 'new topic', placeholder: 'add a topic', quick: 8, ...opts });
}

// a passage from the source, or your own note on it
function modeSwitch(get, set, after) {
  const seg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Quote or note' });
  const draw = () => put(seg, ['quote', 'note'].map((k) => h('button', { type: 'button', class: get() === k ? 'on' : '',
    'aria-pressed': get() === k ? 'true' : 'false', onclick: () => { set(k); draw(); after?.(); } }, k === 'quote' ? 'Quote' : 'Note')));
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

// the page is served in the language of whoever is logged in; before that, the one last chosen on this device
const PAGE_LANG = document.documentElement.lang || 'en';
function chooseLanguage(lang) {
  document.cookie = `marginote_lang=${lang}; path=/; max-age=31536000; samesite=lax${location.protocol === 'https:' ? '; secure' : ''}`;
  location.reload();
}

async function viewLogin() {
  const name = h('input', { class: 'input', type: 'text', id: 'nm', name: 'username', autocomplete: 'username', autocapitalize: 'words',
    spellcheck: 'false', value: prefs.get('loginName', '') });
  const pw = h('input', { class: 'input', type: 'password', id: 'pw', autocomplete: 'current-password', required: true });
  const msg = h('div', { class: 'note-line', role: 'alert' });
  const form = h('form', { class: 'login', onsubmit: async (ev) => {
    ev.preventDefault();
    msg.textContent = '';
    try {
      const me = await api('/api/login', { method: 'POST', body: { name: name.value, password: pw.value } });
      prefs.set('loginName', name.value.trim());
      const after = sessionStorage.getItem('marginote.after');
      sessionStorage.removeItem('marginote.after');
      store.changed();
      const target = after && !after.startsWith('#/login') ? after.replace(/^#\/?/, '') : '';
      if (me.language && me.language !== PAGE_LANG) {   // the app in this person's language
        history.replaceState(null, '', `#/${target}`);
        location.reload();
        return;
      }
      nav.replace(target);
    } catch (err) { msg.textContent = err.message; pw.select(); }
  } },
  h('h1', {}, 'Marginote'),
  h('label', { class: 'field', for: 'nm' }, h('span', { text: 'your name' }), name),
  h('label', { class: 'field', for: 'pw' }, h('span', { text: 'password' }), pw),
  h('button', { class: 'btn primary big', type: 'submit' }, 'Log in'), msg,
  h('button', { class: 'link-btn lang-switch', type: 'button', lang: PAGE_LANG === 'fr' ? 'en' : 'fr',
    onclick: () => chooseLanguage(PAGE_LANG === 'fr' ? 'en' : 'fr') }, PAGE_LANG === 'fr' ? 'English' : 'Français'));
  setTimeout(() => (name.value ? pw : name).focus(), 50);
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
    return [shown.length ? h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'source' }), h('span', { class: 'w40 r', text: 'items' })) : null,
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
    const out = [h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'person' }), h('span', { class: 'w40 r', text: 'quotes' }))];
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
    return [h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'topic' }), h('span', { class: 'w40 r', text: 'quotes' })),
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
      needle.length > 1 ? [h('a', { class: 'more-btn', href: `#/quotes?q=${encodeURIComponent(q.value.trim())}` },
        `Quotes containing “${q.value.trim()}” ›`), h('a', { class: 'more-btn', href: `#/notes?q=${encodeURIComponent(q.value.trim())}` },
        `Notes containing “${q.value.trim()}” ›`)] : null);
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

// ----- folding: a +/− on a section or a group, remembered on this device -----

const folds = {
  all() { return prefs.get('folded', {}); },
  // a part opens unfolded, unless it starts folded (startFolded): only a change from that is kept
  is(key, startFolded = false) { const v = this.all()[key]; return v === undefined ? startFolded : v === 1; },
  set(key, folded, startFolded = false) {
    const all = this.all();
    if (folded !== startFolded) all[key] = folded ? 1 : 0; else delete all[key];
    const keys = Object.keys(all);
    if (keys.length > 600) for (const k of keys.slice(0, keys.length - 600)) delete all[k];   // the oldest go
    prefs.set('folded', all);
  },
};

// head: the section's or group's title line (the button is added to it); body: what folds away
function foldable(key, head, body, startFolded = false) {
  const box = h('div', { class: 'fold-body' }, body);
  let folded = folds.is(key, startFolded);
  const btn = h('button', { type: 'button', class: 'fold-btn' });
  const apply = () => {
    box.hidden = folded;
    btn.textContent = folded ? '+' : '−';
    btn.setAttribute('aria-expanded', String(!folded));
    btn.setAttribute('aria-label', folded ? 'Show this part' : 'Hide this part');
    head.classList.toggle('folded', folded);
  };
  btn.addEventListener('click', (ev) => { ev.preventDefault(); ev.stopPropagation(); folded = !folded; folds.set(key, folded, startFolded); apply(); });
  head.append(btn);
  apply();
  return [head, box];
}

// ----- a source -----

async function viewSource({ args: [id] }) {
  const order = prefs.get('sourceOrder', 'page');
  const [source, entries, notes, docs] = await Promise.all([api(`/api/sources/${id}`), api(`/api/sources/${id}/entries?order=${order}`),
    api(`/api/notes?source_id=${id}&order=place`), api(`/api/documents?source_id=${id}`)]);
  nav.label(shorten(source.title, 24));
  const k = kindOf(source);
  const fresh = nav.flash.entry || null;
  const freshNote = nav.flash.note || null;
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

  const needle = () => fold(q.value.trim());
  const shownEntries = () => entries.filter((e) => !needle() || fold(`${e.text} ${e.note || ''} ${e.topics.map((t) => t.name).join(' ')} ${e.page || ''}`).includes(needle()));
  const shownNotes = () => notes.filter((n) => !needle() || fold(`${n.title || ''} ${n.text} ${n.place || ''} ${n.topics.map((t) => t.name).join(' ')}`).includes(needle()));

  function drawSelectBar() {
    const shown = shownEntries();
    put(selectBar,
      h('span', { class: 'grow', text: chosen.size ? `${chosen.size} selected` : 'Tap the quotes to delete' }),
      h('button', { type: 'button', class: 'btn small', onclick: () => {
        const all = shown.every((e) => chosen.has(e.id));
        shown.forEach((e) => (all ? chosen.delete(e.id) : chosen.add(e.id)));
        draw();
      } }, shown.length && shown.every((e) => chosen.has(e.id)) ? 'None' : 'All'),
      h('button', { type: 'button', class: 'btn small danger primary', disabled: !chosen.size, onclick: async () => {
        const n = chosen.size;
        const ok = await confirmDialog({ title: `Delete ${plural(n, 'quote')}?`, text: 'This cannot be undone.',
          choices: [{ label: `Delete ${plural(n, 'quote')}`, value: true, danger: true }] });
        if (!ok) return;
        try { await deleteEntries([...chosen]); toast(`${plural(n, 'quote')} deleted`); render(); } catch (err) { toast(err.message); }
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
        return h('label', { class: 'entry-row' }, h('span', { class: 'check' }, box),
          h('div', { class: 'body' }, h('p', { class: 'txt' }, e.text), h('span', { class: 'meta', text: where(e) })));
      }), h('div', { class: 'list-end' }));
      return;
    }
    const sn = shownNotes();
    const both = notes.length && entries.length;
    const quotesPart = shown.length ? entryList(shown, { showSource: false, source: source.id, fresh, head: both ? false : 'quote' }) : null;
    const notesPart = sn.length ? [sn.map((n) => noteBlock(n, { here: { source: source.id }, fresh: n.id === freshNote })), h('div', { class: 'list-end' })] : null;
    const parts = [];
    const section = (key, title, count, content) => {
      if (!content) return;
      if (!both) { parts.push(content); return; }   // one kind only: no heading needed
      parts.push(...foldable(`source:${source.id}:${key}`, sectionHead(null, title, count), content));
    };
    const notesSection = () => section('notes', 'Your notes', sn.length, notesPart);
    const quotesSection = () => section('quotes', 'Quotes', shown.length, quotesPart);
    if (k.notesFirst) { notesSection(); quotesSection(); } else { quotesSection(); notesSection(); }
    put(list, parts,
      !shown.length && !sn.length && (entries.length || notes.length) ? h('div', { class: 'empty', text: 'Nothing matches.' }) : null,
      !entries.length && !notes.length ? h('div', { class: 'empty' }, 'Nothing captured from it yet.',
        h('div', { class: 'row-btns' },
          h('a', { class: 'btn primary', href: `#/capture?source=${source.id}` }, '+ Capture'),
          h('a', { class: 'btn', href: `#/note/new?source=${source.id}` }, '+ Note'))) : null);
  }
  q.addEventListener('input', draw);

  const removeSource = async () => {
    const n = entries.length;
    const kept = notes.length ? ` Your ${plural(notes.length, 'note')} on it ${notes.length === 1 ? 'is' : 'are'} kept.` : '';
    const choice = await confirmDialog({
      title: `Delete “${source.title}”?`,
      text: (n ? `It has ${plural(n, 'quote')}. This cannot be undone.` : 'This cannot be undone.') + kept,
      choices: [
        { label: n ? `Delete it and its ${plural(n, 'quote')}` : 'Delete it', value: 'all', danger: true },
        n ? { label: `Delete only its ${plural(n, 'quote')}`, value: 'entries' } : null,
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
        toast(`${plural(n, 'quote')} deleted`);
        render();
      }
    } catch (err) { toast(err.message); }
  };

  draw();
  if (fresh || freshNote) setTimeout(() => document.getElementById(fresh ? `e${fresh}` : `n${freshNote}`)?.scrollIntoView({ block: 'center' }), 60);

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
  const journal = inJournal(source);
  const details = joinDots([h('span', { class: 'sc', text: source.kind }), journal ? h('i', { text: journal }) : source.publisher,
    source.date ? plainDate(source.date) : source.year, source.edition, source.field ? h('i', { text: source.field }) : null]);
  const idLinks = joinDots([
    source.doi ? h('a', { class: 'doi-link', href: `https://doi.org/${source.doi}`, target: '_blank', rel: 'noopener noreferrer', text: `doi:${source.doi}` }) : null,
    source.arxiv && journal !== `arXiv:${source.arxiv}` ? h('a', { class: 'doi-link', href: `https://arxiv.org/abs/${source.arxiv}`, target: '_blank', rel: 'noopener noreferrer',
      text: `arXiv:${source.arxiv}` }) : null]);
  // a paper with many authors: the first three, and the others one tap away
  const byLine = h('span', { class: 'by' });
  const allMakers = makers(source);
  const showMakers = (all) => put(byLine, all || allMakers.length <= 6 ? personLinks(allMakers)
    : [...personLinks(allMakers.slice(0, 3)).map((x) => (x === ' and ' ? ', ' : x)), ' and ',
      h('button', { class: 'link-btn inline', type: 'button', onclick: () => showMakers(true) }, `${allMakers.length - 3} others`)]);
  showMakers(false);
  const counts = [source.quote_count ? plural(source.quote_count, 'quote') : null, source.note_count ? plural(source.note_count, 'note') : null]
    .filter(Boolean).join(' · ');
  const info = h('div', { class: 'info' },
    h('h1', { text: source.title }),
    source.subtitle ? h('span', { class: 'it', text: source.subtitle }) : null,
    allMakers.length ? byLine : null,
    people.translator.length ? h('span', { class: 'meta' }, 'translated by ', personLinks(people.translator)) : null,
    h('span', { class: 'meta' }, details),
    idLinks.length ? h('span', { class: 'meta' }, idLinks) : null,
    people.about.length ? h('span', { class: 'meta' }, 'about ', personLinks(people.about)) : null,
    source.topics.length ? topicLinks(source.topics) : null,
    counts ? h('span', { class: 'counts', text: counts }) : null,
    docs.length ? h('div', { class: 'doc-rows' }, docs.map((d) => h('a', { class: 'doc-row', href: `#/document/${d.id}` }, icon('pdf', 18),
      h('span', { class: 't', text: d.name }),
      h('span', { class: 'muted', text: d.status === 'reading' ? 'being read…' : joinDots([plural(d.pages, 'page'), d.entry_count ? `${d.entry_count} kept` : null]).join('') })))) : null,
    h('div', { class: 'actions' },
      h('a', { class: 'btn primary small', href: `#/capture?source=${source.id}` }, '+ Capture'),
      h('a', { class: 'btn small', href: `#/note/new?source=${source.id}` }, '+ Note'),
      !docs.length && ['article', 'book', 'ebook', 'other'].includes(source.kind)
        ? h('label', { class: 'btn small file-btn' }, '+ PDF', pdfInput(source.id)) : null,
      source.url ? h('a', { class: 'btn small', href: source.url, target: '_blank', rel: 'noopener noreferrer' },
        k.link && source.kind !== 'article' ? `Open the ${source.kind}` : 'Open the link', icon('external', 14)) : null,
      entries.length || notes.length ? h('a', { class: 'btn small', href: `/api/sources/${source.id}/export.md`, download: '' }, 'Export') : null,
      entries.length ? h('button', { class: 'btn small', type: 'button', onclick: () => { selecting = true; draw(); } }, 'Select') : null));
  const el = h('div', {},
    bar(backButton('', 'Library'), '', h('a', { class: 'link-btn', href: `#/source/${id}/edit` }, 'Edit')),
    h('header', { class: 'top', style: { paddingTop: '6px' } },
      wide ? [coverEl, h('div', { class: 'book-head' }, info)] : h('div', { class: 'book-head' }, coverEl, info),
      entries.length + notes.length > 5 ? h('label', { class: 'search' }, icon('search', 16), q) : null,
      entries.length > 1 && orderBtn ? h('div', { class: 'tools' }, orderBtn) : null),
    list,
    selectBar,
    h('div', { class: 'pad' }, h('button', { class: 'btn small danger', type: 'button', style: { alignSelf: 'flex-start' }, onclick: removeSource },
      `Delete this ${k.name.toLowerCase()}…`)));
  return { el, nav: 'library' };
}

// ----- a person -----

const SECTION_TITLES = { works: 'Works', translated: 'Translations', said: 'Said', quoted: 'Quoted elsewhere' };

function noteBlock(n, { full = false, here = null, fresh = false } = {}) {
  const on = (n.sources || []).filter((s) => s.id !== here?.source);
  const also = [...n.people.filter((p) => p.id !== here?.person).map((p) => surname(p)),
    ...n.topics.filter((t) => t.id !== here?.topic).map((t) => t.name)];
  return h('a', { class: `note-block${full ? ' full' : ''}${fresh ? ' fresh' : ''}`, href: `#/note/${n.id}`, id: `n${n.id}` },
    n.title || n.place ? h('b', { class: 'note-title', text: [placeText(n.place), n.title].filter(Boolean).join(' — ') }) : null,
    h('p', { class: 'note-text', text: n.text }),
    h('span', { class: 'meta' }, joinDots([on.length ? h('i', { text: shorten(on.map((s) => s.title).join(', '), 60) }) : null,
      fullDate(n.created_at), also.length ? `also on ${also.join(', ')}` : null])));
}

async function viewPerson({ args: [id] }) {
  const data = await api(`/api/people/${id}`);
  const p = data.person;
  nav.label(surname(p));
  let medium = '';
  const media = {};
  const kindKey = (g) => (g.source ? g.source.kind : 'said');
  for (const sec of data.sections) for (const g of sec.groups) media[kindKey(g)] = (media[kindKey(g)] || 0) + Math.max(1, g.entries.length + g.notes.length);
  const body = h('div');
  const aside = h('div', { class: 'aside' });

  function groupBlock(sec, g) {
    const content = [
      g.notes.length ? g.notes.map((note) => noteBlock(note, { here: { person: p.id, source: g.source?.id } })) : null,
      g.entries.length ? moreGroup(g.entries, g.source ? 3 : 8, { person: p.id, source: g.source?.id }) : null,
    ];
    if (!g.source) return content;           // what they said: one group, with no source to name
    const head = h('div', { class: 'group-row' }, sourceRow(g.source, { count: false }));
    return g.notes.length || g.entries.length ? foldable(`person:${p.id}:${sec.key}:${g.source.id}`, head, content) : head;
  }

  function draw() {
    const parts = [];
    const notes = data.notes.length ? foldable(`person:${p.id}:notes`, sectionHead(isWide() ? null : 1, 'Notes', data.notes.length),
      data.notes.map((note) => noteBlock(note, { here: { person: p.id } }))) : null;
    for (const sec of data.sections) {
      const groups = sec.groups.filter((g) => !medium || kindKey(g) === medium);
      if (!groups.length) continue;
      const quotes = groups.reduce((a, g) => a + g.entries.length, 0);
      const noteCount = groups.reduce((a, g) => a + g.notes.length, 0);
      const title = sec.key === 'about' ? `About ${surname(p)}` : SECTION_TITLES[sec.key];
      const count = [sec.key === 'said' ? null : plural(groups.filter((g) => g.source).length, 'source'),
        quotes ? plural(quotes, 'quote') : null, noteCount ? plural(noteCount, 'note') : null].filter(Boolean).join(' · ');
      parts.push(...foldable(`person:${p.id}:${sec.key}`, sectionHead(null, title, count), groups.map((g) => groupBlock(sec, g))));
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
    p.said ? `said ${p.said}` : null, p.quoted_in ? `quoted in ${plural(p.quoted_in, 'source')}` : null,
    p.about_in ? `written about in ${p.about_in}` : null, plural(p.entries, 'quote')].filter(Boolean).join(' · ');
  const el = h('div', {},
    bar(backButton('?view=people', 'People'), '', h('a', { class: 'link-btn', href: `#/person/${id}/edit` }, 'Edit')),
    h('header', { class: 'top', style: { paddingTop: '6px' } },
      h('h1', { text: p.sort_name }),
      p.dates ? h('span', { class: 'meta', text: p.dates }) : null,
      h('span', { class: 'meta', text: counts }),
      p.aliases.length ? h('span', { class: 'meta it', text: `Also written: ${p.aliases.join(', ')}` }) : null,
      h('div', { class: 'actions' },
        h('a', { class: 'btn small', href: `#/note/new?person=${p.id}` }, '+ Note'),
        h('a', { class: 'btn small', href: `#/capture?said=${p.id}` }, `+ Words ${surname(p)} said`),
        h('a', { class: 'btn small', href: `#/capture?about=${p.id}` }, `+ Capture about ${surname(p)}`)),
      kinds.length > 1 ? filterRow([['', 'all'], ...kinds.map((m) => [m, `${m === 'said' ? 'said' : KINDS[m].several} ${media[m]}`])], '',
        (m) => { medium = m; draw(); }) : null),
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
      else if (by === 'source') {
        key = e.source ? 's' + e.source.id : 'said';
        label = e.source ? e.source.title : 'Said, no source';
        href = e.source ? `#/source/${e.source.id}` : null;
      } else { key = e.created_at.slice(0, 7); label = plainDate(key); }
      if (!map.has(key)) map.set(key, { key, label, href, entries: [] });
      map.get(key).entries.push(e);
    }
    const list = [...map.values()];
    if (by !== 'date') list.sort((a, b) => b.entries.length - a.entries.length || a.label.localeCompare(b.label));
    return list;
  }
  function draw() {
    put(body, groups().map((g) => foldable(`topic:${t.id}:${by}:${g.key}`,
      h('div', { class: 'group-head' }, g.href ? h('a', { href: g.href, text: g.label }) : h('span', { text: g.label }), h('span', { class: 'count', text: g.entries.length })),
      moreGroup(g.entries, 3, { showSource: by !== 'source', person: by === 'person' ? Number(g.href?.split('/').pop()) : null }))),
    data.entries.length ? h('div', { class: 'list-end' }) : null);
  }
  draw();
  let n = 0;
  const el = h('div', {},
    bar(backButton('?view=topics', 'Topics'), '', h('a', { class: 'link-btn', href: `#/topic/${id}/edit` }, 'Edit')),
    h('header', { class: 'top', style: { paddingTop: '6px' } },
      h('h1', { text: t.name }),
      h('span', { class: 'meta', text: [plural(t.sources, 'source'), plural(data.people.length, 'person'), plural(t.entries, 'quote'),
        t.notes ? plural(t.notes, 'note') : null].filter(Boolean).join(' · ') }),
      data.people.length ? h('div', { class: 'chips' }, h('span', { class: 'label', text: 'people' }),
        data.people.slice(0, 12).map((pp) => h('a', { class: 'chip serif', href: `#/person/${pp.id}` }, surname(pp), h('span', { class: 'n', text: pp.count })))) : null,
      data.related.length ? h('div', { class: 'chips' }, h('span', { class: 'label', text: 'often with' }),
        data.related.map((r) => h('a', { class: 'chip', href: `#/topic/${r.id}` }, r.name, h('span', { class: 'n', text: r.count })))) : null,
      h('div', { class: 'actions' },
        h('a', { class: 'btn small', href: `#/note/new?topic=${t.id}` }, '+ Note'),
        h('a', { class: 'btn small', href: `#/capture?topic=${t.id}` }, '+ Capture'))),
    data.notes.length ? foldable(`topic:${t.id}:notes`, sectionHead(++n, 'Notes', data.notes.length),
      data.notes.map((note) => noteBlock(note, { full: true, here: { topic: t.id } }))) : null,
    data.entries.length ? [...foldable(`topic:${t.id}:quotes`, sectionHead(++n, 'Quotes', data.entries.length), [
      h('div', { class: 'tools pad-x' }, h('span', { class: 'label', text: 'group by' }),
        segmented('Group quotes by', [['person', 'person'], ['source', 'source'], ['date', 'date']], by, (k) => { by = k; prefs.set('topicGroup', k); draw(); })),
      body])] : h('div', { class: 'empty', text: 'No quote on this topic yet.' }));
  return { el, nav: 'library' };
}

// ----- all quotes -----

async function viewEntries({ params }) {
  const f = { q: params.get('q') || '', medium: params.get('medium') || '' };
  let entries = [];
  let offset = 0;
  let more = false;
  const PAGE = 200;
  const mediumOf = (e) => (e.source ? e.source.kind : 'said');
  async function load(append) {
    if (f.q) {
      let hits = await api(`/api/search?q=${encodeURIComponent(f.q)}&limit=500`);
      hits = hits.filter((e) => !f.medium || mediumOf(e) === f.medium);
      entries = hits; more = false;
    } else {
      const qs = new URLSearchParams({ limit: PAGE, offset });
      if (f.medium) qs.set('medium', f.medium);
      const page = await api(`/api/entries?${qs}`);
      entries = append ? entries.concat(page) : page;
      more = page.length === PAGE;
    }
  }
  await load(false);
  nav.label('Quotes');
  const setFilter = (key, value) => {
    f[key] = value;
    const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v));
    history.replaceState(null, '', `#/quotes${qs.toString() ? '?' + qs : ''}`);
    const top = nav.stack[nav.stack.length - 1];
    if (top) { top.hash = location.hash; nav.save(); }
    offset = 0;
    load(false).then(draw).catch((err) => put(list, errorBox(err)));
  };
  const q = h('input', { type: 'search', placeholder: 'Search words, people, topics', 'aria-label': 'Search quotes', value: f.q, enterkeyhint: 'search' });
  q.addEventListener('input', debounce(() => setFilter('q', q.value.trim()), 350));
  const mediumSel = h('select', { class: 'filter', 'aria-label': 'From', onchange: () => setFilter('medium', mediumSel.value) },
    h('option', { value: '' }, 'from everything'), Object.entries(KINDS).map(([k, v]) => h('option', { value: k }, `from ${v.several}`)),
    h('option', { value: 'said' }, 'said, no source'));
  mediumSel.value = f.medium;
  const list = h('div');
  const count = h('span', { class: 'count' });
  function draw() {
    count.textContent = entries.length + (more ? '+' : '');
    put(list,
      entryList(entries, { showSource: true }),
      entries.length ? null : h('div', { class: 'empty', text: f.q || f.medium ? 'Nothing matches.' : 'No quotes yet.' }),
      more ? h('div', { class: 'pad' }, h('button', { class: 'btn', type: 'button', onclick: async () => { offset += PAGE; await load(true); draw(); } }, 'Show more')) : null);
  }
  draw();
  const el = h('div', {},
    h('header', { class: 'top' },
      h('div', { class: 'top-row' }, h('h1', {}, 'Quotes', count)),
      h('label', { class: 'search' }, icon('search', 16), q),
      h('div', { class: 'tools half' }, mediumSel)),
    list);
  if (f.q) setTimeout(() => { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 30);
  return { el, nav: 'quotes' };
}

// ----- one quote -----

function citation(e, source) {
  if (!source) return `${e.by?.name || ''}${e.page ? ', ' + e.page : ''}`;
  const who = e.words_by ? `${e.words_by.name}, quoted in ` : '';
  const by = shortNames(makers(source).map((p) => p.name));
  const place = where(e);
  return `${who}${by ? by + ', ' : ''}${source.title}${source.year ? ` (${source.year})` : source.date ? ` (${plainDate(source.date)})` : ''}${place ? ', ' + place : ''}`;
}

async function viewEntry({ args: [id] }) {
  const e = await api(`/api/entries/${id}`);
  const source = e.source ? await api(`/api/sources/${e.source.id}`) : null;
  nav.label('Quote');
  const home = source ? `source/${source.id}` : e.by ? `person/${e.by.id}` : 'quotes';
  const del = async () => {
    const ok = await confirmDialog({ title: 'Delete this quote?', text: 'This cannot be undone.',
      choices: [{ label: 'Delete the quote', value: true, danger: true }] });
    if (!ok) return;
    try {
      await deleteEntries([e.id]);
      toast('Quote deleted');
      nav.back(home);
    } catch (err) { toast(err.message); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(`${e.text}\n— ${citation(e, source)}`); toast('Copied with its reference'); } catch { toast('Copying is not allowed here'); }
  };
  const linkLabel = source?.kind === 'article' ? 'Open at this passage' : `Open the ${source?.kind}`;
  const el = h('div', {},
    bar(backButton(home, source ? shorten(source.title, 24) : e.by ? surname(e.by) : 'Quotes'), '', h('a', { class: 'link-btn', href: `#/entry/${id}/edit` }, 'Edit')),
    h('article', { class: 'entry-page' },
      source ? h('a', { class: 'book-link', href: `#/source/${source.id}` }, thumb(source),
        h('span', {}, h('span', { class: 't', text: source.title }), makers(source).length ? [h('br'), h('span', { class: 'muted', text: makers(source).map((p) => p.name).join(', ') })] : null))
        : h('p', { class: 'words-by said' }, h('span', { class: 'sc', text: 'said by ' }),
          e.by ? h('a', { class: 'plink', href: `#/person/${e.by.id}`, text: e.by.name }) : null, e.page ? `, ${e.page}` : ''),
      h('div', { class: 'kv' }, joinDots([where(e) || null, fullDate(e.created_at)])),
      source && e.words_by ? h('p', { class: 'words-by' }, h('span', { class: 'sc', text: 'words of ' }), h('a', { class: 'plink', href: `#/person/${e.words_by.id}`, text: e.words_by.name }),
        `, quoted by ${makers(source).map((p) => p.name).join(', ') || 'the source'}`) : null,
      h('p', { class: 'quote-env', lang: source?.language || null, text: e.text }),
      e.note ? h('p', { class: 'note-p' }, h('b', { text: 'Comment.' }), e.note) : null,
      e.about.length ? h('p', { class: 'kv-line' }, h('span', { class: 'label', text: 'about ' }), personLinks(e.about)) : null,
      e.topics.length ? topicLinks(e.topics) : null,
      e.link ? h('a', { class: 'btn small', href: e.link, target: '_blank', rel: 'noopener noreferrer', style: { alignSelf: 'flex-start' } }, linkLabel, icon('external', 14)) : null,
      e.notes?.length ? h('div', { class: 'kv-line' }, h('span', { class: 'label', text: 'in your notes ' }),
        e.notes.flatMap((n, k) => [k ? ', ' : '', h('a', { class: 'plink', href: `#/note/${n.id}`, text: n.title })])) : null,
      h('p', { class: 'cite muted', text: citation(e, source) }),
      h('div', { class: 'row-btns' },
        h('a', { class: 'btn small', href: `#/entry/${id}/edit` }, 'Edit'),
        e.photo_id ? h('a', { class: 'btn small', href: `#/entry/${id}/photo` }, e.photo_document ? 'See it in the PDF' : 'Photo') : null,
        h('button', { class: 'btn small', type: 'button', onclick: copy }, 'Copy'),
        h('a', { class: 'btn small', href: `#/note/new?entry=${e.id}` }, '+ Note'),
        h('button', { class: 'btn small danger', type: 'button', onclick: del }, 'Delete…'))));
  return { el, nav: 'quotes' };
}

// The fields shared by capture and editing: where, which source, your comment, about whom, topics, whose words.
// source null: words someone said, from no source; "said by" then comes first and is needed.
function entryFields({ source, sources, people, topics, entry = null, about = null, topicNames = null, onSourceChange, mode = 'quote', place = true }) {
  let touchedAbout = false;
  let touchedTopics = false;
  let current = source;
  const page = h('input', { class: 'input', id: 'f-page', value: entry?.page || '', inputmode: 'text' });
  const pageLabel = h('span');
  const sourceSel = h('select', { class: 'select', id: 'f-source' },
    h('option', { value: '', disabled: Boolean(entry?.photo_id) }, 'none: words someone said'),   // a photo's quote keeps its source
    sources.map((s) => h('option', { value: String(s.id) }, shorten(s.title, 60))));
  sourceSel.value = source ? String(source.id) : '';
  const wordsBy = peopleInput('', entry?.words_by ? [entry.words_by] : !source && entry?.by ? [entry.by] : [], people,
    { single: true, id: 'f-by' });
  const aboutIn = peopleInput('about', about || entry?.about || source?.people.about || [], people,
    { id: 'f-about', placeholder: 'who it is about', onchange: () => { touchedAbout = true; } });
  const topicsIn = topicsInput('topics', topicNames || (entry ? entry.topics.map((t) => t.name) : (source?.topics || []).map((t) => t.name)), topics,
    { id: 'f-topics', onchange: () => { touchedTopics = true; } });
  if (about) touchedAbout = true;
  if (topicNames) touchedTopics = true;
  const note = h('textarea', { class: 'textarea', rows: 3, id: 'f-note', value: entry?.note || '' });
  const noteField = h('label', { class: 'field', for: 'f-note' }, h('span', { text: 'your comment' }), note);
  const pageField = h('label', { class: 'field', for: 'f-page' }, pageLabel, page);
  const pageRow = h('div', { class: 'two', hidden: !place }, pageField,
    h('label', { class: 'field grow', for: 'f-source' }, h('span', { text: 'source' }), sourceSel));
  const holder = h('div', { class: 'fields' }, pageRow, noteField, aboutIn.el, topicsIn.el, wordsBy.el);
  function arrange() {
    // with no source, who said it comes first; otherwise last, for a quote within a quote
    const said = !current;
    wordsBy.el.querySelector('.label').textContent = said ? 'said by' : 'words of (when not the author’s)';
    wordsBy.el.querySelector('input')?.setAttribute('placeholder', said ? 'who said it' : 'a quote within the quote');
    if (said) holder.prepend(wordsBy.el); else holder.append(wordsBy.el);
    pageLabel.textContent = said ? 'where, when' : kindOf(current).where || 'where';
    pageField.style.width = said ? '' : '110px';
    pageField.classList.toggle('grow', said);
    pageField.hidden = !said && !kindOf(current).where && !page.value;     // articles, videos: no place inside them
    noteField.hidden = mode === 'note';
    wordsBy.el.hidden = mode === 'note';
  }
  arrange();
  sourceSel.addEventListener('change', () => {
    current = sources.find((x) => String(x.id) === sourceSel.value) || null;
    // from no source: whose words they were stays who said them
    if (!current && !wordsBy.items.length && entry?.by) wordsBy.set([personItem(entry.by)]);
    arrange();
    onSourceChange?.(current);
  });
  return {
    els: [holder],
    focusNote: () => note.focus(),
    about: () => aboutIn.value,
    topics: () => topicsIn.value,
    source: () => current,
    setMode(m) { mode = m; arrange(); },
    values() {
      const out = { page: page.value, note: note.value, source_id: sourceSel.value ? Number(sourceSel.value) : null };
      const by = wordsBy.value;
      out.words_by = by.length ? by[0] : null;
      if (touchedAbout || entry) out.about = aboutIn.value;
      if (touchedTopics || entry) out.topics = topicsIn.value;
      return out;
    },
    // the same, as a note on the source: it carries whom and what it is about itself
    noteValues() {
      return { sources: sourceSel.value ? [Number(sourceSel.value)] : [], place: page.value, people: aboutIn.value, topics: topicsIn.value };
    },
  };
}

async function viewEntryEdit({ args: [id] }) {
  const [e, sources, people, topics] = await Promise.all([api(`/api/entries/${id}`), store.sources(), store.people(), store.topics()]);
  const source = e.source ? sources.find((s) => s.id === e.source.id) || await api(`/api/sources/${e.source.id}`) : null;
  nav.label('Edit');
  const text = h('textarea', { class: 'textarea', rows: 6, id: 'f-text', value: e.text });
  const fields = entryFields({ source, sources, people, topics, entry: e });
  const msg = h('div', { class: 'note-line', role: 'alert' });
  const save = async (ev) => {
    ev.preventDefault();
    const body = { ...fields.values(), text: text.value };
    if (!body.source_id && !body.words_by) { msg.textContent = 'Say who said it: with no source, a quote needs a person.'; return; }
    try {
      await api(`/api/entries/${id}`, { method: 'PATCH', body });
      store.changed();
      toast('Saved');
      nav.finish(`entry/${id}`);
    } catch (err) { msg.textContent = err.message; }
  };
  const el = h('form', { onsubmit: save },
    bar(cancelButton(`entry/${id}`), 'Edit', h('button', { class: 'link-btn strong', type: 'submit' }, 'Save')),
    h('div', { class: 'details' },
      h('label', { class: 'field', for: 'f-text' }, h('span', { text: 'passage' }), text),
      fields.els,
      e.photo_id ? h('a', { class: 'btn small', href: `#/entry/${id}/photo`, style: { alignSelf: 'flex-start' } },
        e.photo_document ? 'Change the selection in the PDF' : 'Change the selection on the photo') : null,
      msg,
      h('button', { class: 'btn primary big', type: 'submit' }, 'Save')));
  return { el, bare: !isWide(), nav: 'quotes' };
}

async function viewEntryPhoto({ args: [id] }) {
  const e = await api(`/api/entries/${id}`);
  if (!e.photo_id) { nav.replace(`entry/${id}`); return null; }
  const photo = await api(`/api/photos/${e.photo_id}`);
  const pdf = photo.document;
  nav.label(pdf ? 'PDF' : 'Photo');
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
  const docLinks = pdf ? h('div', { class: 'page-turn' },
    pdf.previous ? h('a', { class: 'link-btn', href: `#/document/${pdf.id}?page=${pdf.index - 1}` }, icon('left', 18), 'page before') : h('span'),
    h('a', { class: 'link-btn', href: `${(await api(`/api/documents/${pdf.id}`)).file_url}#page=${pdf.index + 1}`, target: '_blank', rel: 'noopener' },
      'Open the PDF here', icon('external', 14)),
    pdf.next ? h('a', { class: 'link-btn', href: `#/document/${pdf.id}?page=${pdf.index + 1}` }, 'page after', icon('right', 18)) : h('span')) : null;
  const el = h('div', { class: 'fill-screen' },
    bar(backButton(`entry/${id}`, 'Quote'), pdf ? joinDots([e.page ? where(e) : null, `page ${pdf.index + 1} of the PDF`]).join('') : e.page ? where(e) : ''),
    sel.el,
    h('div', { class: 'sel-sheet' }, preview, nudgeBar(sel), saveBtn, docLinks));
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

function makeSelector(photo, { start = null, end = null, onChange = () => {}, startMode = null, kept = [] } = {}) {
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
  const keptLayer = h('div', { class: 'layer', 'aria-hidden': 'true' });
  const startDot = h('div', { class: 'handle start', title: 'Drag to move the start' });
  const endDot = h('div', { class: 'handle end', title: 'Drag to move the end' });
  const stage = h('div', { class: 'photo-stage' }, img, wordLayer, keptLayer, markLayer, startDot, endDot);
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

  // passages already kept from this page: a line in the margin beside them
  function drawKept() {
    put(keptLayer);
    for (const [a, b] of kept) {
      const span = words.slice(a, b + 1).filter(Boolean);
      if (!span.length) continue;
      const top = Math.min(...span.map((w) => w.y)), bottom = Math.max(...span.map((w) => w.y + w.h));
      const left = Math.min(...lines.filter((l) => l.words.some((w) => w.i >= a && w.i <= b)).map((l) => l.left));
      keptLayer.append(h('div', { class: 'kept', style: box(Math.max(0, left - photo.width * 0.018), top, photo.width * 0.006, bottom - top) }));
    }
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
  drawKept();
  const onResize = debounce(() => { sizeStage(); drawMarks(); }, 150);
  window.addEventListener('resize', onResize);
  sizeStage();
  setMode(mode, false);

  return {
    el: root,
    nudge,
    get range() { return s == null ? null : { start: s, end: e }; },
    setKept(list) { kept = list; drawKept(); },
    clear() { s = e = null; phase = 'none'; update(); },
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
    if (!url && !SHOP_HOSTS.test(host)) url = m.replace(/[.,;:!?)\]]+$/, '').replace(/#:~:text=.*$/, '');
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
    if (sh.url) { keepShared(sh); stepLink(sh.url, sh.title || '', sh.text, Boolean(sh.raw)); return; }
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
      h('label', { class: 'pick file-btn' }, h('span', { class: 'slot small icon-slot' }, icon('pdf', 26)),
        h('span', { class: 'main' }, h('span', { class: 't', text: 'PDF' }),
          h('span', { class: 'a', text: 'An article or a book as a PDF: recognised, kept, then read page by page' })), pdfInput(null)),
      newRow('link', 'Link', 'Article, video or podcast: paste the link, or share it from the app', () => stepLink('')),
      newRow('class', 'Class', 'A course you take: notes for each session, and quotes',
        () => go(`source/new?kind=class&then=capture${carry ? '&' + carry : ''}`)),
      newRow('pen', 'Something else', 'A talk, a film: type its title and who gave it',
        () => go(`source/new?kind=talk&then=capture${carry ? '&' + carry : ''}`)),
      newRow('said', 'Words someone said', 'Heard or read, with no source to point to', () => stepSaid('')),
      newRow('note', 'Note', 'Your own thoughts on a person, a topic or a source', () => go(`note/new${carry ? '?' + carry.replace('about=', 'person=') : ''}`)),
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
    if (!k.photos) { stepDetails(null, false, k.notesFirst ? 'note' : 'quote'); return; }
    const fileInput = (useCamera) => h('input', { type: 'file', accept: 'image/*', capture: useCamera ? 'environment' : null,
      'aria-label': useCamera ? 'Take a photo' : 'Choose a photo', onchange: (ev) => { const f = ev.target.files[0]; if (f) send(f); } });
    const drop = h('div', { class: 'drop wide-only' }, 'or drop a photo, a screenshot or a PDF here');
    for (const t of ['dragenter', 'dragover']) drop.addEventListener(t, (ev) => { ev.preventDefault(); drop.classList.add('over'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('over'));
    drop.addEventListener('drop', (ev) => {
      ev.preventDefault();
      drop.classList.remove('over');
      const f = ev.dataTransfer.files[0];
      if (f && (f.type === 'application/pdf' || /\.pdf$/i.test(f.name))) sendPdf(f, s.id); else if (f) send(f);
    });
    put(root,
      bar(startedHere ? backTo(home) : leave(), ''),
      h('div', { class: 'capture-start' },
        sourceChoice(s, () => stepPick((x) => stepSource(x))),
        root.dataset.error ? h('div', { class: 'error', role: 'alert', text: root.dataset.error }) : null,
        k.notesFirst ? h('button', { class: 'btn primary big', type: 'button', onclick: () => stepDetails(null, false, 'note') }, icon('note', 20), 'Write a note') : null,
        coarse()
          ? [h('label', { class: `btn ${k.notesFirst ? '' : 'primary '}big file-btn` }, icon('camera', 20), 'Take a photo', fileInput(true)),
            h('label', { class: 'btn big file-btn' }, icon('image', 20), s.kind === 'ebook' ? 'Choose a screenshot' : 'Choose a photo', fileInput(false))]
          : [h('label', { class: `btn ${k.notesFirst ? '' : 'primary '}big file-btn` }, icon('image', 20), 'Choose a photo or a screenshot', fileInput(false)), drop],
        h('button', { class: 'btn big', type: 'button', onclick: () => stepLater(s) }, icon('inbox', 20), 'Several pages, sort later'),
        h('label', { class: 'btn big file-btn' }, icon('pdf', 20), 'Its PDF', pdfInput(s.id)),
        h('button', { class: 'btn big', type: 'button', onclick: () => stepDetails(null) }, icon('pen', 20), 'Type a quote'),
        k.notesFirst ? null : h('button', { class: 'btn big', type: 'button', onclick: () => stepDetails(null, false, 'note') }, icon('note', 20), 'Write a note')));
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
      row('said', 'Someone said it', 'Who said it, with no source to point to', () => stepSaid(sh.text)),
      row('note', 'Your own note', 'Keep it as a note on a person, a topic or a source', () => go(`note/new?shared=1${carry ? '&' + carry.replace('about=', 'person=') : ''}`)),
      h('div', { class: 'list-end' }));
  }

  // words someone said, heard or read, with no source to point to
  function stepSaid(said = '', who = null) {
    cleanup();
    root.classList.remove('fill-screen');
    source = null;
    const text = h('textarea', { class: 'textarea', rows: 5, id: 'c-text', value: said });
    const fields = entryFields({ source: null, sources, people, topics, entry: who ? { by: who, about: [], topics: [] } : null,
      about: aboutPreset?.length ? aboutPreset : null, topicNames: topicPreset?.length ? topicPreset : null });
    const saveBtn = h('button', { class: 'btn primary big', type: 'submit' }, 'Save');
    const save = async (ev) => {
      ev.preventDefault();
      if (!text.value.trim()) { text.focus(); toast('The words are empty'); return; }
      const body = { ...fields.values(), text: text.value };
      if (!body.source_id && !body.words_by) { document.querySelector('#f-by')?.focus(); toast('Say who said it'); return; }
      saveBtn.disabled = true;
      try {
        const e = await api('/api/entries', { method: 'POST', body });
        store.changed();
        if (shared) finishShared();
        nav.flash = { entry: e.id };
        nav.finish(e.source ? `source/${e.source.id}` : `person/${e.by.id}`);
        toast('Saved');
      } catch (err) { saveBtn.disabled = false; toast(err.message); }
    };
    put(root, h('form', { onsubmit: save, class: 'fill-form' },
      bar(startedHere || shared ? backTo(home) : leave(), 'Words someone said'),
      h('div', { class: 'details' },
        h('label', { class: 'field', for: 'c-text' }, h('span', { text: 'what was said' }), text),
        fields.els),
      h('div', { class: 'save-bar' }, saveBtn)));
    setTimeout(() => (who ? text : document.getElementById('f-by'))?.focus(), 50);
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

  function stepDetails(selectedText, typedWithPhoto, startMode) {
    cleanup();
    root.classList.remove('fill-screen');
    const fromPhoto = Boolean(photo && selectedText != null && !typedWithPhoto);
    const k = kindOf(source);
    let mode = fromPhoto ? 'quote' : startMode || (k.notesFirst && !selectedText ? 'note' : 'quote');
    const text = h('textarea', { class: 'textarea', rows: fromPhoto ? 5 : 6, id: 'c-text', value: selectedText || '' });
    const textLabel = h('span');
    const fields = entryFields({ source, sources, people, topics, mode, about: aboutPreset?.length ? [...source.people.about, ...aboutPreset.filter((p) => !source.people.about.some((a) => a.id === p.id))] : null,
      topicNames: topicPreset?.length ? [...new Set([...source.topics.map((t) => t.name), ...topicPreset])] : null });
    const showMode = () => { textLabel.textContent = mode === 'quote' ? 'passage' : 'note'; fields.setMode(mode); };
    const modeSeg = modeSwitch(() => mode, (x) => { mode = x; }, showMode);
    showMode();
    const saveBtn = h('button', { class: 'btn primary big', type: 'submit' }, 'Save');
    const saveNote = async () => {
      const n = await api('/api/notes', { method: 'POST', body: { ...fields.noteValues(), text: text.value } });
      store.changed();
      if (shared) finishShared();
      const sid = n.sources[0]?.id;
      nav.flash = { note: n.id };
      nav.finish(sid ? `source/${sid}` : `note/${n.id}`);
      toast('Note saved');
    };
    const save = async (ev) => {
      ev.preventDefault();
      if (!text.value.trim()) { text.focus(); toast('The text is empty'); return; }
      saveBtn.disabled = true;
      if (mode === 'note') {
        try { await saveNote(); } catch (err) { saveBtn.disabled = false; toast(err.message); }
        return;
      }
      try {
        const body = { ...fields.values(), text: text.value };
        if (!body.source_id && !body.words_by) { saveBtn.disabled = false; toast('Say who said it'); return; }
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
          nav.finish(body.source_id ? `source/${body.source_id}` : `person/${e.by.id}`);
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
        fromPhoto ? null : modeSeg,
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
    let mode = quoted ? 'quote' : 'note';
    let sourceKind = info?.kind || source?.kind;
    const text = h('textarea', { class: 'textarea', rows: 5, id: 'c-text', value: quoted || '' });
    const textLabel = h('span');
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
    const fields = entryFields({ source: pseudo, sources: source ? sources : [{ ...pseudo, title: 'this new source' }], people, topics, mode, place: false,
      about: aboutPreset?.length ? aboutPreset : null, topicNames: topicPreset?.length ? topicPreset : null });
    const showMode = () => { textLabel.textContent = mode === 'quote' ? 'passage' : 'note'; fields.setMode(mode); };
    const modeSeg = modeSwitch(() => mode, (x) => { mode = x; }, showMode);
    showMode();
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
        let flash;
        if (mode === 'note') {
          const n = await api('/api/notes', { method: 'POST', body: { ...fields.noteValues(), sources: [sid], text: text.value } });
          flash = { note: n.id };
        } else {
          const e = await api('/api/entries', { method: 'POST', body: { ...values, source_id: sid, text: text.value } });
          flash = { entry: e.id };
        }
        store.changed();
        finishShared();
        nav.flash = { ...flash, cover: info?.image_url ? sid : null };
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
        modeSeg,
        h('label', { class: 'field', for: 'c-text' }, textLabel, text),
        fields.els),
      h('div', { class: 'save-bar' }, saveBtn)));
    if (!quoted) setTimeout(() => text.focus(), 50);
  }

  if (fromInbox) {
    photo = await api(`/api/photos/${encodeURIComponent(fromInbox)}`);
    if (photo.status !== 'ready') { toast('This page is still being read'); nav.replace('inbox'); return null; }
    source = sources.find((s) => s.id === photo.source_id);
    if (source) stepSelect();
    else stepPick(async (s) => { source = s; await api(`/api/photos/${photo.id}`, { method: 'PATCH', body: { source_id: s.id } }).catch(() => null); stepSelect(); });
  } else if (params.get('said')) {
    const who = people.find((p) => String(p.id) === params.get('said'));
    stepSaid('', who || null);
  } else if (params.has('share')) {
    // from the iPhone Shortcut or Android's Share menu: whatever another app shared (a passage, a link, or both),
    // and from Android, the page's title when a page was shared
    const raw = sharedParam();
    let saved = null;
    try { saved = sessionStorage.getItem('marginote.sharedSaved'); } catch { /* none */ }
    if (raw && raw === saved) stepStart();
    else takeShared({ ...parseShared(raw), raw, title: params.get('title') || '' });
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
  const [photos, docs] = await Promise.all([api('/api/photos'), api('/api/documents?queued=true')]);
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
  if (photos.some((p) => p.status === 'reading') || docs.some((d) => d.status === 'reading')) {   // check again until every page is read
    const mark = location.hash;
    setTimeout(() => { if (location.hash === mark) render(); }, 3000);
  }
  const el = h('div', {},
    h('header', { class: 'top' }, h('div', { class: 'top-row' }, h('h1', {}, 'Inbox', h('span', { class: 'count', text: photos.length + docs.length })))),
    docs.length ? [h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'PDFs to sort' })),
      docs.map((d) => h('a', { class: 'inbox-row doc', href: `#/document/${d.id}` },
        h('span', { class: 'thumb icon-slot' }, icon('pdf', 30)),
        h('div', { class: 'main' },
          h('span', { class: 't', text: d.found?.source?.title || d.found?.title || d.name }),
          h('span', { class: 'a' }, joinDots([
            d.name,
            d.status === 'reading' ? h('i', { text: `being read… ${d.read_pages}/${d.pages}` }) : plural(d.pages, 'page'),
            d.status === 'failed' ? h('i', { class: 'bad', text: 'could not be read' }) : null,
            d.existing ? h('i', { text: 'already in your library' }) : d.found?.source ? h('i', { text: 'recognised' }) : null,
          ])))))] : null,
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
      : docs.length ? null : h('div', { class: 'empty' }, 'Nothing to sort.', h('a', { class: 'btn', href: '#/capture' }, 'Capture')));
  return { el, nav: 'inbox' };
}

// ----- a PDF: read on the server, recognised, then its pages used like photos -----

// Send a PDF; its page opens and follows the reading.
async function sendPdf(file, sourceId = null, { replace = false } = {}) {
  if (!/\.pdf$/i.test(file.name) && file.type !== 'application/pdf') { toast('Choose a PDF file'); return; }
  toast(`Sending ${file.name}…`);
  try {
    const form = new FormData();
    form.append('file', file);
    const doc = await api(`/api/documents${sourceId ? `?source_id=${sourceId}` : ''}`, { method: 'POST', form });
    document.querySelector('.toast')?.remove();
    if (replace) nav.replace(`document/${doc.id}`); else go(`document/${doc.id}`);
  } catch (err) { toast(err.message); }
}

function pdfInput(sourceId, opts) {
  return h('input', { type: 'file', accept: 'application/pdf,.pdf', 'aria-label': 'Choose a PDF',
    onchange: (ev) => { const f = ev.target.files[0]; ev.target.value = ''; if (f) sendPdf(f, sourceId, opts); } });
}

const foundBy = { doi: 'the DOI', arxiv: 'the arXiv number', isbn: 'the ISBN' };

async function viewDocument({ args: [id], params }) {
  let doc = await api(`/api/documents/${id}`);
  nav.label('PDF');
  const root = h('div', { class: 'doc-view' });
  let selector = null;
  const cleanup = () => { selector?.destroy(); selector = null; };
  const back = () => (doc.source ? backButton(`source/${doc.source.id}`, shorten(doc.source.title, 22)) : backButton('inbox', 'Inbox'));
  const reload = async () => { doc = await api(`/api/documents/${id}`); };
  const remove = async () => {
    const ok = await confirmDialog({ title: 'Delete this PDF?', text: doc.entry_count
      ? `The ${plural(doc.entry_count, 'quote')} kept from it stay, with their page.` : 'Nothing was kept from it yet.',
    choices: [{ label: 'Delete the PDF', value: true, danger: true }] });
    if (!ok) return;
    try {
      await api(`/api/documents/${id}`, { method: 'DELETE' });
      store.changed();
      toast('PDF deleted');
      nav.back(doc.source ? `source/${doc.source.id}` : 'inbox');
    } catch (err) { toast(err.message); }
  };
  const giveSource = async (sourceId) => {
    try {
      doc = await api(`/api/documents/${id}`, { method: 'PATCH', body: { source_id: sourceId } });
      store.changed();
      pages(0);
    } catch (err) { toast(err.message); }
  };

  function reading() {
    cleanup();
    put(root, bar(back(), 'PDF'),
      h('div', { class: 'capture-start' },
        h('p', { class: 'doc-name' }, icon('pdf', 22), h('span', { text: doc.name })),
        h('div', { class: 'status-line', role: 'status' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }),
          `Reading the PDF… ${doc.read_pages} of ${plural(doc.pages, 'page')}`),
        h('p', { class: 'note-line', text: 'You can leave this page: the reading goes on, and the PDF waits in the inbox.' })));
    const mark = location.hash;
    setTimeout(async () => {
      if (location.hash !== mark) return;
      try { await reload(); } catch { return; }
      if (location.hash === mark) show();
    }, 1500);
  }

  function failed() {
    put(root, bar(back(), 'PDF'),
      h('div', { class: 'capture-start' },
        h('p', { class: 'doc-name' }, icon('pdf', 22), h('span', { text: doc.name })),
        h('div', { class: 'error', role: 'alert', text: 'This PDF could not be read.' }),
        h('button', { class: 'btn danger', type: 'button', onclick: remove, style: { alignSelf: 'flex-start' } }, 'Delete it')));
  }

  // what the PDF is: recognised from what is printed in it, or chosen
  function recognise(notThis = false) {
    cleanup();
    const f = doc.found;
    const src = notThis ? null : f.source;
    const ex = notThis ? null : doc.existing;
    const sent = h('p', { class: 'doc-name' }, icon('pdf', 22), h('span', { text: doc.name }), h('span', { class: 'muted', text: ` · ${plural(doc.pages, 'page')}` }));
    const how = f.by ? `Found from ${foundBy[f.by]} printed on page ${(f.page ?? 0) + 1}` : null;
    let card = null;
    if (ex) {
      card = [h('div', { class: 'found-card' },
        h('span', { class: 'sc', text: 'already in your library' }),
        h('b', { class: 't', text: ex.title })),
      h('button', { class: 'btn primary big', type: 'button', onclick: () => giveSource(ex.id) }, 'Yes, it is this one'),
      h('button', { class: 'btn big', type: 'button', onclick: () => recognise(true) }, 'It is not…')];
    } else if (src) {
      const names = src.people?.author || [];
      const create = async (ev) => {
        ev.currentTarget.disabled = true;
        try {
          const body = { ...src, fetch_cover: src.kind === 'book' };
          delete body.found_by;
          const made = await api('/api/sources', { method: 'POST', body });
          await giveSource(made.id);
        } catch (err) { ev.currentTarget.disabled = false; toast(err.message); }
      };
      card = [h('div', { class: 'found-card' },
        h('span', { class: 'sc', text: src.kind === 'book' ? 'book recognised' : 'article recognised' }),
        h('b', { class: 't', text: src.title }),
        names.length ? h('span', { text: names.length > 3 ? `${names.slice(0, 3).join(', ')} and ${names.length - 3} others` : names.join(', ') }) : null,
        inJournal(src) || src.publisher ? h('i', { text: [inJournal(src) || src.publisher, src.year].filter(Boolean).join(', ') }) : null,
        src.doi ? h('span', { class: 'muted', text: `doi:${src.doi}` }) : null,
        how ? h('span', { class: 'note-line', text: `${how}, then completed by ${src.found_by}.` }) : null),
      h('button', { class: 'btn primary big', type: 'button', onclick: create }, 'That’s it'),
      h('button', { class: 'btn big', type: 'button', onclick: () => recognise(true) }, 'It is not…'),
      names.length ? h('p', { class: 'note-line', text: 'Its authors join your people; those already there are not doubled.' }) : null];
    }
    const q = h('input', { type: 'search', placeholder: 'Find a source', 'aria-label': 'Find a source' });
    const list = h('div');
    const drawList = async () => {
      const sources = await store.sources();
      const needle = fold(q.value.trim());
      put(list, sources.filter((x) => !needle || fold(`${x.title} ${makers(x).map((m) => m.name).join(' ')}`).includes(needle)).slice(0, needle ? 30 : 6)
        .map((x) => h('button', { type: 'button', class: 'pick', onclick: () => giveSource(x.id) }, thumb(x),
          h('span', { class: 'main' }, h('span', { class: 't', text: x.title }), h('span', { class: 'a' }, sourceLine(x))))));
    };
    q.addEventListener('input', debounce(drawList, 120));
    const guess = f.title || doc.name.replace(/\.pdf$/i, '');
    const newHref = `#/source/new?kind=${src?.kind === 'book' || f.by === 'isbn' ? 'book' : 'article'}&title=${encodeURIComponent(guess)}&document=${id}`;
    const unreachable = f.note && /reached/.test(f.note);
    put(root, bar(back(), card ? 'Recognised' : 'Which source?'),
      h('div', { class: 'capture-start' },
        h('h1', { class: 'ask', text: card ? 'Is it this?' : 'Where is it from?' }),
        sent,
        card || [
          f.note ? h('p', { class: 'note-line', text: `${f.note}.` }) : null,
          unreachable ? h('button', { class: 'btn small', type: 'button', style: { alignSelf: 'flex-start' }, onclick: async () => {
            try { doc = await api(`/api/documents/${id}/recognize`, { method: 'POST' }); show(); } catch (err) { toast(err.message); }
          } }, 'Look again') : null,
          f.title && !notThis ? h('p', { class: 'note-line' }, 'Its title seems to be ', h('i', { text: `“${f.title}”` }), '.') : null,
          h('a', { class: 'btn primary big', href: newHref }, '+ New source')]),
      card ? null : [h('div', { class: 'colhead' }, h('span', { style: { flex: 1 }, text: 'or from your library' })),
        h('div', { class: 'pad' }, h('label', { class: 'search' }, icon('search', 16), q)), list],
      h('div', { class: 'pad' }, h('button', { class: 'btn small danger', type: 'button', onclick: remove, style: { alignSelf: 'flex-start' } }, 'Delete this PDF…')));
    if (!card) drawList();
  }

  // the pages, one at a time: choose a passage, keep it
  async function pages(index) {
    cleanup();
    const all = doc.page_list;
    index = Math.max(0, Math.min(index, all.length - 1));
    prefs.set(`docPage.${id}`, index);
    const meta = all[index];
    const [photo, entries] = await Promise.all([api(`/api/photos/${meta.photo_id}`), api(`/api/sources/${doc.source.id}/entries`)]);
    const kept = entries.filter((e) => e.photo_id === photo.id && e.word_start != null).map((e) => [e.word_start, e.word_end]);
    let range = null;
    const preview = h('p', { class: 'sel-preview empty', text: 'Tap the first word, then the last.' });
    const keptLine = h('span', { class: 'kept-count' });
    const showCount = () => { keptLine.textContent = joinDots([kept.length ? `${kept.length} kept on this page` : null, doc.entry_count ? `${doc.entry_count} in the PDF` : null]).join(''); };
    showCount();
    const keep = h('button', { class: 'btn primary big', type: 'button', disabled: true }, 'Keep this passage');
    keep.addEventListener('click', async () => {
      if (!range) return;
      keep.disabled = true;
      try {
        const e = await api('/api/entries', { method: 'POST', body: { source_id: doc.source.id, photo_id: photo.id,
          word_start: range.start, word_end: range.end, page: meta.page } });
        store.changed();
        kept.push([range.start, range.end]);
        doc.entry_count += 1;
        meta.entry_count += 1;
        selector.setKept(kept);
        selector.clear();
        showCount();
        toast('Kept', { label: 'Add a comment', run: () => go(`entry/${e.id}/edit`) });
      } catch (err) { keep.disabled = false; toast(err.message); }
    });
    selector = makeSelector(photo, { kept, onChange: (r) => {
      range = r.phase === 'none' ? null : { start: r.start, end: r.end };
      preview.textContent = r.text || 'Tap the first word, then the last.';
      preview.classList.toggle('empty', !r.text);
      keep.disabled = !range;
      keep.textContent = range ? `Keep this passage · ${plural(r.end - r.start + 1, 'word')}` : 'Keep this passage';
    } });
    const prev = all[index - 1], next = all[index + 1];
    put(root,
      bar(back(), `p. ${meta.page} · ${index + 1}/${all.length}`,
        h('a', { class: 'link-btn', href: `${doc.file_url}#page=${index + 1}`, target: '_blank', rel: 'noopener' }, 'Open', icon('external', 14))),
      selector.el,
      h('div', { class: 'sel-sheet' }, preview, nudgeBar(selector), keep,
        h('div', { class: 'page-turn' },
          prev ? h('button', { class: 'link-btn', type: 'button', onclick: () => pages(index - 1) }, icon('left', 18), `p. ${prev.page}`) : h('span'),
          keptLine,
          next ? h('button', { class: 'link-btn', type: 'button', onclick: () => pages(index + 1) }, `p. ${next.page}`, icon('right', 18)) : h('span'))));
    root.classList.add('fill-screen');
  }

  function show() {
    root.classList.remove('fill-screen');
    if (doc.status === 'reading') reading();
    else if (doc.status === 'failed') failed();
    else if (!doc.source) recognise();
    else {
      const at = params.get('page') != null ? Number(params.get('page')) : prefs.get(`docPage.${id}`, 0);
      pages(Number.isFinite(at) ? at : 0);
    }
  }
  show();
  return { el: root, bare: true, cleanup };
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
  const title = field('s-title', 'title', { required: true, autocapitalize: 'sentences' }, s.title || params.get('title') || '');
  const subtitle = field('s-subtitle', 'subtitle', {}, s.subtitle);
  const fields = [...new Set(sources.map((x) => x.field).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  const fieldIn = field('s-field', 'kind of work', { list: 'fields', autocomplete: 'off', autocapitalize: 'sentences', placeholder: 'Philosophie, Roman, Histoire…' }, s.field);
  const publisher = field('s-publisher', 'publisher', {}, s.publisher);
  const edition = field('s-edition', 'edition', {}, s.edition);
  const year = field('s-year', 'year', { inputmode: 'numeric' }, s.year);
  const date = field('s-date', 'date', { inputmode: 'numeric', placeholder: '2026-10-02' }, s.date);
  // a scientific article: its DOI or arXiv number, and where it was published
  const ids = { doi: s.doi || null, arxiv: s.arxiv || null };
  const ident = field('s-ident', 'doi or arxiv', { autocomplete: 'off', autocapitalize: 'none', autocorrect: 'off', spellcheck: 'false',
    placeholder: '10.1000/xyz123 or 2401.01234' }, s.doi || (s.arxiv ? `arXiv:${s.arxiv}` : ''));
  const journal = field('s-journal', 'journal', { autocapitalize: 'words' }, s.journal);
  const volume = field('s-volume', 'volume', { inputmode: 'numeric' }, s.volume);
  const issue = field('s-issue', 'issue', {}, s.issue);
  const pages = field('s-pages', 'pages', { placeholder: '45–56' }, s.pages);
  let journalOpen = Boolean(s.journal || s.volume || s.issue || s.pages || s.doi || s.arxiv);
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

  const named = (list) => list.map((n) => ({ key: 'new:' + fold(n), label: n, value: n }));
  const showIds = () => { ident.input.value = ids.doi || (ids.arxiv ? `arXiv:${ids.arxiv}` : ''); };
  const fillArticle = (f) => {
    if (!editing && KINDS[f.kind]) kind = f.kind;
    for (const [key, input] of Object.entries({ title, subtitle, publisher, journal, volume, issue, pages, isbn })) if (f[key]) input.input.value = f[key];
    if (f.date || f.year) date.input.value = f.date || String(f.year);
    if (f.year) year.input.value = f.year;
    if (f.people?.author?.length) makersIn.set(named(f.people.author));     // every author is kept
    if (f.people?.editor?.length) editors.set(named(f.people.editor));
    if (f.language) language.value = ['fr', 'en'].includes(f.language) ? f.language : 'other';
    if (f.url && !url.input.value.trim()) url.input.value = f.url;
    ids.doi = f.doi || ids.doi;
    ids.arxiv = f.arxiv || ids.arxiv;
    showIds();
    journalOpen = true;
    layout();
  };
  const lookUpArticle = async () => {
    const text = ident.input.value.trim();
    if (!text) { ident.input.focus(); return; }
    put(msg, 'Looking up…');
    try {
      const r = await api('/api/recognize', { method: 'POST', body: { text } });
      if (r.kind === 'url') { url.input.value = r.value; showIds(); await readPage(); return; }
      if (r.kind === 'isbn') { if (!editing) { kind = 'book'; layout(); } isbn.input.value = r.value; showIds(); await lookUp(); return; }
      if (r.kind === 'text') { put(msg, 'No DOI or arXiv number found here. A DOI looks like 10.1000/xyz123.'); return; }
      ids[r.kind] = r.value;
      if (r.kind === 'doi' && ids.arxiv && r.source?.arxiv !== ids.arxiv) ids.arxiv = r.source?.arxiv || null;
      showIds();
      if (r.existing && r.existing.id !== s.id) { put(msg, found(r.existing)); return; }
      if (!r.source) { put(msg, `${r.note || 'Nothing found'}. Type the details in.`); return; }
      fillArticle(r.source);
      put(msg, `Found on ${r.source.found_by}.`, found(r.existing));
    } catch (err) { put(msg, err.message); }
  };
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
      if (f.people?.length) makersIn.set(named(f.people));
      if (f.language) language.value = ['fr', 'en'].includes(f.language) ? f.language : 'other';
      if (f.doi || f.arxiv || f.journal) {          // a scientific article: its journal, every author
        for (const [key, input] of Object.entries({ journal, volume, issue, pages })) if (f[key]) input.input.value = f[key];
        ids.doi = f.doi || ids.doi;
        ids.arxiv = f.arxiv || ids.arxiv;
        showIds();
        journalOpen = true;
        layout();
      }
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
  ident.input.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); lookUpArticle(); } });
  const identRow = h('div', { class: 'two' }, h('div', { class: 'grow' }, ident.el),
    h('button', { class: 'btn small', type: 'button', onclick: lookUpArticle }, 'Look up'));
  const journalBox = h('div', { class: 'journal-box' }, journal.el,
    h('div', { class: 'two' }, h('div', { class: 'w-short' }, volume.el), h('div', { class: 'w-short' }, issue.el), h('div', { class: 'grow' }, pages.el)));
  const journalOpener = h('button', { class: 'link-btn more-fields', type: 'button', onclick: () => { journalOpen = true; layout(); journal.input.focus(); } },
    '+ Journal, volume, pages');
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
    identRow.hidden = !(kind === 'article' || ids.doi || ids.arxiv);
    journalBox.hidden = !(kind === 'article' && journalOpen);
    journalOpener.hidden = !(kind === 'article' && !journalOpen);
    for (const el of bookOnly) el.hidden = !(kind === 'book' || kind === 'ebook');
    yearBox.hidden = Boolean(k.dated);
    dateBox.hidden = !k.dated;
    publisher.el.firstChild.textContent = kind === 'article' && journalOpen ? 'publisher' : k.publisher;
    makersIn.el.querySelector('.label').textContent = k.makerLabel;
  }
  layout();

  const payload = () => {
    const y = year.input.value.trim();
    const lang = language.value === 'other' ? (s.language && !['fr', 'en'].includes(s.language) ? s.language : null) : language.value || null;
    const k = KINDS[kind];
    const roles = { author: k.maker === 'author' ? makersIn.value : [], speaker: k.maker === 'speaker' ? makersIn.value : [], about: about.value };
    if (kind === 'book' || kind === 'ebook') Object.assign(roles, { translator: translators.value, editor: editors.value });
    // the field holds the DOI, or the arXiv number when there is no DOI; the other one is kept as found
    const idText = identRow.hidden ? null : ident.input.value.trim();
    const isDoi = /(^|doi\.org\/|^doi:?\s*)10\.\d{4,9}\//i.test(idText || '');     // arXiv's own DOIs too: 10.48550/arXiv.…
    const isArxiv = !isDoi && /arxiv|^\d{4}\.\d{4,5}(v\d+)?$|^[a-z-]+(\.[a-z]{2})?\/\d{7}(v\d+)?$/i.test(idText || '');
    const article = kind === 'article';
    Object.assign(ids, idText === null ? {} : !idText ? { doi: null, arxiv: null } : isArxiv ? { arxiv: idText } : { doi: idText });
    return { kind, doi: ids.doi, arxiv: ids.arxiv,
      journal: article ? journal.input.value : null, volume: article ? volume.input.value : null,
      issue: article ? issue.input.value : null, pages: article ? pages.input.value : null, title: title.input.value, subtitle: subtitle.input.value, publisher: publisher.input.value, edition: edition.input.value,
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
        if (params.get('document')) {        // a PDF waiting for the source it is
          await api(`/api/documents/${params.get('document')}`, { method: 'PATCH', body: { source_id: created.id } });
          nav.replace(`document/${params.get('document')}`);
        } else if (params.get('then') === 'capture') nav.replace(`capture?source=${created.id}${carry}`);
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
      isbnRow, identRow, urlRow,
      msg,
      title.el, subtitle.el,
      makersIn.el, translators.el,
      about.el, topicsIn.el,
      journalBox,
      h('div', { class: 'two' }, h('div', { class: 'grow' }, publisher.el), yearBox, dateBox),
      journalOpener,
      fieldIn.el,
      h('div', { class: 'two' }, editionBox, h('label', { class: 'field grow', for: 's-language' }, h('span', { text: 'language' }), language)),
      editors.el,
      h('button', { class: 'btn primary big', type: 'submit' }, editing ? 'Save' : 'Add it')));
  if (!editing) setTimeout(() => (!isbnRow.hidden ? isbn.input : !identRow.hidden ? ident.input : !urlRow.hidden ? url.input : title.input).focus(), 50);
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
    others.map((x) => h('option', { value: String(x.id) }, `${x.sort_name}${x.entries ? ` (${plural(x.entries, 'quote')})` : ''}`)));
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
    : h('div', { class: 'empty' }, q ? 'No note contains these words.' : 'Your own writing goes here: on a book, a video, a class, a person or a topic.',
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
      n.sources.length ? h('div', { class: 'note-sources' }, n.sources.map((src) => h('a', { class: 'plink it', href: `#/source/${src.id}`, text: src.title })),
        n.place ? h('span', { class: 'muted', text: `, ${placeText(n.place)}` }) : null) : n.place ? h('div', { class: 'kv', text: placeText(n.place) }) : null,
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
  const [note, people, topics, sources] = await Promise.all([editing ? api(`/api/notes/${id}`) : null, store.people(), store.topics(), store.sources()]);
  nav.label(editing ? 'Edit' : 'New note');
  const n = note || { title: '', text: '', place: '', sources: [], people: [], topics: [], entries: [] };
  if (!editing) {
    const person = people.find((p) => String(p.id) === params.get('person'));
    const topic = topics.find((t) => String(t.id) === params.get('topic'));
    const source = sources.find((x) => String(x.id) === params.get('source'));
    if (person) n.people = [person];
    if (topic) n.topics = [topic];
    if (source) n.sources = [source];
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
  const sourcesIn = sourcesInput('on (a book, a video, a class…)', n.sources.map((x) => sources.find((y) => y.id === x.id) || x), sources,
    { id: 'n-sources', onchange: (items) => { placeBox.hidden = !items.length; } });
  const place = field('n-place', 'where in it (page, chapter, session)', { placeholder: 'Séance 3, p. 57…' }, n.place || '');
  const placeBox = h('div', { hidden: !n.sources.length }, place.el);
  const peopleIn = peopleInput('people', n.people, people, { id: 'n-people', placeholder: 'who it is about' });
  const topicsIn = topicsInput('topics', n.topics.map((t) => t.name), topics, { id: 'n-topics' });
  const linkedBox = h('div');
  const finder = h('div', { class: 'finder', hidden: true });
  const findInput = h('input', { type: 'search', placeholder: 'Words of the quote, its source, a person', 'aria-label': 'Find a quote' });
  const found = h('div');
  findInput.addEventListener('input', debounce(async () => {
    const q = findInput.value.trim();
    if (q.length < 2) { put(found); return; }
    try {
      const hits = await api(`/api/search?q=${encodeURIComponent(q)}&limit=12`);
      put(found, hits.filter((e) => !linked.some((x) => x.id === e.id)).map((e) => h('button', { type: 'button', class: 'pick',
        onclick: () => { linked.push(e); drawLinked(); finder.hidden = true; findInput.value = ''; put(found); } },
      h('span', { class: 'main' }, h('span', { class: 'txt2', text: shorten(e.text, 140) }), h('span', { class: 'a', text: citation(e, e.source) })))));
    } catch (err) { put(found, errorBox(err)); }
  }, 300));
  put(finder, h('label', { class: 'search' }, icon('search', 16), findInput), found);
  function drawLinked() {
    put(linkedBox, linked.map((e) => h('div', { class: 'linked-row' },
      h('span', { class: 'main' }, h('span', { class: 'txt2', text: shorten(e.text, 110) }), h('span', { class: 'a', text: citation(e, e.source) })),
      h('button', { type: 'button', class: 'x', 'aria-label': 'Remove this reference', onclick: () => { linked = linked.filter((x) => x !== e); drawLinked(); } }, '×'))));
  }
  drawLinked();
  const msg = h('div', { class: 'note-line', role: 'alert' });
  const save = async (ev) => {
    ev.preventDefault();
    if (!text.value.trim()) { text.focus(); msg.textContent = 'The note is empty'; return; }
    const body = { title: title.input.value, text: text.value, sources: sourcesIn.value, place: sourcesIn.value.length ? place.input.value : '',
      people: peopleIn.value, topics: topicsIn.value, entries: linked.map((e) => e.id) };
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
        if (params.get('source')) nav.flash = { note: created.id };
        if (nav.prev() && (params.get('person') || params.get('topic') || params.get('entry') || params.get('source'))) nav.back(`note/${created.id}`);
        else nav.replace(`note/${created.id}`);
      }
    } catch (err) { msg.textContent = err.message; }
  };
  const el = h('form', { onsubmit: save },
    bar(cancelButton(editing ? `note/${id}` : 'notes'), editing ? 'Edit note' : 'New note', h('button', { class: 'link-btn strong', type: 'submit' }, 'Save')),
    h('div', { class: 'details' },
      title.el,
      h('label', { class: 'field', for: 'n-text' }, h('span', { text: 'note' }), text),
      sourcesIn.el, placeBox,
      topicsIn.el, peopleIn.el,
      h('div', { class: 'field' }, h('span', { class: 'label', text: 'refers to (optional)' }), linkedBox,
        h('button', { type: 'button', class: 'btn small', style: { alignSelf: 'flex-start', marginTop: '6px' },
          onclick: () => { finder.hidden = !finder.hidden; if (!finder.hidden) findInput.focus(); } }, '+ Link a quote'), finder),
      h('p', { class: 'note-line', text: 'Shown on the page of each source, person and topic it is on.' }),
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

// ----- sending keys: a computer or a phone adds to this library without logging in -----

async function windowsInstaller(key) {
  const template = await (await fetch('/static/marginote-windows.ps1', { cache: 'no-store' })).text();
  const script = template.replace("'__SERVER__'", `'${location.origin}'`).replace("'__KEY__'", `'${key}'`).replace(/\r?\n/g, '\r\n');
  // with its byte-order mark, so that Windows PowerShell reads its accents right
  const url = URL.createObjectURL(new Blob(['\ufeff' + script], { type: 'application/octet-stream' }));
  const a = h('a', { href: url, download: 'marginote-windows.ps1' });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

function keysSection(keys, copyBtn, steps) {
  const list = h('div', { class: 'key-list' });
  const shown = h('div', { class: 'key-made' });
  const name = h('input', { class: 'input', id: 'k-name', maxlength: 60, placeholder: 'PC du bureau, iPhone…', autocomplete: 'off' });
  const drawList = () => put(list, keys.length ? keys.map((k) => h('div', { class: 'key-row' },
    h('div', { class: 'main' }, h('b', { text: k.name }),
      h('span', { class: 'muted', text: joinDots([`made ${fullDate(k.created_at)}`, k.last_used ? `last used ${dateTime(k.last_used)}` : 'never used']).join('') })),
    h('button', { class: 'btn small danger', type: 'button', onclick: async () => {
      const ok = await confirmDialog({ title: `Delete the key “${k.name}”?`, text: 'That device can no longer send to your library.',
        choices: [{ label: 'Delete the key', value: true, danger: true }] });
      if (!ok) return;
      try { await api(`/api/keys/${k.id}`, { method: 'DELETE' }); keys = keys.filter((x) => x.id !== k.id); drawList(); toast('Key deleted'); } catch (err) { toast(err.message); }
    } }, 'Delete…'))) : h('p', { class: 'note-line', text: 'No key yet.' }));
  const make = async (ev) => {
    ev.preventDefault();
    if (!name.value.trim()) { name.focus(); return; }
    try {
      const made = await api('/api/keys', { method: 'POST', body: { name: name.value.trim() } });
      keys = [...keys, made];
      name.value = '';
      drawList();
      const endpoint = `${location.origin}/api/send/passage`;
      const bearer = `Bearer ${made.key}`;
      const command = 'powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\\Downloads\\marginote-windows.ps1"';
      put(shown,
        h('p', {}, h('b', { text: `The key for “${made.name}”` }), ', shown only now:'),
        h('pre', { class: 'code', text: made.key }),
        copyBtn(made.key, 'Copy the key'),
        h('h3', { class: 'sub-title', text: 'On Windows: Ctrl+Alt+M' }),
        steps([
          h('span', {}, 'Click ', h('button', { class: 'btn small', type: 'button', onclick: () => windowsInstaller(made.key).catch((err) => toast(err.message)) },
            icon('download'), 'Download the Windows installer'), ': marginote-windows.ps1 lands in Téléchargements.'),
          'Open PowerShell: right-click the Start button (or Windows+X), then « Terminal » (« Windows PowerShell » on Windows 10).',
          h('span', {}, 'Paste this line, then press Entrée:', h('pre', { class: 'code', text: command }), copyBtn(command, 'Copy the line')),
        ]),
        h('p', { class: 'note-line', text: 'Done when: PowerShell writes « C’est prêt. » Then, in a PDF, select a sentence, copy it (Ctrl+C) and press Ctrl+Alt+M: a notification says where it was kept. Ctrl+Alt+N asks for a comment first. A PDF or an image: right-click › Envoyer vers › Marginote (« Afficher d’autres options » first on Windows 11).' }),
        h('p', { class: 'note-line', text: 'The installer deletes itself once done: it held the key. If PowerShell says the file is not found, type powershell -ExecutionPolicy Bypass -File and a space, drag the file from Téléchargements into the window, then Entrée.' }),
        h('h3', { class: 'sub-title', text: 'On the iPhone: send without opening the app' }),
        steps([
          'In Raccourcis, tap +. Tap the name at the top, « Renommer », and type Marginote · envoyer.',
          'Tap ⓘ and turn on « Dans la feuille de partage », then OK. Tap the blue word after « Recevoir », tap « Effacer », tick only « Texte », then OK.',
          h('span', {}, 'Add the action « Obtenir le contenu de l’URL ». Touch its blue « URL » and paste:', h('pre', { class: 'code', text: endpoint }), copyBtn(endpoint, 'Copy the address')),
          h('span', {}, 'Tap › on that action. Méthode: POST. En-têtes: « Ajouter un nouvel en-tête », key Authorization, text:', h('pre', { class: 'code', text: bearer }), copyBtn(bearer, 'Copy this text')),
          'Corps de la requête: JSON. « Ajouter un nouveau champ » › Texte: key text, value: tap « Entrée du raccourci » above the keyboard. Another field › Texte: key origin, value iphone.',
          'Add the action « Obtenir la valeur du dictionnaire »: « Valeur » for the key say, in « Contenu de l’URL ».',
          'Add the action « Afficher la notification » and put « Valeur du dictionnaire » in it. OK.',
        ]),
        h('p', { class: 'note-line', text: 'Done when: in Fichiers or Livres, you select a sentence of a PDF, tap Partager › Marginote · envoyer, and a notification says « Gardé · … » (or « À trier · … »). The first time, iOS asks whether the shortcut may connect to your server: Autoriser.' }));
      shown.scrollIntoView({ block: 'start', behavior: 'smooth' });
    } catch (err) { toast(err.message); }
  };
  drawList();
  return h('div', { class: 'keys-block' },
    h('h3', { class: 'sub-title', text: 'Sending keys' }),
    h('p', {}, 'A sending key lets a computer or a phone add passages, PDFs and photos to your library without logging in: Ctrl+Alt+M on Windows, or a shortcut on the iPhone that does not open the app. It can only add, never read your library. One key per device; delete it, and that device can no longer send.'),
    list,
    h('form', { class: 'two key-form', onsubmit: make },
      h('label', { class: 'field grow', for: 'k-name' }, h('span', { text: 'for which device?' }), name),
      h('button', { class: 'btn small', type: 'submit' }, 'Make a key')),
    shown);
}

// the phone or computer this is: its way of sending from other apps is the one shown unfolded in Settings
function deviceKind() {
  const ua = navigator.userAgent;
  if (/Android/i.test(ua)) return 'android';
  if (/iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return 'iphone';
  return 'computer';
}

// your name, language and password; the owner also adds and removes people
function accountSection(me, accounts) {
  const msg = h('div', { class: 'note-line', role: 'alert' });
  const nameIn = h('input', { class: 'input', id: 'me-name', value: me.name, autocomplete: 'off' });
  const rename = async (ev) => {
    ev.preventDefault();
    try { await api('/api/me', { method: 'PATCH', body: { name: nameIn.value } }); prefs.set('loginName', nameIn.value.trim()); toast('Saved'); }
    catch (err) { msg.textContent = err.message; }
  };
  const language = segmented('Language', [['fr', 'Français'], ['en', 'English']], me.language, async (lang) => {
    try { await api('/api/me', { method: 'PATCH', body: { language: lang } }); location.reload(); } catch (err) { msg.textContent = err.message; }
  });
  const current = h('input', { class: 'input', type: 'password', id: 'pw-current', autocomplete: 'current-password' });
  const fresh = h('input', { class: 'input', type: 'password', id: 'pw-new', autocomplete: 'new-password', minlength: 8 });
  const changePassword = async (ev) => {
    ev.preventDefault();
    try {
      await api('/api/me', { method: 'PATCH', body: { password: { current: current.value, new: fresh.value } } });
      current.value = ''; fresh.value = '';
      toast('Password changed');
    } catch (err) { msg.textContent = err.message; }
  };
  const parts = [
    h('h2', { class: 'section-title', text: 'Account' }),
    h('form', { class: 'inline-form', onsubmit: rename },
      h('label', { class: 'field grow', for: 'me-name' }, h('span', { text: 'your name' }), nameIn),
      h('button', { class: 'btn small', type: 'submit' }, 'Rename')),
    h('div', { class: 'field' }, h('span', { class: 'label', text: 'language' }), language),
    h('p', { class: 'note-line', text: 'Your library is yours alone: nobody else can see it, not even the owner.' }),
    me.owner
      ? h('p', { class: 'note-line', text: 'Your password is MARGINOTE_PASSWORD, in the compose file: change it there, then redeploy.' })
      : h('form', { class: 'stack-form', onsubmit: changePassword },
        h('h3', { class: 'sub-title', text: 'Change your password' }),
        h('label', { class: 'field', for: 'pw-current' }, h('span', { text: 'current password' }), current),
        h('label', { class: 'field', for: 'pw-new' }, h('span', { text: 'new password (8 characters at least)' }), fresh),
        h('button', { class: 'btn small', type: 'submit', style: { alignSelf: 'flex-start' } }, 'Change the password')),
    msg,
  ];
  if (!me.owner) return parts;
  // the owner: who else has a library here
  const others = accounts.filter((a) => !a.owner);
  const newName = h('input', { class: 'input', id: 'acc-name', autocomplete: 'off' });
  const newPw = h('input', { class: 'input', type: 'text', id: 'acc-pw', autocomplete: 'off', minlength: 8 });
  const newLang = h('select', { class: 'select', id: 'acc-lang' }, h('option', { value: 'fr' }, 'Français'), h('option', { value: 'en' }, 'English'));
  const add = async (ev) => {
    ev.preventDefault();
    try {
      const a = await api('/api/accounts', { method: 'POST', body: { name: newName.value, password: newPw.value, language: newLang.value } });
      toast(`${a.name} can log in now`);
      render();
    } catch (err) { msg.textContent = err.message; }
  };
  const row = (a) => {
    const box = h('div', { class: 'account-row' });
    const draw = (resetting) => put(box,
      h('div', { class: 'grow' }, h('b', { text: a.name }), h('span', { class: 'meta' }, joinDots([a.language === 'fr' ? 'Français' : 'English',
        `since ${fullDate(a.created_at)}`]))),
      resetting
        ? h('form', { class: 'inline-form', onsubmit: async (ev) => {
          ev.preventDefault();
          const pw = ev.target.querySelector('input').value;
          try {
            await api(`/api/accounts/${a.id}`, { method: 'PATCH', body: { password: pw } });
            toast('New password set: they are logged out everywhere');
            draw(false);
          } catch (err) { msg.textContent = err.message; }
        } }, h('input', { class: 'input', type: 'text', autocomplete: 'off', minlength: 8, 'aria-label': 'new password (8 characters at least)',
          placeholder: 'new password (8 characters at least)' }), h('button', { class: 'btn small', type: 'submit' }, 'Save'))
        : h('div', { class: 'row-btns' },
          h('button', { class: 'btn small', type: 'button', onclick: () => draw(true) }, 'New password…'),
          h('button', { class: 'btn small danger', type: 'button', onclick: async () => {
            const ok = await confirmDialog({ title: `Remove ${a.name}?`,
              text: 'They can no longer log in. Their library is kept on the NAS, in data/users/removed.',
              choices: [{ label: 'Remove the account', value: true, danger: true }] });
            if (!ok) return;
            try { await api(`/api/accounts/${a.id}`, { method: 'DELETE' }); toast('Account removed'); render(); } catch (err) { msg.textContent = err.message; }
          } }, 'Remove…')));
    draw(false);
    return box;
  };
  return [...parts,
    h('h2', { class: 'section-title', text: 'People with access' }),
    h('p', { class: 'note-line', text: 'Each person has their own library. Nobody, not even you, can read or change another person’s quotes, notes or photos in the app.' }),
    others.map(row),
    h('form', { class: 'stack-form', onsubmit: add },
      h('h3', { class: 'sub-title', text: 'Add someone' }),
      h('label', { class: 'field', for: 'acc-name' }, h('span', { text: 'their name' }), newName),
      h('label', { class: 'field', for: 'acc-pw' }, h('span', { text: 'password (8 characters at least)' }), newPw),
      h('label', { class: 'field', for: 'acc-lang' }, h('span', { text: 'language' }), newLang),
      h('button', { class: 'btn small', type: 'submit', style: { alignSelf: 'flex-start' } }, 'Add'))];
}

async function viewSettings() {
  const [health, backups, me, keys] = await Promise.all([api('/api/health'), api('/api/backup/status'), api('/api/me'), api('/api/keys')]);
  const accounts = me.owner ? await api('/api/accounts') : [];
  const folder = 'data/users/' + me.id;   // where this library is, on the NAS
  nav.label('Settings');
  const backupMsg = h('span', { class: 'note-line', role: 'status' });
  const daily = backups.copies.filter((c) => c.kind === 'daily');
  const upgrades = backups.copies.filter((c) => c.kind === 'before upgrade');
  const table = (rows) => h('table', { class: 'grid settings' }, h('tbody', {}, rows.map(([k, v]) => h('tr', {}, h('td', { text: k }), h('td', { class: 'm', text: v })))));
  const copyBtn = (text, label) => h('button', { class: 'btn small', type: 'button', style: { alignSelf: 'flex-start' }, onclick: async () => {
    try { await navigator.clipboard.writeText(text); toast('Copied'); } catch { toast('Copying is not allowed here: select the text and copy it'); }
  } }, label);
  const steps = (items) => h('ol', { class: 'steps' }, items.map((i) => h('li', {}, i)));
  // a way of sending from other apps: the one for this device is unfolded, the others folded
  const way = (kind, title, body) => foldable(`settings:send:${kind}`, h('div', { class: 'group-row sub-head' }, h('h3', { class: 'sub-title', text: title })),
    body, kind !== deviceKind());
  const el = h('div', {},
    h('header', { class: 'top' }, h('div', { class: 'top-row' }, h('h1', {}, 'Settings'))),
    h('div', { class: 'pad settings-page' },
      h('h2', { class: 'section-title', text: 'Export' }),
      h('p', {}, 'Your quotes and notes in a PDF or Word file, by author, by topic or by source, with a table of contents you can tap.'),
      h('a', { class: 'btn', href: '#/export', style: { alignSelf: 'flex-start' } }, icon('download'), 'Export…'),
      accountSection(me, accounts),
      h('h2', { class: 'section-title', text: 'Backups' }),
      table([
        ['Last copy', daily[0] ? dateTime(daily[0].written_at) : 'none yet'],
        ['Copies kept', `${daily.length}: the last ${backups.kept} days, and the first of each of the last ${backups.monthly} months`],
        ['Next copy', dateTime(backups.next)],
        ['Before upgrades', upgrades.length ? upgrades.map((c) => c.file).join(', ') : 'none'],
      ]),
      h('p', { class: 'note-line', text: `Copies of the database are zips in ${folder}/backups on the NAS. Photos and covers are plain files: your NAS snapshots keep them.` }),
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
      keysSection(keys, copyBtn, steps),
      way('computer', 'On a computer: a bookmark', [
        h('p', {}, 'Drag this button to your bookmarks bar, once. Then select text on any page and click the bookmark: the page opens here, with the passage, its link and its title filled in.'),
        h('a', { class: 'btn small bookmarklet', href: bookmarklet(), onclick: (ev) => { ev.preventDefault(); toast('Drag it to the bookmarks bar'); } }, '→ Marginote')]),
      way('iphone', 'On the iPhone: « Marginote » in every app’s Share menu', [
        h('p', {}, 'A shortcut made once in Apple’s Shortcuts app (Raccourcis). Then select text in any app (Safari, Notes, Mail, Books, a PDF…), tap Partager, then Marginote: this app opens with the passage and asks where it is from. A link shared on its own (YouTube, Podcasts, an article) opens its form here.'),
        steps([
          'In Raccourcis, tap + (top right). Tap the name at the top, « Renommer », and type Marginote.',
          'Tap ⓘ (at the bottom, or in the menu under the name) and turn on « Dans la feuille de partage » (« Afficher dans la feuille de partage » on older iPhones), then OK. A first line appears: « Recevoir … ». Tap the blue word after « Recevoir », tap « Effacer », tick only « Texte » and « URL », then OK.',
          'Add the action « Texte » (search box at the bottom). Touch inside its box and tap « Entrée du raccourci » in the bar above the keyboard.',
          'Add the action that encodes text for an address: search « encod » and choose « Encoder l’URL » (it may be worded slightly differently). It takes the Texte above by itself; leave it on « Encoder ».',
          'Add the action « URL ». Paste the address below in its box, then, right after it with no space, tap the result of the encoding step in the bar above the keyboard.',
          'Add the action « Ouvrir les URL », then OK (top right).',
        ]),
        h('pre', { class: 'code', text: shareAddress() }),
        copyBtn(shareAddress(), 'Copy the address'),
        h('p', { class: 'note-line', text: 'Done when: in Notes, you select a sentence, tap Partager (behind › in the small menu if needed), scroll down to Marginote, and this app opens on « Where is it from? » with your sentence. The first time, iOS asks whether the shortcut may open the address: Autoriser.' }),
        h('p', { class: 'note-line', text: 'It opens in Safari: log in there once (the app on the Home Screen keeps its own login), with Tailscale on. To find Marginote at the top of the Share menu: « Modifier les actions… » at its bottom, then add it to Favoris.' }),
        h('p', { class: 'note-line', text: 'An app without Partager in its menu (Kindle): Copy the passage, then here, Capture › Paste what you copied.' })]),
      way('android', 'On Android (Samsung and others): « Marginote » in the Share menu', [
        h('p', {}, 'Nothing to make: once this app is installed from Chrome, Android lists it in the Share menu. Then select text in any app (Chrome, Samsung Notes, Gmail, a PDF…), tap Partager, then Marginote: this app opens with the passage and asks where it is from. A link shared on its own (YouTube, an article) opens its form here.'),
        steps([
          'Turn Tailscale on, then open this address in Chrome (Google’s browser, not Samsung Internet) and log in.',
          'In Chrome, tap ⋮ (top right), then « Installer l’application ». If you only see « Ajouter à l’écran d’accueil », tap it, then « Installer ».',
          'Confirm. Marginote appears among your apps, with its own icon.',
        ]),
        h('pre', { class: 'code', text: location.origin }),
        copyBtn(location.origin, 'Copy the address'),
        h('p', { class: 'note-line', text: 'Done when: in Samsung Notes, you select a sentence, tap Partager, and Marginote is in the list (sometimes under « Plus » or after a minute); tapping it opens this app on « Where is it from? » with your sentence.' }),
        h('p', { class: 'note-line', text: 'The installed app and Chrome share their login: log in once. If the icon on the Home screen has a small Chrome logo in its corner, Chrome made a plain shortcut rather than installing the app, and a shortcut is not in the Share menu: remove it, and install again from ⋮.' }),
        h('p', { class: 'note-line', text: 'An app that shares only a link to the book (Kindle): Copy the passage instead, then here, Capture › Paste what you copied.' })]),
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
      link('quotes', '#/quotes', 'Quotes'), link('notes', '#/notes', 'Notes'),
      link('inbox', '#/inbox', 'Inbox'), link('settings', '#/settings', 'Settings')));
  const tabbar = h('nav', { class: 'tabbar', 'aria-label': 'Main' },
    link('library', '#/', 'Library'), link('quotes', '#/quotes', 'Quotes'), link('notes', '#/notes', 'Notes'),
    h('span', { class: 'tab-capture' }, h('a', { class: 'btn primary', href: '#/capture' }, '+ Capture')));
  const main = h('main', { class: 'view', id: 'view' });
  put(document.body, h('div', { class: 'app', id: 'app' }, side, main, tabbar));
}

// ----- exporting quotes and notes as a PDF or a Word file -----

const EXPORT_BY = {
  author: { all: 'All authors', search: 'Search an author', word: 'author', none: 'No author has quotes or notes yet.' },
  topic: { all: 'All topics', search: 'Search a topic', word: 'topic', none: 'No topic has quotes or notes yet.' },
  source: { all: 'All sources', search: 'Search a source', word: 'source', none: 'No source has quotes or notes yet.' },
};

async function viewExport() {
  const choices = await api('/api/export/choices');
  nav.label('Export');
  const kept = prefs.get('export', {});
  // format, way of organising and content are remembered; what you pick is not
  const st = {
    format: kept.format === 'docx' ? 'docx' : 'pdf',
    by: EXPORT_BY[kept.by] ? kept.by : 'author',
    quotes: kept.quotes ?? true, notes: kept.notes ?? true, bibliography: kept.bibliography ?? true,
    picked: { author: new Set(), topic: new Set(), source: new Set() },
    all: { author: false, topic: false, source: false },
    said: false, search: '', kind: '',
  };
  const keep = () => prefs.set('export', { format: st.format, by: st.by, quotes: st.quotes, notes: st.notes, bibliography: st.bibliography });
  const lists = { author: choices.authors, topic: choices.topics, source: choices.sources };
  const kindWord = (k) => KINDS[k]?.label || (KINDS[k] || KINDS.other).name.toLowerCase();
  const counts = (x) => [x.quotes ? plural(x.quotes, 'quote') : null, x.notes ? plural(x.notes, 'note') : null];
  const describe = {
    author: (a) => {
      const kinds = Object.entries(a.works);
      const total = kinds.reduce((n, [, c]) => n + c, 0);
      const works = !total ? null : kinds.length > 1 ? plural(total, 'work')
        : total === 1 ? `1 ${kindWord(kinds[0][0])}` : `${total} ${KINDS[kinds[0][0]].several}`;
      return [works, ...counts(a)].filter(Boolean).join(' · ');
    },
    topic: (t) => [t.sources ? plural(t.sources, 'source') : null, ...counts(t)].filter(Boolean).join(' · '),
    source: (s) => [s.by.join(', '), s.kind === 'book' || s.kind === 'ebook' ? null : kindWord(s.kind), s.year, ...counts(s)]
      .filter(Boolean).join(' · '),
  };
  const title = { author: (a) => a.name, topic: (t) => t.name, source: (s) => s.title };

  const chosen = () => st.all[st.by] || st.picked[st.by].size > 0 || (st.by === 'source' && st.said);
  const payload = () => ({
    format: st.format, by: st.by, all: st.all[st.by], ids: st.all[st.by] ? [] : [...st.picked[st.by]],
    said: st.by === 'source' && (st.all.source || st.said), quotes: st.quotes, notes: st.notes, bibliography: st.bibliography,
  });

  const countEl = h('span', { class: 'count' });
  const chooseHead = h('div', { class: 'section-head' }, h('h2', {}, h('span', { class: 'num-sec', text: 3 }), 'Choose'), countEl);
  const kindsBox = h('div');
  const listEl = h('div', { class: 'pick-list' });
  const sumEl = h('span', { class: 'sum', role: 'status' });
  const goBtn = h('button', { type: 'button', class: 'btn primary big' });
  const readyBox = h('div', { class: 'ready' });

  const searchInput = h('input', { type: 'search', 'aria-label': EXPORT_BY[st.by].search, placeholder: EXPORT_BY[st.by].search,
    oninput: () => { st.search = searchInput.value; drawList(); } });

  function row(cls, label, meta, checked, disabled, onchange, italic) {
    return h('label', { class: `pick-row ${cls}` },
      h('input', { type: 'checkbox', checked, disabled, onchange: (ev) => onchange(ev.target.checked) }),
      h('span', { class: 'pick-body' }, h('span', { class: italic ? 'it' : '' }, label), meta ? h('span', { class: 'pick-meta', text: meta }) : null));
  }

  function drawList() {
    const by = st.by;
    const all = lists[by];
    const q = fold(st.search.trim());
    const shown = all.filter((x) => (!st.kind || x.kind === st.kind)
      && (!q || fold(title[by](x)).includes(q) || (x.by && fold(x.by.join(' ')).includes(q))));
    const picked = st.picked[by];
    const n = st.all[by] ? all.length + (by === 'source' && choices.said ? 1 : 0) : picked.size + (by === 'source' && st.said ? 1 : 0);
    const total = all.length + (by === 'source' && choices.said ? 1 : 0);
    countEl.textContent = total ? `${n} of ${total}` : '';
    if (!total) { put(listEl, h('p', { class: 'empty', text: EXPORT_BY[by].none })); return; }
    put(listEl,
      row('all', [EXPORT_BY[by].all, h('span', { class: 'n', text: total })], null, st.all[by], false, (on) => { st.all[by] = on; changed(); }),
      shown.map((x) => row('', title[by](x), describe[by](x), st.all[by] || picked.has(x.id), st.all[by], (on) => {
        if (on) picked.add(x.id); else picked.delete(x.id);
        changed();
      }, by === 'source')),
      by === 'source' && choices.said && !st.kind && (!q || fold('Said, with no source').includes(q))
        ? row('', 'Said, with no source', `what people said · ${plural(choices.said, 'quote')}`, st.all.source || st.said, st.all.source,
          (on) => { st.said = on; changed(); }, true) : null,
      shown.length || !q ? null : h('p', { class: 'empty', text: 'Nothing matches.' }));
  }

  function drawKinds() {
    if (st.by !== 'source') { put(kindsBox); return; }
    const present = {};
    for (const s of choices.sources) present[s.kind] = (present[s.kind] || 0) + 1;
    const kinds = Object.keys(KINDS).filter((k) => present[k]);
    put(kindsBox, kinds.length > 1 ? filterRow([['', 'all'], ...kinds.map((k) => [k, `${KINDS[k].several} ${present[k]}`])], st.kind,
      (k) => { st.kind = k; drawList(); }) : null);
  }

  const updateSummary = debounce(async () => {
    if (!chosen() || !(st.quotes || st.notes)) return;
    const asked = JSON.stringify(payload());
    try {
      const c = await api('/api/export/summary', { method: 'POST', body: payload() });
      if (asked !== JSON.stringify(payload())) return;            // changed meanwhile
      sumEl.textContent = [plural(c.chapters, EXPORT_BY[st.by].word), plural(c.quotes, 'quote'), plural(c.notes, 'note')].join(' · ');
      goBtn.disabled = c.chapters === 0;
    } catch { /* the button still works, and says what is wrong */ }
  }, 250);

  function drawButton() {
    goBtn.hidden = false;
    put(goBtn, icon('download'), st.format === 'pdf' ? 'Download the PDF' : 'Download the Word file');
    goBtn.disabled = !(chosen() && (st.quotes || st.notes));
  }

  function drawGo() {
    const ok = chosen() && (st.quotes || st.notes);
    sumEl.textContent = !chosen() ? 'Choose at least one.' : !(st.quotes || st.notes) ? 'Choose quotes, notes, or both.' : '…';
    drawButton();
    if (ok) updateSummary();
  }

  function changed() { put(readyBox); drawList(); drawGo(); }

  goBtn.addEventListener('click', async () => {
    goBtn.disabled = true;
    put(goBtn, 'Preparing…');
    put(readyBox);
    let ready = false;
    try {
      const made = await api('/api/export', { method: 'POST', body: payload() });
      ready = true;
      if (navigator.standalone === true) {
        // the iPhone app hands the file to Safari, which shows it and can share it or save it (its login is separate,
        // and the link needs none); a tap is needed, so the button becomes that link until something changes
        goBtn.hidden = true;
        put(readyBox,
          h('a', { class: 'btn primary big', href: made.url, target: '_blank', rel: 'noopener' }, icon('external'),
            st.format === 'pdf' ? 'Open the PDF' : 'Open the Word file'),
          h('p', { class: 'note-line', text: 'Opens in Safari, where you can share it or save it to Files.' }));
      } else {
        const a = h('a', { href: made.url, download: made.name, hidden: true });
        document.body.append(a);
        a.click();
        a.remove();
        put(readyBox, h('p', { class: 'ready-name' }, `Ready (${size(made.size)}) · `,
          h('a', { href: made.url, download: made.name }, 'Download again')));
      }
    } catch (err) {
      put(readyBox, h('div', { class: 'error', role: 'alert', text: err.message }));
    } finally {
      if (!ready || navigator.standalone !== true) drawButton();
    }
  });

  const check = (key, label, extra) => h('label', { class: 'pick-row plain' },
    h('input', { type: 'checkbox', checked: st[key], onchange: (ev) => { st[key] = ev.target.checked; keep(); changed(); } }),
    h('span', {}, label, extra ? h('span', { class: 'pick-meta inline', text: extra }) : null));

  const el = h('div', { class: 'export-page' },
    bar(backButton('settings', 'Settings'), 'Export', null),
    h('header', { class: 'top' }, h('h1', {}, 'Export'), h('p', { class: 'muted it', text: 'Your quotes and notes, gathered in one file.' })),
    sectionHead(1, 'Format'),
    h('div', { class: 'pick-pad' }, segmented('Format', [['pdf', 'PDF'], ['docx', 'Word']], st.format, (f) => { st.format = f; keep(); changed(); })),
    sectionHead(2, 'Organise by'),
    h('div', { class: 'pick-pad' }, segmented('Organise by', [['author', 'Authors'], ['topic', 'Topics'], ['source', 'Sources']], st.by, (b) => {
      st.by = b; st.search = ''; st.kind = ''; searchInput.value = '';
      searchInput.placeholder = EXPORT_BY[b].search;
      searchInput.setAttribute('aria-label', EXPORT_BY[b].search);
      keep(); drawKinds(); changed();
    })),
    chooseHead,
    h('div', { class: 'pick-pad' }, kindsBox, h('label', { class: 'search' }, icon('search'), searchInput)),
    listEl,
    sectionHead(4, 'Content'),
    h('div', { class: 'pick-list' },
      check('quotes', 'Quotes', 'with your comments'), check('notes', 'Notes'), check('bibliography', 'Bibliography at the end')),
    h('div', { class: 'export-go' }, sumEl, goBtn, readyBox));
  drawKinds();
  changed();
  return { el, nav: 'settings' };
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
  [/^quotes$/, viewEntries, true],
  [/^entry\/(\d+)$/, viewEntry],
  [/^entry\/(\d+)\/edit$/, viewEntryEdit],
  [/^entry\/(\d+)\/photo$/, viewEntryPhoto],
  [/^notes$/, viewNotes, true],
  [/^note\/new$/, viewNoteForm],
  [/^note\/(\d+)$/, viewNote],
  [/^note\/(\d+)\/edit$/, viewNoteForm],
  [/^capture$/, viewCapture, (params) => ![...params.keys()].length],
  [/^inbox$/, viewInbox, true],
  [/^document\/([0-9a-f]+)$/, viewDocument],
  [/^settings$/, viewSettings, true],
  [/^export$/, viewExport],
  // addresses of earlier versions, from bookmarks or the home screen
  [/^entries$/, ({ params }) => { nav.replace(`quotes${params.toString() ? '?' + params : ''}`); return null; }],
  [/^book\/(\d+)$/, ({ args: [id] }) => { nav.replace(`source/${id}`); return null; }],
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
