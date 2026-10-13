// preview.js -- live playback: master clock, audio sync, WebSocket frames, glowing point-cloud viewer.
'use strict';
App.Preview = (() => {
  const cv = $('#preview');
  let ws = null, inflight = false, lastFrame = null, lastFrameT = -1, wantSeek = false;
  let clock = { t0: 0, start: 0 };
  let audioEls = {};                       // audio clip id -> <audio>
  // orbit camera: yaw around z (0 = in front of the panels, on the -y side, looking +y), pitch (0 = level, 90 = top-down),
  // dist to the target, perspective with a mild fov. cam.s = px per inch at the target's depth (drives dot sizes).
  let cam = { yaw: 0, pitch: 8, dist: 600, tx: 0, ty: 0, tz: 40, fov: 40, ox: 0, oy: 0, F: 500, s: 1, fitted: '' }, drag = null, viewMode = 'front';
  const PRESETS = { front: { yaw: 0, pitch: 8 }, top: { yaw: 0, pitch: 89.5 }, threeq: { yaw: 35, pitch: 28 }, drive: { yaw: -30, pitch: 4 } };
  // car view: the camera rides the route (S.layout.route) at speed_mph, eye_in above the road, looking ahead;
  // dragging turns the driver's head. pos0 = where the car is at show time 0 (inches along the route).
  let car = { pos0: 0, headYaw: 0, headPitch: -2, d: 0 };
  function route() { const r = S.layout.route; return r && r.points && r.points.length > 1 ? r : null; }
  function routeLength(P) { let L = 0; for (let i = 1; i < P.length; i++) L += Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]); return L; }
  function routeAt(d) {                                   // point + heading at distance d along the route (loops)
    const P = route().points; const L = routeLength(P); d = ((d % L) + L) % L;
    for (let i = 1; i < P.length; i++) {
      const seg = Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]);
      if (d <= seg || i === P.length - 1) { const t = seg ? Math.min(1, d / seg) : 0; return { x: P[i - 1][0] + (P[i][0] - P[i - 1][0]) * t, y: P[i - 1][1] + (P[i][1] - P[i - 1][1]) * t, h: Math.atan2(P[i][1] - P[i - 1][1], P[i][0] - P[i - 1][0]) }; }
      d -= seg;
    }
    return { x: P[0][0], y: P[0][1], h: 0 };
  }
  function carSpeed() { return ((S.layout.route || {}).speed_mph || 5) * 17.6; }      // mph -> in/s
  function carDist() { return car.pos0 + carSpeed() * S.time; }
  function carTools(on) { $('#carTools').hidden = !on; if (on && route()) { const L = routeLength(route().points); $('#carPos').max = Math.round(L); $('#carPos').value = Math.round(((carDist() % L) + L) % L); $('#carMph').value = S.layout.route.speed_mph || 5; $('#carEye').value = S.layout.route.eye_in || 48; } }
  let base = null;                         // offscreen canvas with the unlit bulbs
  let scr = {};                            // prop id -> Float32Array of screen x,y pairs (rebuilt with base)
  let baseImg = null;                      // ImageData copy of base for the fast (zoomed-out) path
  let fpsMeter = { n: 0, t: performance.now(), v: 0 };

  function init() {
    $('#tPlay').onclick = togglePlay;
    $('#tHome').onclick = () => seek(0);
    $('#previewGroup').onchange = e => { S.previewGroups = e.target.value ? [e.target.value] : null; cam.fitted = ''; S.previewDirty = true; App.Timeline.layoutTracks(); App.Timeline.draw(); App.Timeline.inspector(); };
    $('#previewView').onchange = e => {
      viewMode = e.target.value;
      if (viewMode === 'car' && !route()) { App.status('draw the route first: Props & groups → 🚗 route', 'warn'); viewMode = 'drive'; e.target.value = 'drive'; }
      Object.assign(cam, PRESETS[viewMode] || {}); if (viewMode === 'drive') cam.dist *= 0.45;
      carTools(viewMode === 'car'); cam.fitted = 'keep'; base = null; drawFrame(); S.previewDirty = true;
    };
    $('#carPos').oninput = e => { car.pos0 = +e.target.value - carSpeed() * S.time; base = null; drawFrame(); S.previewDirty = true; };
    $('#carMph').onchange = e => { const d = carDist(); S.layout.route.speed_mph = +e.target.value || 5; car.pos0 = d - carSpeed() * S.time; App.saveLayout(); base = null; drawFrame(); };
    $('#carEye').onchange = e => { S.layout.route.eye_in = +e.target.value || 48; App.saveLayout(); base = null; drawFrame(); };
    $('#previewGlow').onchange = () => { S.previewDirty = true; };
    cv.addEventListener('wheel', e => { e.preventDefault(); if (viewMode === 'car') { car.pos0 += e.deltaY * 2; $('#carPos').value = Math.round(carDist()); } else cam.dist = clamp(cam.dist * Math.exp(e.deltaY * 0.0015), 20, 60000); base = null; drawFrame(); S.previewDirty = true; }, { passive: false });
    cv.addEventListener('mousedown', e => { drag = { sx: e.clientX, sy: e.clientY, yaw: cam.yaw, pitch: cam.pitch, tx: cam.tx, ty: cam.ty, tz: cam.tz, hy: car.headYaw, hp: car.headPitch, pan: e.button !== 0 || e.shiftKey }; e.preventDefault(); });
    cv.addEventListener('contextmenu', e => e.preventDefault());
    window.addEventListener('mousemove', e => {
      if (!drag) return; const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
      if (drag.pan) { const { right, up } = basis(); const k = cam.dist / cam.F; cam.tx = drag.tx - (right[0] * dx - up[0] * dy) * k; cam.ty = drag.ty - (right[1] * dx - up[1] * dy) * k; cam.tz = drag.tz - (right[2] * dx - up[2] * dy) * k; }
      else if (viewMode === 'car') { car.headYaw = clamp(drag.hy - dx * 0.3, -150, 150); car.headPitch = clamp(drag.hp - dy * 0.3, -60, 60); }
      else { cam.yaw = drag.yaw + dx * 0.4; cam.pitch = clamp(drag.pitch + dy * 0.3, -10, 89.5); }
      cam.fitted = 'keep'; base = null; drawFrame();
    });
    window.addEventListener('mouseup', () => drag = null);
    cv.addEventListener('dblclick', () => { cam.fitted = ''; base = null; drawFrame(); });
    window.addEventListener('resize', () => { cam.fitted = ''; base = null; });
    window.addEventListener('keydown', e => {
      if (S.mode !== 'timeline' || App.typing(e) || e.metaKey || e.ctrlKey) return;
      const k = e.key; let hit = true;
      if (k === '1') $('#previewView').value = 'front'; else if (k === '2') $('#previewView').value = 'top'; else if (k === '3') $('#previewView').value = 'threeq'; else if (k === '4') $('#previewView').value = 'drive'; else if (k === '5') $('#previewView').value = 'car';
      else if (k === 'f' || k === 'F') { if (viewMode === 'car') { car.headYaw = 0; car.headPitch = -2; base = null; drawFrame(); return; } cam.fitted = ''; base = null; drawFrame(); return; }
      else hit = false;
      if (hit) { e.preventDefault(); $('#previewView').onchange({ target: $('#previewView') }); }
    });
    connect();
    requestAnimationFrame(tick);
  }

  function connect() {
    ws = new WebSocket(`ws://${location.host}/ws/preview`);
    ws.binaryType = 'arraybuffer';
    ws.onopen = () => { inflight = false; S.previewDirty = true; };
    ws.onmessage = ev => {
      inflight = false;
      const dv = new DataView(ev.data); lastFrameT = dv.getFloat64(0, true);
      lastFrame = new Uint8Array(ev.data, 8);
      fpsMeter.n++; const now = performance.now(); if (now - fpsMeter.t > 1000) { fpsMeter.v = fpsMeter.n * 1000 / (now - fpsMeter.t); fpsMeter.n = 0; fpsMeter.t = now; }
      drawFrame();
    };
    ws.onclose = () => { inflight = false; setTimeout(connect, 1000); };
    ws.onerror = () => ws.close();
  }

  // ------------------------------------------------------------- transport
  function activeAudio(t) { return S.project.audio.find(a => a.duration && a.start <= t && t < a.start + a.duration); }
  function audioEl(a) {
    if (!audioEls[a.id]) { const e = new Audio(`/api/audio/${a.id}/file`); e.preload = 'auto'; audioEls[a.id] = e; }
    return audioEls[a.id];
  }
  function togglePlay() { S.playing ? pause() : play(); }
  function play() {
    S.playing = true; clock = { t0: S.time, start: performance.now() }; $('#tPlay').textContent = '⏸';
    syncAudio(true);
  }
  function pause() {
    S.playing = false; $('#tPlay').textContent = '▶';
    for (const e of Object.values(audioEls)) e.pause();
  }
  function seek(t) {
    S.time = Math.max(0, t); clock = { t0: S.time, start: performance.now() }; wantSeek = true; S.previewDirty = true;
    if (S.playing) syncAudio(true);
    App.Timeline.draw(); $('#tTime').textContent = fmtT(S.time);
  }
  function syncAudio(force) {
    const a = activeAudio(S.time);
    for (const [id, e] of Object.entries(audioEls)) if (!a || id !== a.id) { if (!e.paused) e.pause(); }
    if (!a) return;
    const e = audioEl(a); const want = S.time - a.start + (a.offset || 0);
    if (force || Math.abs(e.currentTime - want) > 0.12) { try { e.currentTime = want; } catch (_) { } }
    if (e.paused) e.play().catch(() => { });
  }
  function tick() {
    requestAnimationFrame(tick);
    if (S.playing) {
      const a = activeAudio(S.time); const e = a && audioEls[a.id];
      if (e && !e.paused && e.readyState >= 2) S.time = a.start - (a.offset || 0) + e.currentTime;   // audio is the master clock
      else S.time = clock.t0 + (performance.now() - clock.start) / 1000;
      syncAudio(false);
      if (S.time >= App.Timeline.duration()) { pause(); }
      $('#tTime').textContent = fmtT(S.time);
      App.Timeline.drawPlayhead();
    }
    // request a frame: while playing every rAF (throttled by the server), else only when dirty
    if (ws && ws.readyState === 1 && !inflight && (S.playing || S.previewDirty) && (S.mode === 'timeline')) {
      inflight = true; S.previewDirty = false;
      ws.send(JSON.stringify({ t: S.time, groups: viewMode === 'car' ? null : S.previewGroups, seek: wantSeek })); wantSeek = false;
    }
  }

  // ---------------------------------------------------------------- viewer
  function visibleProps() { return S.layout.props.filter(p => viewMode === 'car' || !S.previewGroups || S.previewGroups.includes(p.group)); }   // the car sees the whole show
  function basis() {
    let pos, f;
    if (viewMode === 'car' && route()) {
      const at = routeAt(carDist()); car.d = carDist();
      pos = [at.x, at.y, (S.layout.route.eye_in || 48)];
      const ph = at.h + car.headYaw * Math.PI / 180, pp = car.headPitch * Math.PI / 180;
      f = [Math.cos(ph) * Math.cos(pp), Math.sin(ph) * Math.cos(pp), Math.sin(pp)];
      cam.dist = 600;                                                          // nominal depth for dot sizing
    } else {
      const yaw = cam.yaw * Math.PI / 180, pitch = cam.pitch * Math.PI / 180, cp = Math.cos(pitch);
      pos = [cam.tx + cam.dist * cp * Math.sin(yaw), cam.ty - cam.dist * cp * Math.cos(yaw), cam.tz + cam.dist * Math.sin(pitch)];
      f = [cam.tx - pos[0], cam.ty - pos[1], cam.tz - pos[2]]; const fl = Math.hypot(...f); f = f.map(v => v / fl);
    }
    let right = [f[1] * 1 - f[2] * 0, f[2] * 0 - f[0] * 1, 0]; const rl = Math.hypot(...right) || 1; right = right.map(v => v / rl);   // f x up(0,0,1)
    if (rl < 1e-6) right = [Math.cos(yaw), Math.sin(yaw), 0];
    const up = [right[1] * f[2] - right[2] * f[1], right[2] * f[0] - right[0] * f[2], right[0] * f[1] - right[1] * f[0]];
    return { pos, f, right, up };
  }
  // project world inches -> screen px; returns NaN for points behind the camera
  function projector(r) {
    const { pos, f, right, up } = basis();
    cam.F = (r.height / 2) / Math.tan(cam.fov * Math.PI / 360); cam.ox = r.width / 2; cam.oy = r.height / 2; cam.s = cam.F / cam.dist;
    return (x, y, z) => {
      const vx = x - pos[0], vy = y - pos[1], vz = z - pos[2];
      const d = vx * f[0] + vy * f[1] + vz * f[2]; if (d < 1) return [NaN, NaN];
      const k = cam.F / d;
      return [cam.ox + (vx * right[0] + vy * right[1] + vz * right[2]) * k, cam.oy - (vx * up[0] + vy * up[1] + vz * up[2]) * k];
    };
  }
  function fit() {
    const r = cv.getBoundingClientRect(); let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9, z0 = 1e9, z1 = -1e9;
    for (const p of visibleProps()) { const w = S.world[p.id]; if (!w) continue; for (let i = 0; i < w.n; i += 3) { x0 = Math.min(x0, w.x[i]); x1 = Math.max(x1, w.x[i]); y0 = Math.min(y0, w.y[i]); y1 = Math.max(y1, w.y[i]); z0 = Math.min(z0, w.z[i]); z1 = Math.max(z1, w.z[i]); } }
    if (x0 > x1) { x0 = -50; x1 = 50; y0 = -10; y1 = 10; z0 = 0; z1 = 50; }
    cam.tx = (x0 + x1) / 2; cam.ty = (y0 + y1) / 2; cam.tz = (z0 + z1) / 2;
    const radius = Math.max(24, Math.hypot(x1 - x0, y1 - y0, z1 - z0) / 2);
    const aspect = Math.min(1, r.width / Math.max(1, r.height));
    cam.dist = radius / Math.tan(cam.fov * Math.PI / 360) / aspect * 1.05;
    cam.fitted = (S.previewGroups || []).join() + r.width + 'x' + r.height; base = null;
  }
  function resize() { cam.fitted = ''; base = null; if (S.mode === 'timeline') drawFrame(); }
  function buildBase(r) {
    base = document.createElement('canvas'); base.width = r.width * devicePixelRatio; base.height = r.height * devicePixelRatio;
    const g = base.getContext('2d'); g.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    g.fillStyle = '#07080c'; g.fillRect(0, 0, r.width, r.height);
    const P = projector(r); const P2 = (x, y) => P(x, y, 0);
    // ground grid at z = 0 around the target: 5 ft cells, fading out with distance
    const { pos: cpos } = basis(); const cell = 60, N = 24; const gcx = viewMode === 'car' ? cpos[0] : cam.tx, gcy = viewMode === 'car' ? cpos[1] : cam.ty; const gx0 = Math.round(gcx / cell) * cell, gy0 = Math.round(gcy / cell) * cell;
    g.lineWidth = 1;
    for (let i = -N; i <= N; i++) {
      const maj = i % 5 === 0; g.strokeStyle = maj ? 'rgba(46,58,80,.7)' : 'rgba(28,36,52,.6)';
      const a = P(gx0 + i * cell, gy0 - N * cell, 0), b = P(gx0 + i * cell, gy0 + N * cell, 0);
      if (isFinite(a[0]) && isFinite(b[0])) { g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke(); }
      const c = P(gx0 - N * cell, gy0 + i * cell, 0), d = P(gx0 + N * cell, gy0 + i * cell, 0);
      if (isFinite(c[0]) && isFinite(d[0])) { g.beginPath(); g.moveTo(c[0], c[1]); g.lineTo(d[0], d[1]); g.stroke(); }
    }
    // the route as a road ribbon on the ground (12 ft wide) with a dashed centre line
    if (route()) {
      const P = route().points; const half = 72;
      g.fillStyle = 'rgba(255,209,102,.07)'; g.strokeStyle = 'rgba(255,209,102,.55)'; g.lineWidth = 1.5; g.setLineDash([24 * cam.s, 18 * cam.s].map(v => Math.max(2, v)));
      for (let i = 1; i < P.length; i++) {
        const dx = P[i][0] - P[i - 1][0], dy = P[i][1] - P[i - 1][1], L = Math.hypot(dx, dy) || 1, nx = -dy / L * half, ny = dx / L * half;
        const q = [P2(P[i - 1][0] + nx, P[i - 1][1] + ny), P2(P[i][0] + nx, P[i][1] + ny), P2(P[i][0] - nx, P[i][1] - ny), P2(P[i - 1][0] - nx, P[i - 1][1] - ny)];
        if (q.every(v => isFinite(v[0]))) { g.beginPath(); q.forEach((v, k) => k ? g.lineTo(v[0], v[1]) : g.moveTo(v[0], v[1])); g.closePath(); g.fill(); }
        const a = P2(P[i - 1][0], P[i - 1][1]), b = P2(P[i][0], P[i][1]); if (isFinite(a[0]) && isFinite(b[0])) { g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke(); }
      }
      g.setLineDash([]);
    }
    g.fillStyle = '#1c2230'; scr = {};
    for (const p of visibleProps()) {
      const w = S.world[p.id]; if (!w) continue; const sz = Math.max(1, Math.min(3, cam.s * 0.5));
      const a = scr[p.id] = new Float32Array(w.n * 2);
      for (let i = 0; i < w.n; i++) { const [sx, sy] = P(w.x[i], w.y[i], w.z[i]); a[2 * i] = sx; a[2 * i + 1] = sy; if (isFinite(sx)) g.fillRect(sx - sz / 2, sy - sz / 2, sz, sz); }
      if (cam.s > 0.5) { const [lx, ly] = P(p.x, p.y, p.z - 6); if (isFinite(lx)) { g.fillStyle = '#3a4356'; g.font = '10px system-ui'; g.textAlign = 'center'; g.fillText(p.id, lx, ly + 10); g.fillStyle = '#1c2230'; } }
    }
  }
  function drawFrame() {
    if (S.mode !== 'timeline') return;
    const r = cv.getBoundingClientRect(); if (!r.width) return;
    const key = (S.previewGroups || []).join() + r.width + 'x' + r.height;
    if (viewMode === 'car' && route()) { if (S.playing || Math.abs(car.d - carDist()) > 0.5) base = null; if (S.playing) $('#carPos').value = Math.round(((carDist() % routeLength(route().points)) + routeLength(route().points)) % routeLength(route().points)); }
    else { if (cam.fitted !== 'keep' && cam.fitted !== key) fit(); if (cam.fitted === 'keep') cam.fitted = key; }
    if (cv.width !== r.width * devicePixelRatio || cv.height !== r.height * devicePixelRatio) { cv.width = r.width * devicePixelRatio; cv.height = r.height * devicePixelRatio; base = null; }
    if (!base) { buildBase(r); baseImg = null; }
    const g = cv.getContext('2d');
    const rad = Math.max(1.2, cam.s * 0.55), d = rad * 2, gd = rad * 5.2;
    if (lastFrame && rad <= 2.5) {                 // zoomed out: plot straight into pixels (16k bulbs at 60 fps)
      const dpr = devicePixelRatio, Wp = cv.width, Hp = cv.height;
      if (!baseImg) { const bg = base.getContext('2d'); baseImg = bg.getImageData(0, 0, Wp, Hp); }
      const img = new ImageData(new Uint8ClampedArray(baseImg.data), Wp, Hp); const px = img.data;
      const size = Math.max(1, Math.round(d * dpr)), half = size >> 1;
      let off = 0;
      for (const [pid, n] of S.order) {
        const a = scr[pid]; if (!a) { off += n * 3; continue; }
        for (let i = 0; i < n; i++, off += 3) {
          const R = lastFrame[off], G = lastFrame[off + 1], B = lastFrame[off + 2]; if (R + G + B < 12) continue;
          if (!isFinite(a[2 * i])) continue;
          const cx = Math.round(a[2 * i] * dpr) - half, cy = Math.round(a[2 * i + 1] * dpr) - half;
          for (let yy = 0; yy < size; yy++) { const y = cy + yy; if (y < 0 || y >= Hp) continue; let k = (y * Wp + cx) * 4;
            for (let xx = 0; xx < size; xx++, k += 4) { const x = cx + xx; if (x < 0 || x >= Wp) continue; px[k] = Math.max(px[k], R); px[k + 1] = Math.max(px[k + 1], G); px[k + 2] = Math.max(px[k + 2], B); px[k + 3] = 255; } }
        }
      }
      g.setTransform(1, 0, 0, 1, 0, 0); g.putImageData(img, 0, 0);
      $('#previewHud').textContent = hud(); return;
    }
    g.setTransform(1, 0, 0, 1, 0, 0); g.drawImage(base, 0, 0); g.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    if (lastFrame) {
      const glow = $('#previewGlow').checked;
      g.globalCompositeOperation = 'lighter';
      let off = 0;
      for (const [pid, n] of S.order) {
        const a = scr[pid];
        if (!a) { off += n * 3; continue; }
        // pass 1: glow (soft squares are indistinguishable from discs at this size and 10x cheaper than arcs)
        if (glow && rad > 1.6) for (let i = 0, o = off; i < n; i++, o += 3) {
          const R = lastFrame[o], G = lastFrame[o + 1], B = lastFrame[o + 2]; if (R + G + B < 30 || !isFinite(a[2 * i])) continue;
          g.fillStyle = `rgba(${R},${G},${B},0.16)`; g.fillRect(a[2 * i] - gd / 2, a[2 * i + 1] - gd / 2, gd, gd);
        }
        for (let i = 0; i < n; i++, off += 3) {
          const R = lastFrame[off], G = lastFrame[off + 1], B = lastFrame[off + 2]; if (R + G + B < 12 || !isFinite(a[2 * i])) continue;
          g.fillStyle = `rgb(${R},${G},${B})`;
          if (rad > 2.5) { g.beginPath(); g.arc(a[2 * i], a[2 * i + 1], rad, 0, 6.283); g.fill(); }
          else g.fillRect(a[2 * i] - d / 2, a[2 * i + 1] - d / 2, d, d);
        }
      }
      g.globalCompositeOperation = 'source-over';
    }
    $('#previewHud').textContent = hud();
  }
  function hud() { if (viewMode === 'car' && route()) return `${fmtT(lastFrameT)} · 🚗 ${(car.d / 12).toFixed(0)} ft along the route · ${S.layout.route.speed_mph || 5} mph · head ${Math.round(car.headYaw)}° · ${S.playing ? fpsMeter.v.toFixed(0) + ' fps · ' : ''}drag = look around · wheel / slider = move the car · F = look ahead`;
    return `${fmtT(lastFrameT)} · ${S.previewGroups ? (S.layout.groups[S.previewGroups[0]] || {}).label : 'all groups'} · yaw ${Math.round(cam.yaw)}° pitch ${Math.round(cam.pitch)}° · ${S.playing ? fpsMeter.v.toFixed(0) + ' fps · ' : ''}drag = orbit · shift/right-drag = pan · wheel = dolly · 1 front 2 top 3 ¾ 4 drive-by · F / double-click = fit`; }

  return { init, togglePlay, play, pause, seek, resize, drawFrame };
})();
