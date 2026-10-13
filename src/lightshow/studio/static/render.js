// render.js -- Render & cards: frame-rate choice, card table, render, printable sheet.
'use strict';
App.Render = (() => {
  function init() {
    $('#bRender').onclick = render;
    $('#bRenderSongs').onclick = renderSongs;
    $('#songFirstScene').onchange = showSongPlan;
    $('#bPrintSheet').onclick = printSheet;
    $('#bImport').onclick = () => $('#importFile').click();
    $('#importFile').onchange = importProject;
  }
  function show() {
    const fc = $('#fpsChoice'); fc.innerHTML = '';
    for (const [k, txt] of Object.entries(S.st.fps_help)) {
      const on = String(S.project.fps) === k;
      fc.append(el('div', { class: 'opt' + (on ? ' on' : ''), onclick: () => { App.commit(); S.project.fps = parseFloat(k); App.saveProject(); show(); } },
        el('input', { type: 'radio', checked: on ? '' : null }), el('div', {}, el('b', {}, k + ' fps'), el('span', { class: 'small dim' }, txt))));
    }
    const dur = App.Timeline.duration() - 5; const frames = Math.round(dur * S.project.fps);
    fc.append(el('div', { class: 'hint' }, `Timeline length ${fmtT(dur)} → ${frames.toLocaleString()} frames at ${S.project.fps} fps ${frames > 65535 ? '— OVER the 65,535-frame cap!' : `(cap 65,535)`}.`));
    const root = $('#cardsTable'); root.innerHTML = '';
    const tbl = el('table', { class: 't' }, el('tr', {}, el('th', {}, 'controller'), el('th', {}, 'group'), el('th', {}, 'SD label'), el('th', {}, 'port 1'), el('th', {}, 'port 2'), el('th', {}, 'port 3'), el('th', {}, 'port 4'), el('th', {}, 'px'), el('th', {}, 'file size'), el('th', {}, 'last rendered')));
    const cids = [...new Set([...Object.keys(S.layout.controllers), ...S.layout.props.map(p => p.controller).filter(Boolean)])].sort();
    let total = 0;
    for (const cid of cids) {
      const ps = S.layout.props.filter(p => p.controller === cid);
      const gid = (S.layout.controllers[cid] || {}).group || (ps[0] || {}).group || '';
      const card = S.project.cards[cid] || (S.project.cards[cid] = { sd_label: cid, formatted: null, written: null, notes: '' });
      const px = ps.reduce((a, p) => a + App.pxOf(p), 0);
      const chans = [1, 2, 3, 4].map(k => { const p = ps.find(q => q.port === k); return p ? App.pxOf(p) : 32; });
      const bytes = chans.reduce((a, b) => a + b, 0) * 3 * frames; total += bytes;
      tbl.append(el('tr', {}, el('td', { class: 'mono' }, cid), el('td', {}, el('span', { class: 'sw', style: `background:${App.groupColor(gid)}` }), ' ', (S.layout.groups[gid] || {}).label || gid),
        el('td', {}, el('input', { value: card.sd_label || cid, style: 'width:90px', onchange: e => { card.sd_label = e.target.value; App.saveProject(); } })),
        ...[1, 2, 3, 4].map(k => { const p = ps.find(q => q.port === k); return el('td', { class: 'mono small' + (p ? '' : ' dim') }, p ? `${p.id} (${App.pxOf(p)})` : 'stub'); }),
        el('td', { class: px > 4096 ? 'err' : '' }, px), el('td', { class: 'dim' }, (bytes / 1e6).toFixed(0) + ' MB'), el('td', { class: 'dim small' }, card.written || '—')));
    }
    root.append(tbl, el('div', { class: 'hint' }, `${cids.length} cards, ${(total / 1e6).toFixed(0)} MB total for scene 1. Formatting and copying to the physical cards is Phase 2 (needs disk access from the backend).`));
    showSongPlan();
  }
  async function showSongPlan() {
    const root = $('#songPlan'); if (!root) return;
    const first = Math.max(1, parseInt($('#songFirstScene').value) || 1);
    let plan = [];
    try { plan = await api.get(`/api/render_songs/plan?first_scene=${first}`); } catch (e) { root.textContent = ''; return; }
    root.innerHTML = '';
    const tbl = el('table', { class: 't' }, el('tr', {}, el('th', {}, 'scene'), el('th', {}, 'DMX value'), el('th', {}, 'song'), el('th', {}, 'from'), el('th', {}, 'to'), el('th', {}, 'frames')));
    for (const p of plan) tbl.append(el('tr', {}, el('td', { class: 'mono' }, `Sc-${String(p.scene).padStart(2, '0')}`), el('td', { class: 'mono' }, p.dmx_value), el('td', {}, p.name), el('td', { class: 'mono' }, fmtT(p.t0)), el('td', { class: 'mono' }, fmtT(p.t1)), el('td', { class: 'mono' }, p.frames.toLocaleString())));
    root.append(tbl);
    const last = first + plan.length - 1;
    if (last > 62) root.append(el('div', { class: 'warn small' }, `scene ${last} is past the controller's 62-file limit`));
  }
  async function renderSongs() {
    const first = Math.max(1, parseInt($('#songFirstScene').value) || 1);
    if (!confirm(`Render one scene per song, starting at Sc-${String(first).padStart(2, '0')}? Existing files with those scene numbers in out/studio/cards/ are overwritten.`)) return;
    $('#renderSongsStatus').textContent = 'rendering…'; $('#bRenderSongs').disabled = true;
    try {
      const cues = await api.send('POST', '/api/render_songs', { first_scene: first });
      $('#renderSongsStatus').textContent = `done: ${cues.scenes.length} scenes (Sc-${String(first).padStart(2, '0')}…Sc-${String(first + cues.scenes.length - 1).padStart(2, '0')}) → out/studio/cards/ + cues.json`;
      await App.reloadState(); show();
    } catch (e) { $('#renderSongsStatus').textContent = 'failed: ' + e.message; }
    $('#bRenderSongs').disabled = false;
  }
  async function render() {
    if (!confirm('Render the whole timeline to cards? A 15-minute yard show takes several minutes; the preview pauses meanwhile.')) return;
    $('#renderStatus').textContent = 'rendering…'; $('#bRender').disabled = true;
    try {
      const man = await api.send('POST', '/api/render', {});
      $('#renderStatus').textContent = `done: ${man.frames.toLocaleString()} frames @ ${man.fps} fps, ${Object.keys(man.cards).length} cards in ${man.render_s}s → out/studio/cards/`;
      await App.reloadState(); show();
    } catch (e) { $('#renderStatus').textContent = 'failed: ' + e.message; }
    $('#bRender').disabled = false;
  }
  async function importProject(e) {
    const f = e.target.files[0]; if (!f) return; e.target.value = '';
    if (!confirm(`Replace the current timeline with ${f.name}? (a backup of the current project is kept)`)) return;
    const fd = new FormData(); fd.append('file', f);
    const rep = $('#importReport'); rep.textContent = 'importing…';
    const r = await fetch('/api/import/project', { method: 'POST', body: fd });
    if (!r.ok) { rep.innerHTML = `<span class="err">import failed: ${(await r.text()).slice(0, 300)}</span>`; return; }
    const j = await r.json();
    await App.reloadState();
    rep.innerHTML = `<div>imported ${j.clips} clips${j.backup ? ` · previous project saved as <span class="mono">${j.backup}</span>` : ''}</div>` +
      (j.warnings.length ? `<div class="warn">${j.warnings.length} fix-ups:</div><ul>${j.warnings.map(w => `<li>${w}</li>`).join('')}</ul>` : '<div class="dim">no fix-ups needed</div>');
  }
  function printSheet() {
    const rows = S.layout.props.slice().sort((a, b) => (a.controller || 'zz').localeCompare(b.controller || 'zz') || (a.port || 0) - (b.port || 0));
    const g = id => (S.layout.groups[id] || {}).label || id;
    const html = `<!doctype html><html><head><meta charset="utf-8"><title>Prop & card sheet</title>
<style>body{font:12px system-ui;margin:24px;color:#000}h1{font-size:18px}h2{font-size:14px;margin-top:22px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #999;padding:3px 6px;text-align:left}th{background:#eee}
.g{display:inline-block;width:10px;height:10px;border:1px solid #333;vertical-align:middle;margin-right:4px}@media print{h2{page-break-before:auto}}</style></head><body>
<h1>Lightshow — prop &amp; SD card sheet</h1><div>${new Date().toLocaleString()} · ${S.st.layout_path} · ${S.layout.props.length} props · ${Object.keys(S.layout.groups).length} groups · ${S.project.fps} fps</div>
<h2>Cards (controller → ports)</h2><table><tr><th>controller</th><th>SD label</th><th>group</th><th>port 1</th><th>port 2</th><th>port 3</th><th>port 4</th><th>px</th><th>map x,y (in)</th></tr>
${[...new Set(rows.map(p => p.controller).filter(Boolean))].sort().map(cid => { const ps = rows.filter(p => p.controller === cid); const c = S.layout.controllers[cid] || {}; const card = S.project.cards[cid] || {}; return `<tr><td><b>${cid}</b></td><td>${card.sd_label || cid}</td><td>${g(c.group || ps[0].group)}</td>${[1, 2, 3, 4].map(k => { const p = ps.find(q => q.port === k); return `<td>${p ? `${p.id} ${p.label || ''} (${App.pxOf(p)} px)` : '<i>stub</i>'}</td>`; }).join('')}<td>${ps.reduce((a, p) => a + App.pxOf(p), 0)}</td><td>${c.x !== undefined ? `${c.x}, ${c.y}` : ''}</td></tr>`; }).join('')}</table>
<h2>Props (where each one is)</h2><table><tr><th>prop</th><th>label</th><th>.mod</th><th>group</th><th>controller</th><th>port</th><th>px</th><th>x (in)</th><th>y (in)</th><th>z (in)</th><th>rot</th><th>painted</th></tr>
${rows.map(p => `<tr><td><b>${p.id}</b></td><td>${p.label || ''}</td><td>${p.mod}</td><td><span class="g" style="background:${App.groupColor(p.group)}"></span>${g(p.group)}</td><td>${p.controller || '<i>none</i>'}</td><td>${p.port || ''}</td><td>${App.pxOf(p)}</td><td>${p.x}</td><td>${p.y}</td><td>${p.z}</td><td>${p.rot}°</td><td>${Object.keys(S.paint[p.mod.replace('.mod', '')] || {}).join(', ')}</td></tr>`).join('')}</table>
<script>window.onload=()=>window.print()</script></body></html>`;
    const w = window.open('', '_blank'); w.document.write(html); w.document.close();
  }
  return { init, show };
})();
