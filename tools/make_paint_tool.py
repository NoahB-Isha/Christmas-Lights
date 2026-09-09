#!/usr/bin/env python3
"""
make_paint_tool.py -- standalone HTML for painting pixel REGIONS on a prop.

    python tools/make_paint_tool.py            # -> out/paint.html (all props embedded)

Open, pick a prop, and split it into named groups: Santa's hat / face /
coat / boots / hands, the bell and its ribbon. Effects can then address
those groups ("only the hat", "coat then boots", "ribbon twinkles").

HOW TO SELECT
  click a bulb            toggle it
  drag on empty space     lasso (freehand) -- everything inside is selected
  shift+click             flood-select: the clicked bulb and every bulb reachable
                          through neighbours within 1.6 x pitch that is not yet
                          in a region (grabs one feature, stops at gaps)
  W then two clicks       wire range: select every bulb between two clicks in
                          wire order (features are usually wired in one run)
  Enter / "Add region"    name the selection, pick its painted colour
  E                       toggle "show existing regions" colouring
  1-9                     jump the selection into region N (re-assign)

Export writes assets/paint/<prop>.json (one file per prop; drop it in the
repo). Import loads one. Existing files are embedded at build time.
"""

import glob, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from lightshow.formats.props import load_mod, UNITS_PER_INCH   # noqa: E402
from lightshow import regions as R                              # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Prop paint</title>
<style>
:root{--bg:#0d0f14;--panel:#151922;--line:#262c3a;--fg:#e6e9f0;--dim:#8a93a6;--acc:#5fb8ff}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font:13px system-ui,sans-serif;overflow:hidden}
#app{display:grid;grid-template-columns:1fr 320px;grid-template-rows:44px 1fr;height:100%}
header{grid-column:1/3;display:flex;gap:10px;align-items:center;padding:0 12px;background:var(--panel);border-bottom:1px solid var(--line)}
button,input,select{background:#1d2330;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:5px 9px;font:inherit}
button.on{background:var(--acc);color:#04111f}
#stage{position:relative}canvas{position:absolute;inset:0;width:100%;height:100%}
aside{border-left:1px solid var(--line);background:var(--panel);padding:10px 12px;overflow:auto}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);margin:14px 0 6px}
.row{display:flex;gap:6px;align-items:center;margin:4px 0;flex-wrap:wrap}
.hint{color:var(--dim);font-size:11px}.mono{font-family:ui-monospace,monospace}
#regions div.r{display:flex;gap:6px;align-items:center;padding:3px 4px;border-radius:4px;cursor:pointer}
#regions div.r:hover{background:#1d2330}#regions div.r.sel{background:#223449}
.sw{width:14px;height:14px;border-radius:3px;border:1px solid #0006}
#hud{position:absolute;left:10px;bottom:10px;color:var(--dim);font-size:12px;background:rgba(13,15,20,.75);padding:4px 8px;border-radius:6px;pointer-events:none}
</style></head><body><div id="app">
<header><b>Prop paint</b>
<select id="prop"></select>
<span class="hint" id="pinfo"></span>
<span style="flex:1"></span>
<button id="bwire" title="show wire order as colour">wire</button>
<button id="bexist" class="on" title="show existing regions">regions (E)</button>
<button id="bimport">Import</button><input type="file" id="file" accept=".json" hidden>
<button id="bexport">Export &lt;prop&gt;.json</button></header>
<div id="stage"><canvas id="c"></canvas><div id="hud"></div></div>
<aside>
<h2>Selection <span class="hint" id="selcount"></span></h2>
<div class="row"><input id="rname" placeholder="region name (hat, coat, ribbon…)" style="flex:1"><input type="color" id="rcolor" value="#d0232a"></div>
<div class="row"><button id="badd">Add region (Enter)</button><button id="bclear">Clear selection</button><button id="bwr">Wire range (W)</button></div>
<div class="hint">click toggles · drag = lasso · shift+click = flood one feature · W then two clicks = wire range · 1–9 = move selection into region N</div>
<h2>Regions</h2>
<div id="regions"></div>
<div class="row"><button id="bdel">Delete region</button><button id="bsuggest">Auto-suggest (wire runs)</button></div>
<h2>Notes</h2>
<div class="hint">Pixels not in any region are the implicit region <b>rest</b>. Colour = the prop's painted colour there; the Drawn theme uses it, and it is a hint for AI. Export puts the file at assets/paint/&lt;prop&gt;.json.</div>
</aside></div>
<script>
const PROPS=__PROPS__;   // {stem: {mod, n, x:[...], y:[...], pitch, regions:{name:{color,pixels}} , suggest:[[...],...]}}
const $=s=>document.querySelector(s);
const sel=$('#prop');for(const k of Object.keys(PROPS).sort((a,b)=>a.localeCompare(b,'zh'))){const o=document.createElement('option');o.value=k;o.textContent=k;sel.appendChild(o);}
let cur=Object.keys(PROPS).sort()[0], P=PROPS[cur], selected=new Set(), showWire=false, showExist=true, wireMode=0, wireA=null, lasso=null, selReg=null;
const c=$('#c');
function load(k){cur=k;P=PROPS[k];selected.clear();selReg=null;$('#pinfo').textContent=`${P.mod} · ${P.n} px · pitch ${P.pitch.toFixed(2)} in`;draw();listRegions();}
sel.onchange=e=>load(e.target.value);
function view(){const r=c.getBoundingClientRect();const W=r.width,H=r.height;const xs=P.x,ys=P.y;const x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
  const s=Math.min((W-80)/Math.max(1,x1-x0),(H-80)/Math.max(1,y1-y0));return {W,H,s,ox:W/2-(x0+x1)/2*s,oy:H/2+(y0+y1)/2*s};}
function toScreen(i,v){return [v.ox+P.x[i]*v.s, v.oy-P.y[i]*v.s];}
function regionOf(i){for(const [n,r] of Object.entries(P.regions)){if(r.pixels.includes(i))return n;}return null;}
function draw(){const r=c.getBoundingClientRect();c.width=r.width*devicePixelRatio;c.height=r.height*devicePixelRatio;const g=c.getContext('2d');g.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  const v=view();g.fillStyle='#0d0f14';g.fillRect(0,0,v.W,v.H);
  const rad=Math.max(3,P.pitch*v.s*0.28);
  // wire path faint
  g.strokeStyle='#1f2636';g.lineWidth=1;g.beginPath();for(let i=0;i<P.n;i++){const [x,y]=toScreen(i,v);i?g.lineTo(x,y):g.moveTo(x,y);}g.stroke();
  for(let i=0;i<P.n;i++){const [x,y]=toScreen(i,v);let col='#6b7385';
    const rn=regionOf(i);
    if(showWire)col=`hsl(${i/P.n*300},85%,55%)`;else if(showExist&&rn)col=P.regions[rn].color;
    g.fillStyle=col;g.beginPath();g.arc(x,y,rad,0,6.283);g.fill();
    if(selected.has(i)){g.strokeStyle='#fff';g.lineWidth=2;g.beginPath();g.arc(x,y,rad+2.5,0,6.283);g.stroke();}
    if(selReg&&rn===selReg){g.strokeStyle=P.regions[rn].color;g.lineWidth=1.5;g.beginPath();g.arc(x,y,rad+4,0,6.283);g.stroke();}
    if(wireMode&&wireA===i){g.strokeStyle='#ffb347';g.lineWidth=3;g.beginPath();g.arc(x,y,rad+5,0,6.283);g.stroke();}}
  if(lasso&&lasso.length>1){g.strokeStyle='#5fb8ff';g.lineWidth=1.5;g.setLineDash([5,4]);g.beginPath();lasso.forEach(([x,y],k)=>k?g.lineTo(x,y):g.moveTo(x,y));g.closePath();g.stroke();g.setLineDash([]);}
  $('#selcount').textContent=selected.size?`${selected.size} px`:'';
  $('#hud').textContent=wireMode?(wireA==null?'wire range: click the FIRST bulb':'wire range: click the LAST bulb'):'click · drag lasso · shift+click flood · W wire range';}
function nearest(mx,my){const v=view();let best=-1,bd=1e9;for(let i=0;i<P.n;i++){const [x,y]=toScreen(i,v);const d=Math.hypot(x-mx,y-my);if(d<bd){bd=d;best=i;}}return bd<Math.max(8,P.pitch*v.s*0.6)?best:-1;}
function flood(i){const out=new Set([i]);const q=[i];const lim=1.6*P.pitch;while(q.length){const a=q.pop();for(let b=0;b<P.n;b++){if(out.has(b)||regionOf(b))continue;if(Math.hypot(P.x[a]-P.x[b],P.y[a]-P.y[b])<=lim){out.add(b);q.push(b);}}}return out;}
function inPoly(x,y,poly){let ins=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){const [xi,yi]=poly[i],[xj,yj]=poly[j];if(((yi>y)!==(yj>y))&&(x<(xj-xi)*(y-yi)/(yj-yi)+xi))ins=!ins;}return ins;}
c.addEventListener('mousedown',e=>{const r=c.getBoundingClientRect();const mx=e.clientX-r.left,my=e.clientY-r.top;const i=nearest(mx,my);
  if(wireMode){if(i<0)return;if(wireA==null){wireA=i;}else{const a=Math.min(wireA,i),b=Math.max(wireA,i);for(let k=a;k<=b;k++)selected.add(k);wireMode=0;wireA=null;$('#bwr').classList.remove('on');}draw();return;}
  if(i>=0){if(e.shiftKey){for(const k of flood(i))selected.add(k);}else{selected.has(i)?selected.delete(i):selected.add(i);}draw();return;}
  lasso=[[mx,my]];});
window.addEventListener('mousemove',e=>{if(!lasso)return;const r=c.getBoundingClientRect();lasso.push([e.clientX-r.left,e.clientY-r.top]);draw();});
window.addEventListener('mouseup',e=>{if(!lasso)return;if(lasso.length>5){const v=view();for(let i=0;i<P.n;i++){const [x,y]=toScreen(i,v);if(inPoly(x,y,lasso))selected.add(i);}}lasso=null;draw();});
function listRegions(){const el=$('#regions');el.innerHTML=Object.entries(P.regions).map(([n,r])=>`<div class="r ${n===selReg?'sel':''}" data-n="${n}"><span class="sw" style="background:${r.color}"></span><b>${n}</b><span class="hint">${r.pixels.length} px</span></div>`).join('')||'<div class="hint">none yet</div>';
  el.querySelectorAll('.r').forEach(d=>d.onclick=()=>{selReg=d.dataset.n;$('#rname').value=selReg;$('#rcolor').value=P.regions[selReg].color;listRegions();draw();});}
function addRegion(){const name=$('#rname').value.trim();if(!name||!selected.size)return;const col=$('#rcolor').value;
  for(const [n,r] of Object.entries(P.regions))r.pixels=r.pixels.filter(i=>!selected.has(i));      // a pixel lives in one region
  const ex=P.regions[name];P.regions[name]={color:col,pixels:[...(ex?ex.pixels:[]),...selected].sort((a,b)=>a-b)};
  for(const n of Object.keys(P.regions))if(!P.regions[n].pixels.length)delete P.regions[n];
  selected.clear();selReg=name;$('#rname').value='';listRegions();draw();}
$('#badd').onclick=addRegion;$('#bclear').onclick=()=>{selected.clear();draw();};
$('#bdel').onclick=()=>{if(selReg&&confirm(`delete region "${selReg}"?`)){delete P.regions[selReg];selReg=null;listRegions();draw();}};
$('#bwr').onclick=()=>{wireMode=1;wireA=null;$('#bwr').classList.add('on');draw();};
$('#bwire').onclick=()=>{showWire=!showWire;$('#bwire').classList.toggle('on',showWire);draw();};
$('#bexist').onclick=()=>{showExist=!showExist;$('#bexist').classList.toggle('on',showExist);draw();};
$('#bsuggest').onclick=()=>{if(!confirm('Replace regions with the auto-suggested wire runs?'))return;P.regions={};const pal=['#d0232a','#f2c9a0','#2b8a3e','#e8b04b','#5fb8ff','#ffffff','#c77dff'];P.suggest.forEach((run,k)=>{P.regions[`run${k+1}`]={color:pal[k%pal.length],pixels:run};});listRegions();draw();};
window.addEventListener('keydown',e=>{if(['INPUT','SELECT'].includes(e.target.tagName)){if(e.key==='Enter')addRegion();return;}
  if(e.key==='Enter')addRegion();else if(e.key==='w'||e.key==='W')$('#bwr').click();else if(e.key==='e'||e.key==='E')$('#bexist').click();
  else if(e.key>='1'&&e.key<='9'){const names=Object.keys(P.regions);const n=names[+e.key-1];if(n&&selected.size){$('#rname').value=n;$('#rcolor').value=P.regions[n].color;addRegion();}}
  else if(e.key==='Escape'){selected.clear();wireMode=0;wireA=null;$('#bwr').classList.remove('on');draw();}});
$('#bexport').onclick=()=>{const d={mod:P.mod,regions:P.regions};const blob=new Blob([JSON.stringify(d,null,1)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=cur+'.json';a.click();};
$('#bimport').onclick=()=>$('#file').click();$('#file').onchange=e=>{const f=e.target.files[0];if(!f)return;const rd=new FileReader();rd.onload=()=>{try{const d=JSON.parse(rd.result);P.regions=d.regions||{};listRegions();draw();}catch(err){alert(err);}};rd.readAsText(f);e.target.value='';};
window.addEventListener('resize',draw);
sel.value=cur;load(cur);
</script></body></html>
"""


def build(out_path):
    props = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "assets", "props", "*.mod"))):
        p = load_mod(path)
        st = R.stem(path)
        xs = [round(x / UNITS_PER_INCH, 2) for x, y in p.xy]
        ys = [round(y / UNITS_PER_INCH, 2) for x, y in p.xy]
        props[st] = {"mod": os.path.basename(path), "n": len(p), "x": xs, "y": ys,
                     "pitch": round(p.pitch_inches(), 3), "regions": R.load(path),
                     "suggest": [r.tolist() for r in R.suggest(p.xy)]}
    html = HTML.replace("__PROPS__", json.dumps(props, ensure_ascii=False, separators=(",", ":")))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    painted = sum(1 for v in props.values() if v["regions"])
    print(f"{out_path}  {len(html)/1e6:.1f} MB  {len(props)} props ({painted} already painted)")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "paint.html"))
