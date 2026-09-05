#!/usr/bin/env python3
"""
make_viewer.py -- standalone HTML preview for a multi-prop show.

    python tools/make_viewer.py out/two_props.html out/TwoProps.rgb

Reads the rig and the section list straight from two_prop_show.py, so the
preview cannot drift out of step with the show it is previewing.

FRAME DATA IS EMBEDDED AS A PNG, NOT AS BASE64 BYTES
    9564 frames x 229 pixels x 3 = 6.6 MB raw, which is ~8.8 MB once
    base64-encoded -- an unpleasant HTML file. Encoding the whole show as a
    single PNG (one row per frame, one column per pixel) and embedding that
    instead lets PNG's filtering and deflate do the work; this show has long
    runs of black and repeated colours and compresses roughly 10x. The
    browser decodes it natively into an offscreen canvas and the viewer
    indexes rows out of the ImageData.

GAMMA
    The controller's LUT is an identity ramp, so byte value maps ~linearly
    to LED luminance, and perceived brightness goes as luminance^(1/2.2).
    Drawing raw byte values to a screen therefore UNDERSTATES how bright the
    prop looks -- badly, at the low end. The viewer applies byte -> perceived
    by default; the toggle shows the raw bytes for comparison.
"""

import base64, io, json, os, sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lightshow.formats.rgbfile import Show                      # noqa: E402
import importlib                                                # noqa: E402

SHOW_MODULE = os.environ.get("SHOW_MODULE", "two_prop_show")
_m = importlib.import_module(SHOW_MODULE)
build_rig, SECTIONS, FPS, GAP_IN = _m.build_rig, _m.SECTIONS, _m.FPS, _m.GAP_IN


def build(rgb_path, out_path):
    show = Show.load(rgb_path)
    props = build_rig()

    # pull each prop's pixels out of every frame into one tall image
    n_px = sum(p.n for p in props)
    strip = np.zeros((len(show.frames), n_px, 3), np.uint8)
    for f, fr in enumerate(show.frames):
        col = 0
        for p in props:
            base = sum(show.channels[:p.port]) * 3
            strip[f, col:col + p.n] = np.frombuffer(
                fr[base:base + p.n * 3], np.uint8).reshape(p.n, 3)
            col += p.n

    buf = io.BytesIO()
    Image.fromarray(strip).save(buf, format="PNG", optimize=True)
    png_b64 = base64.b64encode(buf.getvalue()).decode()

    # rebuild the section timing exactly as the show builder does
    def fr_(s):
        return max(1, int(round(s * FPS)))
    marks, cur = [], fr_(1.0)
    for name, _fn, dur in SECTIONS:
        marks.append({"start": round(cur / FPS, 2),
                      "end": round((cur + fr_(dur)) / FPS, 2),
                      "name": name})
        cur += fr_(dur) + fr_(0.7)

    col = 0
    pj = []
    for p in props:
        pj.append({"name": p.name, "port": p.port, "n": p.n,
                   "col": col, "fold": int(p.fold),
                   "pitch": round(p.pitch_in, 2),
                   "xy": [[round(float(x), 2), round(float(y), 2)]
                          for x, y in zip(p.x_in, p.y_in)],
                   "tips": [int(v) for v in p.tips]})
        col += p.n

    data = {"fps": FPS, "nframes": len(show.frames), "nPx": n_px,
            "props": pj, "sections": marks, "gap": GAP_IN, "title": SHOW_MODULE,
            "duration": round(len(show.frames) / FPS, 2)}

    html = (TEMPLATE.replace("__DATA__", json.dumps(data))
                    .replace("__PNG__", png_b64))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path, len(show.frames), n_px, len(buf.getvalue())


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Show preview</title>
<style>
  :root{--void:#070B14;--panel:#0E1524;--line:#1E2A42;
        --text:#C6D6EA;--dim:#63758F;--ice:#7FD8F0;}
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:var(--void);color:var(--text);
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
    font-variant-numeric:tabular-nums;overflow:hidden}
  #app{display:flex;flex-direction:column;height:100%}
  header{padding:11px 18px 9px;border-bottom:1px solid var(--line);
    display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}
  h1{font-size:15px;font-weight:600;margin:0}
  header .m{color:var(--dim);font-size:12.5px}
  main{flex:1;display:grid;grid-template-columns:1fr 236px;min-height:0}
  #stage{position:relative;min-width:0}
  canvas#cv{width:100%;height:100%;display:block}
  aside{border-left:1px solid var(--line);background:var(--panel);
    padding:14px;overflow-y:auto;font-size:12.5px}
  aside h2{font-size:11.5px;font-weight:600;color:var(--dim);margin:0 0 8px}
  .prop{padding:8px 10px;background:#162034;border-radius:6px;margin-bottom:8px}
  .prop b{font-size:13.5px}
  .prop span{color:var(--dim)}
  #secnow{margin-top:12px;padding:10px;background:#162034;border-radius:6px;
    line-height:1.5}
  #secnow b{color:var(--ice)}
  footer{border-top:1px solid var(--line);background:var(--panel);padding:9px 16px}
  #tl{width:100%;height:44px;display:block;cursor:pointer}
  .row{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-top:7px}
  button{background:#182236;color:var(--text);border:1px solid var(--line);
    border-radius:6px;padding:7px 14px;font:inherit;font-size:13px;cursor:pointer}
  button:hover{border-color:var(--ice)}
  button:focus-visible,input:focus-visible{outline:2px solid var(--ice);
    outline-offset:2px}
  #play{color:var(--ice);min-width:80px}
  label{display:flex;align-items:center;gap:7px;color:var(--dim);font-size:12.5px}
  input[type=range]{accent-color:var(--ice);width:120px}
  #clock{margin-left:auto;color:var(--dim)}
  #clock b{color:var(--text)}
  #boot{position:absolute;inset:0;display:grid;place-items:center;
    color:var(--dim);font-size:13px}
