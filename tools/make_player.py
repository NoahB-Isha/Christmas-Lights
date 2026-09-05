#!/usr/bin/env python3
"""
make_player.py -- standalone HTML that plays the show against the music.

    python make_player.py OUT.html SHOW.rgb SONG.mp3

The rendered frames are embedded (base64) so the page works with no server.
The AUDIO is not embedded -- the page loads your own local copy, either from
a file sitting next to it or via the file picker. That keeps the HTML small
and means the page is just a viewer for files you already have.

The offset slider is the point of this tool. Alignment is manual on this
hardware, and hand-starting lands within ~150 ms at best. Scrub the offset
until the hits land, read the number off, and bake it into show47.py.
"""

import sys, os, os, base64, json
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from lightshow.formats.rgbfile import Show
from lightshow.formats.props import load_mod, UNITS_PER_INCH
from lightshow import music

FPS = 60
MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "props", "47号.mod")
PROP_CH = 3


def build(rgb_path, song_path, out_path, lead_frames=None):
    show = Show.load(rgb_path)
    prop = load_mod(MOD)
    N = len(prop)
    base = sum(show.channels[:PROP_CH]) * 3

    # pull just the prop's pixels out of each frame
    buf = bytearray()
    for fr in show.frames:
        buf += fr[base:base + N * 3]
    frames_b64 = base64.b64encode(bytes(buf)).decode()

    a = music.analyse(song_path, fps=FPS, beats_per_bar=6)
    if lead_frames is None:
        lead_frames = len(show.frames) - a.n_frames

    def ds(x, step=6):          # thin the feature curves for the timeline
        return [round(float(v), 3) for v in x[::step]]

    data = {
        "n": N,
        "nframes": len(show.frames),
        "lead": int(lead_frames),
        "fps": FPS,
        "duration": a.duration,
        "bpm": round(a.bpm, 1),
        "beatsPerBar": a.beats_per_bar,
        "xy": [[round(x, 1), round(y, 1)] for x, y in prop.xy],
        "unitsPerInch": UNITS_PER_INCH,
        "bulb": 10.0,
        "sections": [{"start": round(s["start"], 2), "end": round(s["end"], 2),
                      "intensity": round(s.get("intensity", 0), 2)}
                     for s in a.sections],
        "featStep": 6,
        "rms": ds(a.rms), "low": ds(a.low), "high": ds(a.high),
        "hit": ds(a.hit), "centroid": ds(a.centroid),
        "downbeats": [round(float(t), 3) for t in a.downbeats],
        "song": os.path.basename(song_path),
    }

    html = TEMPLATE.replace("__DATA__", json.dumps(data)) \
                   .replace("__FRAMES__", frames_b64)
    open(out_path, "w", encoding="utf-8").write(html)
    return out_path, len(show.frames), N


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Snowflake — show preview</title>
<style>
  :root{ --void:#070B14; --panel:#0E1524; --line:#1E2A42;
         --text:#C6D6EA; --dim:#63758F; --ice:#7FD8F0; }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:var(--void);color:var(--text);
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
    font-variant-numeric:tabular-nums;overflow:hidden}
  #app{display:flex;flex-direction:column;height:100%}
  header{padding:12px 18px 10px;border-bottom:1px solid var(--line);
    display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}
  h1{font-size:15px;font-weight:600;margin:0;letter-spacing:-.01em}
  header .m{color:var(--dim);font-size:12.5px}
  main{flex:1;display:grid;grid-template-columns:1fr 250px;min-height:0}
  #stage{position:relative;min-width:0}
  canvas#cv{width:100%;height:100%;display:block}
  aside{border-left:1px solid var(--line);background:var(--panel);
    padding:14px;overflow-y:auto;font-size:12.5px}
  aside h2{font-size:12px;font-weight:600;color:var(--dim);margin:0 0 8px}
  .meter{margin-bottom:9px}
  .meter .lab{display:flex;justify-content:space-between;color:var(--dim);
    margin-bottom:3px}
  .bar{height:6px;background:#162034;border-radius:3px;overflow:hidden}
  .bar i{display:block;height:100%;width:0;border-radius:3px}
  #secnow{margin:14px 0 4px;padding:9px 10px;background:#162034;border-radius:6px}
  #secnow b{font-size:14px}
  footer{border-top:1px solid var(--line);background:var(--panel);padding:10px 16px}
  #tl{width:100%;height:74px;display:block;cursor:pointer}
  .row{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-top:8px}
  button{background:#182236;color:var(--text);border:1px solid var(--line);
    border-radius:6px;padding:8px 15px;font:inherit;font-size:13px;cursor:pointer}
  button:hover{border-color:var(--ice)}
  button:focus-visible,input:focus-visible{outline:2px solid var(--ice);outline-offset:2px}
  #play{color:var(--ice);min-width:82px}
  label{display:flex;align-items:center;gap:7px;color:var(--dim);font-size:12.5px}
  input[type=range]{accent-color:var(--ice)}
  #off{width:190px}
  #clock{margin-left:auto;color:var(--dim)}
  #clock b{color:var(--text)}
  #load{padding:26px;text-align:center;color:var(--dim);line-height:1.7}
  #load b{color:var(--text)}
  #load input{margin-top:10px}
  .warn{color:#F0C674}
</style></head><body>
<div id="app">
  <header>
    <h1>Snowflake · Carol of the Bells</h1>
    <span class="m" id="hmeta"></span>
  </header>
  <main>
    <div id="stage"><canvas id="cv"></canvas></div>
    <aside>
      <h2>What's driving it</h2>
      <div class="meter"><div class="lab"><span>bass</span><span id="v0"></span></div>
        <div class="bar"><i id="m0" style="background:#4E7BE8"></i></div></div>
      <div class="meter"><div class="lab"><span>loudness</span><span id="v1"></span></div>
        <div class="bar"><i id="m1" style="background:#7FD8F0"></i></div></div>
      <div class="meter"><div class="lab"><span>highs</span><span id="v2"></span></div>
        <div class="bar"><i id="m2" style="background:#CFE9FF"></i></div></div>
      <div class="meter"><div class="lab"><span>hits</span><span id="v3"></span></div>
        <div class="bar"><i id="m3" style="background:#A98BE0"></i></div></div>
      <div id="secnow"></div>
      <div id="load">
        <b>Load the audio</b><br>
        Put the mp3 next to this file, or pick it:
        <input type="file" accept="audio/*" id="pick">
      </div>
    </aside>
  </main>
  <footer>
    <canvas id="tl"></canvas>
    <div class="row">
      <button id="play">Play</button>
      <label>offset <input type="range" id="off" min="-500" max="500" step="5" value="0">
        <span id="offv">0 ms</span></label>
      <label>glow <input type="range" id="glow" min="0" max="3" step="0.1" value="1.5"></label>
      <div id="clock"></div>
    </div>
  </footer>
</div>
<audio id="au" preload="auto"></audio>
<script>
const D = __DATA__;
const RAW = Uint8Array.from(atob("__FRAMES__"), c=>c.charCodeAt(0));
const N = D.n, FPS = D.fps;
const au = document.getElementById('au');
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
const tl = document.getElementById('tl'), tctx = tl.getContext('2d');
let offset = 0, W=0,H=0,view={s:1,ox:0,oy:0,r:2};

document.getElementById('hmeta').textContent =
  `${D.bpm} BPM · bar ${D.beatsPerBar} beats · ${D.sections.length} sections · `
  + `${N} bulbs · ${D.duration.toFixed(0)}s`;

/* try the file sitting beside this page; the picker is the fallback */
au.src = D.song;
au.addEventListener('canplay', ()=>{ document.getElementById('load').style.display='none'; });
document.getElementById('pick').onchange = e=>{
  const f = e.target.files[0];
  if(f){ au.src = URL.createObjectURL(f); au.play(); }
};

/* ---- geometry, bulbs drawn at true size relative to 2in pitch ---- */
const xs=D.xy.map(p=>p[0]), ys=D.xy.map(p=>p[1]);
const bx0=Math.min(...xs),bx1=Math.max(...xs),by0=Math.min(...ys),by1=Math.max(...ys);
const cx=(bx0+bx1)/2, cy=(by0+by1)/2, span=Math.max(bx1-bx0,by1-by0)/2;
function resize(){
  const r=cv.getBoundingClientRect(), dpr=Math.min(2,devicePixelRatio||1);
  W=r.width;H=r.height;cv.width=W*dpr;cv.height=H*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);
  const s=Math.min(W,H)/2-38;
  view={s:s,ox:W/2,oy:H/2,r:Math.max(1.6,(D.bulb/2)/span*s)};
  const tr=tl.getBoundingClientRect();
  tl.width=tr.width*dpr;tl.height=74*dpr;tctx.setTransform(dpr,0,0,dpr,0,0);
  drawTimeline();
}
new ResizeObserver(resize).observe(cv);

/* ---- show frame for a given audio time ---- */
function frameFor(t){
  let f = D.lead + Math.round((t + offset/1000) * FPS);
  return Math.max(0, Math.min(D.nframes-1, f));
}
function featAt(t){
  const i = Math.max(0, Math.min(D.rms.length-1, Math.round(t*FPS/D.featStep)));
  return {rms:D.rms[i], low:D.low[i], high:D.high[i], hit:D.hit[i]};
}
function sectionAt(t){
  for(const s of D.sections) if(t>=s.start && t<s.end) return s;
  return D.sections[D.sections.length-1];
}

function draw(){
  const t = au.currentTime||0, f = frameFor(t);
  const glow = parseFloat(document.getElementById('glow').value);
  const off = f*N*3;
  ctx.fillStyle='#070B14'; ctx.fillRect(0,0,W,H);
  ctx.globalCompositeOperation='lighter';
  for(let i=0;i<N;i++){
    const r=RAW[off+i*3], g=RAW[off+i*3+1], b=RAW[off+i*3+2];
    if(r+g+b===0) { // still draw an unlit bulb so the shape stays readable
      const X=view.ox+(D.xy[i][0]-cx)/span*view.s, Y=view.oy-(D.xy[i][1]-cy)/span*view.s;
      ctx.globalCompositeOperation='source-over';
      ctx.fillStyle='#111a2b';ctx.beginPath();ctx.arc(X,Y,view.r,0,6.283);ctx.fill();
      ctx.globalCompositeOperation='lighter';
      continue;
    }
    const X=view.ox+(D.xy[i][0]-cx)/span*view.s, Y=view.oy-(D.xy[i][1]-cy)/span*view.s;
    const lum=(r+g+b)/765;
    if(glow>0){
      const R=view.r*(2.4+3.4*glow);
      const gr=ctx.createRadialGradient(X,Y,0,X,Y,R);
      gr.addColorStop(0,`rgba(${r},${g},${b},${0.36*glow*lum})`);
      gr.addColorStop(1,'rgba(0,0,0,0)');
      ctx.fillStyle=gr;ctx.beginPath();ctx.arc(X,Y,R,0,6.283);ctx.fill();
    }
    ctx.fillStyle=`rgb(${r},${g},${b})`;
    ctx.beginPath();ctx.arc(X,Y,view.r,0,6.283);ctx.fill();
  }
  ctx.globalCompositeOperation='source-over';

  const fe=featAt(t);
  const set=(i,v)=>{document.getElementById('m'+i).style.width=(v*100).toFixed(0)+'%';
                    document.getElementById('v'+i).textContent=v.toFixed(2);};
  set(0,fe.low); set(1,fe.rms); set(2,fe.high); set(3,fe.hit);
  const s=sectionAt(t), idx=D.sections.indexOf(s)+1;
  document.getElementById('secnow').innerHTML =
    `section <b>${idx}</b> of ${D.sections.length}<br>`+
    `<span style="color:var(--dim)">intensity ${s.intensity.toFixed(2)} · `+
    `${(s.end-s.start).toFixed(1)}s long</span>`;
  document.getElementById('clock').innerHTML =
    `<b>${t.toFixed(2)}</b>s · frame <b>${f}</b>`;
  drawPlayhead(t);
  requestAnimationFrame(draw);
}

/* ---- timeline: sections + features + downbeats ----
   Cached to an offscreen canvas. Redrawing ~7600 line segments every frame
   at 60fps competes with the show render for no reason -- only the playhead
   actually changes. */
let tlW=0, tlCache=null;
function drawTimeline(){
  const r=tl.getBoundingClientRect(); tlW=r.width;
  const dpr=Math.min(2,devicePixelRatio||1);
  tlCache=document.createElement('canvas');
  tlCache.width=tlW*dpr; tlCache.height=74*dpr;
  const tctx=tlCache.getContext('2d'); tctx.setTransform(dpr,0,0,dpr,0,0);
  tctx.clearRect(0,0,tlW,74);
  const X=t=>t/D.duration*tlW;
  D.sections.forEach((s,i)=>{
    const v=Math.round(20+70*s.intensity);
    tctx.fillStyle=`rgb(${Math.round(v*0.35)},${Math.round(v*0.6)},${v})`;
    tctx.fillRect(X(s.start),0,X(s.end)-X(s.start)-1,15);
    tctx.fillStyle='#C6D6EA';tctx.font='10px system-ui';
    if(X(s.end)-X(s.start)>26) tctx.fillText(String(i+1),X(s.start)+4,11);
  });
  const curve=(arr,y,h,col)=>{
    tctx.strokeStyle=col;tctx.lineWidth=1;tctx.beginPath();
    for(let i=0;i<arr.length;i++){
      const t=i*D.featStep/FPS, xx=X(t), yy=y+h-arr[i]*h;
      i?tctx.lineTo(xx,yy):tctx.moveTo(xx,yy);
    } tctx.stroke();
  };
  curve(D.rms,19,20,'#7FD8F0'); curve(D.low,19,20,'#4E7BE8');
  curve(D.high,42,16,'#CFE9FF'); curve(D.hit,42,16,'#A98BE0');
  tctx.strokeStyle='#2A3A58';
  D.downbeats.forEach(t=>{tctx.beginPath();tctx.moveTo(X(t),62);tctx.lineTo(X(t),70);tctx.stroke();});
  blit(0);
}
function blit(t){
  if(!tlCache)return;
  const c=tl.getContext('2d');
  c.clearRect(0,0,tlW,74);
  c.drawImage(tlCache,0,0,tlW,74);
  const x=t/D.duration*tlW;
  c.strokeStyle='#FFFFFF';c.lineWidth=1.5;
  c.beginPath();c.moveTo(x,0);c.lineTo(x,74);c.stroke();
}
function drawPlayhead(t){ blit(t); }
tl.onclick=e=>{const r=tl.getBoundingClientRect();
  au.currentTime=Math.max(0,Math.min(D.duration,(e.clientX-r.left)/r.width*D.duration));};

document.getElementById('play').onclick=()=>{ au.paused?au.play():au.pause(); };
au.onplay=()=>document.getElementById('play').textContent='Pause';
au.onpause=()=>document.getElementById('play').textContent='Play';
document.addEventListener('keydown',e=>{
  if(e.key===' '){e.preventDefault();document.getElementById('play').click();}
  if(e.key==='ArrowLeft')au.currentTime=Math.max(0,au.currentTime-5);
  if(e.key==='ArrowRight')au.currentTime=Math.min(D.duration,au.currentTime+5);
});
const offEl=document.getElementById('off');
offEl.oninput=()=>{offset=+offEl.value;
  document.getElementById('offv').textContent=offset+' ms';};

resize(); draw();
</script></body></html>
"""


if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "out"), exist_ok=True)
    out = sys.argv[1] if len(sys.argv) > 1 else "player.html"
    rgb = sys.argv[2] if len(sys.argv) > 2 else "Show47Music.rgb"
    song = sys.argv[3]
    p, nf, n = build(rgb, song, out)
    print(f"wrote {p}  ({os.path.getsize(p)/1e6:.1f} MB)  "
          f"{nf} frames x {n} bulbs")
