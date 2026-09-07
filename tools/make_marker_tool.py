#!/usr/bin/env python3
"""
make_marker_tool.py -- build the standalone music marker tool.

    python tools/make_marker_tool.py assets/audio/show16.mp3      # -> out/markers.html
    python tools/make_marker_tool.py SONG.mp3 out/markers.html

Open the HTML in a browser (it sits next to the audio in out/, and loads
../assets/audio/<file> directly; if your browser refuses file:// audio, use
the "Load audio" button and pick the same file).

WHAT IT DOES
  * waveform with zoom/scroll, play/pause, click to seek
  * the analyser's SECTION CANDIDATES are drawn as faint ticks; click one to
    accept it as a section marker
  * drop markers while listening:  S = song change,  D = section change
  * every marker can carry a label, an intensity 0-10 and a palette
    (monochrome / limited / full) -- the inputs show.yaml consumes
  * drag a marker to move it, [ ] to jump between markers, Delete removes
  * "Export markers.json" downloads; commit it at assets/show/markers.json

The analysis is embedded at build time so the tool has beats and section
candidates without a server. Rebuild after changing the audio.
"""

import json, os, sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from lightshow.music import analyse, decode, SR   # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Music markers</title>
<style>
:root{--bg:#0d0f14;--panel:#151922;--line:#262c3a;--fg:#e6e9f0;--dim:#8a93a6;--acc:#5fb8ff;--song:#ff6b5f;--sec:#e8b04b}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font:13px/1.4 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;overflow:hidden}
#app{display:grid;grid-template-rows:44px 90px 1fr 260px;height:100%}
header{display:flex;align-items:center;gap:10px;padding:0 12px;border-bottom:1px solid var(--line);background:var(--panel)}
header h1{font-size:14px;margin:0 12px 0 0;font-weight:600}
button,select,input{background:#1d2330;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:5px 9px;font:inherit}
button{cursor:pointer}button:hover{border-color:var(--acc)}
.mono{font-family:ui-monospace,Menlo,Consolas,monospace}
#over,#detail{position:relative;min-height:0;overflow:hidden}
canvas{display:block;position:absolute;inset:0;width:100%;height:100%}
#tools{border-top:1px solid var(--line);background:var(--panel);display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:10px 12px;overflow:hidden}
#list{overflow:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
td,th{padding:3px 5px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--dim);font-weight:500}
tr.sel td{background:#223449}
td input,td select{padding:2px 5px;font-size:12px}
td input.lbl{width:150px}
.hint{color:var(--dim);font-size:12px}
.song{color:var(--song)}.sec{color:var(--sec)}
kbd{background:#1d2330;border:1px solid var(--line);border-radius:4px;padding:0 5px;font-family:ui-monospace,monospace}
#help p{margin:4px 0}
</style></head><body>
<div id="app">
<header>
  <h1>Music markers</h1>
  <button id="play">▶ Play</button>
  <span class="mono" id="time">0:00.00</span><span class="hint">/ <span class="mono" id="dur"></span></span>
  <span style="width:10px"></span>
  <button id="bsong" class="song">+ Song change (S)</button>
  <button id="bsec" class="sec">+ Section (D)</button>
  <label class="hint">speed <select id="rate"><option>0.75</option><option selected>1</option><option>1.25</option></select></label>
  <span style="flex:1"></span>
  <span id="audiostate" class="hint"></span>
  <button id="bload">Load audio</button><input type="file" id="afile" accept="audio/*" hidden>
  <button id="bimport">Import</button><input type="file" id="mfile" accept=".json" hidden>
  <button id="bexport">Export markers.json</button>
</header>
<div id="over"><canvas id="c1"></canvas></div>
<div id="detail"><canvas id="c2"></canvas></div>
<div id="tools">
  <div id="list"><table><thead><tr><th>#</th><th>time</th><th>type</th><th>label</th><th>intensity</th><th>palette</th><th></th></tr></thead><tbody></tbody></table></div>
  <div id="help">
    <p><b>Listen and mark.</b> <kbd>Space</kbd> play/pause · <kbd>S</kbd> song change · <kbd>D</kbd> section · <kbd>←</kbd><kbd>→</kbd> 1 s (<kbd>Shift</kbd> 5 s) · <kbd>[</kbd> <kbd>]</kbd> previous/next marker · <kbd>Delete</kbd> removes selected</p>
    <p>Overview strip: click to seek, drag the window to scroll. Detail strip: wheel to zoom, click to seek, drag a marker to move it. Faint grey ticks are the analyser's <b>section candidates</b> — click one to accept it; taller grey ticks are the strongest (intensity jumps). Thin ticks at the bottom are detected beats.</p>
    <p><b>Intensity</b> 0–10 and <b>palette</b> are optional overrides for the stretch that starts at the marker — leave blank to let the music analysis decide. A song change resets the pattern altogether; a section change keeps the family of pattern but changes it up.</p>
    <p class="hint">Markers live only in this page until you export. Export often; the file is small and diffs cleanly.</p>
  </div>
</div>
</div>
<script>
const D = __DATA__;      // {audio, duration, env:[...], envRate, beats:[...], candidates:[{t,strength}], sections:[...]}
let M = __MARKERS__;     // {markers:[{t,type,label,intensity,palette}]}
const $=s=>document.querySelector(s);
const audio=new Audio(); audio.preload='auto';
let dur=D.duration, win={t0:0,t1:Math.min(D.duration,90)}, sel=-1, drag=null, ready=false;
function fmt(t){const m=Math.floor(t/60),s=t-m*60;return `${m}:${s<10?'0':''}${s.toFixed(2)}`;}
function fmt1(t){const m=Math.floor(t/60),s=t-m*60;return `${m}:${s<10?'0':''}${s.toFixed(1)}`;}
function parseT(s){const m=/^(\d+):(\d+(?:\.\d+)?)$/.exec(s.trim());return m?(+m[1])*60+ +m[2]:parseFloat(s);}

// ------------------------------------------------------------ audio
function loadAudio(src,label){audio.src=src;audio.load();$('#audiostate').textContent='loading '+label+'…';
  audio.onloadedmetadata=()=>{ready=true;if(isFinite(audio.duration))dur=audio.duration;$('#audiostate').textContent='audio: '+label;$('#dur').textContent=fmt1(dur);draw();};
  audio.onerror=()=>{ready=false;$('#audiostate').textContent='could not load '+label+' — use Load audio';};}
loadAudio(D.audio, D.audio.split('/').pop());
$('#bload').onclick=()=>$('#afile').click();
$('#afile').onchange=e=>{const f=e.target.files[0];if(f)loadAudio(URL.createObjectURL(f),f.name);};
$('#play').onclick=toggle;
function toggle(){if(!ready)return;if(audio.paused){audio.play();$('#play').textContent='❚❚ Pause';}else{audio.pause();$('#play').textContent='▶ Play';}}
$('#rate').onchange=e=>audio.playbackRate=+e.target.value;
function seek(t){t=Math.max(0,Math.min(dur,t));audio.currentTime=t;draw();}
$('#dur').textContent=fmt1(dur);

// ------------------------------------------------------------ markers
function add(type,t){t=t??audio.currentTime;const n=M.markers.filter(m=>m.type===type).length+1;
  M.markers.push({t:+t.toFixed(2),type,label:type==='song'?`Song ${n}`:``,intensity:null,palette:null});sort();sel=M.markers.findIndex(m=>m.t===+t.toFixed(2));refresh();}
function sort(){M.markers.sort((a,b)=>a.t-b.t);}
function del(i){if(i<0)return;M.markers.splice(i,1);sel=-1;refresh();}
$('#bsong').onclick=()=>add('song');$('#bsec').onclick=()=>add('section');
window.addEventListener('keydown',e=>{if(['INPUT','SELECT'].includes(e.target.tagName))return;
  switch(e.key){case ' ':e.preventDefault();toggle();break;case 's':case 'S':add('song');break;case 'd':case 'D':add('section');break;
  case 'ArrowLeft':seek(audio.currentTime-(e.shiftKey?5:1));break;case 'ArrowRight':seek(audio.currentTime+(e.shiftKey?5:1));break;
  case '[':{const prev=[...M.markers].reverse().find(m=>m.t<audio.currentTime-0.3);if(prev){seek(prev.t);sel=M.markers.indexOf(prev);refresh();}break;}
  case ']':{const nx=M.markers.find(m=>m.t>audio.currentTime+0.3);if(nx){seek(nx.t);sel=M.markers.indexOf(nx);refresh();}break;}
  case 'Delete':case 'Backspace':del(sel);break;}});

// ------------------------------------------------------------ drawing
const c1=$('#c1'),c2=$('#c2');
function size(c){const r=c.getBoundingClientRect();c.width=r.width*devicePixelRatio;c.height=r.height*devicePixelRatio;return [r.width,r.height];}
function envAt(t){const i=Math.floor(t*D.envRate);return D.env[Math.max(0,Math.min(D.env.length-1,i))]||0;}
function wave(g,W,H,t0,t1,color){const n=Math.floor(W);g.fillStyle=color;
  for(let px=0;px<n;px++){const ta=t0+(t1-t0)*px/n,tb=t0+(t1-t0)*(px+1)/n;let v=0;const ia=Math.floor(ta*D.envRate),ib=Math.max(ia+1,Math.floor(tb*D.envRate));
    for(let i=ia;i<ib&&i<D.env.length;i++)v=Math.max(v,D.env[i]);const h=Math.max(1,v*H*0.9);g.fillRect(px,H/2-h/2,1,h);}}
function markers(g,W,H,t0,t1,big){const x=t=>(t-t0)/(t1-t0)*W;
  // candidates
  for(const c of D.candidates){if(c.t<t0||c.t>t1)continue;const X=x(c.t);g.strokeStyle=`rgba(190,200,220,${0.45+0.5*c.strength})`;g.lineWidth=big?2:1;g.beginPath();g.moveTo(X,H*(big?(0.55-0.4*c.strength):0.2));g.lineTo(X,H);g.stroke();}
  if(big){g.strokeStyle='rgba(95,184,255,.35)';for(const b of D.beats){if(b<t0||b>t1)continue;const X=x(b);g.beginPath();g.moveTo(X,H-6);g.lineTo(X,H);g.stroke();}}
  M.markers.forEach((m,i)=>{if(m.t<t0-1||m.t>t1+1)return;const X=x(m.t),col=m.type==='song'?'#ff6b5f':'#e8b04b';
    g.strokeStyle=col;g.lineWidth=i===sel?3:(m.type==='song'?2:1.5);g.beginPath();g.moveTo(X,0);g.lineTo(X,H);g.stroke();
    if(big){g.fillStyle=col;g.font='11px system-ui';g.textAlign='left';g.textBaseline='top';const lab=(m.label||(m.type==='song'?'song':'section'))+(m.intensity!=null?` · i${m.intensity}`:'')+(m.palette?` · ${m.palette}`:'');
      const tw=g.measureText(lab).width+8;g.fillStyle='rgba(13,15,20,.85)';g.fillRect(X+2,2,tw,15);g.fillStyle=col;g.fillText(lab,X+6,3);}});
  // playhead
  const X=x(audio.currentTime);g.strokeStyle='#fff';g.lineWidth=1.5;g.beginPath();g.moveTo(X,0);g.lineTo(X,H);g.stroke();}
function draw(){
  {const [W,H]=size(c1);const g=c1.getContext('2d');g.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);g.fillStyle='#0d0f14';g.fillRect(0,0,W,H);
    wave(g,W,H,0,dur,'#2b3550');g.fillStyle='rgba(95,184,255,.12)';g.fillRect(win.t0/dur*W,0,(win.t1-win.t0)/dur*W,H);g.strokeStyle='rgba(95,184,255,.5)';g.strokeRect(win.t0/dur*W,0.5,(win.t1-win.t0)/dur*W,H-1);
    markers(g,W,H,0,dur,false);
    g.fillStyle='#8a93a6';g.font='10px system-ui';g.textAlign='left';g.textBaseline='bottom';for(let t=0;t<dur;t+=60){g.fillText(fmt1(t).replace('.0',''),t/dur*W+2,H-2);}}
  {const [W,H]=size(c2);const g=c2.getContext('2d');g.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);g.fillStyle='#0a0c11';g.fillRect(0,0,W,H);
    // time grid every 5 s or 1 s
    const span=win.t1-win.t0,step=span>120?30:(span>40?10:(span>12?5:1));g.strokeStyle='#1a2030';g.fillStyle='#8a93a6';g.font='11px system-ui';g.textAlign='left';g.textBaseline='top';
    for(let t=Math.ceil(win.t0/step)*step;t<=win.t1;t+=step){const X=(t-win.t0)/span*W;g.beginPath();g.moveTo(X,0);g.lineTo(X,H);g.stroke();g.fillText(fmt1(t),X+3,H-16);}
    wave(g,W,H,win.t0,win.t1,'#3b4a70');markers(g,W,H,win.t0,win.t1,true);}
  $('#time').textContent=fmt(audio.currentTime);
  if(!audio.paused){const t=audio.currentTime;if(t>win.t1-1||t<win.t0){const s=win.t1-win.t0;win.t0=Math.max(0,t-2);win.t1=Math.min(dur,win.t0+s);}}
}
function loop(){draw();requestAnimationFrame(loop);}
window.addEventListener('resize',draw);

// overview: click seeks, drag moves the window
c1.addEventListener('mousedown',e=>{const r=c1.getBoundingClientRect();const t=(e.clientX-r.left)/r.width*dur;
  if(t>=win.t0&&t<=win.t1){drag={kind:'win',t,t0:win.t0,t1:win.t1};}else{const s=win.t1-win.t0;win.t0=Math.max(0,Math.min(dur-s,t-s/2));win.t1=win.t0+s;seek(t);}});
// detail: click seeks / selects marker / accepts candidate; drag marker
c2.addEventListener('mousedown',e=>{const r=c2.getBoundingClientRect();const span=win.t1-win.t0,t=win.t0+(e.clientX-r.left)/r.width*span,tol=span/r.width*6;
  let best=-1,bd=tol;M.markers.forEach((m,i)=>{const d=Math.abs(m.t-t);if(d<bd){bd=d;best=i;}});
  if(best>=0){sel=best;drag={kind:'mk',i:best};refresh();return;}
  const c=D.candidates.find(c=>Math.abs(c.t-t)<tol);if(c){add('section',c.t);return;}
  sel=-1;seek(t);refresh();});
window.addEventListener('mousemove',e=>{if(!drag)return;
  if(drag.kind==='win'){const r=c1.getBoundingClientRect();const t=(e.clientX-r.left)/r.width*dur,s=drag.t1-drag.t0;win.t0=Math.max(0,Math.min(dur-s,drag.t0+t-drag.t));win.t1=win.t0+s;}
  else if(drag.kind==='mk'){const r=c2.getBoundingClientRect();const t=win.t0+(e.clientX-r.left)/r.width*(win.t1-win.t0);M.markers[drag.i].t=+Math.max(0,Math.min(dur,t)).toFixed(2);drag.moved=true;}
  draw();});
window.addEventListener('mouseup',()=>{if(drag&&drag.kind==='mk'&&drag.moved){const m=M.markers[drag.i];sort();sel=M.markers.indexOf(m);refresh();}drag=null;});
c2.addEventListener('wheel',e=>{e.preventDefault();const r=c2.getBoundingClientRect();const f=(e.clientX-r.left)/r.width,span=win.t1-win.t0,t=win.t0+f*span;
  const ns=Math.max(4,Math.min(dur,span*Math.exp(e.deltaY*0.0015)));win.t0=Math.max(0,t-f*ns);win.t1=Math.min(dur,win.t0+ns);win.t0=Math.max(0,win.t1-ns);draw();},{passive:false});
c1.addEventListener('wheel',e=>{e.preventDefault();const s=win.t1-win.t0;win.t0=Math.max(0,Math.min(dur-s,win.t0+e.deltaY*s/500));win.t1=win.t0+s;draw();},{passive:false});

// ------------------------------------------------------------ table
function refresh(){const tb=$('#list tbody');
  tb.innerHTML=M.markers.map((m,i)=>`<tr data-i="${i}" class="${i===sel?'sel':''}"><td class="hint">${i+1}</td><td><input class="mono t" value="${fmt(m.t)}" style="width:80px"></td>
   <td><select class="ty"><option value="song"${m.type==='song'?' selected':''}>song</option><option value="section"${m.type==='section'?' selected':''}>section</option></select></td>
   <td><input class="lbl" value="${(m.label||'').replace(/"/g,'&quot;')}" placeholder="${m.type==='song'?'song title':'what changes here'}"></td>
   <td><input type="number" class="int" min="0" max="10" step="1" value="${m.intensity??''}" style="width:56px" placeholder="auto"></td>
   <td><select class="pal"><option value="">auto</option>${['monochrome','limited','full'].map(p=>`<option${m.palette===p?' selected':''}>${p}</option>`).join('')}</select></td>
   <td><button class="go" title="jump">⤓</button> <button class="rm" title="delete">✕</button></td></tr>`).join('');
  tb.querySelectorAll('tr').forEach(tr=>{const i=+tr.dataset.i,m=M.markers[i];
    tr.onclick=()=>{sel=i;tb.querySelectorAll('tr').forEach(r=>r.classList.remove('sel'));tr.classList.add('sel');};
    tr.querySelector('.t').onchange=e=>{const t=parseT(e.target.value);if(isFinite(t)){m.t=+t.toFixed(2);sort();sel=M.markers.indexOf(m);refresh();}};
    tr.querySelector('.ty').onchange=e=>{m.type=e.target.value;draw();};
    tr.querySelector('.lbl').onchange=e=>{m.label=e.target.value;draw();};
    tr.querySelector('.int').onchange=e=>{m.intensity=e.target.value===''?null:Math.max(0,Math.min(10,Math.round(+e.target.value)));draw();};
    tr.querySelector('.pal').onchange=e=>{m.palette=e.target.value||null;draw();};
    tr.querySelector('.go').onclick=e=>{e.stopPropagation();seek(m.t);const s=win.t1-win.t0;if(m.t<win.t0||m.t>win.t1){win.t0=Math.max(0,m.t-s/3);win.t1=Math.min(dur,win.t0+s);}};
    tr.querySelector('.rm').onclick=e=>{e.stopPropagation();del(i);};});
  const r=tb.querySelector('tr.sel');if(r)r.scrollIntoView({block:'nearest'});draw();}

// ------------------------------------------------------------ io
$('#bexport').onclick=()=>{const out={audio:D.audio.replace(/^\.\.\//,''),duration:+dur.toFixed(2),markers:M.markers};
  const blob=new Blob([JSON.stringify(out,null,1)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='markers.json';a.click();};
$('#bimport').onclick=()=>$('#mfile').click();
$('#mfile').onchange=e=>{const f=e.target.files[0];if(!f)return;const rd=new FileReader();rd.onload=()=>{try{const d=JSON.parse(rd.result);M={markers:(d.markers||[]).map(m=>({t:+m.t,type:m.type||'section',label:m.label||'',intensity:m.intensity??null,palette:m.palette||null}))};sort();sel=-1;refresh();}catch(err){alert('bad markers.json: '+err);}};rd.readAsText(f);e.target.value='';};
window.addEventListener('beforeunload',e=>{if(M.markers.length){e.preventDefault();e.returnValue='';}});
refresh();loop();
</script></body></html>
"""


def build(song, out_path, markers_path=None, env_rate=25):
    a = analyse(song)
    y = a.y
    hop = int(SR / env_rate)
    n = len(y) // hop
    env = np.abs(y[:n * hop]).reshape(n, hop)
    env = np.percentile(env, 98, axis=1)
    env = env / max(1e-9, np.percentile(env, 99.5))
    env = np.clip(env, 0, 1)
    # candidates: every detected section boundary, strength = intensity jump
    cands = []
    for s0, s1 in zip(a.sections[:-1], a.sections[1:]):
        jump = abs(s1.get("intensity", 0) - s0.get("intensity", 0))
        cands.append({"t": round(s1["start"], 2), "strength": round(float(min(1.0, jump * 1.5)), 2)})
    rel_audio = os.path.relpath(os.path.abspath(song), os.path.dirname(os.path.abspath(out_path)))
    data = {"audio": rel_audio.replace(os.sep, "/"), "duration": round(a.duration, 2),
            "envRate": env_rate, "env": [round(float(v), 3) for v in env],
            "beats": [round(float(b), 2) for b in a.beats], "candidates": cands,
            "bpm": round(float(a.bpm), 1),
            "sections": [{"start": round(s["start"], 2), "end": round(s["end"], 2),
                          "intensity": round(s.get("intensity", 0), 2)} for s in a.sections]}
    markers = {"markers": []}
    if markers_path and os.path.exists(markers_path):
        with open(markers_path) as fh:
            markers = {"markers": json.load(fh).get("markers", [])}
    html = HTML.replace("__DATA__", json.dumps(data, separators=(",", ":"))).replace("__MARKERS__", json.dumps(markers))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"{out_path}  {len(html)/1e6:.1f} MB  {a.duration:.1f} s  {len(a.beats)} beats  "
          f"{len(cands)} section candidates  {len(markers['markers'])} existing markers")


if __name__ == "__main__":
    song = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "assets", "audio", "show16.mp3")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "out", "markers.html")
    build(song, out, os.path.join(ROOT, "assets", "show", "markers.json"))