</style></head><body>
<div id="app">
  <header><h1 id="ttl">Show preview</h1><span class="m" id="hmeta"></span></header>
  <main>
    <div id="stage"><canvas id="cv"></canvas><div id="boot">decoding frames…</div></div>
    <aside>
      <h2>Rig</h2><div id="rig"></div>
      <h2 style="margin-top:14px">Now playing</h2>
      <div id="secnow"></div>
    </aside>
  </main>
  <footer>
    <canvas id="tl"></canvas>
    <div class="row">
      <button id="play">Play</button>
      <label>speed <input type="range" id="spd" min="0.15" max="2" step="0.05" value="1"><span id="spdv">1.0x</span></label>
      <label>glow <input type="range" id="glow" min="0" max="3" step="0.1" value="1.5"></label>
      <label><input type="checkbox" id="raw"> raw bytes</label>
      <div id="clock"></div>
    </div>
  </footer>
</div>
<script>
const D = __DATA__;
const cv=document.getElementById('cv'), ctx=cv.getContext('2d');
const tl=document.getElementById('tl');
let PIX=null, frame=0, playing=false, W=0,H=0,view={s:1,ox:0,oy:0,r:2};

/* byte -> perceived. Identity LUT on the controller means byte maps
   ~linearly to luminance; the eye sees luminance^(1/2.2). Without this the
   preview looks far darker than the prop actually does. */
const LUT=new Uint8Array(256);
for(let i=0;i<256;i++) LUT[i]=Math.round(255*Math.pow(i/255,1/2.2));

const img=new Image();
img.onload=()=>{
  const oc=document.createElement('canvas');
  oc.width=D.nPx; oc.height=D.nframes;
  const o=oc.getContext('2d',{willReadFrequently:true});
  o.drawImage(img,0,0);
  PIX=o.getImageData(0,0,D.nPx,D.nframes).data;
  document.getElementById('boot').remove();
  playing=true; document.getElementById('play').textContent='Pause';
  loop();
};
img.src="data:image/png;base64,__PNG__";

/* ---- layout in world inches ---- */
const xs=[],ys=[];
D.props.forEach(p=>p.xy.forEach(([x,y])=>{xs.push(x);ys.push(y);}));
const x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
document.getElementById('ttl').textContent = D.title.replace(/_/g,' ');
document.getElementById('hmeta').textContent =
  `${D.props.length} props · ${D.nPx} bulbs · ${(x1-x0).toFixed(0)}×${(y1-y0).toFixed(0)} in `
  +`· ${D.gap} in gap · ${D.duration.toFixed(0)}s @ ${D.fps}fps`;
document.getElementById('rig').innerHTML = D.props.map(p=>
  `<div class="prop"><b>${p.name}</b> <span>port ${p.port+1}</span><br>
   <span>${p.n} px · ${p.fold}-fold · ${p.pitch} in pitch</span></div>`).join('');

function resize(){
  const r=cv.getBoundingClientRect(), dpr=Math.min(2,devicePixelRatio||1);
  W=r.width;H=r.height;cv.width=W*dpr;cv.height=H*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);
  const pad=34, s=Math.min((W-2*pad)/(x1-x0),(H-2*pad)/(y1-y0));
  view={s:s,ox:W/2-((x0+x1)/2)*s,oy:H/2+((y0+y1)/2)*s,
        r:Math.max(1.7,0.5/2*s)};   /* half-inch bulb at true size */
  const tr=tl.getBoundingClientRect();
  tl.width=tr.width*dpr;tl.height=44*dpr;
  tl.getContext('2d').setTransform(dpr,0,0,dpr,0,0);
  drawTimeline();
}
new ResizeObserver(resize).observe(cv);

