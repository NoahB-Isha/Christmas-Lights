// app.js -- shared state, API, undo, mode switching. Other files add to `App`.
'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v; else if (k === 'style') e.style.cssText = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else if (v !== null && v !== undefined) e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined) e.append(k.nodeType ? k : document.createTextNode(String(k)));
  return e;
};
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const fmtT = t => { t = Math.max(0, t || 0); const m = Math.floor(t / 60), s = t - m * 60; return `${m}:${s < 10 ? '0' : ''}${s.toFixed(1)}`; };
const parseT = s => { s = String(s).trim(); if (s.includes(':')) { const [m, ss] = s.split(':'); return (+m) * 60 + parseFloat(ss); } return parseFloat(s); };
const uid = p => `${p}_${Math.random().toString(16).slice(2, 10)}`;
const debounce = (fn, ms) => { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); }; };

const S = {
  st: null, project: null, layout: null, shapes: null, paint: null, world: null, order: null, effects: null, fxByName: {},
  mode: 'props', selGroup: null, selProp: null, selProps: [], onlyGroup: false, showCtrl: true,   // selProps = multi-selection on the grid (ids); selProp = primary
  time: 0, playing: false, previewGroups: null, previewDirty: true,
  selClip: null, selClips: [], selAudio: null, selSection: null, analysis: {},   // selClips = the multi-selection (ids); selClip = the primary one
  undo: [], redo: [],
};

const api = {
  async get(u) { const r = await fetch(u); if (!r.ok) throw new Error(await r.text()); return r.json(); },
  async send(method, u, body) { const r = await fetch(u, { method, headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }); if (!r.ok) throw new Error(await r.text()); return r.json(); },
};

