#!/usr/bin/env python3
"""
make_show_player.py -- audio-synced HTML preview of rendered show frames.

Used by render_show.py --player. Standalone: no server. The frames are
embedded as one PNG (row = frame, column = pixel); the audio is loaded from
../assets/audio/<file> or via the file picker. Props are drawn where the
layout puts them, seen from the front (world x across, height up), coloured
with the rendered pixels. A timeline shows songs and sections; click to seek.
The offset slider nudges lights against audio (ms) for judging sync.
"""

import base64, io, json, os

import numpy as np
from PIL import Image

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Show preview</title>
<style>
:root{--bg:#0b0d12;--panel:#151922;--line:#262c3a;--fg:#e6e9f0;--dim:#8a93a6;--acc:#5fb8ff}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font:13px system-ui,sans-serif;overflow:hidden}
#app{display:grid;grid-template-rows:44px 1fr 120px;height:100%}
header{display:flex;gap:10px;align-items:center;padding:0 12px;background:var(--panel);border-bottom:1px solid var(--line)}
button,input,select{background:#1d2330;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:5px 9px;font:inherit}
.mono{font-family:ui-monospace,monospace}.hint{color:var(--dim);font-size:12px}
#stage{position:relative}canvas{position:absolute;inset:0;width:100%;height:100%}
#tl{position:relative;border-top:1px solid var(--line);background:var(--panel)}
#info{position:absolute;left:12px;top:10px;background:rgba(11,13,18,.8);padding:6px 10px;border-radius:8px;border:1px solid var(--line);max-width:60%}
#info b{color:var(--acc)}
</style></head><body><div id="app">
<header><b>Show preview</b><button id="play">▶ Play</button><span class="mono" id="time">0:00.00</span>
<label class="hint">offset <input type="range" id="off" min="-500" max="500" value="0" step="10" style="width:160px"> <span class="mono" id="offv">0 ms</span></label>
<label class="hint">glow <input type="checkbox" id="glow" checked></label>
<label class="hint">perceived <input type="checkbox" id="gam" checked></label>
<label class="hint" title="checked: props as rotated in the layout (a cane at rot 270 is edge-on). unchecked: every prop faces you">match scene geometry <input type="checkbox" id="geo"></label>
<span style="flex:1"></span><span id="astate" class="hint"></span><button id="bload">Load audio</button><input type="file" id="afile" accept="audio/*" hidden></header>
<div id="stage"><canvas id="c"></canvas><div id="info"></div></div>
<div id="tl"><canvas id="t"></canvas></div></div>
<script>
const D=__DATA__;
const $=s=>document.querySelector(s);
const img=new Image();let px=null;img.onload=()=>{const oc=document.createElement('canvas');oc.width=img.width;oc.height=img.height;const g=oc.getContext('2d');g.drawImage(img,0,0);px=g.getImageData(0,0,img.width,img.height).data;draw();};
img.src="data:image/png;base64,__PNG__";
const audio=new Audio();let ready=false;
function loadAudio(src,label){audio.src=src;audio.onloadedmetadata=()=>{ready=true;$('#astate').textContent='audio: '+label;};audio.onerror=()=>{$('#astate').textContent='no audio -- Load audio';};}
loadAudio(D.audio,D.audio.split('/').pop());
$('#bload').onclick=()=>$('#afile').click();$('#afile').onchange=e=>{const f=e.target.files[0];if(f)loadAudio(URL.createObjectURL(f),f.name);};
let offset=0;$('#off').oninput=e=>{offset=+e.target.value;$('#offv').textContent=offset+' ms';};
let t=D.t0, playing=false, last=null;
function toggle(){playing=!playing;$('#play').textContent=playing?'❚❚ Pause':'▶ Play';if(ready){if(playing){audio.currentTime=t;audio.play();}else audio.pause();}last=null;}
$('#play').onclick=toggle;window.addEventListener('keydown',e=>{if(e.key===' '){e.preventDefault();toggle();}if(e.key==='ArrowLeft')seek(t-5);if(e.key==='ArrowRight')seek(t+5);});
function seek(v){t=Math.max(D.t0,Math.min(D.t1,v));if(ready)audio.currentTime=t;draw();}
const c=$('#c'),tc=$('#t');
let _gc=null;function glowCanvas(W,H){if(!_gc)_gc=document.createElement('canvas');const w=Math.ceil(W/2),h=Math.ceil(H/2);if(_gc.width!==w||_gc.height!==h){_gc.width=w;_gc.height=h;}return _gc;}
function fmt(s){const m=Math.floor(s/60);return `${m}:${(s%60).toFixed(2).padStart(5,'0')}`;}
function frameAt(tt){return Math.max(0,Math.min(D.frames-1,Math.round((tt-D.t0+offset/1000)*D.fps)));}
function sizeCanvas(cv){const r=cv.getBoundingClientRect();cv.width=r.width*devicePixelRatio;cv.height=r.height*devicePixelRatio;return [r.width,r.height];}
function draw(){
  const [W,H]=sizeCanvas(c);const g=c.getContext('2d');g.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  g.fillStyle='#07080c';g.fillRect(0,0,W,H);
  const f=frameAt(t);const gam=$('#gam').checked, glow=$('#glow').checked, geo=$('#geo').checked;
  const PX=p=>geo?p.x:p.fx, PZ=p=>geo?p.z:p.fz;
  // world -> screen: x across, z up
  const pad=40;const sx=(W-2*pad)/Math.max(1,D.x1-D.x0), sz=(H-2*pad-40)/Math.max(1,D.z1);const s=Math.min(sx,sz);
  const ox=pad+((W-2*pad)-(D.x1-D.x0)*s)/2, oy=H-pad;
  g.fillStyle='#1a2030';g.fillRect(0,oy,W,2);
  if(px){const row=f*img.width*4;
    // GLOW: draw soft blobs into a half-resolution offscreen canvas, blur it once, composite 'lighter'.
    // One blur pass for the whole frame instead of an alpha disc per bulb -- cheaper and it actually blooms.
    if(glow){const oc=glowCanvas(W,H);const og=oc.getContext('2d');og.setTransform(0.5,0,0,0.5,0,0);og.clearRect(0,0,W,H);og.globalCompositeOperation='screen';
      for(const p of D.props){const dens=Math.min(1,p.pitch/1.6);          // dense props overlap more -> less alpha per bulb
        for(let i=0;i<p.n;i++){const k=row+(p.col+i)*4;let r=px[k],gg=px[k+1],b=px[k+2];const lum=(r+gg+b)/765;if(lum<0.06)continue;
        if(gam){r=255*Math.pow(r/255,1/2.2);gg=255*Math.pow(gg/255,1/2.2);b=255*Math.pow(b/255,1/2.2);}
        const X=ox+(PX(p)[i]-D.x0)*s, Y=oy-PZ(p)[i]*s; const rad=Math.max(2.5,p.pitch*s*0.75);
        og.fillStyle=`rgba(${r|0},${gg|0},${b|0},${(0.14+0.55*lum)*dens})`;og.beginPath();og.arc(X,Y,rad,0,6.283);og.fill();}}
      // two blur passes: a wide soft haze and a tighter halo, both 'screen' so colour survives and nothing saturates to white
      g.save();g.globalCompositeOperation='screen';
      g.filter=`blur(${Math.max(7,s*2.0)}px)`;g.globalAlpha=0.9;g.drawImage(oc,0,0,W,H);
      g.filter=`blur(${Math.max(2,s*0.5)}px)`;g.globalAlpha=0.6;g.drawImage(oc,0,0,W,H);g.restore();}
    for(const p of D.props){for(let i=0;i<p.n;i++){const k=row+(p.col+i)*4;let r=px[k],gg=px[k+1],b=px[k+2];
      if(gam){r=255*Math.pow(r/255,1/2.2);gg=255*Math.pow(gg/255,1/2.2);b=255*Math.pow(b/255,1/2.2);}
      const X=ox+(PX(p)[i]-D.x0)*s, Y=oy-PZ(p)[i]*s; const rad=Math.max(1.4,p.pitch*s*0.32);
      const lum=(r+gg+b)/765, k2=1+0.35*lum;                                  // bright bulbs get a hot core
      g.fillStyle=`rgb(${Math.min(255,r*k2)|0},${Math.min(255,gg*k2)|0},${Math.min(255,b*k2)|0})`;g.beginPath();g.arc(X,Y,rad,0,6.283);g.fill();}
      g.fillStyle='#6b7385';g.font='11px system-ui';g.textAlign='center';g.fillText(p.id,ox+(p.cx-D.x0)*s,oy+16);}}
  const sec=D.sections.find(q=>t>=q.t0&&t<q.t1)||D.sections[D.sections.length-1];
  const song=D.songs.find(q=>t>=q.t0&&t<q.t1);
  $('#info').innerHTML=`<div><b>${song?song.name:''}</b> <span class="hint">${song?song.theme||'':''}</span></div><div>${sec?sec.look:''} <span class="hint">· intensity ${sec&&sec.intensity!=null?sec.intensity:'auto'} · ${sec?sec.note||'':''}</span></div>`;
  $('#time').textContent=fmt(t);
  // timeline
  const [TW,TH]=sizeCanvas(tc);const tg=tc.getContext('2d');tg.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);tg.fillStyle='#151922';tg.fillRect(0,0,TW,TH);
  const X=v=>(v-D.t0)/(D.t1-D.t0)*TW;
  for(const q of D.songs){const a=X(q.t0),b=X(Math.min(q.t1,D.t1));if(b<0||a>TW)continue;tg.fillStyle='#1d2330';tg.fillRect(a,8,b-a,26);tg.strokeStyle='#33405a';tg.strokeRect(a+.5,8.5,b-a-1,25);tg.fillStyle='#cfd6e4';tg.font='11px system-ui';tg.textAlign='left';tg.fillText(q.name,a+6,26);}
  for(const q of D.sections){const a=X(q.t0),b=X(Math.min(q.t1,D.t1));if(b<0||a>TW)continue;tg.fillStyle=q===sec?'#2a4a6a':'#20283a';tg.fillRect(a,42,Math.max(1,b-a-1),40);
    if(b-a>40){tg.fillStyle='#e6e9f0';tg.font='11px system-ui';tg.fillText(q.look,a+4,58);tg.fillStyle='#8a93a6';tg.fillText(q.intensity!=null?'i'+q.intensity:'auto',a+4,74);}}
  // brightness strip
  for(let x=0;x<TW;x++){const ff=Math.floor(x/TW*D.frames);const v=D.bright[Math.min(D.bright.length-1,Math.floor(ff/D.brightStep))];tg.fillStyle=v>=0.6?'#3fa36a':'#7a3a3a';tg.fillRect(x,90,1,22*v);}
  tg.fillStyle='#fff';tg.fillRect(X(t),0,1.5,TH);
}
tc.onmousedown=e=>{const r=tc.getBoundingClientRect();seek(D.t0+(e.clientX-r.left)/r.width*(D.t1-D.t0));};
function loop(ts){if(playing){if(ready&&!audio.paused){t=audio.currentTime;}else{if(last!=null)t+=(ts-last)/1000;}if(t>=D.t1){t=D.t1;playing=false;$('#play').textContent='▶ Play';if(ready)audio.pause();}}last=ts;draw();requestAnimationFrame(loop);}
window.addEventListener('resize',draw);requestAnimationFrame(loop);
</script></body></html>
"""


def build_player(R, frames, t0, out_path, bright_step=6):
    props = R.props
    n_px = sum(p.n for p in props)
    strip = np.zeros((len(frames), n_px, 3), np.uint8)
    cols = {}
    col = 0
    for p in props:
        cols[p.id] = col; col += p.n
    from lightshow.effects import to_bytes
    bright = []
    for f, fr in enumerate(frames):
        for p in props:
            strip[f, cols[p.id]:cols[p.id] + p.n] = to_bytes(fr[p.id])
        if f % bright_step == 0:
            bright.append(float(np.mean([fr[p.id].max(1).mean() for p in props])))
    buf = io.BytesIO(); Image.fromarray(strip).save(buf, format="PNG", optimize=True)
    png = base64.b64encode(buf.getvalue()).decode()
    t1 = t0 + len(frames) / 60.0
    # audio path relative to the html
    root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    audio_abs = os.path.join(root, R.spec["audio"])
    audio_rel = os.path.relpath(audio_abs, os.path.dirname(os.path.abspath(out_path))).replace(os.sep, "/")
    zmax = max(float(p.wz.max()) for p in props)
    data = {
        "audio": audio_rel, "fps": 60, "t0": t0, "t1": t1, "frames": len(frames),
        "x0": min(R.world[0], min(float((p.pl.x + p.lx).min()) for p in props)) - 10,
        "x1": max(R.world[1], max(float((p.pl.x + p.lx).max()) for p in props)) + 10, "z1": zmax + 6,
        "props": [{"id": p.id, "n": p.n, "col": cols[p.id], "cx": p.cx, "pitch": p.pitch,
                   "x": [round(float(v), 1) for v in p.wx], "z": [round(float(v), 1) for v in p.wz],
                   # front-facing (rotation ignored): the prop's own plane, centred on its placement
                   "fx": [round(float(v), 1) for v in p.pl.x + p.lx], "fz": [round(float(v), 1) for v in p.pl.z + p.ly]} for p in props],
        "songs": [{"name": s["name"], "theme": s.get("theme"), "t0": s["from"], "t1": s["to"]} for s in R.songs],
        "sections": [{"t0": s["t0"], "t1": s["t1"], "look": s["look"], "note": s["note"],
                      "intensity": None if s["intensity"] is None else round(s["intensity"] * 10)} for s in R.sections],
        "bright": [round(b, 3) for b in bright], "brightStep": bright_step,
    }
    html = HTML.replace("__DATA__", json.dumps(data, separators=(",", ":"))).replace("__PNG__", png)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path