function draw(){
  if(!PIX)return;
  const glow=parseFloat(document.getElementById('glow').value);
  const raw=document.getElementById('raw').checked;
  const row=Math.max(0,Math.min(D.nframes-1,Math.round(frame)))*D.nPx*4;
  ctx.fillStyle='#070B14';ctx.fillRect(0,0,W,H);
  ctx.globalCompositeOperation='lighter';
  for(const p of D.props){
    for(let i=0;i<p.n;i++){
      const o=row+(p.col+i)*4;
      let r=PIX[o],g=PIX[o+1],b=PIX[o+2];
      if(!raw){r=LUT[r];g=LUT[g];b=LUT[b];}
      const X=view.ox+p.xy[i][0]*view.s, Y=view.oy-p.xy[i][1]*view.s;
      if(r+g+b<10){
        ctx.globalCompositeOperation='source-over';
        ctx.fillStyle='#0F1728';ctx.beginPath();ctx.arc(X,Y,view.r,0,6.283);ctx.fill();
        ctx.globalCompositeOperation='lighter';
        continue;
      }
      const lum=(r+g+b)/765;
      if(glow>0){
        const R=view.r*(2.3+3.3*glow);
        const gr=ctx.createRadialGradient(X,Y,0,X,Y,R);
        gr.addColorStop(0,`rgba(${r},${g},${b},${0.34*glow*lum})`);
        gr.addColorStop(1,'rgba(0,0,0,0)');
        ctx.fillStyle=gr;ctx.beginPath();ctx.arc(X,Y,R,0,6.283);ctx.fill();
      }
      ctx.fillStyle=`rgb(${r},${g},${b})`;
      ctx.beginPath();ctx.arc(X,Y,view.r,0,6.283);ctx.fill();
    }
  }
  ctx.globalCompositeOperation='source-over';
  const t=frame/D.fps;
  const s=D.sections.find(s=>t>=s.start&&t<s.end);
  document.getElementById('secnow').innerHTML = s
    ? `<b>${s.name}</b><br><span style="color:var(--dim)">`
      +`${s.start.toFixed(0)}–${s.end.toFixed(0)}s</span>`
    : '<span style="color:var(--dim)">between sections</span>';
  document.getElementById('clock').innerHTML=
    `<b>${t.toFixed(2)}</b>s · frame <b>${Math.round(frame)}</b>`;
  blit(t);
}

let tlW=0, cache=null;
function drawTimeline(){
  const r=tl.getBoundingClientRect(); tlW=r.width;
  const dpr=Math.min(2,devicePixelRatio||1);
  cache=document.createElement('canvas');
  cache.width=tlW*dpr;cache.height=44*dpr;
  const c=cache.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);
  c.clearRect(0,0,tlW,44);
  const X=t=>t/D.duration*tlW;
  D.sections.forEach((s,i)=>{
    c.fillStyle=i%2?'#1B2C46':'#16243A';
    c.fillRect(X(s.start),0,X(s.end)-X(s.start)-1,30);
    c.fillStyle='#8FA6C4';c.font='10px system-ui';
    const w=X(s.end)-X(s.start);
    if(w>34) c.fillText(String(i+1),X(s.start)+4,12);
  });
  c.fillStyle='#63758F';c.font='10px system-ui';
  c.fillText('click to scrub',4,41);
  blit(frame/D.fps);
}
function blit(t){
  if(!cache)return;
  const c=tl.getContext('2d');
  c.clearRect(0,0,tlW,44);c.drawImage(cache,0,0,tlW,44);
  const x=t/D.duration*tlW;
  c.strokeStyle='#7FD8F0';c.lineWidth=1.5;
  c.beginPath();c.moveTo(x,0);c.lineTo(x,44);c.stroke();
}
tl.onclick=e=>{const r=tl.getBoundingClientRect();
  frame=Math.max(0,Math.min(D.nframes-1,
    (e.clientX-r.left)/r.width*D.duration*D.fps));draw();};

function loop(){
  if(playing){
    frame+=parseFloat(document.getElementById('spd').value);
    if(frame>=D.nframes) frame=0;
  }
  draw();requestAnimationFrame(loop);
}
document.getElementById('play').onclick=e=>{
  playing=!playing;e.target.textContent=playing?'Pause':'Play';};
document.getElementById('spd').oninput=e=>{
  document.getElementById('spdv').textContent=(+e.target.value).toFixed(2)+'x';};
document.addEventListener('keydown',e=>{
  if(e.key===' '){e.preventDefault();document.getElementById('play').click();}
  if(e.key==='ArrowLeft'){frame=Math.max(0,frame-D.fps*5);draw();}
  if(e.key==='ArrowRight'){frame=Math.min(D.nframes-1,frame+D.fps*5);draw();}
});
resize();
</script></body></html>
"""


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "out/two_props.html"
    rgb = sys.argv[2] if len(sys.argv) > 2 else "out/TwoProps.rgb"
    # SHOW_MODULE=showcase python tools/make_viewer.py ...
    p, nf, n, png = build(rgb, out)
    raw = nf * n * 3
    print(f"wrote {p}  ({os.path.getsize(p)/1e6:.2f} MB)")
    print(f"  {nf} frames x {n} bulbs")
    print(f"  frame data {raw/1e6:.2f} MB raw -> {png/1e6:.2f} MB as PNG "
          f"({raw/png:.1f}x smaller; base64 of raw would have been "
          f"{raw*4/3/1e6:.1f} MB)")