const App = {
  status(msg, cls = '') { const s = $('#status'); s.textContent = msg; s.className = 'small ' + (cls || 'dim'); if (msg) clearTimeout(App._sh), App._sh = setTimeout(() => { s.textContent = ''; }, 4000); },

  async boot() {
    S.st = await api.get('/api/state');
    App.applyState(S.st);
    $$('#modes button').forEach(b => b.onclick = () => App.setMode(b.dataset.mode));
    window.addEventListener('keydown', App.onKey);
    // ⌘C / ⌘V also arrive as clipboard events -- Safari and some keyboard layouts swallow the keydown
    document.addEventListener('copy', e => { if (S.mode === 'timeline' && !App.typing(e) && !String(window.getSelection())) { e.preventDefault(); App.Timeline.copySelection(); } });
    document.addEventListener('paste', e => { if (S.mode === 'timeline' && !App.typing(e)) { e.preventDefault(); App.Timeline.pasteSelection(); } });
    App.Props.init(); App.Preview.init(); App.Timeline.init(); App.Render.init();
    App.setMode('props');
    App.status('ready');
  },

  applyState(st) {
    S.project = st.project; S.layout = st.layout; S.shapes = st.shapes; S.paint = st.paint; S.world = st.world;
    for (const w of Object.values(S.world)) w.n = w.x.length;
    S.order = st.order; S.effects = st.effects; S.fxByName = Object.fromEntries(st.effects.map(e => [e.name, e]));
    S.issues = st.issues;
    $('#layoutName').textContent = st.layout_path;
    const pg = $('#previewGroup'); pg.innerHTML = '<option value="">all groups</option>';
    for (const [gid, g] of Object.entries(S.layout.groups)) pg.append(el('option', { value: gid }, g.label || gid));
  },

  setMode(m) {
    S.mode = m;
    $$('#modes button').forEach(b => b.classList.toggle('on', b.dataset.mode === m));
    $$('.mode').forEach(s => s.hidden = s.id !== 'mode-' + m);
    if (m === 'props') App.Props.show();
    if (m === 'timeline') App.Timeline.show();
    if (m === 'render') App.Render.show();
    App.Preview.resize();
  },

  // ---------------------------------------------------------- persistence
  commit() {                       // snapshot for undo BEFORE a mutation
    S.undo.push(JSON.stringify({ p: S.project, l: S.layout }));
    if (S.undo.length > 60) S.undo.shift();
    S.redo.length = 0;
  },
  undoStep(redo) {
    const from = redo ? S.redo : S.undo, to = redo ? S.undo : S.redo;
    if (!from.length) return;
    to.push(JSON.stringify({ p: S.project, l: S.layout }));
    const snap = JSON.parse(from.pop());
    const layoutChanged = JSON.stringify(snap.l) !== JSON.stringify(S.layout);
    S.project = snap.p; S.layout = snap.l;
    App.saveProject(); if (layoutChanged) App.saveLayout();
    App.refreshAll();
  },
  saveProject: debounce(async () => {
    try { await api.send('PUT', '/api/project', S.project); S.previewDirty = true; App.status('saved'); }
    catch (e) { App.status('save failed: ' + e.message, 'err'); }
  }, 350),
  async saveProjectNow() {
    try { await api.send('PUT', '/api/project', S.project); S.previewDirty = true; }
    catch (e) { App.status('save failed: ' + e.message, 'err'); }
  },
  saveLayout: debounce(async () => {
    try { const r = await api.send('PUT', '/api/layout', S.layout); S.issues = r.issues; S.previewDirty = true; App.rebuildWorld(); App.status('layout saved'); App.Props.renderGroups(); }
    catch (e) { App.status('layout save failed: ' + e.message, 'err'); }
  }, 350),
  async reloadState() { S.st = await api.get('/api/state'); App.applyState(S.st); App.refreshAll(); },
  refreshAll() { App.Props.renderAll(); App.Timeline.layoutTracks(); App.Timeline.draw(); App.Timeline.inspector(); App.Render.show(); S.previewDirty = true; },

  // world coordinates recomputed client-side after a drag (server does the same on save)
  propWorld(p) {
    const s = S.shapes[p.mod]; const a = p.rot * Math.PI / 180, ca = Math.cos(a), sa = Math.sin(a);
    const X = new Float32Array(s.n), Y = new Float32Array(s.n), Z = new Float32Array(s.n);
    for (let i = 0; i < s.n; i++) { const lx = p.mirror ? -s.lx[i] : s.lx[i]; X[i] = p.x + lx * ca; Y[i] = p.y + lx * sa; Z[i] = p.z + s.ly[i]; }
    return { n: s.n, x: X, y: Y, z: Z };
  },
  rebuildWorld() { for (const p of S.layout.props) S.world[p.id] = App.propWorld(p); },

  groupColor(gid) { return (S.layout.groups[gid] || {}).color || '#8a93a6'; },
  propById(id) { return S.layout.props.find(p => p.id === id); },
  propsIn(gid) { return S.layout.props.filter(p => p.group === gid); },
  pxOf(p) { return S.shapes[p.mod] ? S.shapes[p.mod].n : 0; },
  trackFor(gid) { let t = S.project.tracks.find(t => t.group === gid); if (!t) { t = { id: uid('t'), group: gid, clips: [] }; S.project.tracks.push(t); } return t; },

  typing(e) {
    // only TEXT entry swallows shortcuts: sliders, checkboxes, selects and buttons in the inspector do not
    const t = e.target; if (!t || !t.tagName) return false;
    if (t.tagName === 'TEXTAREA' || t.isContentEditable) return true;
    if (t.tagName === 'INPUT') return !['range', 'checkbox', 'radio', 'color', 'button', 'submit', 'file'].includes(t.type);
    return false;
  },
  onKey(e) {
    const typing = App.typing(e);
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); App.undoStep(e.shiftKey); return; }
    if (typing) return;
    if (e.target && e.target.tagName === 'SELECT' && ['ArrowLeft', 'ArrowRight', ' '].includes(e.key)) return;   // let the select work
    if (e.code === 'Space') { e.preventDefault(); if (S.mode !== 'props') App.Preview.togglePlay(); return; }   // in Props mode Space is the hand tool
    if (e.key === 'Home') { App.Preview.seek(0); return; }
    if (S.mode === 'timeline') App.Timeline.onKey(e);
    if (S.mode === 'props') App.Props.onKey(e);
  },
};
