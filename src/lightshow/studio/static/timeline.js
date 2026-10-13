// timeline.js -- the linear editor: ruler, audio lane, sections, per-group lanes, clips, inspector.
'use strict';
App.Timeline = (() => {
  const cv = $('#tl'), scroll = $('#tlScroll'), headers = $('#tlHeaders');
  const H = { ruler: 22, audio: 56, sections: 20, anim: 34, trans: 16, mod: 24, gap: 6 };
  const COL = { anim: '#3b6fd6', trans: '#c77dff', mod: '#2fb37a', audio: '#7a8fb3', sec: '#e8b04b' };
  let pps = 20, scrollX = 0;                 // px per second, seconds scrolled
  let lanes = [];                            // [{kind, group, y, h}]
  let drag = null, hover = null, lastDraw = 0, vs = 0;   // vs = vertical scroll of the lanes (px)

  function init() {
    $('#zoom').oninput = e => setZoom(+e.target.value);
    $('#bZoomIn').onclick = () => setZoom(pps * 1.4); $('#bZoomOut').onclick = () => setZoom(pps / 1.4);
    $('#bZoomFit').onclick = fitZoom;
    $('#bAddAudio').onclick = addAudio;
    $('#bSections').onclick = detectSections;
    $('#audioFile').onchange = uploadAudio;
    cv.addEventListener('mousedown', onDown); window.addEventListener('mousemove', onMove); window.addEventListener('mouseup', onUp);
    cv.addEventListener('wheel', onWheel, { passive: false });
    cv.addEventListener('dblclick', onDbl);
    cv.addEventListener('dragover', e => { if (e.dataTransfer.types.includes('text/fx')) { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; } });
    cv.addEventListener('drop', onDrop);
    window.addEventListener('resize', () => { if (S.mode === 'timeline') draw(); });
    renderFxBrowser();
  }
  async function show() {
    // the timeline edits ONE group at a time (the previewed one); default to the first group
    if (!S.previewGroups || !S.layout.groups[S.previewGroups[0]]) { const g0 = Object.keys(S.layout.groups)[0]; S.previewGroups = g0 ? [g0] : null; $('#previewGroup').value = g0 || ''; }
    renderFxBrowser(); layoutTracks(); await ensureAnalysis(); draw(); inspector();
  }
  function selectGroup(gid) { S.previewGroups = gid ? [gid] : null; $('#previewGroup').value = gid || ''; S.previewDirty = true; S.selClip = null; S.selClips = []; layoutTracks(); setVS(0); draw(); inspector(); App.Preview.resize(); }
  function renderGroupTabs() {
    const bar = $('#tlGroups'); if (!bar) return; bar.innerHTML = '';
    const cur = S.previewGroups ? S.previewGroups[0] : '';
    for (const [gid, g] of Object.entries(S.layout.groups)) {
      const tr = S.project.tracks.find(t => t.group === gid); const n = tr ? tr.clips.length : 0;
      bar.append(el('button', { class: 'chip2 gtab' + (gid === cur ? ' on' : ''), style: `--gc:${g.color || '#8a93a6'}`, title: `${n} clips`, onclick: () => selectGroup(gid) }, el('span', { class: 'sw', style: `background:${g.color || '#8a93a6'}` }), ` ${g.label || gid}`, n ? el('span', { class: 'dim' }, ` ${n}`) : null));
    }
    bar.append(el('button', { class: 'chip2 gtab' + (!cur ? ' on' : ''), title: 'every group\'s lanes at once', onclick: () => selectGroup(null) }, 'all'));
  }

  // ------------------------------------------------------------- geometry
  const tToX = t => (t - scrollX) * pps;
  const xToT = x => x / pps + scrollX;
  function duration() { let d = 60; for (const a of S.project.audio) d = Math.max(d, a.start + (a.duration || 0)); for (const t of S.project.tracks) for (const c of t.clips) d = Math.max(d, c.t1); return d + 5; }
  function setZoom(v) { const r = cv.getBoundingClientRect(); const mid = xToT(r.width / 2); pps = clamp(v, 2, 400); scrollX = Math.max(0, mid - r.width / 2 / pps); $('#zoom').value = pps; draw(); }
  function fitZoom() { const r = cv.getBoundingClientRect(); pps = clamp((r.width - 20) / duration(), 2, 400); scrollX = 0; $('#zoom').value = pps; draw(); }
  function layoutTracks() {
    lanes = []; let y = H.ruler;
    lanes.push({ kind: 'audio', y, h: H.audio }); y += H.audio;
    lanes.push({ kind: 'sections', y, h: H.sections }); y += H.sections + H.gap;
    renderGroupTabs();
    for (const gid of (S.previewGroups && S.previewGroups.length ? S.previewGroups.filter(g => S.layout.groups[g]) : Object.keys(S.layout.groups))) {
      lanes.push({ kind: 'anim', group: gid, y, h: H.anim }); y += H.anim;
      lanes.push({ kind: 'trans', group: gid, y, h: H.trans }); y += H.trans;
      lanes.push({ kind: 'mod', group: gid, y, h: H.mod }); y += H.mod + H.gap;
    }
    lanes.total = y;
    headers.innerHTML = '';
    const inner = el('div', { id: 'tlHeadersInner', style: `position:absolute;left:0;right:0;top:${-vs}px` }); headers.append(inner);
    inner.append(el('div', { class: 'tlHead', style: `top:${H.ruler}px;height:${H.audio}px` }, el('b', {}, 'Audio'), el('span', { class: 'sub' }, `${S.project.audio.length} clip${S.project.audio.length === 1 ? '' : 's'}`)));
    inner.append(el('div', { class: 'tlHead', style: `top:${H.ruler + H.audio}px;height:${H.sections}px` }, el('span', { class: 'sub' }, 'Sections')));
    for (const L of lanes) {
      if (!L.group) continue;
      const g = S.layout.groups[L.group];
      if (L.kind === 'anim') inner.append(el('div', { class: 'tlHead', style: `top:${L.y}px;height:${L.h}px;border-bottom:0` }, el('span', { class: 'sw', style: `background:${g.color}` }), el('b', {}, g.label || L.group),
        el('button', { class: 'small', title: 'preview only this group', onclick: () => { S.previewGroups = [L.group]; $('#previewGroup').value = L.group; S.previewDirty = true; } }, '👁')));
      if (L.kind === 'trans') inner.append(el('div', { class: 'tlHead', style: `top:${L.y}px;height:${L.h}px;border-bottom:0` }, el('span', { class: 'sub' }, 'transitions')));
      if (L.kind === 'mod') inner.append(el('div', { class: 'tlHead', style: `top:${L.y}px;height:${L.h}px` }, el('span', { class: 'sub' }, 'modifiers')));
    }
  }
  function laneAt(y) { y += vs; return lanes.find(L => y >= L.y && y < L.y + L.h); }
  function setVS(v) { const r = scroll.getBoundingClientRect(); vs = clamp(v, 0, Math.max(0, lanes.total - r.height + 20)); const inner = $('#tlHeadersInner'); if (inner) inner.style.top = -vs + 'px'; }
  function laneFor(kind, gid) { return lanes.find(L => L.kind === kind && L.group === gid); }

  // -------------------------------------------------------------- analysis
  async function ensureAnalysis(force) {
    for (const a of S.project.audio) {
      if (S.analysis[a.id] && !force) continue;
      try { S.analysis[a.id] = await api.get(`/api/audio/${a.id}/analysis`); if (!a.duration) a.duration = S.analysis[a.id].duration; }
      catch (e) { App.status('analysis failed: ' + e.message, 'err'); }
    }
    draw();
  }
  function beatGrid() {                       // timeline-time beats and downbeats
    const beats = [], bars = [];
    for (const a of S.project.audio) {
      const an = S.analysis[a.id]; if (!an) continue; const sh = a.start - (a.offset || 0);
      for (const b of an.beats) { const t = sh + b; if (t >= a.start && t <= a.start + a.duration) beats.push(t); }
      for (const b of an.bars) { const t = sh + b; if (t >= a.start && t <= a.start + a.duration) bars.push(t); }
    }
    return { beats, bars };
  }
  function songAt(t) { const a = S.project.audio.find(a => a.start <= t && t < a.start + (a.duration || 0)); const an = a && S.analysis[a.id]; if (!an) return null; const ft = t - a.start + (a.offset || 0); return an.songs.find(s => s.from <= ft && ft < s.to) || an.songs[an.songs.length - 1]; }
  function bpmAt(sg, ft) { if (!sg) return 120; if (!sg.bpm_end || !sg.bpm) return sg.bpm; const u = Math.min(1, Math.max(0, (ft - sg.from) / Math.max(1e-6, sg.to - sg.from))); return sg.bpm + (sg.bpm_end - sg.bpm) * u; }
  function barLenAt(t) { const sg = songAt(t); if (!sg) return 2.0; const a = S.project.audio.find(a => a.start <= t && t < a.start + (a.duration || 0)); const ft = a ? t - a.start + (a.offset || 0) : t; return 60 / bpmAt(sg, ft) * (sg.beats_per_bar || 4); }
  const bpmLabel = sg => sg.bpm_end && sg.bpm && Math.abs(sg.bpm_end - sg.bpm) > 0.05 ? `${sg.bpm.toFixed(0)}→${(+sg.bpm_end).toFixed(0)} BPM` : `${(+sg.bpm).toFixed(0)} BPM`;
  function snap(t, exclude) {
    if (!$('#snap').checked) return t;
    const { beats, bars } = beatGrid(); const cands = pps > 60 ? beats : bars;
    let best = t, bd = 8 / pps;
    const consider = v => { const d = Math.abs(v - t); if (d < bd) { bd = d; best = v; } };
    for (const v of cands) consider(v);
    for (const s of S.project.sections) { consider(s.t0); consider(s.t1); }
    for (const tr of S.project.tracks) for (const c of tr.clips) if (c !== exclude) { consider(c.t0); consider(c.t1); }
    consider(S.time);
    return best;
  }

  // ------------------------------------------------------------------ draw
  function draw() {
    if (S.mode !== 'timeline') return;
    const r = scroll.getBoundingClientRect(); if (!r.width) return;
    cv.width = r.width * devicePixelRatio; cv.height = r.height * devicePixelRatio;
    const g = cv.getContext('2d'); g.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    const W = r.width, Hh = r.height;
    g.fillStyle = '#10141c'; g.fillRect(0, 0, W, Hh);
    const tEnd = xToT(W);
    g.save(); g.translate(0, -vs);
    // beat / bar grid
    const { beats, bars } = beatGrid();
    if (pps > 60) { g.strokeStyle = '#1b2231'; g.beginPath(); for (const b of beats) { if (b < scrollX || b > tEnd) continue; const x = tToX(b); g.moveTo(x, H.ruler); g.lineTo(x, lanes.total); } g.stroke(); }
    if (pps > 8) { g.strokeStyle = '#2b3547'; g.beginPath(); for (const b of bars) { if (b < scrollX || b > tEnd) continue; const x = tToX(b); g.moveTo(x, H.ruler); g.lineTo(x, lanes.total); } g.stroke(); }
    // lanes background
    for (const L of lanes) { g.fillStyle = L.kind === 'anim' ? '#141a25' : L.kind === 'audio' ? '#12171f' : '#10141c'; g.fillRect(0, L.y, W, L.h); g.strokeStyle = '#1d2230'; g.beginPath(); g.moveTo(0, L.y + L.h - 0.5); g.lineTo(W, L.y + L.h - 0.5); g.stroke(); }
    g.restore();
    // ruler (fixed at the top)
    g.fillStyle = '#0d1017'; g.fillRect(0, 0, W, H.ruler);
    const stepS = [0.5, 1, 2, 5, 10, 15, 30, 60, 120].find(s => s * pps > 70) || 300;
    g.fillStyle = '#8a93a6'; g.font = '10.5px ui-monospace,monospace'; g.textBaseline = 'top'; g.textAlign = 'left';
    for (let t = Math.floor(scrollX / stepS) * stepS; t < tEnd; t += stepS) { const x = tToX(t); g.fillRect(x, H.ruler - 6, 1, 6); g.fillText(fmtT(t).replace(/\.0$/, ''), x + 3, 4); }
    g.save(); g.translate(0, -vs);
    // audio clips + waveform
    const LA = lanes[0];
    for (const a of S.project.audio) {
      const x0 = tToX(a.start), x1 = tToX(a.start + (a.duration || 0)); if (x1 < 0 || x0 > W) continue;
      g.fillStyle = S.selAudio === a.id ? '#2a3550' : '#1c2434'; g.fillRect(x0, LA.y + 2, x1 - x0, LA.h - 4);
      const an = S.analysis[a.id];
      if (an) {
        g.fillStyle = '#5f7fb3'; const mid = LA.y + LA.h / 2, amp = (LA.h - 10) / 2;
        const i0 = Math.max(0, Math.floor((Math.max(scrollX, a.start) - a.start + (a.offset || 0)) * an.wave_hz));
        const i1 = Math.min(an.wave.length, Math.ceil((Math.min(tEnd, a.start + a.duration) - a.start + (a.offset || 0)) * an.wave_hz));
        const perPx = Math.max(1, Math.floor(an.wave_hz / pps));
        for (let i = i0; i < i1; i += perPx) { let v = 0; for (let k = 0; k < perPx && i + k < i1; k++) v = Math.max(v, an.wave[i + k]); const x = tToX(a.start - (a.offset || 0) + i / an.wave_hz); g.fillRect(x, mid - v * amp, Math.max(1, perPx / an.wave_hz * pps), v * amp * 2); }
      }
      g.fillStyle = '#dfe6f3'; g.font = '11px system-ui'; g.textBaseline = 'top'; g.textAlign = 'left';
      g.fillText(`${a.name}${an ? (an.songs.length > 1 ? `  ·  ${an.songs.length} songs` : `  ·  ${an.songs[0].bpm.toFixed(1)} BPM ${a.songs && a.songs.length && a.songs[0].bpm ? '' : '(detected)'}  ·  ${an.songs[0].beats_per_bar}/4`) : '  · analysing…'}`, Math.max(4, x0 + 4), LA.y + 4);
      if (an && an.songs.length > 1) for (const sg of an.songs) {                    // song boundaries + names inside the audio lane
        const sx = tToX(a.start - (a.offset || 0) + sg.from); if (sx < -200 || sx > W) continue;
        g.fillStyle = '#e8b04b'; g.fillRect(sx, LA.y + 2, 1, LA.h - 4);
        g.fillStyle = '#c9b27a'; g.font = '10px system-ui'; g.textBaseline = 'bottom';
        g.save(); g.beginPath(); g.rect(sx, LA.y, tToX(a.start - (a.offset || 0) + sg.to) - sx - 2, LA.h); g.clip(); g.fillText(`${sg.name || ''} ${bpmLabel(sg)} ${sg.beats_per_bar}/4`, sx + 4, LA.y + LA.h - 3); g.restore();
      }
      if (a.transition && a !== S.project.audio[0]) { g.fillStyle = '#e8b04b'; g.fillRect(x0 - 1, LA.y + 2, 2, LA.h - 4); }
    }
    // sections
    const LS = lanes[1];
    S.project.sections.forEach((s, i) => {
      const x0 = tToX(s.t0), x1 = tToX(s.t1); if (x1 < 0 || x0 > W) return;
      g.fillStyle = s.id === S.selSection ? '#e8b04b' : (i % 2 ? '#5a4a22' : '#3f3518'); g.fillRect(x0 + 1, LS.y + 2, x1 - x0 - 2, LS.h - 4);
      g.fillStyle = s.id === S.selSection ? '#1a1406' : '#f0dba8'; g.font = '10.5px system-ui'; g.textBaseline = 'middle'; g.textAlign = 'left';
      g.save(); g.beginPath(); g.rect(x0, LS.y, x1 - x0, LS.h); g.clip(); g.fillText(s.label || `section ${i + 1}`, x0 + 5, LS.y + LS.h / 2); g.restore();
    });
    // clips
    for (const tr of S.project.tracks) {
      for (const c of tr.clips) {
        const L = laneFor(c.kind, tr.group); if (!L) continue;
        const x0 = tToX(c.t0), x1 = tToX(c.t1); if (x1 < 0 || x0 > W) continue;
        const fx = S.fxByName[c.effect] || { label: c.effect };
        const sel = c.id === S.selClip || S.selClips.includes(c.id);
        const pad = c.kind === 'trans' ? 2 : 3;
        g.fillStyle = COL[c.kind] + (c.kind === 'mod' ? 'aa' : 'dd'); roundRect(g, x0 + 1, L.y + pad, Math.max(3, x1 - x0 - 2), L.h - 2 * pad, 4); g.fill();
        if (sel) { g.strokeStyle = c.id === S.selClip ? '#fff' : '#ffd166'; g.lineWidth = 1.5; roundRect(g, x0 + 1, L.y + pad, Math.max(3, x1 - x0 - 2), L.h - 2 * pad, 4); g.stroke(); }
        if (x1 - x0 > 24) {
          g.save(); g.beginPath(); g.rect(x0 + 1, L.y, x1 - x0 - 2, L.h); g.clip();
          g.fillStyle = '#fff'; g.font = (c.kind === 'trans' ? '10px' : '11px') + ' system-ui'; g.textBaseline = 'middle'; g.textAlign = 'left';
          g.fillText(fx.label + (c.kind === 'anim' && x1 - x0 > 160 ? `  ·  ${paletteName(c.palette)}` : ''), x0 + 6, L.y + L.h / 2 - (c.kind === 'anim' && x1 - x0 > 90 ? 0 : 0));
          g.restore();
        }
        if (c.kind === 'anim' && fx.lamp) { g.fillStyle = '#ffb347'; g.fillRect(x0 + 1, L.y + L.h - pad - 3, Math.max(3, x1 - x0 - 2), 2); }
      }
    }
    g.restore();
    if (drag && drag.kind === 'marquee' && drag.moved) { const x0 = Math.min(drag.x, drag.x2), y0 = Math.min(drag.y, drag.y2); g.fillStyle = 'rgba(255,209,102,0.15)'; g.strokeStyle = '#ffd166'; g.lineWidth = 1; g.fillRect(x0, y0, Math.abs(drag.x2 - drag.x), Math.abs(drag.y2 - drag.y)); g.strokeRect(x0 + 0.5, y0 + 0.5, Math.abs(drag.x2 - drag.x), Math.abs(drag.y2 - drag.y)); }
    // playhead
    const px = tToX(S.time); g.fillStyle = '#ff5f5f'; g.fillRect(px - 0.5, 0, 1.5, Math.max(lanes.total, Hh)); g.beginPath(); g.moveTo(px - 6, 0); g.lineTo(px + 6, 0); g.lineTo(px, 8); g.fill();
    lastDraw = performance.now();
  }
  function roundRect(g, x, y, w, h, r) { r = Math.min(r, w / 2, h / 2); g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }
  function drawPlayhead() {
    if (S.mode !== 'timeline') return;
    const r = scroll.getBoundingClientRect(); const x = tToX(S.time);
    if (S.playing && (x > r.width * 0.9 || x < 0)) scrollX = Math.max(0, S.time - r.width * 0.15 / pps);
    if (performance.now() - lastDraw > 33) draw();
  }
  function paletteName(ref) { if (!ref) return ''; if (typeof ref === 'object') return ref.name || 'custom'; return (S.st.default_palettes[ref] || S.project.palettes[ref] || { name: ref }).name; }

  // ------------------------------------------------------------ hit tests
  function clipAt(x, y) {
    const L = laneAt(y); if (!L || !L.group) return null;
    const tr = App.trackFor(L.group); const t = xToT(x);
    const cs = tr.clips.filter(c => c.kind === L.kind && c.t0 <= t && t <= c.t1);
    if (!cs.length) return null;
    const c = cs[cs.length - 1];
    const x0 = tToX(c.t0), x1 = tToX(c.t1);
    const edge = x - x0 < 6 ? 'l' : x1 - x < 6 ? 'r' : null;
    return { clip: c, track: tr, edge: (x1 - x0 > 16) ? edge : null };
  }
  function selectedIds() { const ids = [...S.selClips]; if (S.selClip && !ids.includes(S.selClip)) ids.push(S.selClip); return ids.filter(i => findClip(i)[1]); }
  function clipsInRect(x0, y0, x1, y1) {
    const ta = xToT(Math.min(x0, x1)), tb = xToT(Math.max(x0, x1)); const ya = Math.min(y0, y1) + vs, yb = Math.max(y0, y1) + vs;
    const out = [];
    for (const L of lanes) { if (!L.group || L.y + L.h < ya || L.y > yb) continue; const tr = App.trackFor(L.group); for (const c of tr.clips) if (c.kind === L.kind && c.t1 > ta && c.t0 < tb) out.push(c.id); }
    return out;
  }
  function selectAll() {
    const gid = S.previewGroups ? S.previewGroups[0] : null;
    S.selClips = S.project.tracks.filter(tr => !gid || tr.group === gid).flatMap(tr => tr.clips.map(c => c.id));
    S.selClip = S.selClips[S.selClips.length - 1] || null; S.selAudio = null; S.selSection = null; inspector(); draw();
    App.status(`${S.selClips.length} clips selected`);
  }
  function onDown(e) {
    const r = cv.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top;
    if (y < H.ruler) { drag = { kind: 'seek' }; App.Preview.seek(xToT(x)); return; }
    const L = laneAt(y);
    if (e.shiftKey && !(L && clipAt(x, y)) && !(L && (L.kind === 'audio' || L.kind === 'sections'))) {   // shift-drag anywhere below the ruler: marquee select
      S.selAudio = null; S.selSection = null; drag = { kind: 'marquee', x, y, x2: x, y2: y, moved: false, base: selectedIds() }; return;
    }
    if (!L) return;
    if (L.kind === 'audio') { const t = xToT(x); const a = S.project.audio.find(a => a.start <= t && t < a.start + (a.duration || 0)); S.selAudio = a ? a.id : null; S.selClip = null; S.selClips = []; S.selSection = null; inspector(); draw(); return; }
    if (L.kind === 'sections') {
      const t = xToT(x); const secs = S.project.sections;
      // boundary drag?
      for (let i = 1; i < secs.length; i++) if (Math.abs(tToX(secs[i].t0) - x) < 5) { App.commit(); drag = { kind: 'secEdge', i }; return; }
      const s = secs.find(s => s.t0 <= t && t < s.t1); S.selSection = s ? s.id : null; S.selClip = null; S.selClips = []; S.selAudio = null; inspector(); draw(); return;
    }
    const h = clipAt(x, y);
    if (h) {
      S.selAudio = null; S.selSection = null;
      if (e.shiftKey || e.metaKey || e.ctrlKey) {                    // shift-click: add / remove from the selection
        const ids = selectedIds();
        if (ids.includes(h.clip.id)) { const rest = ids.filter(i => i !== h.clip.id); S.selClips = rest; S.selClip = rest[rest.length - 1] || null; }
        else { S.selClips = [...ids, h.clip.id]; S.selClip = h.clip.id; }
        inspector(); draw(); return;
      }
      if (!selectedIds().includes(h.clip.id)) { S.selClips = []; }   // plain click on an unselected clip: select just it
      S.selClip = h.clip.id; inspector(); draw();
      App.commit();
      // a move drags EVERY selected clip along; a trim only the one under the mouse
      const others = h.edge ? [] : selectedIds().filter(i => i !== h.clip.id).map(i => { const [t, c] = findClip(i); return c ? { track: t, clip: c, t0: c.t0, t1: c.t1 } : null; }).filter(Boolean);
      drag = { kind: h.edge ? 'trim' : 'move', edge: h.edge, clip: h.clip, track: h.track, x, t0: h.clip.t0, t1: h.clip.t1, moved: false, alt: e.altKey, others };
      return;
    }
    S.selAudio = null; S.selSection = null;
    S.selClip = null; S.selClips = []; inspector(); draw();
    drag = { kind: 'scrub', x, sx: scrollX };
  }
  function onMove(e) {
    const r = cv.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top;
    if (!drag) {
      if (S.mode !== 'timeline') return;
      const h = clipAt(x, y); cv.style.cursor = y < H.ruler ? 'text' : h ? (h.edge ? 'col-resize' : 'grab') : 'default'; return;
    }
    if (drag.kind === 'seek') { App.Preview.seek(Math.max(0, xToT(x))); return; }
    if (drag.kind === 'scrub') { scrollX = Math.max(0, drag.sx - (x - drag.x) / pps); draw(); return; }
    if (drag.kind === 'secEdge') { const secs = S.project.sections; const t = snap(xToT(x)); const s = secs[drag.i], p = secs[drag.i - 1]; if (t > p.t0 + 0.2 && t < s.t1 - 0.2) { s.t0 = t; p.t1 = t; } draw(); return; }
    if (drag.kind === 'marquee') { drag.x2 = x; drag.y2 = y; drag.moved = Math.abs(x - drag.x) > 3 || Math.abs(y - drag.y) > 3; if (drag.moved) { S.selClips = [...new Set([...drag.base, ...clipsInRect(drag.x, drag.y, x, y)])]; S.selClip = S.selClips[S.selClips.length - 1] || null; } draw(); return; }
    const c = drag.clip; const dt = (x - drag.x) / pps;
    if (!drag.moved && Math.abs(x - drag.x) < 3) return;
    if (!drag.moved && drag.alt && drag.kind === 'move') {   // alt-drag duplicates (the whole selection)
      const copy = JSON.parse(JSON.stringify(c)); copy.id = uid('c'); drag.track.clips.push(copy); drag.clip = copy; S.selClip = copy.id;
      drag.others = drag.others.map(o => { const cp = JSON.parse(JSON.stringify(o.clip)); cp.id = uid('c'); o.track.clips.push(cp); return { ...o, clip: cp }; });
      S.selClips = [copy.id, ...drag.others.map(o => o.clip.id)];
    }
    drag.moved = true;
    const cc = drag.clip;
    if (drag.kind === 'move') {
      const len = drag.t1 - drag.t0; const minT0 = Math.min(drag.t0, ...drag.others.map(o => o.t0));
      let t0 = snap(Math.max(drag.t0 - minT0, drag.t0 + dt), cc); const shift = t0 - drag.t0;      // the group never moves before 0
      cc.t0 = t0; cc.t1 = t0 + len;
      for (const o of drag.others) { o.clip.t0 = o.t0 + shift; o.clip.t1 = o.t1 + shift; }
    }
    else if (drag.edge === 'l') { cc.t0 = clamp(snap(drag.t0 + dt, cc), 0, cc.t1 - 0.1); }
    else { cc.t1 = Math.max(cc.t0 + 0.1, snap(drag.t1 + dt, cc)); }
    draw(); inspectorTimes();
  }
  function onUp() {
    if (!drag) return;
    if (drag.kind === 'marquee') { drag = null; inspector(); draw(); return; }
    if ((drag.kind === 'move' || drag.kind === 'trim') && drag.moved) {
      if (drag.clip.kind === 'anim') resolveOverlaps(drag.track, drag.clip, selectedIds());
      for (const o of drag.others) if (o.clip.kind === 'anim') resolveOverlaps(o.track, o.clip, selectedIds());
      App.saveProject(); draw(); inspector();
    }
    else if ((drag.kind === 'move' || drag.kind === 'trim') && !drag.moved) { S.undo.pop(); }
    else if (drag.kind === 'secEdge') { App.saveProject(); }
    drag = null;
  }
  function onWheel(e) {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) { const r = cv.getBoundingClientRect(); const x = e.clientX - r.left; const t = xToT(x); pps = clamp(pps * Math.exp(-e.deltaY * 0.01), 2, 400); scrollX = Math.max(0, t - x / pps); $('#zoom').value = pps; }
    else { scrollX = Math.max(0, scrollX + (e.deltaX + (e.shiftKey ? e.deltaY : 0)) / pps); if (!e.shiftKey && Math.abs(e.deltaY) > Math.abs(e.deltaX)) setVS(vs + e.deltaY); }
    draw();
  }
  function onDbl(e) {
    const r = cv.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top; const L = laneAt(y);
    if (L && L.kind === 'sections') { const t = xToT(x); const s = S.project.sections.find(s => s.t0 <= t && t < s.t1); if (s) { const v = prompt('Section label', s.label || ''); if (v !== null) { App.commit(); s.label = v; App.saveProject(); draw(); } } }
    if (L && L.kind === 'anim') { const h = clipAt(x, y); if (!h) { const t = snap(xToT(x)); addClip(L, 'starfield', t); } }
  }
  function onDrop(e) {
    e.preventDefault(); const name = e.dataTransfer.getData('text/fx'); const fx = S.fxByName[name]; if (!fx) return;
    const r = cv.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top;
    let L = laneAt(y);
    if (!L || !L.group) { App.status('drop onto a group lane', 'warn'); return; }
    if (L.kind !== fx.kind) L = laneFor(fx.kind, L.group);       // be forgiving: land on the right lane of that group
    addClip(L, name, snap(xToT(x)));
  }
  function addClip(L, name, t0) {
    const fx = S.fxByName[name]; const tr = App.trackFor(L.group); const bar = barLenAt(t0);
    let t1;
    if (fx.kind === 'anim') { const next = tr.clips.filter(c => c.kind === 'anim' && c.t0 > t0 + 0.05).sort((a, b) => a.t0 - b.t0)[0]; t1 = next ? Math.min(next.t0, t0 + bar * 8) : t0 + bar * 8; const sec = S.project.sections.find(s => s.t0 <= t0 + 0.01 && t0 < s.t1); if (sec && sec.t1 > t0 + 0.5 && (!next || sec.t1 <= next.t0 + 0.01)) t1 = sec.t1; }
    else if (fx.kind === 'trans') { t0 = t0 - bar / 8; t1 = t0 + bar / 4; }
    else t1 = t0 + bar * 4;
    App.commit();
    const c = { id: uid('c'), kind: fx.kind, effect: name, t0: Math.max(0, t0), t1, params: {}, palette: (S.layout.groups[L.group] || {}).palette in S.st.default_palettes ? S.layout.groups[L.group].palette : 'classic' };
    tr.clips.push(c);
    if (fx.kind === 'anim') resolveOverlaps(tr, c);
    S.selClip = c.id; S.selClips = []; S.selAudio = null; S.selSection = null;
    App.saveProject(); draw(); inspector();
  }
  function resolveOverlaps(tr, c, protect = []) {
    const keep = [];
    for (const o of tr.clips) {
      if (o === c || o.kind !== 'anim' || o.t1 <= c.t0 || o.t0 >= c.t1 || (protect.includes(o.id) && protect.includes(c.id))) { keep.push(o); continue; }
      if (o.t0 < c.t0 && o.t1 > c.t1) { const right = JSON.parse(JSON.stringify(o)); right.id = uid('c'); right.t0 = c.t1; o.t1 = c.t0; keep.push(o, right); continue; }
      if (o.t0 < c.t0) o.t1 = c.t0; else if (o.t1 > c.t1) o.t0 = c.t1; else continue;
      if (o.t1 - o.t0 > 0.05) keep.push(o);
    }
    tr.clips = keep;
  }
  let clipboard = null;
  function clipUnderPlayhead(kind) {
    const gid = S.previewGroups ? S.previewGroups[0] : null;
    for (const tr of S.project.tracks) { if (gid && tr.group !== gid) continue; const c = tr.clips.find(c => c.kind === kind && c.t0 < S.time && S.time < c.t1); if (c) return [tr, c]; }
    return [null, null];
  }
  function splitAtPlayhead() {
    // split every selected clip the playhead is inside; with nothing selected, the animation under the playhead
    let targets = selectedIds().map(findClip).filter(([tr, c]) => c && c.t0 + 0.05 < S.time && S.time < c.t1 - 0.05);
    if (!targets.length) { const [tr, c] = clipUnderPlayhead('anim'); if (c && c.t0 + 0.05 < S.time && S.time < c.t1 - 0.05) targets = [[tr, c]]; }
    if (!targets.length) return App.status('put the playhead inside a clip to split it (S or ⌘T)', 'warn');
    App.commit();
    const newIds = [];
    for (const [tr, c] of targets) { const right = JSON.parse(JSON.stringify(c)); right.id = uid('c'); right.t0 = S.time; c.t1 = S.time; tr.clips.push(right); newIds.push(right.id); }
    S.selClips = newIds; S.selClip = newIds[newIds.length - 1]; App.saveProject(); draw(); inspector(); App.status(targets.length > 1 ? `split ${targets.length} clips` : 'split');
  }
  function copySelection() {
    const items = selectedIds().map(findClip).filter(([tr, c]) => c).map(([tr, c]) => ({ group: tr.group, clip: JSON.parse(JSON.stringify(c)) }));
    if (!items.length) return App.status('select a clip to copy', 'warn');
    const t0 = Math.min(...items.map(i => i.clip.t0));
    clipboard = { t0, items };
    App.status(items.length === 1 ? `copied ${(S.fxByName[items[0].clip.effect] || {}).label || items[0].clip.effect}` : `copied ${items.length} clips`);
  }
  function pasteSelection() {
    if (!clipboard) return App.status('nothing copied', 'warn');
    // one group's clips paste onto the previewed group (if one is chosen); a multi-group selection keeps its groups
    const groups = new Set(clipboard.items.map(i => i.group));
    const target = (groups.size === 1 && S.previewGroups) ? S.previewGroups[0] : null;
    const shift = snap(S.time) - clipboard.t0;
    App.commit();
    const ids = [];
    for (const it of clipboard.items) {
      const tr = App.trackFor(target || it.group); const c = JSON.parse(JSON.stringify(it.clip));
      c.id = uid('c'); c.t0 = Math.max(0, it.clip.t0 + shift); c.t1 = c.t0 + (it.clip.t1 - it.clip.t0);
      tr.clips.push(c); ids.push(c.id);
    }
    for (const id of ids) { const [tr, c] = findClip(id); if (c && c.kind === 'anim') resolveOverlaps(tr, c, ids); }
    S.selClips = ids; S.selClip = ids[ids.length - 1]; App.saveProject(); draw(); inspector();
    App.status(ids.length === 1 ? `pasted at ${fmtT(S.time)} on ${(S.layout.groups[target || clipboard.items[0].group] || {}).label || ''}` : `pasted ${ids.length} clips at ${fmtT(S.time)}`);
  }
  const copyClip = copySelection, pasteClip = pasteSelection;
  function deleteSelection() {
    const ids = selectedIds(); if (!ids.length) return false;
    App.commit(); for (const tr of S.project.tracks) tr.clips = tr.clips.filter(c => !ids.includes(c.id));
    S.selClip = null; S.selClips = []; App.saveProject(); draw(); inspector(); App.status(ids.length > 1 ? `deleted ${ids.length} clips` : 'deleted'); return true;
  }
  function duplicateSelection() {
    const items = selectedIds().map(findClip).filter(([tr, c]) => c); if (!items.length) return;
    const span = Math.max(...items.map(([, c]) => c.t1)) - Math.min(...items.map(([, c]) => c.t0));   // the block repeats right after itself
    App.commit(); const ids = [];
    for (const [tr, c] of items) { const copy = JSON.parse(JSON.stringify(c)); copy.id = uid('c'); copy.t0 = c.t0 + span; copy.t1 = c.t1 + span; tr.clips.push(copy); ids.push(copy.id); }
    for (const id of ids) { const [tr, c] = findClip(id); if (c && c.kind === 'anim') resolveOverlaps(tr, c, ids); }
    S.selClips = ids; S.selClip = ids[ids.length - 1]; App.saveProject(); draw(); inspector();
  }
  function onKey(e) {
    const cmd = e.metaKey || e.ctrlKey;
    if (e.key === '/' && !cmd) { e.preventDefault(); FxBrowser.focusSearch(); return; }
    if (cmd && e.key.toLowerCase() === 'c') { e.preventDefault(); copySelection(); return; }
    if (cmd && e.key.toLowerCase() === 'v') { e.preventDefault(); pasteSelection(); return; }
    if (cmd && e.key.toLowerCase() === 'a') { e.preventDefault(); selectAll(); return; }
    // ⌘T is a browser shortcut (new tab) that pages are not allowed to intercept in Chrome / Safari, so S also splits
    if ((cmd && e.key.toLowerCase() === 't') || (!cmd && e.key.toLowerCase() === 's')) { e.preventDefault(); splitAtPlayhead(); return; }
    if (e.key === 'Escape') { S.selClip = null; S.selClips = []; inspector(); draw(); return; }
    if ((e.key === 'Delete' || e.key === 'Backspace')) {
      if (deleteSelection()) return;
      if (S.selSection) { App.commit(); const i = S.project.sections.findIndex(s => s.id === S.selSection); if (i > 0) { S.project.sections[i - 1].t1 = S.project.sections[i].t1; S.project.sections.splice(i, 1); } else if (i === 0 && S.project.sections.length > 1) { S.project.sections[1].t0 = S.project.sections[0].t0; S.project.sections.splice(0, 1); } S.selSection = null; App.saveProject(); draw(); inspector(); }
      return;
    }
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { const { beats, bars } = beatGrid(); const grid = e.shiftKey ? bars : beats; const dir = e.key === 'ArrowRight' ? 1 : -1; const next = dir > 0 ? grid.find(b => b > S.time + 0.01) : [...grid].reverse().find(b => b < S.time - 0.01); if (next !== undefined) App.Preview.seek(next); }
    if (e.key.toLowerCase() === 'd' && cmd) { e.preventDefault(); duplicateSelection(); }
  }
  function findClip(id) { for (const tr of S.project.tracks) for (const c of tr.clips) if (c.id === id) return [tr, c]; return [null, null]; }
  function focusGroup(gid) { selectGroup(gid); }

  // ------------------------------------------------------------- fx browser
  // live previews: the server renders each effect once on a fixed 4-prop rig; we loop it in a small canvas
  const FxPreview = (() => {
    const cv = $('#fxPreview'); let rig = null, cache = {}, cur = null, frame = 0, timer = null, pinned = null;
    async function getRig() { if (!rig) { rig = await api.get('/api/fx/rig'); rig.n = rig.props.reduce((a, p) => a + p.n, 0); let x0 = 1e9, x1 = -1e9, z0 = 1e9, z1 = -1e9; for (const p of rig.props) for (let i = 0; i < p.n; i++) { x0 = Math.min(x0, p.x[i]); x1 = Math.max(x1, p.x[i]); z0 = Math.min(z0, p.z[i]); z1 = Math.max(z1, p.z[i]); } rig.b = { x0, x1, z0, z1 }; } return rig; }
    async function load(name) {
      if (cache[name]) return cache[name];
      const r = await fetch(`/api/fx/preview/${encodeURIComponent(name)}`); if (!r.ok) return null;
      const buf = await r.arrayBuffer(); const dv = new DataView(buf); const nf = dv.getUint32(0, true), per = dv.getUint32(4, true);
      const frames = []; for (let k = 0; k < nf; k++) frames.push(new Uint8Array(buf, 8 + k * per, per));
      return (cache[name] = frames);
    }
    async function show(name, pin) {
      if (pin) pinned = name; else if (pinned && name !== pinned) return;
      cur = name; $('#fxPreviewName').textContent = (S.fxByName[name] || {}).label || name;
      await getRig(); const frames = await load(name); if (!frames || cur !== name) return;
      clearInterval(timer); frame = 0;
      timer = setInterval(() => { draw(frames[frame % frames.length]); frame++; }, 1000 / 12);
    }
    function unhover() { if (pinned) show(pinned, true); }
    function draw(fr) {
      const r = cv.getBoundingClientRect(); if (!r.width) return;
      if (cv.width !== r.width * devicePixelRatio) { cv.width = r.width * devicePixelRatio; cv.height = r.height * devicePixelRatio; }
      const g = cv.getContext('2d'); g.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
      g.fillStyle = '#07080c'; g.fillRect(0, 0, r.width, r.height);
      const b = rig.b; const s = Math.min((r.width - 12) / (b.x1 - b.x0), (r.height - 12) / (b.z1 - b.z0));
      const ox = r.width / 2 - (b.x0 + b.x1) / 2 * s, oy = r.height / 2 + (b.z0 + b.z1) / 2 * s; const d = Math.max(1, s * 1.1);
      let off = 0; g.globalCompositeOperation = 'lighter';
      for (const p of rig.props) for (let i = 0; i < p.n; i++, off += 3) {
        const R = fr[off], G = fr[off + 1], B = fr[off + 2];
        g.fillStyle = R + G + B < 12 ? '#1c2230' : `rgb(${R},${G},${B})`;
        g.fillRect(ox + p.x[i] * s - d / 2, oy - p.z[i] * s - d / 2, d, d);
      }
      g.globalCompositeOperation = 'source-over';
    }
    return { show, unhover };
  })();
  // Effects browser: search + kind/tag filters + collapsible packs + favourites.
  // Filter state and which packs are folded live in localStorage so the panel
  // comes back the way you left it.
  const FxBrowser = (() => {
    const PACK_ORDER = ['Favourites', 'Transitions', 'Static', 'Incandescent', 'Classic LED', 'Christmas classics',
      'Song themes', 'Choreography', 'Music driven', 'Ice & Snow', 'Fire', 'Ibiza', 'Techno', 'Lava lamp', 'Starfield', 'Modifiers'];
    const TAG_LABEL = { music: '♪', slow: 'slow', regions: 'painted', incandescent: 'bulbs', geometry: 'multi-prop' };
    let q = '', kinds = { anim: true, trans: true, mod: true }, tags = {}, closed = {}, favs = {}, shown = false;
    const save = () => { try { localStorage.setItem('fxBrowser', JSON.stringify({ kinds, tags, closed, favs })); } catch (_) { } };
    function load() {
      try {
        const d = JSON.parse(localStorage.getItem('fxBrowser') || '{}');
        kinds = { anim: true, trans: true, mod: true, ...(d.kinds || {}) }; tags = d.tags || {}; closed = d.closed || {}; favs = d.favs || {};
      } catch (_) { }
    }
    function init() {
      load();
      const sb = $('#fxSearch');
      sb.value = '';
      sb.oninput = () => { q = sb.value.trim().toLowerCase(); render(); };
      sb.onkeydown = e => {
        if (e.key === 'Escape') { sb.value = ''; q = ''; render(); sb.blur(); }
        if (e.key === 'Enter') { const first = $('.fx'); if (first) first.click(); }
        e.stopPropagation();                                         // the timeline's own shortcuts must not fire while typing
      };
      $$('#fxKinds .chip2').forEach(b => { b.classList.toggle('on', !!kinds[b.dataset.kind]); b.onclick = () => { kinds[b.dataset.kind] = !kinds[b.dataset.kind]; b.classList.toggle('on', kinds[b.dataset.kind]); save(); render(); }; });
      $$('#fxTags .chip2').forEach(b => { b.classList.toggle('on', !!tags[b.dataset.tag]); b.onclick = () => { tags[b.dataset.tag] = !tags[b.dataset.tag]; b.classList.toggle('on', tags[b.dataset.tag]); save(); render(); }; });
      render();
      if (!shown) { shown = true; const first = S.effects.find(f => favs[f.name]) || S.effects.find(f => f.kind === 'anim'); if (first) FxPreview.show(first.name, false); }
    }
    function matches(fx) {
      if (!kinds[fx.kind]) return false;
      const want = Object.keys(tags).filter(k => tags[k]);
      for (const w of want) {
        if (w === 'fav') { if (!favs[fx.name]) return false; }
        else if (!(fx.tags || []).includes(w)) return false;
      }
      if (!q) return true;
      return (fx.label + ' ' + fx.name + ' ' + (fx.pack || '') + ' ' + (fx.tags || []).join(' ') + ' ' + fx.doc).toLowerCase().includes(q);
    }
    function mark(text) {                                            // highlight the search term in the label
      if (!q) return [text];
      const i = text.toLowerCase().indexOf(q);
      if (i < 0) return [text];
      return [text.slice(0, i), el('em', {}, text.slice(i, i + q.length)), text.slice(i + q.length)];
    }
    function row(fx) {
      const d = el('div', { class: 'fx ' + fx.kind, draggable: 'true', title: `${fx.doc}\n\n(${fx.pack} · ${fx.name})` },
        el('span', {}, ...mark(fx.label)));
      const t = (fx.tags || []).filter(x => TAG_LABEL[x]).map(x => TAG_LABEL[x]).slice(0, 2).join(' ');
      if (t) d.append(el('span', { class: 'tag' }, t));
      const star = el('span', { class: 'star' + (favs[fx.name] ? ' on' : ''), title: 'favourite' }, favs[fx.name] ? '★' : '☆');
      star.onclick = e => { e.stopPropagation(); favs[fx.name] = !favs[fx.name]; save(); render(); };
      d.append(star);
      d.ondragstart = e => { e.dataTransfer.setData('text/fx', fx.name); e.dataTransfer.effectAllowed = 'copy'; };
      d.onmouseenter = () => FxPreview.show(fx.name, false);
      d.onmouseleave = () => FxPreview.unhover();
      d.onclick = () => { FxPreview.show(fx.name, true); $$('.fx.on').forEach(x => x.classList.remove('on')); d.classList.add('on'); };
      return d;
    }
    function render() {
      const root = $('#fxList'); root.innerHTML = '';
      const hits = S.effects.filter(matches);
      $('#fxCount').textContent = hits.length === S.effects.length ? `(${S.effects.length})` : `(${hits.length} of ${S.effects.length})`;
      const packs = {};
      const starred = hits.filter(fx => favs[fx.name]);
      if (starred.length && !tags.fav) packs['Favourites'] = starred;
      for (const fx of hits) (packs[fx.pack || fx.kind] = packs[fx.pack || fx.kind] || []).push(fx);
      const names = [...PACK_ORDER.filter(p => packs[p]), ...Object.keys(packs).filter(p => !PACK_ORDER.includes(p)).sort()];
      if (!names.length) { root.append(el('div', { id: 'fxEmpty' }, q ? `nothing matches “${sbVal()}”` : 'no effects match these filters')); return; }
      for (const pk of names) {
        const shut = !!closed[pk] && !q;                              // a search always opens everything
        const head = el('div', { class: 'fxPack' + (shut ? ' closed' : '') }, el('span', { class: 'tw' }, '▾'), pk, el('span', { class: 'n' }, packs[pk].length));
        head.onclick = () => { closed[pk] = !closed[pk]; save(); render(); };
        root.append(head);
        if (shut) continue;
        for (const fx of packs[pk]) root.append(row(fx));
      }
    }
    function sbVal() { const e = $('#fxSearch'); return e ? e.value : ''; }
    function focusSearch() { const e = $('#fxSearch'); if (e) { e.focus(); e.select(); } }
    return { init, render, focusSearch };
  })();
  function renderFxBrowser() { FxBrowser.init(); }

  // --------------------------------------------------------------- inspector
  function inspector() {
    const root = $('#clipInspector'); root.innerHTML = '';
    if (selectedIds().length > 1) return multiInspector(root);
    if (S.selClip) return clipInspector(root);
    if (S.selAudio) return audioInspector(root);
    if (S.selSection) return sectionInspector(root);
    root.append(el('h2', {}, 'Timeline'),
      el('div', { class: 'hint' }, 'Drag an effect from the left onto a group lane. Double-click an empty animation lane for a quick Starfield. Select a clip to edit its sliders and palette; drag its edges to trim; alt-drag to duplicate; shift-click (or shift-drag a box) to select several; ⌘A selects all; ⌘C / ⌘V copy & paste at the playhead; S (or ⌘T) splits at the playhead; ⌘D repeats after; Delete; Esc clears the selection; ← → step beats (shift: bars).'),
      el('div', { class: 'hint' }, `Audio clips play one after another (no stacking). Sections are detected from the beat grid and measures — click “detect sections” after setting a BPM.`),
      el('h2', {}, 'Frame rate'), el('div', { class: 'small dim' }, `Project renders at ${S.project.fps} fps (change in Render & cards).`));
  }
  function multiInspector(root) {
    const items = selectedIds().map(findClip).filter(([tr, c]) => c);
    const groups = [...new Set(items.map(([tr]) => tr.group))];
    const t0 = Math.min(...items.map(([, c]) => c.t0)), t1 = Math.max(...items.map(([, c]) => c.t1));
    root.append(el('h2', {}, `${items.length} clips selected`),
      el('div', { class: 'small dim' }, `${fmtT(t0)} → ${fmtT(t1)} · ${groups.map(g => (S.layout.groups[g] || {}).label || g).join(', ')}`),
      el('div', { class: 'hint' }, 'Drag any of them to move the whole block (alt-drag copies it). ⌘C / ⌘V copies and pastes the block at the playhead keeping the spacing; S (or ⌘T) splits every selected clip at the playhead; ⌘D repeats the block after itself; Delete removes them all; Esc clears the selection.'),
      el('div', { class: 'row', style: 'margin-top:10px' },
        el('button', { class: 'small', onclick: copySelection }, 'copy'),
        el('button', { class: 'small', onclick: splitAtPlayhead }, 'split at playhead'),
        el('button', { class: 'small', onclick: duplicateSelection }, 'repeat after'),
        el('button', { class: 'small err', onclick: deleteSelection }, 'delete all')));
    const list = el('div', { class: 'small', style: 'margin-top:8px' });
    for (const [tr, c] of items.sort((a, b) => a[1].t0 - b[1].t0)) list.append(el('div', { class: 'row', style: 'cursor:pointer', onclick: () => { S.selClip = c.id; S.selClips = []; inspector(); draw(); } }, el('span', { class: 'sw', style: `background:${COL[c.kind]}` }), ' ', (S.fxByName[c.effect] || {}).label || c.effect, el('span', { class: 'dim mono' }, ` ${fmtT(c.t0)}–${fmtT(c.t1)}`)));
    root.append(list);
  }
  function inspectorTimes() { const t0 = $('#clipT0'), t1 = $('#clipT1'); const [, c] = findClip(S.selClip); if (t0 && c) { t0.value = fmtT(c.t0); t1.value = fmtT(c.t1); $('#clipLen').textContent = `${(c.t1 - c.t0).toFixed(2)} s · ${((c.t1 - c.t0) / barLenAt(c.t0)).toFixed(1)} bars`; } }
  function clipInspector(root) {
    const [tr, c] = findClip(S.selClip); if (!c) return;
    const fx = S.fxByName[c.effect] || { label: c.effect, params: [], doc: '' };
    const patch = (fn) => { App.commit(); fn(); App.saveProject(); draw(); S.previewDirty = true; };
    root.append(el('h2', {}, el('span', { class: 'sw', style: `background:${COL[c.kind]}` }), ' ', fx.label, el('span', { class: 'dim' }, ` · ${fx.pack || c.kind} · ${S.layout.groups[tr.group].label}`)));
    root.append(el('div', { class: 'hint' }, fx.doc));
    root.append(el('div', { class: 'row' }, el('label', {}, 'start'), el('input', { id: 'clipT0', value: fmtT(c.t0), style: 'width:70px', onchange: e => patch(() => { const v = parseT(e.target.value); if (!isNaN(v)) { c.t0 = Math.max(0, Math.min(v, c.t1 - 0.1)); if (c.kind === 'anim') resolveOverlaps(tr, c); } }) }),
      el('label', {}, 'end'), el('input', { id: 'clipT1', value: fmtT(c.t1), style: 'width:70px', onchange: e => patch(() => { const v = parseT(e.target.value); if (!isNaN(v)) { c.t1 = Math.max(c.t0 + 0.1, v); if (c.kind === 'anim') resolveOverlaps(tr, c); } }) }),
      el('span', { id: 'clipLen', class: 'dim small' }, `${(c.t1 - c.t0).toFixed(2)} s · ${((c.t1 - c.t0) / barLenAt(c.t0)).toFixed(1)} bars`)));
    if (c.kind === 'trans') {
      const anims = tr.clips.filter(x => x.kind === 'anim').sort((a, b) => a.t0 - b.t0);
      const cut = anims.find(x => c.t0 < x.t0 && x.t0 < c.t1);
      root.append(el('div', { class: 'row' }, el('label', {}, 'duration'), el('input', { type: 'number', step: 0.1, min: 0.1, value: (c.t1 - c.t0).toFixed(2), style: 'width:70px', onchange: e => patch(() => { const d = Math.max(0.1, parseFloat(e.target.value) || 1); const mid = (c.t0 + c.t1) / 2; c.t0 = Math.max(0, mid - d / 2); c.t1 = c.t0 + d; }) }), el('span', { class: 'dim small' }, 's'),
        el('button', { class: 'small', title: 'centre the transition on the nearest animation boundary', onclick: () => { const d = c.t1 - c.t0; const mid = (c.t0 + c.t1) / 2; const edges = anims.map(x => x.t0).concat(anims.map(x => x.t1)); if (!edges.length) return; const b = edges.reduce((a, x) => Math.abs(x - mid) < Math.abs(a - mid) ? x : a); patch(() => { c.t0 = Math.max(0, b - d / 2); c.t1 = c.t0 + d; }); inspector(); } }, 'centre on cut')));
      root.append(el('div', { class: 'hint' }, cut ? `Blends “${(S.fxByName[(anims.find(x => x.t1 >= cut.t0 && x.t0 < cut.t0) || {}).effect] || {}).label || 'nothing'}” → “${(S.fxByName[cut.effect] || {}).label}”. Both animations keep running through the whole transition, so there is no visible stop.` : 'No animation boundary inside this transition: it fades between whatever plays before and after its midpoint.'));
    }
    if (fx.regions) {
      const ps = App.propsIn(tr.group); const painted = ps.filter(p => Object.keys(S.paint[p.mod.replace('.mod', '')] || {}).length);
      root.append(el('div', { class: 'hint ' + (painted.length === ps.length ? '' : 'warn') }, `Uses painted regions: ${painted.length}/${ps.length} props in this group are painted` + (painted.length < ps.length ? ` (unpainted: ${ps.filter(p => !painted.includes(p)).map(p => p.label || p.id).join(', ')} → one palette colour each).` : '.')));
    }
    if (fx.lamp) root.append(el('div', { class: 'hint' }, `Lamp model: ${fx.lamp} (filament attack / afterglow, amber when dim).`));
    // palette
    if (c.kind !== 'mod' || true) {
      root.append(el('h2', {}, 'Palette'));
      root.append(paletteGrid(c.palette, ref => patch(() => c.palette = ref)));
      const schemeSel = el('select', {}, ...S.st.schemes.map(s => el('option', { value: s }, s)));
      root.append(el('div', { class: 'row' }, schemeSel,
        el('button', { class: 'small', onclick: async () => { const p = await api.get(`/api/palettes/generate?scheme=${schemeSel.value}`); const id = uid('pal'); patch(() => { S.project.palettes[id] = p; c.palette = id; }); inspector(); } }, '✨ generate'),
        el('button', { class: 'small', onclick: () => { const cur = resolvePalette(c.palette); const id = uid('pal'); patch(() => { S.project.palettes[id] = { name: 'custom ' + (Object.keys(S.project.palettes).length + 1), colors: [...cur.colors] }; c.palette = id; }); inspector(); } }, '+ custom')));
      if (S.project.palettes[c.palette]) {
        const pal = S.project.palettes[c.palette];
        const row = el('div', { class: 'row' }, el('input', { value: pal.name, style: 'width:110px', onchange: e => patch(() => pal.name = e.target.value) }));
        pal.colors.forEach((col, i) => row.append(el('input', { type: 'color', value: col, oninput: e => { pal.colors[i] = e.target.value; App.saveProject(); S.previewDirty = true; } })));
        row.append(el('button', { class: 'small', onclick: () => { patch(() => pal.colors.push('#ffffff')); inspector(); } }, '+'),
          pal.colors.length > 2 ? el('button', { class: 'small', onclick: () => { patch(() => pal.colors.pop()); inspector(); } }, '−') : null,
          el('button', { class: 'small', title: 'delete this custom palette', onclick: () => { patch(() => { delete S.project.palettes[c.palette]; c.palette = 'classic'; }); inspector(); } }, '🗑'));
        root.append(row);
      }
    }
    // params
    if (fx.params.length) root.append(el('h2', {}, 'Settings'));
    for (const s of fx.params) {
      const val = c.params[s.name] !== undefined ? c.params[s.name] : s.default;
      const set = v => { c.params[s.name] = v; App.saveProject(); S.previewDirty = true; };
      if (s.kind === 'choice') root.append(el('div', { class: 'row' }, el('label', {}, s.label), el('select', { onchange: e => { App.commit(); set(e.target.value); } }, ...s.choices.map(ch => el('option', { value: ch, selected: ch === val ? '' : null }, ch)))));
      else if (s.kind === 'prop') {
        // one of THIS group's props, by name (the value stored is the prop id)
        const ps = App.propsIn(tr.group);
        const modeSel = fx.params.find(x => x.name === 'feature');
        const mode = modeSel ? (c.params.feature !== undefined ? c.params.feature : modeSel.default) : 'specific prop';
        const sel = el('select', { onchange: e => { App.commit(); set(e.target.value); if (modeSel && e.target.value && mode !== 'specific prop') { c.params.feature = 'specific prop'; App.saveProject(); inspector(); } } },
          el('option', { value: '', selected: !val ? '' : null }, '— none —'),
          ...ps.map(pp => el('option', { value: pp.id, selected: pp.id === val ? '' : null }, `${pp.label || pp.id}${pp.controller ? ' · ' + pp.controller + ':' + pp.port : ''}`)));
        root.append(el('div', { class: 'row' }, el('label', {}, s.label), sel));
        if (val && !ps.some(pp => pp.id === val)) root.append(el('div', { class: 'hint warn' }, `Prop ${val} is not in this group any more — the centre prop is used until you pick another.`));
        else if (modeSel && mode !== 'specific prop') root.append(el('div', { class: 'hint' }, `Picking a prop here switches “${modeSel.label}” to “specific prop”.`));
      }
      else if (s.kind === 'bool') root.append(el('div', { class: 'row' }, el('label', { style: 'min-width:0' }, el('input', { type: 'checkbox', checked: val ? '' : null, onchange: e => { App.commit(); set(e.target.checked); } }), ' ', s.label)));
      else {
        const wrap = el('div', { class: 'slider' });
        const lbl = el('div', { class: 'lbl' }, el('span', {}, s.label), el('b', {}, `${val}${s.unit ? ' ' + s.unit : ''}`));
        const rng = el('input', { type: 'range', min: s.lo, max: s.hi, step: s.step, value: val });
        const num = el('input', { type: 'number', min: s.lo, max: s.hi, step: s.step, value: val });
        let committed = false;
        rng.oninput = e => { const v = s.kind === 'int' ? parseInt(e.target.value) : parseFloat(e.target.value); if (!committed) { App.commit(); committed = true; } num.value = v; lbl.lastChild.textContent = `${v}${s.unit ? ' ' + s.unit : ''}`; set(v); };
        rng.onchange = () => committed = false;
        num.onchange = e => { const v = s.kind === 'int' ? parseInt(e.target.value) : parseFloat(e.target.value); App.commit(); rng.value = v; lbl.lastChild.textContent = `${v}${s.unit ? ' ' + s.unit : ''}`; set(v); };
        wrap.append(lbl, rng, num); root.append(wrap);
      }
    }
    root.append(el('div', { class: 'row', style: 'margin-top:14px' },
      el('button', { class: 'small', onclick: () => { App.commit(); c.params = {}; App.saveProject(); S.previewDirty = true; inspector(); } }, 'reset settings'),
      el('button', { class: 'small', onclick: () => App.Preview.seek(c.t0) }, 'jump to start'),
      el('button', { class: 'small', title: '⌘C', onclick: copySelection }, 'copy'),
      el('button', { class: 'small', title: 'S or ⌘T', onclick: splitAtPlayhead }, 'split at playhead'),
      el('button', { class: 'small err', onclick: () => { App.commit(); tr.clips = tr.clips.filter(x => x !== c); S.selClip = null; App.saveProject(); draw(); inspector(); } }, 'delete')));
  }
  function resolvePalette(ref) { if (typeof ref === 'object') return ref; return S.st.default_palettes[ref] || S.project.palettes[ref] || S.st.default_palettes.classic; }
  function paletteGrid(current, onPick) {
    const grid = el('div', { class: 'palGrid' });
    const all = [...Object.entries(S.st.default_palettes), ...Object.entries(S.project.palettes)];
    for (const [id, p] of all) {
      grid.append(el('div', { class: 'pal' + (id === current ? ' on' : ''), onclick: () => { onPick(id); inspector(); } },
        el('div', { class: 'sws' }, ...p.colors.map(c => el('span', { style: `background:${c}` }))), el('div', { class: 'nm' }, p.name)));
    }
    return grid;
  }
  function audioInspector(root) {
    const a = S.project.audio.find(a => a.id === S.selAudio); if (!a) return;
    const an = S.analysis[a.id] || { songs: [] };
    if (!a.songs || !a.songs.length) a.songs = an.songs.length ? [{ name: a.name, from: 0, to: a.duration, bpm: null, beats_per_bar: an.songs[0].beats_per_bar || 4, beat_offset: null }] : [];
    const reanalyse = async () => { await App.saveProjectNow(); S.analysis[a.id] = await api.get(`/api/audio/${a.id}/analysis`); draw(); inspector(); };
    root.append(el('h2', {}, el('span', { class: 'sw', style: `background:${COL.audio}` }), ' ', a.name),
      el('div', { class: 'small dim mono' }, a.file),
      el('div', { class: 'row' }, el('label', {}, 'starts'), el('span', { class: 'mono' }, fmtT(a.start)), el('label', {}, 'length'), el('span', { class: 'mono' }, fmtT(a.duration || 0)),
        el('span', { class: 'dim small' }, an.bpm_detected ? `· detector: ${an.bpm_detected.toFixed(1)} BPM, ${an.beats_per_bar_detected}/4 over the whole file` : '')),
      el('h2', {}, 'Songs & tempo map'),
      el('div', { class: 'hint' }, 'A medley changes tempo, so each song gets its own BPM and meter. A typed BPM always wins over the detector (it locks onto subdivisions on some songs); leave it blank to use detected beats. Nudge the first beat until the grid sits on the drums when zoomed in. For a passage that speeds up or slows down, split the song at the start and end of the change and type the end tempo in the → box: the beat grid then ramps across that song, and every beat-stepped effect (sign walk, build, alternate…) follows it.'));
    const tbl = el('div');
    a.songs.forEach((sg, i) => {
      const used = an.songs[i] || {};
      const off = used.beat_offset !== undefined && used.beat_offset !== null ? (+used.beat_offset).toFixed(2) : (sg.beat_offset !== null && sg.beat_offset !== undefined ? (+sg.beat_offset).toFixed(2) : 'auto');
      tbl.append(el('div', { class: 'song' },
        el('div', { class: 'row', style: 'margin:0' },
          el('input', { value: sg.name || '', style: 'flex:1;min-width:0', placeholder: `song ${i + 1}`, onchange: e => { App.commit(); sg.name = e.target.value; App.saveProject(); draw(); } }),
          i > 0 ? el('button', { class: 'small', title: 'merge into previous song', onclick: () => { App.commit(); a.songs[i - 1].to = sg.to; a.songs.splice(i, 1); reanalyse(); } }, '⤺') : null),
        el('div', { class: 'row small', style: 'margin:3px 0 0' },
          el('span', { class: 'dim' }, 'from'), el('input', { value: fmtT(sg.from), style: 'width:58px', class: 'mono small', disabled: i === 0 ? '' : null, onchange: e => { const v = parseT(e.target.value); if (isNaN(v) || i === 0) return; App.commit(); sg.from = v; a.songs[i - 1].to = v; reanalyse(); } }),
          el('span', { class: 'dim' }, 'BPM'), el('input', { type: 'number', step: 0.1, value: sg.bpm || '', placeholder: used.bpm ? used.bpm.toFixed(1) : '', style: 'width:62px', class: 'small', onchange: e => { App.commit(); sg.bpm = parseFloat(e.target.value) || null; sg.beat_offset = null; reanalyse(); } }),
          el('span', { class: 'dim', title: 'tempo at the END of this song: leave blank for a steady tempo, type a BPM for an accelerando / ritardando that ramps linearly from the start BPM to this one' }, '→'),
          el('input', { type: 'number', step: 0.1, value: sg.bpm_end || '', placeholder: 'same', style: 'width:62px', class: 'small', title: 'end tempo (ramp)', onchange: e => { App.commit(); sg.bpm_end = parseFloat(e.target.value) || null; sg.beat_offset = null; reanalyse(); } }),
          el('select', { class: 'small', title: 'beats per bar', onchange: e => { App.commit(); sg.beats_per_bar = +e.target.value; reanalyse(); } }, ...[2, 3, 4, 6].map(k => el('option', { value: k, selected: k === (sg.beats_per_bar || 4) ? '' : null }, k + '/4'))),
          el('span', { class: 'dim', title: 'first beat (file seconds)' }, '1st'), el('span', { class: 'mono' }, off),
          el('button', { class: 'small', title: '20 ms earlier', onclick: () => { App.commit(); sg.beat_offset = firstBeat(an, i, sg) - 0.02; reanalyse(); } }, '−'),
          el('button', { class: 'small', title: '20 ms later', onclick: () => { App.commit(); sg.beat_offset = firstBeat(an, i, sg) + 0.02; reanalyse(); } }, '+'),
          off !== 'auto' ? el('button', { class: 'small', title: 'back to automatic', onclick: () => { App.commit(); sg.beat_offset = null; reanalyse(); } }, 'auto') : null)));
    });
    root.append(tbl);
    root.append(el('div', { class: 'row' },
      el('button', { class: 'small', onclick: () => { const ft = S.time - a.start + (a.offset || 0); const i = a.songs.findIndex(sg => sg.from < ft && ft < sg.to); if (i < 0) return App.status('put the playhead inside this audio clip', 'warn'); App.commit(); const sg = a.songs[i]; const n = { name: '', from: ft, to: sg.to, bpm: null, beats_per_bar: sg.beats_per_bar, beat_offset: null }; sg.to = ft; a.songs.splice(i + 1, 0, n); reanalyse(); } }, 'split song at playhead'),
      el('button', { class: 'small', onclick: () => detectSections(a) }, 'detect sections for this clip')));
    root.append(el('h2', {}, 'Into this clip'),
      el('div', { class: 'row' }, el('label', {}, 'transition'), el('select', { onchange: e => { App.commit(); a.transition = { ...(a.transition || {}), type: e.target.value }; App.saveProject(); } }, ...['cut', 'crossfade', 'fade out / in'].map(k => el('option', { value: k, selected: k === (a.transition || {}).type ? '' : null }, k))),
        el('input', { type: 'number', step: 0.1, min: 0, value: (a.transition || {}).dur || 1, style: 'width:60px', onchange: e => { App.commit(); a.transition = { ...(a.transition || {}), dur: parseFloat(e.target.value) || 0 }; App.saveProject(); } }), el('span', { class: 'dim small' }, 's')),
      el('div', { class: 'hint' }, 'Audio transitions apply when the cue track / show file is rendered; the preview plays a hard cut for now.'),
      el('div', { class: 'row', style: 'margin-top:12px' },
        el('button', { class: 'small', onclick: () => moveAudio(a, -1) }, '↑ earlier'), el('button', { class: 'small', onclick: () => moveAudio(a, 1) }, '↓ later'),
        el('button', { class: 'small err', onclick: () => { if (!confirm(`Remove ${a.name} from the timeline?`)) return; App.commit(); S.project.audio = S.project.audio.filter(x => x !== a); relayoutAudio(); S.selAudio = null; App.saveProject(); layoutTracks(); draw(); inspector(); } }, 'remove')));
  }
  function firstBeat(an, i, sg) { const used = an.songs[i]; if (sg.beat_offset !== null && sg.beat_offset !== undefined) return +sg.beat_offset; const b = an.beats.find(b => b >= sg.from); return b !== undefined ? b : sg.from; }
  function relayoutAudio() { let t = 0; for (const a of S.project.audio) { a.start = Math.round(t * 1000) / 1000; t += a.duration || 0; } }
  function moveAudio(a, dir) { const i = S.project.audio.indexOf(a); const j = i + dir; if (j < 0 || j >= S.project.audio.length) return; App.commit(); S.project.audio.splice(i, 1); S.project.audio.splice(j, 0, a); relayoutAudio(); App.saveProject(); draw(); inspector(); }
  function sectionInspector(root) {
    const s = S.project.sections.find(s => s.id === S.selSection); if (!s) return;
    const i = S.project.sections.indexOf(s);
    root.append(el('h2', {}, el('span', { class: 'sw', style: `background:${COL.sec}` }), ` Section ${i + 1}`),
      el('div', { class: 'row' }, el('label', {}, 'label'), el('input', { value: s.label || '', style: 'flex:1', onchange: e => { App.commit(); s.label = e.target.value; App.saveProject(); draw(); } })),
      el('div', { class: 'row' }, el('label', {}, 'range'), el('span', { class: 'mono' }, `${fmtT(s.t0)} – ${fmtT(s.t1)}`), el('span', { class: 'dim small' }, `${(s.t1 - s.t0).toFixed(1)} s · ${((s.t1 - s.t0) / barLenAt(s.t0)).toFixed(1)} bars`)),
      el('div', { class: 'row' }, el('button', { class: 'small', onclick: () => App.Preview.seek(s.t0) }, 'jump here'),
        el('button', { class: 'small', onclick: () => { const t = S.time; if (t <= s.t0 + 0.2 || t >= s.t1 - 0.2) return App.status('put the playhead inside the section first', 'warn'); App.commit(); const n = { id: uid('s'), t0: t, t1: s.t1, label: '' }; s.t1 = t; S.project.sections.splice(i + 1, 0, n); App.saveProject(); draw(); } }, 'split at playhead'),
        el('button', { class: 'small err', onclick: () => App.Timeline.onKey({ key: 'Delete' }) }, 'merge into previous')),
      el('h2', {}, 'Fill this section'),
      el('div', { class: 'hint' }, 'Pick a group and an animation to cover exactly this section.'),
      ...Object.entries(S.layout.groups).map(([gid, g]) => {
        const sel = el('select', {}, ...S.effects.filter(f => f.kind === 'anim').map(f => el('option', { value: f.name }, f.label)));
        return el('div', { class: 'row' }, el('span', { class: 'sw', style: `background:${g.color}` }), el('span', { style: 'min-width:90px' }, g.label || gid), sel,
          el('button', { class: 'small', onclick: () => { const L = laneFor('anim', gid); App.commit(); const tr = App.trackFor(gid); const c = { id: uid('c'), kind: 'anim', effect: sel.value, t0: s.t0, t1: s.t1, params: {}, palette: g.palette in S.st.default_palettes ? g.palette : 'classic' }; tr.clips.push(c); resolveOverlaps(tr, c); App.saveProject(); draw(); } }, 'fill'));
      }));
  }

  // ------------------------------------------------------------------ audio
  async function addAudio() {
    const files = S.st.audio_files || [];
    const choice = prompt(`Audio file to add. Type a name from assets/audio:\n${files.join('\n')}\n\nor type "upload" to pick a file from your computer.`, files[0] || 'upload');
    if (!choice) return;
    if (choice.trim().toLowerCase() === 'upload') { $('#audioFile').click(); return; }
    try { App.commit(); const a = await api.send('POST', '/api/audio/import', { path: choice.trim() }); S.project.audio.push(a); await ensureAnalysis(); layoutTracks(); draw(); App.status(`added ${a.name}`); }
    catch (e) { App.status('import failed: ' + e.message, 'err'); }
  }
  async function uploadAudio(e) {
    const f = e.target.files[0]; if (!f) return; const fd = new FormData(); fd.append('file', f);
    App.status('uploading + analysing… (a 15-minute track takes ~1 min)');
    const r = await fetch('/api/audio/upload', { method: 'POST', body: fd }); if (!r.ok) return App.status('upload failed', 'err');
    const a = await r.json(); S.project.audio.push(a); await ensureAnalysis(); layoutTracks(); draw(); e.target.value = ''; App.status(`added ${a.name}`);
  }
  async function detectSections(only) {
    App.commit();
    const keep = only ? S.project.sections.filter(s => s.audio && s.audio !== only.id) : [];
    const out = [...keep];
    for (const a of S.project.audio) {
      if (only && a !== only) continue;
      await App.saveProjectNow();
      const an = await api.get(`/api/audio/${a.id}/analysis`); S.analysis[a.id] = an;
      an.sections.forEach((s, i) => { const sg = an.songs[s.song] || {}; const first = an.sections.findIndex(x => x.song === s.song) === i; out.push({ id: uid('s'), t0: a.start - (a.offset || 0) + s.t0, t1: a.start - (a.offset || 0) + s.t1, label: first && sg.name ? `♪ ${sg.name}` : `${s.kind}`, audio: a.id }); });
    }
    out.sort((x, y) => x.t0 - y.t0);
    S.project.sections = out; App.saveProject(); draw(); App.status(`${out.length} sections`);
  }

  return { init, show, draw, drawPlayhead, layoutTracks, inspector, onKey, focusGroup, duration, ensureAnalysis, copySelection, pasteSelection, splitAtPlayhead, selectAll, selectGroup };
})();
