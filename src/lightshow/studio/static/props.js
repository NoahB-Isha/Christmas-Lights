// props.js -- prop-group tool: groups panel (drag & drop), grid placement, paint view, inspector.
'use strict';
App.Props = (() => {
  const grid = $('#grid');
  let view = { s: 1.5, ox: 0, oy: 0 };          // px per inch, screen offset of world origin
  let drag = null, spaceDown = false, handOn = false;
  let paintMode = false;

  function init() {
    $('#bNewGroup').onclick = newGroup;
    $('#bAddProp').onclick = () => Library.open(S.selGroup || Object.keys(S.layout.groups)[0]);
    $('#bFit').onclick = () => { fit(); draw(); };
    $('#onlyGroup').onchange = e => { S.onlyGroup = e.target.checked; draw(); };
    $('#showCtrl').onchange = e => { S.showCtrl = e.target.checked; draw(); };
    MapLayer.init(); Route.init();
    grid.addEventListener('mousedown', onDown);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    grid.addEventListener('wheel', onWheel, { passive: false });
    grid.addEventListener('dblclick', onDbl);
    grid.addEventListener('contextmenu', e => e.preventDefault());
    // hand tool: hold H (or Space) to pan with the left button; the ✋ button toggles it on permanently
    window.addEventListener('keydown', e => { if (S.mode === 'props' && !App.typing(e) && (e.code === 'Space' || e.key === 'h' || e.key === 'H')) { if (!e.repeat) { spaceDown = true; grid.style.cursor = 'grab'; } e.preventDefault(); } });
    window.addEventListener('keyup', e => { if (e.code === 'Space' || e.key === 'h' || e.key === 'H') { spaceDown = false; grid.style.cursor = handOn ? 'grab' : ''; } });
    $('#bHand').onclick = () => { handOn = !handOn; $('#bHand').classList.toggle('on', handOn); grid.style.cursor = handOn ? 'grab' : ''; };
    window.addEventListener('resize', () => { if (S.mode === 'props') { draw(); Paint.draw(); } });
    Paint.init();
  }

  function show() { renderAll(); if (!view.fitted) { fit(); view.fitted = true; } draw(); }

  // silhouette thumbnails of a prop (front view), cached per mod + size
  const thumbs = {};
  function thumb(mod, size, color, shape) {
    const key = mod + '|' + size + '|' + color;
    if (thumbs[key]) return thumbs[key];
    const sh = shape || S.shapes[mod]; if (!sh) return null;
    const c = document.createElement('canvas'); c.width = c.height = size * devicePixelRatio;
    const g = c.getContext('2d'); g.scale(devicePixelRatio, devicePixelRatio);
    const sc = (size - 4) / Math.max(sh.w || 1, sh.h || 1, 1);
    const d = Math.max(0.8, Math.min(2.2, sc * (sh.pitch_in || 1) * 0.5));
    g.fillStyle = color;
    for (let i = 0; i < sh.n; i++) g.fillRect(size / 2 + sh.lx[i] * sc - d / 2, size - 2 - sh.ly[i] * sc - d / 2, d, d);
    thumbs[key] = c; return c;
  }
  function thumbEl(mod, size, color, shape) { const c = thumb(mod, size, color, shape); if (!c) return el('span'); const i = el('canvas', { class: 'thumb', width: c.width, height: c.height, style: `width:${size}px;height:${size}px` }); i.getContext('2d').drawImage(c, 0, 0); return i; }
  function renderAll() { renderGroups(); renderInspector(); renderCtrl(); draw(); }

  // ------------------------------------------------------------ groups panel
  function renderGroups() {
    const root = $('#groups'); root.innerHTML = '';
    for (const [gid, g] of Object.entries(S.layout.groups)) {
      const ps = App.propsIn(gid);
      const px = ps.reduce((a, p) => a + App.pxOf(p), 0);
      const ctrls = [...new Set(ps.map(p => p.controller).filter(Boolean))].sort();
      const unassigned = ps.filter(p => !p.controller).length;
      const card = el('div', { class: 'group' + (gid === S.selGroup ? ' sel' : ''), 'data-gid': gid });
      const head = el('div', { class: 'gHead', onclick: () => { S.selGroup = gid; S.selProp = null; renderAll(); } },
        el('span', { class: 'sw', style: `background:${g.color || '#888'}` }),
        el('b', {}, g.label || gid),
        el('span', { class: 'n' }, `${ps.length} props · ${px.toLocaleString()} px`));
      head.ondblclick = e => { e.stopPropagation(); const v = prompt('Group name', g.label || gid); if (v) { App.commit(); g.label = v; App.saveLayout(); renderAll(); } };
      card.append(head);
      card.append(el('div', { class: 'gCtl' }, ...ctrls.map(c => el('span', { class: 'chip' }, c)),
        unassigned ? el('span', { class: 'chip bad' }, `${unassigned} unassigned`) : null));
      const body = el('div', { class: 'gBody' });
      for (const p of ps.sort((a, b) => a.x - b.x)) {
        const row = el('div', { class: 'prop' + (p.id === S.selProp ? ' sel' : ''), draggable: 'true', title: p.mod },
          thumbEl(p.mod, 18, '#cfd6e4'),
          el('span', { class: 'id' }, p.id), el('span', { class: 'lbl' }, p.label || ''),
          el('span', { class: 'ct' }, p.controller ? `${p.controller}:${p.port}` : '—'),
          el('span', { class: 'px' }, App.pxOf(p)));
        row.onclick = () => { S.selProp = p.id; S.selGroup = gid; if (paintMode) { Paint.open(p); renderGroups(); } else { renderAll(); centreOn(p); } };
        row.ondblclick = () => Paint.open(p);
        row.ondragstart = e => { e.dataTransfer.setData('text/prop', p.id); e.dataTransfer.effectAllowed = 'move'; };
        body.append(row);
      }
      card.append(body);
      card.append(el('div', { class: 'gActions' },
        el('button', { class: 'small primary', onclick: () => editOnTimeline(gid) }, '▶ Edit on timeline'),
        el('button', { class: 'small', onclick: () => autoAssign(gid, false), title: 'pack this group\'s props onto controllers, 4 neighbours per controller' }, 'auto-assign'),
        el('button', { class: 'small', onclick: () => autoAssign(gid, true), title: 'only assign the props that have no controller yet' }, 'assign missing'),
        el('button', { class: 'small', onclick: () => Library.open(gid) }, '+ add props'),
        el('button', { class: 'small', title: 'select every prop of this group on the grid and zoom to them (then arrange them together, or ⌖ move the block to a spot on the map)', onclick: () => { selectIds(ps.map(p => p.id)); S.selGroup = gid; renderAll(); fitTo(ps); } }, '⬚ select all & zoom'),
        ctrls.length ? el('button', { class: 'small', title: 'put each controller at the centroid of its props (3 ft toward -y)', onclick: () => { App.commit(); placeCtrls(ps); App.saveLayout(); draw(); } }, '⌂ place controllers') : null,
        el('input', { type: 'color', value: g.color || '#888888', title: 'group colour', onchange: e => { App.commit(); g.color = e.target.value; App.saveLayout(); renderAll(); } }),
        ps.length ? null : el('button', { class: 'small', onclick: () => { App.commit(); delete S.layout.groups[gid]; App.saveLayout(); renderAll(); } }, '× delete')));
      card.ondragover = e => { if (e.dataTransfer.types.includes('text/prop')) { e.preventDefault(); card.classList.add('dropping'); } };
      card.ondragleave = () => card.classList.remove('dropping');
      card.ondrop = e => { e.preventDefault(); card.classList.remove('dropping'); const pid = e.dataTransfer.getData('text/prop'); if (pid) moveProp(pid, gid); };
      root.append(card);
    }
  }

  function moveProp(pid, gid) {
    const p = App.propById(pid); if (!p || p.group === gid) return;
    App.commit(); p.group = gid; p.controller = null; p.port = null; S.selGroup = gid; S.selProp = pid;
    App.saveLayout(); renderAll();
  }
  function newGroup() {
    const label = prompt('New group name'); if (!label) return;
    let gid = label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || uid('g');
    while (S.layout.groups[gid]) gid += '2';
    App.commit();
    S.layout.groups[gid] = { label, prefix: label.slice(0, 2).toUpperCase(), palette: 'classic', color: `hsl(${Math.random() * 360},70%,60%)` };
    S.selGroup = gid; App.saveLayout(); renderAll();
  }
  async function autoAssign(gid, keep) {
    App.commit();
    const r = await api.send('POST', '/api/layout/auto_assign', { group: gid, keep });
    S.layout = r.layout; S.issues = r.issues; App.rebuildWorld(); App.status(`assigned: ${r.touched.join(', ') || 'nothing new'}`); renderAll();
  }
  function editOnTimeline(gid) { S.previewGroups = [gid]; $('#previewGroup').value = gid; App.Timeline.focusGroup(gid); App.setMode('timeline'); }
  // ------------------------------------------------------------- library
  const Library = (() => {
    let lib = null, modal = null;
    async function open(gid) {
      lib = lib || await api.get('/api/props');
      const g = S.layout.groups[gid] || {};
      const used = {}; for (const p of S.layout.props) used[p.mod] = p;
      modal = el('div', { class: 'modal', onclick: e => { if (e.target === modal) close(); } });
      const box = el('div', { class: 'modalBox' });
      const search = el('input', { placeholder: 'filter…', style: 'flex:1' });
      const grid = el('div', { class: 'libGrid' });
      const render = () => {
        grid.innerHTML = ''; const q = search.value.trim().toLowerCase();
        for (const m of lib) {
          const stem = m.mod.replace('.mod', ''); if (q && !stem.toLowerCase().includes(q) && !(used[m.mod] && ((used[m.mod].label || '') + used[m.mod].id).toLowerCase().includes(q))) continue;
          const u = used[m.mod];
          const card = el('div', { class: 'libCard' + (u ? ' used' : ''), title: u ? `already placed: ${u.id} in ${(S.layout.groups[u.group] || {}).label || u.group}` : `add to ${g.label || gid}` },
            thumbEl(m.mod, 64, u ? '#4a5262' : '#cfd6e4', m), el('div', { class: 'nm' }, stem), el('div', { class: 'dim small' }, `${m.n} px · ${m.w}×${m.h} in`),
            u ? el('div', { class: 'small warn' }, `in ${(S.layout.groups[u.group] || {}).label || u.group} as ${u.label || u.id}`) : null);
          if (!u) card.onclick = () => { add(m, gid); used[m.mod] = App.propById(lastAdded); render(); };
          grid.append(card);
        }
      };
      search.oninput = render;
      box.append(el('div', { class: 'row' }, el('b', {}, `Add props to ${g.label || gid}`), search, el('button', { class: 'small', onclick: close }, 'done')),
        el('div', { class: 'hint' }, 'Click a prop to add it next to the group\'s right-most prop. Greyed props are already placed (hover shows where); move them by dragging between groups instead.'), grid);
      modal.append(box); document.body.append(modal); render(); search.focus();
    }
    function close() { if (modal) modal.remove(); modal = null; renderAll(); }
    let lastAdded = null;
    function add(m, gid) {
      App.commit();
      let id = m.mod.replace('.mod', '').replace('号', '').replace('左', 'L').replace('右', 'R'); while (App.propById(id)) id += 'b';
      const ps = App.propsIn(gid); const right = ps.length ? ps.reduce((a, p) => p.x > a.x ? p : a) : null;
      const x = right ? right.x + (S.shapes[right.mod] ? S.shapes[right.mod].w / 2 : 24) + m.w / 2 + 24 : (S.layout.props.length ? Math.max(...S.layout.props.map(p => p.x)) + 60 : 0);
      const y = right ? right.y : 0;
      if (!S.shapes[m.mod]) S.shapes[m.mod] = { n: m.n, w: m.w, h: m.h, pitch_in: m.pitch_in, lx: m.lx, ly: m.ly };
      S.layout.props.push({ id, mod: m.mod, label: '', group: gid, x: Math.round(x), y, z: 0, rot: 0, mirror: false, controller: null, port: null });
      App.rebuildWorld(); S.selProp = id; S.selGroup = gid; lastAdded = id; App.saveLayout(); App.status(`added ${id}`);
    }
    return { open, close };
  })();

  // -------------------------------------------------------------- inspector
  function renderInspector() {
    const root = $('#propDetails'); root.innerHTML = '';
    if (selected().length > 1) return Arrange.panel(root);
    const p = S.selProp && App.propById(S.selProp);
    if (!p) {
      root.append(el('h2', {}, 'Prop'), el('div', { class: 'hint' }, 'Click a prop on the grid or in a group. Double-click to paint its regions.'));
      if (S.issues && S.issues.length) {
        root.append(el('h2', {}, 'Checks'));
        for (const i of S.issues.slice(0, 30)) root.append(el('div', { class: 'small ' + (i.level === 'error' ? 'err' : 'warn') }, i.msg));
      }
      return;
    }
    const s = S.shapes[p.mod] || {};
    const num = (k, step = 1) => el('input', { type: 'number', step, value: p[k], onchange: e => { App.commit(); p[k] = parseFloat(e.target.value) || 0; S.world[p.id] = App.propWorld(p); App.saveLayout(); draw(); } });
    // every controller is offered -- this group's first, then the rest labelled with their group --
    // so a prop swapped into an existing group can go back onto that group's controller
    const ctlGroup = c => S.layout.controllers[c].group || (S.layout.props.find(q => q.controller === c) || {}).group || '';
    const allCtrls = Object.keys(S.layout.controllers).sort();
    const mine = allCtrls.filter(c => ctlGroup(c) === p.group || !ctlGroup(c));
    const others = allCtrls.filter(c => !mine.includes(c));
    const ctlLabel = c => { const used = S.layout.props.filter(q => q.controller === c).length; const g = ctlGroup(c); return `${c}  (${used}/4 ports${g && g !== p.group ? ', group ' + ((S.layout.groups[g] || {}).label || g) : ''})`; };
    const ctlSel = el('select', { onchange: e => {
      if (e.target.value === '__new') return;
      App.commit(); p.controller = e.target.value || null;
      if (!p.controller) p.port = null;
      else { const free = freePort(p.controller, p.id); p.port = free; if (!free) App.status(`${p.controller} has no free port -- pick one below to take it over`, 'warn'); }
      App.saveLayout(); renderAll(); } },
      el('option', { value: '' }, '— none —'),
      ...mine.map(c => el('option', { value: c, selected: c === p.controller ? '' : null }, ctlLabel(c))),
      ...(others.length ? [el('optgroup', { label: 'other groups' }, ...others.map(c => el('option', { value: c, selected: c === p.controller ? '' : null }, ctlLabel(c))))] : []),
      el('option', { value: '__new' }, '+ new controller'));
    ctlSel.addEventListener('change', e => { if (e.target.value === '__new') { const prefix = (S.layout.groups[p.group] || {}).prefix || p.group.slice(0, 2).toUpperCase(); let n = 1; while (S.layout.controllers[`${prefix}${String(n).padStart(2, '0')}`]) n++; const cid = `${prefix}${String(n).padStart(2, '0')}`; S.layout.controllers[cid] = { model: 'GC-6004', dmx_addr: 1, group: p.group, x: p.x, y: p.y - 36 }; p.controller = cid; p.port = 1; App.saveLayout(); renderAll(); } });
    // ports show who is on them; taking an occupied port moves the other prop off it (it is reported in the status bar)
    const portLabel = k => { const q = S.layout.props.find(q => q.controller === p.controller && q.port === k && q.id !== p.id); return q ? `port ${k} — ${q.label || q.id} (${(S.shapes[q.mod] || {}).n || '?'} px)` : `port ${k} — free`; };
    const portSel = el('select', { onchange: e => { App.commit(); const k = +e.target.value; const other = S.layout.props.find(q => q.controller === p.controller && q.port === k && q.id !== p.id);
      if (other) { other.controller = null; other.port = null; App.status(`${other.id} taken off ${p.controller} port ${k} -- it now needs a port`, 'warn'); }
      p.port = k; App.saveLayout(); renderAll(); } },
      ...(p.port ? [] : [el('option', { value: '', selected: '' }, '— pick a port —')]),
      ...[1, 2, 3, 4].map(k => el('option', { value: k, selected: k === p.port ? '' : null }, portLabel(k))));
    const groupSel = el('select', { onchange: e => moveProp(p.id, e.target.value) }, ...Object.entries(S.layout.groups).map(([gid, g]) => el('option', { value: gid, selected: gid === p.group ? '' : null }, g.label || gid)));
    root.append(
      el('h2', {}, 'Prop ', el('span', { class: 'mono' }, p.id)),
      el('div', { class: 'row' }, el('label', {}, 'label'), el('input', { value: p.label || '', style: 'flex:1', onchange: e => { App.commit(); p.label = e.target.value; App.saveLayout(); renderGroups(); } })),
      el('div', { class: 'row dim small' }, `${p.mod} · ${s.n} px · ${s.w} × ${s.h} in · pitch ${s.pitch_in} in · ${S.paint[p.mod.replace('.mod', '')] && Object.keys(S.paint[p.mod.replace('.mod', '')]).length ? Object.keys(S.paint[p.mod.replace('.mod', '')]).length + ' regions' : 'not painted'}`),
      el('div', { class: 'row' }, el('label', {}, 'group'), groupSel),
      el('div', { class: 'row' }, el('label', {}, 'controller'), ctlSel, p.controller ? portSel : null),
      el('div', { class: 'row' }, el('label', {}, 'x / y (in)'), num('x'), num('y')),
      el('div', { class: 'row' }, el('label', {}, 'z / rot'), num('z'), num('rot', 5)),
      el('div', { class: 'row' }, el('label', {}, 'mirror'), el('input', { type: 'checkbox', checked: p.mirror ? '' : null, onchange: e => { App.commit(); p.mirror = e.target.checked; S.world[p.id] = App.propWorld(p); App.saveLayout(); draw(); } })),
      el('div', { class: 'row' },
        el('button', { class: 'primary', onclick: () => Paint.open(p) }, '🎨 Paint this prop'),
        el('button', { onclick: () => editOnTimeline(p.group) }, '▶ Edit group on timeline')),
      el('div', { class: 'row' }, el('button', { class: 'small', title: 'move this prop to the middle of the grid view', onclick: () => { const r = grid.getBoundingClientRect(); const [wx, wy] = toW(r.width / 2, r.height / 2); App.commit(); setPos(p, Math.round(wx / 6) * 6, Math.round(wy / 6) * 6); App.saveLayout(); draw(); renderInspector(); } }, '⌖ move to view centre'),
        el('button', { class: 'small', onclick: () => centreOn(p) }, 'find on grid')),
      el('div', { class: 'row' }, el('button', { class: 'small', onclick: () => { if (!confirm(`Remove ${p.id} from the layout?`)) return; App.commit(); S.layout.props = S.layout.props.filter(q => q !== p); S.selProp = null; App.saveLayout(); renderAll(); } }, 'remove from layout')));
  }
  function freePort(cid, exceptId) { const used = new Set(S.layout.props.filter(p => p.controller === cid && p.id !== exceptId).map(p => p.port)); for (let k = 1; k <= 4; k++) if (!used.has(k)) return k; return null; }

  // controllers / SD cards of the selected group
  function renderCtrl() {
    const root = $('#ctrlPanel'); root.innerHTML = '';
    const gid = S.selGroup || (S.selProp && App.propById(S.selProp) || {}).group;
    if (!gid || paintMode) return;
    const g = S.layout.groups[gid] || {};
    const ps = App.propsIn(gid);
    const cids = [...new Set([...ps.map(p => p.controller).filter(Boolean), ...Object.keys(S.layout.controllers).filter(c => S.layout.controllers[c].group === gid)])].sort();
    root.append(el('h2', {}, `Controllers & SD cards — ${g.label || gid}`));
    if (!cids.length) root.append(el('div', { class: 'hint' }, 'No controllers yet. Use auto-assign on the group, or pick "+ new controller" on a prop.'));
    const tbl = el('table', { class: 't' }, el('tr', {}, el('th', {}, 'ctrl'), el('th', {}, 'SD label'), el('th', {}, 'ports 1–4'), el('th', {}, 'px')));
    for (const cid of cids) {
      const card = S.project.cards[cid] || (S.project.cards[cid] = { sd_label: cid, formatted: null, written: null, notes: '' });
      const ports = [1, 2, 3, 4].map(k => { const p = ps.find(q => q.controller === cid && q.port === k) || S.layout.props.find(q => q.controller === cid && q.port === k); return p ? p.id : '·'; });
      const px = S.layout.props.filter(p => p.controller === cid).reduce((a, p) => a + App.pxOf(p), 0);
      tbl.append(el('tr', {}, el('td', { class: 'mono' }, cid),
        el('td', {}, el('input', { value: card.sd_label || cid, style: 'width:80px', onchange: e => { card.sd_label = e.target.value; App.saveProject(); } })),
        el('td', { class: 'mono small' }, ports.join(' ')),
        el('td', { class: px > 4096 ? 'err' : 'dim' }, px)));
    }
    root.append(tbl);
    root.append(el('div', { class: 'hint' }, 'Limits: 1024 px per port, 4096 px per controller, one prop per port. Empty ports export as 32-px stubs.'));
  }

  // -------------------------------------------------------------------- grid
  function bounds(props) {
    let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
    for (const p of props) { const w = S.world[p.id]; if (!w) continue; for (let i = 0; i < w.n; i += 4) { x0 = Math.min(x0, w.x[i]); x1 = Math.max(x1, w.x[i]); y0 = Math.min(y0, w.y[i]); y1 = Math.max(y1, w.y[i]); } }
    if (x0 > x1) { x0 = -100; x1 = 100; y0 = -100; y1 = 100; }
    return { x0, x1, y0, y1 };
  }
  function fit() {
    const r = grid.getBoundingClientRect(); const props = S.onlyGroup && S.selGroup ? App.propsIn(S.selGroup) : S.layout.props;
    const b = bounds(props);
    view.s = Math.min((r.width - 80) / Math.max(24, b.x1 - b.x0), (r.height - 80) / Math.max(24, b.y1 - b.y0 + 60));
    view.ox = r.width / 2 - (b.x0 + b.x1) / 2 * view.s; view.oy = r.height / 2 + (b.y0 + b.y1) / 2 * view.s;
  }
  function centreOn(p) { const r = grid.getBoundingClientRect(); view.ox = r.width / 2 - p.x * view.s; view.oy = r.height / 2 + p.y * view.s; draw(); }
  const toS = (x, y) => [view.ox + x * view.s, view.oy - y * view.s];
  const toW = (sx, sy) => [(sx - view.ox) / view.s, (view.oy - sy) / view.s];

  function draw() {
    if (S.mode !== 'props' || paintMode) return;
    const r = grid.getBoundingClientRect(); if (!r.width) return;
    grid.width = r.width * devicePixelRatio; grid.height = r.height * devicePixelRatio;
    const g = grid.getContext('2d'); g.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    g.fillStyle = '#07080c'; g.fillRect(0, 0, r.width, r.height);
    MapLayer.draw(g, r);
    // grid: 1 ft minor (when zoomed), 5 ft major
    const [wx0, wy1] = toW(0, 0), [wx1, wy0] = toW(r.width, r.height);
    const step = view.s > 2.5 ? 12 : view.s > 0.25 ? 60 : 600;                          // 1 ft / 5 ft / 50 ft
    g.lineWidth = 1; g.globalAlpha = S.layout.map ? 0.35 : 1;                        // grid stays faint over a map
    for (let x = Math.floor(wx0 / step) * step; x <= wx1; x += step) { const [sx] = toS(x, 0); g.strokeStyle = x % (step * 5) === 0 ? '#1c2331' : '#12161f'; g.beginPath(); g.moveTo(sx, 0); g.lineTo(sx, r.height); g.stroke(); }
    for (let y = Math.floor(wy0 / step) * step; y <= wy1; y += step) { const [, sy] = toS(0, y); g.strokeStyle = y % (step * 5) === 0 ? '#1c2331' : '#12161f'; g.beginPath(); g.moveTo(0, sy); g.lineTo(r.width, sy); g.stroke(); }
    const [ax, ay] = toS(0, 0); g.strokeStyle = '#2a3446'; g.beginPath(); g.moveTo(ax, 0); g.lineTo(ax, r.height); g.moveTo(0, ay); g.lineTo(r.width, ay); g.stroke(); g.globalAlpha = 1;
    // controllers
    if (S.showCtrl) for (const [cid, c] of Object.entries(S.layout.controllers)) {
      if (c.x === undefined) continue; const [sx, sy] = toS(c.x, c.y);
      const dim = S.onlyGroup && S.selGroup && c.group !== S.selGroup;
      g.fillStyle = dim ? '#1a1f2a' : '#2b3546'; g.strokeStyle = App.groupColor(c.group); g.lineWidth = 1;
      g.beginPath(); g.rect(sx - 9, sy - 6, 18, 12); g.fill(); g.stroke();
      g.fillStyle = dim ? '#3a4152' : '#cfd6e4'; g.font = '10px ui-monospace,monospace'; g.textAlign = 'center'; g.textBaseline = 'top'; g.fillText(cid, sx, sy + 8);
      // cable to each prop
      g.strokeStyle = dim ? '#1a1f2a' : '#2b3546'; g.setLineDash([2, 3]);
      for (const p of S.layout.props) if (p.controller === cid) { const [px, py] = toS(p.x, p.y); g.beginPath(); g.moveTo(sx, sy); g.lineTo(px, py); g.stroke(); }
      g.setLineDash([]);
    }
    // group outlines: a padded box in the group colour with its name, so a group is findable at any zoom (esp. over a map)
    for (const [gid, gr] of Object.entries(S.layout.groups)) {
      const ps = App.propsIn(gid); if (!ps.length) continue;
      const dim = S.onlyGroup && S.selGroup && gid !== S.selGroup;
      const b = bounds(ps); const pad = 24;
      const [x0, y0] = toS(b.x0 - pad, b.y1 + pad), [x1, y1] = toS(b.x1 + pad, b.y0 - pad);
      g.globalAlpha = dim ? 0.15 : (gid === S.selGroup ? 0.9 : 0.5);
      g.strokeStyle = gr.color || '#8a93a6'; g.lineWidth = gid === S.selGroup ? 2 : 1; g.setLineDash([6, 4]); g.strokeRect(x0, y0, Math.max(8, x1 - x0), Math.max(8, y1 - y0)); g.setLineDash([]);
      g.fillStyle = 'rgba(7,8,12,.75)'; const lbl = `${gr.label || gid} · ${ps.length}`; g.font = 'bold 11px system-ui'; const tw = g.measureText(lbl).width;
      g.fillRect(x0, y0 - 16, tw + 10, 15); g.fillStyle = gr.color || '#8a93a6'; g.textAlign = 'left'; g.textBaseline = 'middle'; g.fillText(lbl, x0 + 5, y0 - 8.5);
      g.globalAlpha = 1;
    }
    // props as point clouds (top-down: a panel is a line of dots along its rot)
    for (const p of S.layout.props) {
      const w = S.world[p.id]; if (!w) continue;
      const dim = S.onlyGroup && S.selGroup && p.group !== S.selGroup;
      const sel = p.id === S.selProp || S.selProps.includes(p.id);
      const col = p.id === S.selProp ? '#ffffff' : sel ? '#ffd166' : App.groupColor(p.group);
      g.fillStyle = col; g.globalAlpha = dim ? 0.15 : 0.9;
      const sz = Math.max(1, Math.min(4, view.s * 0.6));
      for (let i = 0; i < w.n; i++) { const [sx, sy] = toS(w.x[i], w.y[i]); g.fillRect(sx - sz / 2, sy - sz / 2, sz, sz); }
      g.globalAlpha = dim ? 0.3 : 1;
      // footprint + label
      const s = S.shapes[p.mod]; const a = p.rot * Math.PI / 180; const hw = s.w / 2;
      const [x1, y1] = toS(p.x - hw * Math.cos(a), p.y - hw * Math.sin(a)), [x2, y2] = toS(p.x + hw * Math.cos(a), p.y + hw * Math.sin(a));
      g.strokeStyle = col; g.lineWidth = sel ? 3 : 1.5; g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
      // facing tick (panel faces -y at rot 0)
      const [cx, cy] = toS(p.x, p.y); const fx = Math.sin(a), fy = -Math.cos(a); const [tx, ty] = toS(p.x + fx * 8, p.y + fy * 8);
      g.beginPath(); g.moveTo(cx, cy); g.lineTo(tx, ty); g.stroke();
      // a marker dot that never disappears
      g.fillStyle = '#07080c'; g.beginPath(); g.arc(cx, cy, 5.5, 0, 6.283); g.fill();
      g.fillStyle = col; g.beginPath(); g.arc(cx, cy, 4, 0, 6.283); g.fill();
      // the silhouette AT SCALE, turned with the prop and laid down behind the panel like a billboard tipped over
      // backwards (its feet on the footprint line, the facing tick points the other way), so an arrangement reads
      // like a plan of the real thing; falls back to a fixed icon when it would be tiny
      const big = Math.max(s.w, s.h) * view.s;
      let isz;
      if (big >= 14) {
        const th = thumb(p.mod, 128, sel ? '#ffffff' : col);
        if (th) {
          const k = big / 124;                              // thumb draws the prop into a 124-px box (128 - 2*2 pad)
          g.save(); g.translate(cx, cy); g.rotate(-a);      // world y is up, screen y is down -> negative rotation
          if (p.mirror) g.scale(-1, 1);
          // thumb: prop bottom at y = 126 of 128, centred in x -> baseline on the footprint line, body away from the facing side
          g.globalAlpha = (dim ? 0.15 : 0.9) * 0.85;
          g.drawImage(th, -64 * k, -126 * k, 128 * k, 128 * k);
          g.restore(); g.globalAlpha = dim ? 0.3 : 1;
        }
        isz = Math.round(s.h * view.s);
      } else {
        isz = 18;
        const th = thumb(p.mod, isz, sel ? '#ffffff' : col);
        if (th) { g.fillStyle = 'rgba(7,8,12,.8)'; g.fillRect(cx - isz / 2 - 2, cy - 12 - isz, isz + 4, isz + 4); g.drawImage(th, cx - isz / 2, cy - 10 - isz, isz, isz); }
      }
      if (view.s > 0.6) { const txt = (view.s > 1.2 && p.label ? p.label : p.id) + (view.s > 1.6 && p.controller ? `  ·  ${p.controller}:${p.port}` : ''); g.font = (sel ? 'bold ' : '') + '11px system-ui'; const tw = g.measureText(txt).width; g.fillStyle = 'rgba(7,8,12,.75)'; g.fillRect(cx - tw / 2 - 3, cy - 12 - isz - 13, tw + 6, 13); g.fillStyle = sel ? '#fff' : '#cfd6e4'; g.textAlign = 'center'; g.textBaseline = 'bottom'; g.fillText(txt, cx, cy - 12 - isz); }
      g.globalAlpha = 1;
    }
    // selection box / calibration line
    if (drag && drag.kind === 'marquee' && drag.moved) { g.fillStyle = 'rgba(255,209,102,.12)'; g.strokeStyle = '#ffd166'; g.lineWidth = 1; g.fillRect(Math.min(drag.sx, drag.x2), Math.min(drag.sy, drag.y2), Math.abs(drag.x2 - drag.sx), Math.abs(drag.y2 - drag.sy)); g.strokeRect(Math.min(drag.sx, drag.x2) + .5, Math.min(drag.sy, drag.y2) + .5, Math.abs(drag.x2 - drag.sx), Math.abs(drag.y2 - drag.sy)); }
    MapLayer.drawOverlay(g);
    Route.draw(g);
    // scale bar
    const ft = view.s * 120; g.strokeStyle = '#cfd6e4'; g.lineWidth = 2; g.beginPath(); g.moveTo(r.width - ft - 14, r.height - 14); g.lineTo(r.width - 14, r.height - 14); g.stroke();
    g.fillStyle = '#cfd6e4'; g.font = '11px system-ui'; g.textAlign = 'right'; g.textBaseline = 'bottom'; g.fillText('10 ft', r.width - 14, r.height - 18);
    // distance readout for the selected prop to its nearest neighbour in the group
    const sp = S.selProp && App.propById(S.selProp);
    if (sp) {
      let best = null; for (const q of App.propsIn(sp.group)) { if (q === sp) continue; const d = Math.hypot(q.x - sp.x, q.y - sp.y); if (!best || d < best.d) best = { q, d }; }
      if (best) { const [x1, y1] = toS(sp.x, sp.y), [x2, y2] = toS(best.q.x, best.q.y); g.strokeStyle = '#5fb8ff'; g.setLineDash([4, 4]); g.lineWidth = 1; g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke(); g.setLineDash([]); g.fillStyle = '#5fb8ff'; g.textAlign = 'center'; g.textBaseline = 'top'; g.fillText(`${(best.d / 12).toFixed(1)} ft to ${best.q.label || best.q.id}`, (x1 + x2) / 2, (y1 + y2) / 2 + 4); }
    }
  }

  function hit(sx, sy) {
    let best = null, bd = 14;
    for (const p of S.layout.props) {
      if (S.onlyGroup && S.selGroup && p.group !== S.selGroup) continue;
      const w = S.world[p.id]; if (!w) continue;
      for (let i = 0; i < w.n; i += 2) { const [x, y] = toS(w.x[i], w.y[i]); const d = Math.hypot(x - sx, y - sy); if (d < bd) { bd = d; best = p; } }
      const [cx, cy] = toS(p.x, p.y); const d = Math.hypot(cx - sx, cy - sy); if (d < bd) { bd = d; best = p; }
    }
    return best;
  }
  function onDown(e) {
    const r = grid.getBoundingClientRect(); const sx = e.clientX - r.left, sy = e.clientY - r.top;
    if (e.button === 2 || e.button === 1 || spaceDown || handOn) { drag = { kind: 'pan', sx, sy, ox: view.ox, oy: view.oy }; grid.style.cursor = 'grabbing'; return; }
    if (MapLayer.onDown(sx, sy, e)) { draw(); return; }
    if (Route.onDown(sx, sy, e)) { draw(); return; }
    const cid = S.showCtrl && hitCtrl(sx, sy);
    if (cid) { const c = S.layout.controllers[cid]; drag = { kind: 'ctrl', cid, sx, sy, x0: c.x, y0: c.y, moved: false }; $('#gridHud').textContent = `${cid}  drag to move the controller`; return; }
    const p = hit(sx, sy);
    if (p) {
      if (e.shiftKey || e.metaKey || e.ctrlKey) {                       // shift-click: toggle in the multi-selection
        const ids = selected().map(q => q.id);
        selectIds(ids.includes(p.id) ? ids.filter(i => i !== p.id) : [...ids, p.id]); S.selGroup = p.group; renderAll(); return;
      }
      if (!S.selProps.includes(p.id)) S.selProps = [];                  // plain click on an unselected prop selects just it
      S.selProp = p.id; S.selGroup = p.group; renderGroups(); renderInspector(); renderCtrl();
      const others = selected().filter(q => q !== p).map(q => ({ p: q, x0: q.x, y0: q.y }));
      const ctrls = ctrlsOf(selected()).map(cid => ({ cid, x0: S.layout.controllers[cid].x, y0: S.layout.controllers[cid].y }));   // controllers ride along when all their props move
      drag = { kind: 'move', p, sx, sy, x0: p.x, y0: p.y, moved: false, others, ctrls };
    }
    else { drag = { kind: 'marquee', sx, sy, x2: sx, y2: sy, moved: false, base: e.shiftKey ? selected().map(q => q.id) : [] }; }
    draw();
  }
  function onMove(e) {
    if (!drag || S.mode !== 'props') return;
    const r = grid.getBoundingClientRect(); const sx = e.clientX - r.left, sy = e.clientY - r.top;
    if (drag.kind === 'pan') { view.ox = drag.ox + (sx - drag.sx); view.oy = drag.oy + (sy - drag.sy); draw(); return; }
    if (drag.kind === 'map') { MapLayer.onMove(sx, sy); draw(); return; }
    if (drag.kind === 'route') { Route.onMove(sx, sy, e); draw(); return; }
    if (drag.kind === 'ctrl') {
      if (!drag.moved) { App.commit(); drag.moved = true; }
      let x = drag.x0 + (sx - drag.sx) / view.s, y = drag.y0 - (sy - drag.sy) / view.s;
      if (!e.shiftKey) { x = Math.round(x / 6) * 6; y = Math.round(y / 6) * 6; }
      const c = S.layout.controllers[drag.cid]; c.x = Math.round(x * 10) / 10; c.y = Math.round(y * 10) / 10; draw();
      $('#gridHud').textContent = `${drag.cid}  x ${c.x} in  y ${c.y} in`; return;
    }
    if (drag.kind === 'marquee') {
      drag.x2 = sx; drag.y2 = sy; drag.moved = drag.moved || Math.abs(sx - drag.sx) > 3 || Math.abs(sy - drag.sy) > 3;
      if (drag.moved) { const [ax, ay] = toW(Math.min(drag.sx, sx), Math.max(drag.sy, sy)), [bx, by] = toW(Math.max(drag.sx, sx), Math.min(drag.sy, sy)); const inBox = S.layout.props.filter(p => !(S.onlyGroup && S.selGroup && p.group !== S.selGroup) && p.x >= ax && p.x <= bx && p.y >= ay && p.y <= by).map(p => p.id); S.selProps = [...new Set([...drag.base, ...inBox])]; S.selProp = S.selProps[S.selProps.length - 1] || null; }
      draw(); return;
    }
    if (drag.kind === 'move') {
      if (!drag.moved) { App.commit(); drag.moved = true; }
      let x = drag.x0 + (sx - drag.sx) / view.s, y = drag.y0 - (sy - drag.sy) / view.s;
      if (!e.shiftKey) { x = Math.round(x / 6) * 6; y = Math.round(y / 6) * 6; }
      const dx = x - drag.x0, dy = y - drag.y0;
      setPos(drag.p, x, y);
      for (const o of drag.others) setPos(o.p, o.x0 + dx, o.y0 + dy);
      for (const c of drag.ctrls) { const cc = S.layout.controllers[c.cid]; cc.x = Math.round((c.x0 + dx) * 10) / 10; cc.y = Math.round((c.y0 + dy) * 10) / 10; }
      draw();
      $('#gridHud').textContent = drag.others.length ? `${drag.others.length + 1} props  Δx ${dx.toFixed(0)} in  Δy ${dy.toFixed(0)} in` : `${drag.p.id}  x ${drag.p.x} in  y ${drag.p.y} in`;
    }
  }
  function onUp() {
    if (!drag) return;
    if (drag.kind === 'pan') grid.style.cursor = (spaceDown || handOn) ? 'grab' : '';
    if ((drag.kind === 'move' || drag.kind === 'ctrl') && drag.moved) { App.saveLayout(); renderInspector(); renderGroups(); }
    else if (drag.kind === 'marquee') { if (!drag.moved && !drag.base.length) { S.selProp = null; S.selProps = []; } renderAll(); }
    else if (drag.kind === 'map') { MapLayer.onUp(); }
    else if (drag.kind === 'route') { Route.onUp(); }
    drag = null;
  }
  function hitCtrl(sx, sy) { for (const [cid, c] of Object.entries(S.layout.controllers)) { if (c.x === undefined) continue; if (S.onlyGroup && S.selGroup && c.group !== S.selGroup) continue; const [x, y] = toS(c.x, c.y); if (Math.abs(x - sx) <= 10 && Math.abs(y - sy) <= 8) return cid; } return null; }
  // controllers whose every assigned prop is in `ps` (so they belong to the block being moved); + a group's unattached ones when the whole group is selected
  function ctrlsOf(ps) {
    const ids = new Set(ps.map(p => p.id)); const out = [];
    for (const [cid, c] of Object.entries(S.layout.controllers)) {
      if (c.x === undefined) continue;
      const mine = S.layout.props.filter(p => p.controller === cid);
      if (mine.length ? mine.every(p => ids.has(p.id)) : (c.group && App.propsIn(c.group).length && App.propsIn(c.group).every(p => ids.has(p.id)))) out.push(cid);
    }
    return out;
  }
  // put each controller (of these props) at the centroid of its props, 3 ft toward -y -- the same rule auto-assign uses
  function placeCtrls(ps) {
    for (const cid of new Set(ps.map(p => p.controller).filter(Boolean))) {
      const mine = S.layout.props.filter(p => p.controller === cid); if (!mine.length) continue;
      const c = S.layout.controllers[cid] || (S.layout.controllers[cid] = { model: 'GC-6004', dmx_addr: 1, group: mine[0].group });
      c.x = Math.round(mine.reduce((a, p) => a + p.x, 0) / mine.length * 10) / 10; c.y = Math.round((mine.reduce((a, p) => a + p.y, 0) / mine.length - 36) * 10) / 10;
    }
  }
  function setPos(p, x, y) { p.x = Math.round(x * 100) / 100; p.y = Math.round(y * 100) / 100; S.world[p.id] = App.propWorld(p); }
  function selected() { const ids = new Set(S.selProps); if (S.selProp) ids.add(S.selProp); return S.layout.props.filter(p => ids.has(p.id)); }
  function selectIds(ids) { S.selProps = [...ids]; S.selProp = ids[ids.length - 1] || null; }
  function fitTo(props) { if (!props.length) return; const r = grid.getBoundingClientRect(); const b = bounds(props); view.s = clamp(Math.min((r.width - 120) / Math.max(48, b.x1 - b.x0), (r.height - 120) / Math.max(48, b.y1 - b.y0)), 0.05, 6); view.ox = r.width / 2 - (b.x0 + b.x1) / 2 * view.s; view.oy = r.height / 2 + (b.y0 + b.y1) / 2 * view.s; draw(); }
  function onWheel(e) {
    e.preventDefault(); const r = grid.getBoundingClientRect(); const sx = e.clientX - r.left, sy = e.clientY - r.top;
    const k = Math.exp(-e.deltaY * 0.0015); const [wx, wy] = toW(sx, sy);
    view.s = clamp(view.s * k, 0.05, 40); view.ox = sx - wx * view.s; view.oy = sy + wy * view.s; draw();
  }
  function onDbl(e) { const r = grid.getBoundingClientRect(); const p = hit(e.clientX - r.left, e.clientY - r.top); if (p) Paint.open(p); }
  function onKey(e) {
    if (paintMode) { Paint.onKey(e); return; }
    if (e.key === 'Escape' || e.key === 'Enter') { if (Route.finish() || MapLayer.cancel()) { draw(); return; } if (e.key === 'Escape') { S.selProp = null; S.selProps = []; renderAll(); } return; }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'a') { e.preventDefault(); const ps = S.onlyGroup && S.selGroup ? App.propsIn(S.selGroup) : S.layout.props; selectIds(ps.map(p => p.id)); renderAll(); return; }
    if (e.key === 'm' || e.key === 'M') { MapLayer.toggleMove(); return; }
    const ps = selected(); if (!ps.length) return;
    const step = e.shiftKey ? 12 : 1;
    const mv = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key];
    if (mv) { e.preventDefault(); App.commit(); for (const p of ps) setPos(p, p.x + mv[0], p.y + mv[1]); for (const cid of ctrlsOf(ps)) { S.layout.controllers[cid].x += mv[0]; S.layout.controllers[cid].y += mv[1]; } App.saveLayout(); draw(); renderInspector(); }
    if (e.key === 'r' || e.key === 'R') { App.commit(); for (const p of ps) { p.rot = (p.rot + (e.shiftKey ? -15 : 15) + 360) % 360; S.world[p.id] = App.propWorld(p); } App.saveLayout(); draw(); renderInspector(); }
  }

  // --------------------------------------------------------------- map layer
  // S.layout.map = { file, in_per_px, x, y, opacity }  (x,y = world inches of the image's top-left corner)
  const MapLayer = (() => {
    let img = null, imgFile = null, moving = false, cal = null;   // cal = { a:[wx,wy], b:[wx,wy]|null }
    // measured from the sheet's own graphic scale bar (0→400 ft = 1027 px at 150 dpi); the PDF is NOT plotted at 1 in = 100 ft
    const KNOWN_SCALE = { 'site_plan_2026.png': 400 * 12 / 1027 };
    function m() { return S.layout.map || null; }
    async function init() {
      const sel = $('#mapSel');
      let files = [];
      try { files = await api.get('/api/site'); }
      catch (e) { App.status('map: the running server is older than the UI — stop it and run `make studio` again', 'err'); $('#mapSel').disabled = true; return; }
      for (const f of files) sel.append(el('option', { value: f }, f));
      sel.value = m() ? m().file : '';
      sel.onchange = () => { App.commit(); let fresh = false; if (!sel.value) { S.layout.map = null; } else if (!m() || m().file !== sel.value) { S.layout.map = { file: sel.value, in_per_px: KNOWN_SCALE[sel.value] || 8, x: 0, y: 0, opacity: Math.min(0.45, parseFloat($('#mapOpacity').value)) }; $('#mapOpacity').value = S.layout.map.opacity; fresh = true; } load().then(() => { if (m() && fresh) centreOnProps(); App.saveLayout(); if (m()) fitMap(); draw(); }); };
      $('#bMapCentre').onclick = () => { if (!m() || !img) return App.status('pick a map first', 'warn'); App.commit(); centreOnProps(); App.saveLayout(); fitMap(); };
      $('#mapOpacity').value = m() ? (m().opacity ?? 0.6) : 0.6;
      $('#mapOpacity').oninput = e => { if (m()) { m().opacity = parseFloat(e.target.value); draw(); } };
      $('#mapOpacity').onchange = () => { if (m()) App.saveLayout(); };
      $('#bMapMove').onclick = toggleMove;
      $('#bMapCal').onclick = () => { if (!m()) return App.status('pick a map first', 'warn'); cal = { a: null, b: null }; moving = false; $('#bMapMove').classList.remove('on'); $('#bMapCal').classList.add('on'); App.status('calibrate: click the first point on the map (e.g. one end of the scale bar)'); };
      $('#bMapFit').onclick = fitMap;
      $('#bMapUpload').onclick = () => $('#mapFile').click();
      $('#mapFile').onchange = async e => {
        const file = e.target.files[0]; if (!file) return;
        const fd = new FormData(); fd.append('file', file);
        App.status('uploading map…');
        try { const r = await fetch('/api/site/upload', { method: 'POST', body: fd }); if (!r.ok) throw new Error(await r.text()); const res = await r.json(); if (![...sel.options].some(o => o.value === res.file)) sel.append(el('option', { value: res.file }, res.file)); sel.value = res.file; sel.onchange(); App.status(`map ${res.file} added`); }
        catch (err) { App.status('upload failed: ' + err.message, 'err'); }
        e.target.value = '';
      };
      await load();
    }
    function load() { return new Promise(res => { if (!m()) { img = null; imgFile = null; return res(); } if (imgFile === m().file && img) return res(); const i = new Image(); i.onload = () => { img = i; imgFile = m().file;
        const M = m(); if (M.in_per_px === 8 && KNOWN_SCALE[M.file]) { const k = KNOWN_SCALE[M.file]; const cx = M.x + i.width * 4, cy = M.y - i.height * 4; M.in_per_px = k; M.x = Math.round(cx - i.width * k / 2); M.y = Math.round(cy + i.height * k / 2); App.saveLayout(); App.status(`map scale corrected to ${k.toFixed(2)} in/px from the sheet's scale bar`); }
        res(); }; i.onerror = () => { img = null; res(); }; i.src = '/api/site/' + encodeURIComponent(m().file); }); }
    function toggleMove() { if (!m()) return App.status('pick a map first', 'warn'); moving = !moving; cal = null; $('#bMapCal').classList.remove('on'); $('#bMapMove').classList.toggle('on', moving); App.status(moving ? 'drag the map to line it up with the props; M or Esc to stop' : ''); }
    function cancel() { if (moving || cal) { moving = false; cal = null; $('#bMapMove').classList.remove('on'); $('#bMapCal').classList.remove('on'); return true; } return false; }
    function centreOnProps() {                              // put the middle of the map under the middle of the props
      if (!img || !m()) return; const M = m(); const b = bounds(S.layout.props);
      M.x = Math.round((b.x0 + b.x1) / 2 - img.width * M.in_per_px / 2); M.y = Math.round((b.y0 + b.y1) / 2 + img.height * M.in_per_px / 2);
    }
    function fitMap() { if (!img || !m()) return; const r = grid.getBoundingClientRect(); const W = img.width * m().in_per_px, H = img.height * m().in_per_px; view.s = Math.min((r.width - 40) / W, (r.height - 40) / H); view.ox = r.width / 2 - (m().x + W / 2) * view.s; view.oy = r.height / 2 + (m().y - H / 2) * view.s; draw(); }
    function render(g, r) {
      if (!img || !m()) return;
      const M = m(); const [sx, sy] = toS(M.x, M.y); const w = img.width * M.in_per_px * view.s, h = img.height * M.in_per_px * view.s;
      g.save(); g.globalAlpha = M.opacity ?? 0.6; g.imageSmoothingEnabled = true; g.drawImage(img, sx, sy, w, h); g.restore();
      if (moving) { g.strokeStyle = '#ffd166'; g.setLineDash([6, 4]); g.lineWidth = 1.5; g.strokeRect(sx, sy, w, h); g.setLineDash([]); }
    }
    function drawOverlay(g) {
      if (!cal) return;
      g.fillStyle = '#ff5f5f'; g.strokeStyle = '#ff5f5f'; g.lineWidth = 2;
      for (const pt of [cal.a, cal.b]) if (pt) { const [x, y] = toS(pt[0], pt[1]); g.beginPath(); g.arc(x, y, 5, 0, 6.283); g.fill(); }
      if (cal.a && cal.b) { const [x1, y1] = toS(...cal.a), [x2, y2] = toS(...cal.b); g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke(); }
    }
    function onDown(sx, sy, e) {
      if (!m()) return false;
      if (cal) {
        const w = toW(sx, sy);
        if (!cal.a) { cal.a = w; App.status('calibrate: now click the second point'); return true; }
        cal.b = w;
        const dpx = Math.hypot(cal.b[0] - cal.a[0], cal.b[1] - cal.a[1]) / m().in_per_px;      // distance in image pixels
        const ans = prompt(`Real distance between the two points, in feet (e.g. the scale bar: 400)`, '400');
        const ft = parseFloat(ans);
        if (ft > 0 && dpx > 0) {
          App.commit(); const M = m(); const old = M.in_per_px; M.in_per_px = ft * 12 / dpx;
          // keep the first clicked point where it is on the map while the scale changes
          const ax = (cal.a[0] - M.x) / old, ay = (M.y - cal.a[1]) / old; M.x = cal.a[0] - ax * M.in_per_px; M.y = cal.a[1] + ay * M.in_per_px;
          App.saveLayout(); App.status(`map scale: ${M.in_per_px.toFixed(3)} in per pixel (${(M.in_per_px / 12).toFixed(2)} ft/px)`);
        }
        cal = null; $('#bMapCal').classList.remove('on'); return true;
      }
      if (moving) { drag = { kind: 'map', sx, sy, x0: m().x, y0: m().y }; App.commit(); return true; }
      return false;
    }
    function onMove(sx, sy) { const M = m(); M.x = Math.round(drag.x0 + (sx - drag.sx) / view.s); M.y = Math.round(drag.y0 - (sy - drag.sy) / view.s); $('#gridHud').textContent = `map origin x ${M.x} in  y ${M.y} in`; }
    function onUp() { App.saveLayout(); }
    return { init, load, draw: render, drawOverlay, onDown, onMove, onUp, toggleMove, cancel, fitMap };
  })();

  // ------------------------------------------------------------------- route
  // S.layout.route = { points: [[x, y], ...] world inches in driving order, speed_mph, eye_in }
  const Route = (() => {
    let drawing = false;
    function R() { return S.layout.route || null; }
    function init() {
      $('#bRoute').onclick = () => { drawing = !drawing; $('#bRoute').classList.toggle('on', drawing); if (drawing && !R()) S.layout.route = { points: [], speed_mph: 5, eye_in: 48 }; App.status(drawing ? 'route: click along the road in driving order (Enter / Esc to finish; drag a point to move it, double-click to delete)' : ''); grid.style.cursor = drawing ? 'crosshair' : ''; draw(); };
      $('#bRouteClear').onclick = () => { if (!R() || !confirm('Delete the route?')) return; App.commit(); S.layout.route = null; drawing = false; $('#bRoute').classList.remove('on'); App.saveLayout(); draw(); };
      grid.addEventListener('dblclick', e => { if (!R()) return; const r = grid.getBoundingClientRect(); const i = hitPoint(e.clientX - r.left, e.clientY - r.top); if (i >= 0) { e.stopImmediatePropagation(); App.commit(); R().points.splice(i, 1); App.saveLayout(); draw(); } }, true);
    }
    function finish() { if (!drawing) return false; drawing = false; $('#bRoute').classList.remove('on'); grid.style.cursor = ''; App.saveLayout(); App.status(R() && R().points.length > 1 ? `route: ${(length() / 12).toFixed(0)} ft, ${R().points.length} points` : ''); return true; }
    function hitPoint(sx, sy) { if (!R()) return -1; for (let i = R().points.length - 1; i >= 0; i--) { const [x, y] = toS(R().points[i][0], R().points[i][1]); if (Math.hypot(x - sx, y - sy) < 8) return i; } return -1; }
    function onDown(sx, sy, e) {
      if (!R()) return false;
      const i = hitPoint(sx, sy);
      if (i >= 0) { App.commit(); drag = { kind: 'route', i, sx, sy }; return true; }
      if (!drawing) return false;
      const [wx, wy] = toW(sx, sy); App.commit(); R().points.push([Math.round(wx), Math.round(wy)]); draw(); return true;
    }
    function onMove(sx, sy, e) { const [wx, wy] = toW(sx, sy); const pt = R().points[drag.i]; pt[0] = e.shiftKey ? Math.round(wx) : Math.round(wx / 6) * 6; pt[1] = e.shiftKey ? Math.round(wy) : Math.round(wy / 6) * 6; $('#gridHud').textContent = `route point ${drag.i + 1}: x ${pt[0]} in  y ${pt[1]} in`; }
    function onUp() { App.saveLayout(); }
    function length() { const P = R() ? R().points : []; let L = 0; for (let i = 1; i < P.length; i++) L += Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]); return L; }
    function draw(g) {
      const rt = R(); if (!rt || !rt.points.length) return;
      const P = rt.points;
      // road ribbon (12 ft wide) + centre line with direction arrows
      g.save(); g.lineCap = 'round'; g.lineJoin = 'round';
      g.strokeStyle = 'rgba(255,209,102,.12)'; g.lineWidth = Math.max(4, 144 * view.s); g.beginPath(); P.forEach((p, i) => { const [x, y] = toS(p[0], p[1]); i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke();
      g.strokeStyle = '#ffd166'; g.lineWidth = 2; g.setLineDash([10, 8]); g.beginPath(); P.forEach((p, i) => { const [x, y] = toS(p[0], p[1]); i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke(); g.setLineDash([]);
      for (let i = 1; i < P.length; i++) { const [x1, y1] = toS(P[i - 1][0], P[i - 1][1]), [x2, y2] = toS(P[i][0], P[i][1]); const a = Math.atan2(y2 - y1, x2 - x1); const mx = (x1 + x2) / 2, my = (y1 + y2) / 2; g.fillStyle = '#ffd166'; g.beginPath(); g.moveTo(mx + 7 * Math.cos(a), my + 7 * Math.sin(a)); g.lineTo(mx + 7 * Math.cos(a + 2.5), my + 7 * Math.sin(a + 2.5)); g.lineTo(mx + 7 * Math.cos(a - 2.5), my + 7 * Math.sin(a - 2.5)); g.fill(); }
      P.forEach((p, i) => { const [x, y] = toS(p[0], p[1]); g.fillStyle = i === 0 ? '#4ccf6a' : i === P.length - 1 ? '#ff5f5f' : '#ffd166'; g.beginPath(); g.arc(x, y, drawing || i === 0 || i === P.length - 1 ? 6 : 4, 0, 6.283); g.fill(); g.strokeStyle = '#07080c'; g.lineWidth = 1.5; g.stroke(); });
      const [sx, sy] = toS(P[0][0], P[0][1]); g.fillStyle = '#4ccf6a'; g.font = 'bold 11px system-ui'; g.textAlign = 'left'; g.textBaseline = 'bottom'; g.fillText(`🚗 start · ${(length() / 12).toFixed(0)} ft`, sx + 9, sy - 6);
      g.restore();
    }
    return { init, onDown, onMove, onUp, draw, finish, length };
  })();

  // ------------------------------------------------------------ arrange (many)
  const Arrange = (() => {
    let spacing = 96, angle = null, dx = 0, dy = 0, arcR = 600, arcSpan = 90;
    function apply(fn) { App.commit(); const ps = selected(); const before = ctrlsOf(ps); fn(ps); for (const p of ps) S.world[p.id] = App.propWorld(p); placeCtrls(ps.filter(p => before.includes(p.controller))); App.saveLayout(); draw(); renderGroups(); Arrange.panel($('#propDetails')); }
    function ordered(ps) {                                     // props in order along their own main axis (best-fit line)
      const { cx, cy, ux, uy } = axis(ps);
      return [...ps].sort((a, b) => ((a.x - cx) * ux + (a.y - cy) * uy) - ((b.x - cx) * ux + (b.y - cy) * uy));
    }
    function axis(ps) {                                        // least-squares direction through the props' centres
      const cx = ps.reduce((a, p) => a + p.x, 0) / ps.length, cy = ps.reduce((a, p) => a + p.y, 0) / ps.length;
      let sxx = 0, sxy = 0, syy = 0; for (const p of ps) { sxx += (p.x - cx) ** 2; sxy += (p.x - cx) * (p.y - cy); syy += (p.y - cy) ** 2; }
      const th = 0.5 * Math.atan2(2 * sxy, sxx - syy);
      let ux = Math.cos(th), uy = Math.sin(th); if (ux < 0) { ux = -ux; uy = -uy; }
      return { cx, cy, ux, uy, deg: Math.atan2(uy, ux) * 180 / Math.PI };
    }
    function panel(root) {
      const ps = selected(); if (ps.length < 2) return;
      const ax = axis(ps); const o = ordered(ps);
      const gaps = o.slice(1).map((p, i) => Math.hypot(p.x - o[i].x, p.y - o[i].y));
      const gid = [...new Set(ps.map(p => p.group))];
      root.innerHTML = '';
      const num = (get, set, step = 1, w = 64) => el('input', { type: 'number', step, value: get(), style: `width:${w}px`, onchange: e => set(parseFloat(e.target.value) || 0) });
      root.append(el('h2', {}, `${ps.length} props selected`),
        el('div', { class: 'small dim' }, `${gid.map(g => (S.layout.groups[g] || {}).label || g).join(', ')} · row runs at ${ax.deg.toFixed(0)}° · gaps ${gaps.length ? Math.min(...gaps).toFixed(0) + '–' + Math.max(...gaps).toFixed(0) + ' in' : ''} · ${ps.reduce((a, p) => a + App.pxOf(p), 0).toLocaleString()} px`),
        el('div', { class: 'hint' }, 'Drag any selected prop to move them all; arrows nudge (shift: 12 in); R rotates each in place. Esc clears.'));
      root.append(el('h2', {}, 'Move & face'));
      root.append(el('div', { class: 'row' }, el('label', {}, 'move by (in)'), num(() => dx, v => dx = v), num(() => dy, v => dy = v),
        el('button', { class: 'small', onclick: () => apply(ps => { for (const p of ps) setPos(p, p.x + dx, p.y + dy); }) }, 'go')));
      root.append(el('div', { class: 'row' },
        el('button', { class: 'small primary', title: 'pick the spot on the map first (zoom / pan so it is in the middle of the grid), then click: the block is moved there keeping its shape', onclick: () => apply(ps => { const r = grid.getBoundingClientRect(); const [wx, wy] = toW(r.width / 2, r.height / 2); const cx = ps.reduce((a, p) => a + p.x, 0) / ps.length, cy = ps.reduce((a, p) => a + p.y, 0) / ps.length; for (const p of ps) setPos(p, Math.round((p.x - cx + wx) / 6) * 6, Math.round((p.y - cy + wy) / 6) * 6); }) }, '⌖ move block to view centre'),
        el('button', { class: 'small', onclick: () => fitTo(ps) }, 'zoom to block'),
        el('button', { class: 'small', title: 'put each controller of these props back at the centroid of its props', onclick: () => apply(ps => placeCtrls(ps)) }, '⌂ re-place controllers')));
      root.append(el('div', { class: 'arr' },
        el('button', { title: 'every prop faces the same way: perpendicular to the row (toward -y side)', onclick: () => apply(ps => { const a = axis(ps); for (const p of ps) p.rot = (a.deg + 360) % 360; }) }, 'face across the row'),
        el('button', { title: 'turn every prop 180°', onclick: () => apply(ps => { for (const p of ps) p.rot = (p.rot + 180) % 360; }) }, 'flip facing'),
        el('button', { onclick: () => apply(ps => rotateAbout(ps, 15)) }, 'rotate block +15°'),
        el('button', { onclick: () => apply(ps => rotateAbout(ps, -15)) }, 'rotate block −15°'),
        el('button', { onclick: () => apply(ps => rotateAbout(ps, 90)) }, 'rotate block +90°'),
        el('button', { onclick: () => apply(ps => { for (const p of ps) p.rot = 0; }) }, 'all rot 0°'),
        el('button', { title: 'mirror the arrangement left↔right about its centre', onclick: () => apply(ps => { const a = axis(ps); for (const p of ps) { const d = (p.x - a.cx) * a.ux + (p.y - a.cy) * a.uy; setPos(p, p.x - 2 * d * a.ux, p.y - 2 * d * a.uy); } }) }, 'mirror order'),
        el('button', { title: 'snap every prop to the 6-inch grid', onclick: () => apply(ps => { for (const p of ps) setPos(p, Math.round(p.x / 6) * 6, Math.round(p.y / 6) * 6); }) }, 'snap to 6 in')));
      root.append(el('h2', {}, 'Line up'));
      root.append(el('div', { class: 'row' }, el('label', {}, 'spacing (in)'), num(() => spacing, v => spacing = v, 6),
        el('span', { class: 'dim small' }, `${(spacing / 12).toFixed(1)} ft`)));
      root.append(el('div', { class: 'arr' },
        el('button', { title: 'project every prop onto its best-fit line (keeps the order and spacing along it)', onclick: () => apply(ps => { const a = axis(ps); for (const p of ps) { const d = (p.x - a.cx) * a.ux + (p.y - a.cy) * a.uy; setPos(p, a.cx + d * a.ux, a.cy + d * a.uy); } }) }, 'straighten'),
        el('button', { title: 'keep the two end props, spread the rest evenly between them', onclick: () => apply(ps => { const o = ordered(ps); const a = o[0], b = o[o.length - 1]; o.forEach((p, i) => { const t = i / (o.length - 1); setPos(p, a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t); }); }) }, 'distribute evenly'),
        el('button', { title: 'from the first prop, place the rest along the row at exactly this spacing', onclick: () => apply(ps => { const a = axis(ps); const o = ordered(ps); const p0 = o[0]; o.forEach((p, i) => setPos(p, p0.x + a.ux * spacing * i, p0.y + a.uy * spacing * i)); }) }, 'space along row'),
        el('button', { title: 'a horizontal row (west→east) from the first prop at this spacing', onclick: () => apply(ps => { const o = ordered(ps); const p0 = o[0]; o.forEach((p, i) => setPos(p, p0.x + spacing * i, p0.y)); }) }, 'row →'),
        el('button', { title: 'a vertical column (south→north) from the first prop', onclick: () => apply(ps => { const o = [...ps].sort((a, b) => a.y - b.y); const p0 = o[0]; o.forEach((p, i) => setPos(p, p0.x, p0.y + spacing * i)); }) }, 'column ↑'),
        el('button', { title: 'reverse the order of the props along the row (positions swap)', onclick: () => apply(ps => { const o = ordered(ps); const pos = o.map(p => [p.x, p.y]).reverse(); o.forEach((p, i) => setPos(p, pos[i][0], pos[i][1])); }) }, 'reverse order'),
        el('button', { title: 'same y for all (average)', onclick: () => apply(ps => { const y = ps.reduce((a, p) => a + p.y, 0) / ps.length; for (const p of ps) setPos(p, p.x, y); }) }, 'align y'),
        el('button', { title: 'same x for all (average)', onclick: () => apply(ps => { const x = ps.reduce((a, p) => a + p.x, 0) / ps.length; for (const p of ps) setPos(p, x, p.y); }) }, 'align x')));
      root.append(el('h2', {}, 'Arc'));
      root.append(el('div', { class: 'row' }, el('label', {}, 'radius (ft)'), num(() => arcR / 12, v => arcR = v * 12, 5, 56), el('label', {}, 'span (°)'), num(() => arcSpan, v => arcSpan = v, 5, 56),
        el('button', { class: 'small', title: 'place the props evenly along an arc through the current centre, keeping the row direction; props face the arc centre', onclick: () => apply(ps => { const a = axis(ps); const o = ordered(ps); const n = o.length; const nx = -a.uy, ny = a.ux; const ccx = a.cx + nx * arcR, ccy = a.cy + ny * arcR; const base = Math.atan2(a.cy - ccy, a.cx - ccx); const span = arcSpan * Math.PI / 180; o.forEach((p, i) => { const t = n > 1 ? i / (n - 1) - 0.5 : 0; const th = base - t * span; setPos(p, ccx + arcR * Math.cos(th), ccy + arcR * Math.sin(th)); p.rot = (th * 180 / Math.PI + 90 + 360) % 360; }); }) }, 'place on arc')));
      root.append(el('h2', {}, 'Heights & group'));
      const zIn = num(() => ps[0].z, () => {}, 1, 56);
      const groupSel = el('select', {}, ...Object.entries(S.layout.groups).map(([g, gg]) => el('option', { value: g, selected: g === ps[0].group ? '' : null }, gg.label || g)));
      root.append(el('div', { class: 'row' }, el('label', {}, 'z for all (in)'), zIn, el('button', { class: 'small', onclick: () => apply(ps => { const z = parseFloat(zIn.value) || 0; for (const p of ps) p.z = z; }) }, 'set'),
        el('label', {}, 'group'), groupSel, el('button', { class: 'small', onclick: () => apply(ps => { for (const p of ps) if (p.group !== groupSel.value) { p.group = groupSel.value; p.controller = null; p.port = null; } S.selGroup = groupSel.value; }) }, 'move')));
      root.append(el('div', { class: 'row', style: 'margin-top:8px' },
        el('button', { class: 'small', onclick: () => fitTo(ps) }, 'zoom to selection'),
        el('button', { class: 'small', onclick: () => { S.selProp = null; S.selProps = []; renderAll(); } }, 'clear selection')));
    }
    function rotateAbout(ps, deg) { const a = axis(ps); const th = deg * Math.PI / 180, c = Math.cos(th), s = Math.sin(th); for (const p of ps) { const rx = p.x - a.cx, ry = p.y - a.cy; setPos(p, a.cx + rx * c - ry * s, a.cy + rx * s + ry * c); p.rot = (p.rot + deg + 360) % 360; } }
    return { panel };
  })();

  // ------------------------------------------------------------------- paint
  const Paint = (() => {
    const c = $('#paint');
    let P = null, prop = null, selected = new Set(), showWire = false, showExist = true, wireMode = 0, wireA = null, lasso = null, selReg = null, dirty = false;
    function init() {
      $('#bPaintBack').onclick = close;
      $('#bPaintWire').onclick = () => { showWire = !showWire; $('#bPaintWire').classList.toggle('on', showWire); draw(); };
      $('#bPaintExist').onclick = () => { showExist = !showExist; $('#bPaintExist').classList.toggle('on', showExist); draw(); };
      $('#badd').onclick = addRegion; $('#bclear').onclick = () => { selected.clear(); draw(); };
      $('#bdel').onclick = () => { if (selReg && confirm(`delete region "${selReg}"?`)) { delete P.regions[selReg]; selReg = null; touched(); listRegions(); draw(); } };
      $('#bwr').onclick = () => { wireMode = 1; wireA = null; $('#bwr').classList.add('on'); draw(); };
      $('#bsuggest').onclick = suggest;
      $('#bPaintSave').onclick = save;
      c.addEventListener('mousedown', onDown); window.addEventListener('mousemove', onMove); window.addEventListener('mouseup', onUp);
      $('#rname').addEventListener('keydown', e => { if (e.key === 'Enter') addRegion(); });
    }
    function open(p) {
      if (P && dirty) save();
      prop = p; const s = S.shapes[p.mod]; const stem = p.mod.replace('.mod', '');
      P = { stem, mod: p.mod, n: s.n, x: s.lx, y: s.ly, pitch: s.pitch_in, regions: JSON.parse(JSON.stringify(S.paint[stem] || {})) };
      selected.clear(); selReg = null; dirty = false; paintMode = true;
      $('#gridWrap').hidden = true; $('#paintWrap').hidden = false; $('#paintPanel').hidden = false; $('#propDetails').hidden = true; $('#ctrlPanel').innerHTML = '';
      $('#paintTitle').textContent = `${p.label || p.id} · ${p.mod} · ${s.n} px`; $('#paintSaved').textContent = 'changes save automatically';
      listRegions(); draw();
    }
    const autosave = debounce(() => { if (dirty) save(); }, 500);
    function touched() { dirty = true; $('#paintSaved').textContent = 'saving…'; autosave(); }
    function close() {
      if (dirty) save();
      paintMode = false; $('#gridWrap').hidden = false; $('#paintWrap').hidden = true; $('#paintPanel').hidden = true; $('#propDetails').hidden = false;
      renderAll();
    }
    async function save() {
      const stem = P.stem, regions = JSON.parse(JSON.stringify(P.regions));
      await api.send('PUT', `/api/paint/${encodeURIComponent(stem)}`, { mod: P.mod, regions });
      S.paint[stem] = regions; if (P.stem === stem) dirty = false; S.previewDirty = true;     // the server rebuilt its renderer: the preview shows the new regions immediately
      $('#paintSaved').textContent = 'saved · assets/paint/' + stem + '.json';
    }
    function view() { const r = c.getBoundingClientRect(); const W = r.width, H = r.height; const x0 = Math.min(...P.x), x1 = Math.max(...P.x), y0 = Math.min(...P.y), y1 = Math.max(...P.y); const s = Math.min((W - 80) / Math.max(1, x1 - x0), (H - 80) / Math.max(1, y1 - y0)); return { W, H, s, ox: W / 2 - (x0 + x1) / 2 * s, oy: H / 2 + (y0 + y1) / 2 * s }; }
    const toScreen = (i, v) => [v.ox + P.x[i] * v.s, v.oy - P.y[i] * v.s];
    function regionOf(i) { for (const [n, r] of Object.entries(P.regions)) if (r.pixels.includes(i)) return n; return null; }
    function draw() {
      if (!paintMode || !P) return;
      const r = c.getBoundingClientRect(); c.width = r.width * devicePixelRatio; c.height = r.height * devicePixelRatio; const g = c.getContext('2d'); g.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
      const v = view(); g.fillStyle = '#07080c'; g.fillRect(0, 0, v.W, v.H);
      const rad = Math.max(3, P.pitch * v.s * 0.28);
      g.strokeStyle = '#1f2636'; g.lineWidth = 1; g.beginPath(); for (let i = 0; i < P.n; i++) { const [x, y] = toScreen(i, v); i ? g.lineTo(x, y) : g.moveTo(x, y); } g.stroke();
      for (let i = 0; i < P.n; i++) {
        const [x, y] = toScreen(i, v); let col = '#6b7385'; const rn = regionOf(i);
        if (showWire) col = `hsl(${i / P.n * 300},85%,55%)`; else if (showExist && rn) col = P.regions[rn].color;
        g.fillStyle = col; g.beginPath(); g.arc(x, y, rad, 0, 6.283); g.fill();
        if (selected.has(i)) { g.strokeStyle = '#fff'; g.lineWidth = 2; g.beginPath(); g.arc(x, y, rad + 2.5, 0, 6.283); g.stroke(); }
        if (selReg && rn === selReg) { g.strokeStyle = P.regions[rn].color; g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, rad + 4, 0, 6.283); g.stroke(); }
        if (wireMode && wireA === i) { g.strokeStyle = '#ffb347'; g.lineWidth = 3; g.beginPath(); g.arc(x, y, rad + 5, 0, 6.283); g.stroke(); }
      }
      if (lasso && lasso.length > 1) { g.strokeStyle = '#5fb8ff'; g.lineWidth = 1.5; g.setLineDash([5, 4]); g.beginPath(); lasso.forEach(([x, y], k) => k ? g.lineTo(x, y) : g.moveTo(x, y)); g.closePath(); g.stroke(); g.setLineDash([]); }
      $('#selcount').textContent = selected.size ? `${selected.size} px` : '';
      $('#paintHud').textContent = wireMode ? (wireA == null ? 'wire range: click the FIRST bulb' : 'wire range: click the LAST bulb') : 'click · drag lasso · shift+click flood · W wire range · Esc clears';
    }
    function nearest(mx, my) { const v = view(); let best = -1, bd = 1e9; for (let i = 0; i < P.n; i++) { const [x, y] = toScreen(i, v); const d = Math.hypot(x - mx, y - my); if (d < bd) { bd = d; best = i; } } return bd < Math.max(8, P.pitch * v.s * 0.6) ? best : -1; }
    function flood(i) { const out = new Set([i]); const q = [i]; const lim = 1.6 * P.pitch; while (q.length) { const a = q.pop(); for (let b = 0; b < P.n; b++) { if (out.has(b) || regionOf(b)) continue; if (Math.hypot(P.x[a] - P.x[b], P.y[a] - P.y[b]) <= lim) { out.add(b); q.push(b); } } } return out; }
    function inPoly(x, y, poly) { let ins = false; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) { const [xi, yi] = poly[i], [xj, yj] = poly[j]; if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) ins = !ins; } return ins; }
    function onDown(e) {
      if (!paintMode) return; const r = c.getBoundingClientRect(); const mx = e.clientX - r.left, my = e.clientY - r.top; const i = nearest(mx, my);
      if (wireMode) { if (i < 0) return; if (wireA == null) wireA = i; else { const a = Math.min(wireA, i), b = Math.max(wireA, i); for (let k = a; k <= b; k++) selected.add(k); wireMode = 0; wireA = null; $('#bwr').classList.remove('on'); } draw(); return; }
      if (i >= 0) { if (e.shiftKey) for (const k of flood(i)) selected.add(k); else selected.has(i) ? selected.delete(i) : selected.add(i); draw(); return; }
      lasso = [[mx, my]];
    }
    function onMove(e) { if (!lasso) return; const r = c.getBoundingClientRect(); lasso.push([e.clientX - r.left, e.clientY - r.top]); draw(); }
    function onUp() { if (!lasso) return; if (lasso.length > 5) { const v = view(); for (let i = 0; i < P.n; i++) { const [x, y] = toScreen(i, v); if (inPoly(x, y, lasso)) selected.add(i); } } lasso = null; draw(); }
    function listRegions() {
      const root = $('#regions'); root.innerHTML = '';
      const ents = Object.entries(P.regions);
      if (!ents.length) root.append(el('div', { class: 'hint' }, 'none yet'));
      ents.forEach(([n, r], k) => root.append(el('div', { class: 'r' + (n === selReg ? ' sel' : ''), onclick: () => { selReg = n; $('#rname').value = n; $('#rcolor').value = r.color; listRegions(); draw(); } },
        el('span', { class: 'sw', style: `background:${r.color}` }), el('b', {}, n), el('span', { class: 'dim small' }, `${r.pixels.length} px · ${k + 1}`),
        el('input', { type: 'color', value: r.color, style: 'margin-left:auto', onclick: e => e.stopPropagation(), oninput: e => { r.color = e.target.value; touched(); draw(); } }))));
    }
    function addRegion() {
      const name = $('#rname').value.trim(); if (!name || !selected.size) return; const col = $('#rcolor').value;
      for (const r of Object.values(P.regions)) r.pixels = r.pixels.filter(i => !selected.has(i));
      const ex = P.regions[name]; P.regions[name] = { color: col, pixels: [...(ex ? ex.pixels : []), ...selected].sort((a, b) => a - b) };
      for (const n of Object.keys(P.regions)) if (!P.regions[n].pixels.length) delete P.regions[n];
      selected.clear(); selReg = name; $('#rname').value = ''; touched(); listRegions(); draw();
    }
    function suggest() {
      if (!confirm('Replace regions with auto-suggested wire runs (cuts where the wire jumps)?')) return;
      const n = P.n; const step = []; for (let i = 1; i < n; i++) step.push(Math.hypot(P.x[i] - P.x[i - 1], P.y[i] - P.y[i - 1]));
      const sorted = [...step].sort((a, b) => a - b); const pitch = sorted[Math.floor(sorted.length / 2)] || 1;
      const cuts = [0]; step.forEach((s, i) => { if (s > 2.6 * pitch) cuts.push(i + 1); }); cuts.push(n);
      const runs = []; for (let k = 0; k < cuts.length - 1; k++) { const r = []; for (let i = cuts[k]; i < cuts[k + 1]; i++) r.push(i); if (runs.length && r.length < 4) runs[runs.length - 1].push(...r); else runs.push(r); }
      const pal = ['#d0232a', '#f2c9a0', '#2b8a3e', '#e8b04b', '#5fb8ff', '#ffffff', '#c77dff'];
      P.regions = {}; runs.forEach((run, k) => P.regions[`run${k + 1}`] = { color: pal[k % pal.length], pixels: run });
      touched(); listRegions(); draw();
    }
    function onKey(e) {
      if (e.key === 'Enter') addRegion(); else if (e.key === 'w' || e.key === 'W') $('#bwr').click(); else if (e.key === 'e' || e.key === 'E') $('#bPaintExist').click();
      else if (e.key >= '1' && e.key <= '9') { const names = Object.keys(P.regions); const n = names[+e.key - 1]; if (n && selected.size) { $('#rname').value = n; $('#rcolor').value = P.regions[n].color; addRegion(); } }
      else if (e.key === 'Escape') { selected.clear(); wireMode = 0; wireA = null; $('#bwr').classList.remove('on'); draw(); }
    }
    return { init, open, close, draw, onKey };
  })();

  return { init, show, renderAll, renderGroups, draw, onKey, Paint, editOnTimeline };
})();
