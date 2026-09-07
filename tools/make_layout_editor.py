#!/usr/bin/env python3
"""
make_layout_editor.py -- build the standalone yard layout editor.

    python tools/make_layout_editor.py                 # -> out/layout_editor.html
    python tools/make_layout_editor.py assets/layout.json out/layout_editor.html

Open the HTML in any browser. No server, no install. It embeds every prop
shape and the current layout.json, so it works offline in the yard.

WHAT IT DOES
  Top-down map        drag props, snap to 6 in, pan (drag empty space or
                      middle mouse), zoom (wheel), grid in feet
  Distances           select 2+ props to read the distance between them;
                      the selected prop's nearest neighbours are always shown
  Groups              recolour / reassign a prop's group from the panel
  Controllers         auto-assign 4 props per controller, neighbours together,
                      never across groups; live warnings against the GC-6004
                      limits (1024 px/port, 4096 px/unit, one prop per port)
  3D view             orbit the yard, props standing at their real height
  Save                "Export layout.json" downloads the file; put it back at
                      assets/layout.json and render. "Import" loads one.

The JSON it writes is exactly what lightshow/layout.py reads, so the Python
side (build_cards.py, multi-prop effects) sees whatever you laid out here.
"""

import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from lightshow.layout import Layout, shapes_json, PORTS, MAX_PX_PORT, MAX_PX_UNIT, STUB_PX  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Yard layout editor</title>
<style>
:root{--bg:#0d0f14;--panel:#151922;--line:#262c3a;--fg:#e6e9f0;--dim:#8a93a6;--acc:#5fb8ff;--warn:#ffb347;--err:#ff5f6d}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font:13px/1.4 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;overflow:hidden}
#app{display:grid;grid-template-columns:1fr 340px;grid-template-rows:44px 1fr;height:100%}
header{grid-column:1/3;display:flex;align-items:center;gap:10px;padding:0 12px;border-bottom:1px solid var(--line);background:var(--panel)}
header h1{font-size:14px;margin:0 12px 0 0;font-weight:600}
button,select,input{background:#1d2330;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:5px 9px;font:inherit}
button{cursor:pointer}button:hover{border-color:var(--acc)}button.on{background:var(--acc);color:#04111f;border-color:var(--acc)}
input[type=number]{width:72px}
#stage{position:relative;overflow:hidden}
canvas{display:block;position:absolute;inset:0}
canvas[hidden]{display:none}
#hud{position:absolute;left:10px;bottom:10px;color:var(--dim);font-size:12px;pointer-events:none;background:rgba(13,15,20,.75);padding:4px 8px;border-radius:6px}
#legend{position:absolute;right:10px;top:10px;background:rgba(13,15,20,.85);padding:6px 10px;border-radius:8px;border:1px solid var(--line)}
#legend div{display:flex;align-items:center;gap:6px;margin:2px 0}
.sw{width:12px;height:12px;border-radius:3px;display:inline-block}
aside{border-left:1px solid var(--line);background:var(--panel);overflow:auto;padding:10px 12px}
aside h2{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);margin:14px 0 6px}
aside h2:first-child{margin-top:0}
.row{display:flex;gap:6px;align-items:center;margin:4px 0;flex-wrap:wrap}
.row label{color:var(--dim);min-width:58px}
table{width:100%;border-collapse:collapse;font-size:12px}
td,th{padding:3px 4px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--dim);font-weight:500}
.warn{color:var(--warn)}.err{color:var(--err)}.ok{color:#6fd39a}
.mono{font-family:ui-monospace,Menlo,Consolas,monospace}
#issues div{margin:2px 0}
.tag{display:inline-block;padding:0 6px;border-radius:10px;font-size:11px;background:#1d2330;border:1px solid var(--line)}
#proplist{max-height:220px;overflow:auto;border:1px solid var(--line);border-radius:6px}
#proplist div{padding:2px 6px;cursor:pointer;display:flex;gap:6px;align-items:center}
#proplist div:hover{background:#1d2330}#proplist div.sel{background:#223449}
.hint{color:var(--dim);font-size:11px}
</style></head><body>
<div id="app">
<header>
  <h1>Yard layout</h1>
  <button id="b2d" class="on">Top-down</button><button id="b3d">3D</button>
  <span style="width:12px"></span>
  <button id="bfit">Fit</button>
  <label class="hint">snap <select id="snap"><option value="0">off</option><option value="6" selected>6 in</option><option value="12">12 in</option></select></label>
  <span style="flex:1"></span>
  <button id="bassign">Auto-assign controllers</button>
  <button id="bimport">Import layout.json</button>
  <button id="bexport">Export layout.json</button>
  <input type="file" id="file" accept=".json" hidden>
</header>
<div id="stage"><canvas id="c2"></canvas><canvas id="c3" hidden></canvas>
  <div id="legend"></div>
  <div id="hud">drag props · drag empty space to pan · wheel zoom · shift-click multi-select · R rotate 90° · M mirror · arrows nudge</div>
</div>
<aside>
  <h2>Selected prop</h2>
  <div id="sel"><span class="hint">Click a prop on the map.</span></div>
  <h2>Props <span class="hint" id="pcount"></span></h2>
  <div id="proplist"></div>
  <h2>Controllers</h2>
  <div class="hint">GC-6004: 4 ports · ≤1024 px/port · ≤4096 px/unit · empty port = 32 px stub</div>
  <table id="ctl"><thead><tr><th>Card</th><th>Group</th><th>Ports 1–4</th><th>px</th></tr></thead><tbody></tbody></table>
  <h2>Checks</h2>
  <div id="issues"></div>
</aside>
</div>
<script>
const SHAPES = __SHAPES__;
let L = __LAYOUT__;
const PORTS=__PORTS__, MAXP=__MAXP__, MAXU=__MAXU__, STUB=__STUB__;

// ------------------------------------------------------------ helpers
const $=s=>document.querySelector(s);
const HUD2='drag props · drag empty space to pan · wheel zoom · shift-click multi-select · R rotate 90° · M mirror · arrows nudge (shift = 1 ft)';
const HUD3='drag to orbit · wheel to dolly · shift-drag to pan · selection shows white';
const deg=Math.PI/180;
function shape(p){return SHAPES[p.mod];}
function gcolor(g){return (L.groups[g]&&L.groups[g].color)||'#ffffff';}
function propWorld(p){ // (n) arrays of world x,y,z in inches
  const s=shape(p), a=p.rot*deg, ca=Math.cos(a), sa=Math.sin(a), m=p.mirror?-1:1;
  const n=s.n, X=new Float32Array(n),Y=new Float32Array(n),Z=new Float32Array(n);
  for(let i=0;i<n;i++){const lx=s.lx[i]*m; X[i]=p.x+lx*ca; Y[i]=p.y+lx*sa; Z[i]=p.z+s.ly[i];}
  return {X,Y,Z,n};
}
function centre(p){const s=shape(p);return [p.x,p.y,p.z+s.h/2];}
function dist(a,b){const A=centre(a),B=centre(b);return Math.hypot(A[0]-B[0],A[1]-B[1],A[2]-B[2]);}
function fmt(inch){const ft=Math.floor(inch/12), r=Math.round(inch-ft*12);return inch>=24?`${ft}′ ${r}″`:`${inch.toFixed(0)}″`;}
function byId(id){return L.props.find(p=>p.id===id);}

// ------------------------------------------------------------ state
let sel=new Set(), view={x:0,y:0,s:1.2}, mode='2d', drag=null;
let cam={yaw:-0.6,pitch:0.45,dist:900,cx:0,cy:0,cz:30}, cdrag=null;
const c2=$('#c2'),c3=$('#c3');
function resize(){const st=$('#stage');for(const c of [c2,c3]){c.width=st.clientWidth*devicePixelRatio;c.height=st.clientHeight*devicePixelRatio;c.style.width=st.clientWidth+'px';c.style.height=st.clientHeight+'px';}draw();}
window.addEventListener('resize',resize);

// ------------------------------------------------------------ 2D map
function w2s(x,y){return [(x-view.x)*view.s+c2.width/2/devicePixelRatio,(-(y-view.y))*view.s+c2.height/2/devicePixelRatio];}
function s2w(px,py){return [(px-c2.width/2/devicePixelRatio)/view.s+view.x, -((py-c2.height/2/devicePixelRatio)/view.s)+view.y];}
function fit(){
  if(!L.props.length)return;let x0=1e9,x1=-1e9,y0=1e9,y1=-1e9;
  for(const p of L.props){const s=shape(p);x0=Math.min(x0,p.x-s.w/2);x1=Math.max(x1,p.x+s.w/2);y0=Math.min(y0,p.y-40);y1=Math.max(y1,p.y+40);}
  const W=c2.width/devicePixelRatio,H=c2.height/devicePixelRatio;
  view.s=Math.min(W/(x1-x0+80),H/(y1-y0+80));view.x=(x0+x1)/2;view.y=(y0+y1)/2;
  cam.cx=view.x;cam.cy=view.y;cam.dist=Math.max(300,(x1-x0)*0.9);draw();
}
function footprint(p){ // 4 corners of the footprint rectangle (w along rot, 10 in deep)
  const s=shape(p),a=p.rot*deg,ca=Math.cos(a),sa=Math.sin(a),hw=s.w/2,hd=5;
  return [[-hw,-hd],[hw,-hd],[hw,hd],[-hw,hd]].map(([u,v])=>[p.x+u*ca-v*sa,p.y+u*sa+v*ca]);
}
function hit(wx,wy){ // topmost prop whose card contains the point
  for(let i=L.props.length-1;i>=0;i--){const p=L.props[i],s=shape(p),a=-p.rot*deg;
    const dx=wx-p.x,dy=wy-p.y,u=dx*Math.cos(a)-dy*Math.sin(a),v=dx*Math.sin(a)+dy*Math.cos(a);
    const cardH=Math.max(18,Math.min(s.h,60)*0.5);
    if(Math.abs(u)<=s.w/2+2&&v>=-6&&v<=cardH+6)return p;}
  return null;
}
function draw2d(){
  const g=c2.getContext('2d');g.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  const W=c2.width/devicePixelRatio,H=c2.height/devicePixelRatio;
  g.fillStyle='#0d0f14';g.fillRect(0,0,W,H);
  // grid: 1 ft minor, 10 ft major
  const [wx0,wy1]=s2w(0,0),[wx1,wy0]=s2w(W,H);
  const step=view.s*12>14?12:(view.s*60>14?60:120);
  g.lineWidth=1;
  for(let x=Math.floor(wx0/step)*step;x<=wx1;x+=step){const [sx]=w2s(x,0);g.strokeStyle=(x%120===0)?'#242b3a':'#181d27';g.beginPath();g.moveTo(sx,0);g.lineTo(sx,H);g.stroke();}
  for(let y=Math.floor(wy0/step)*step;y<=wy1;y+=step){const [,sy]=w2s(0,y);g.strokeStyle=(y%120===0)?'#242b3a':'#181d27';g.beginPath();g.moveTo(0,sy);g.lineTo(W,sy);g.stroke();}
  // origin axes
  {const [ox,oy]=w2s(0,0);g.strokeStyle='#33405a';g.beginPath();g.moveTo(ox,0);g.lineTo(ox,H);g.moveTo(0,oy);g.lineTo(W,oy);g.stroke();}
  // controller markers
  for(const [cid,c] of Object.entries(L.controllers)){if(c.x==null)continue;const [sx,sy]=w2s(c.x,c.y);
    g.fillStyle='#1d2330';g.strokeStyle=gcolor(c.group);g.lineWidth=1.5;g.beginPath();g.roundRect(sx-16,sy-8,32,16,4);g.fill();g.stroke();
    g.fillStyle='#cfd6e4';g.font='10px ui-monospace,monospace';g.textAlign='center';g.textBaseline='middle';g.fillText(cid,sx,sy);
    // leader lines to its props
    g.strokeStyle=gcolor(c.group)+'55';g.lineWidth=1;
    for(const p of L.props)if(p.controller===cid){const [px,py]=w2s(p.x,p.y);g.beginPath();g.moveTo(sx,sy);g.lineTo(px,py);g.stroke();}
  }
  // props
  for(const p of L.props){
    const s=shape(p),col=gcolor(p.group),isSel=sel.has(p.id);
    const [sx,sy]=w2s(p.x,p.y);
    g.save();g.translate(sx,sy);g.rotate(-p.rot*deg);
    const w=s.w*view.s, cardH=Math.max(18,Math.min(s.h,60)*0.5)*view.s;
    // footprint line (the panel seen from above) + card with silhouette
    g.strokeStyle=col;g.lineWidth=isSel?4:2.5;g.beginPath();g.moveTo(-w/2,0);g.lineTo(w/2,0);g.stroke();
    g.fillStyle=isSel?col+'44':col+'22';g.strokeStyle=isSel?'#fff':col+'99';g.lineWidth=isSel?1.5:1;
    g.beginPath();g.roundRect(-w/2,-cardH,w,cardH,3);g.fill();g.stroke();
    // silhouette dots, scaled to fit the card
    if(w>14){const k=Math.min(w/s.w,cardH/s.h)*0.92,m=p.mirror?-1:1;g.fillStyle=col;
      const r=Math.max(0.6,Math.min(1.6,k*s.pitch_in*0.35));
      for(let i=0;i<s.n;i++){g.fillRect(s.lx[i]*m*k-r/2,-(s.ly[i]*k)-cardH*0.04-r/2,r,r);}}
    // facing tick (which way the front faces: -y locally)
    g.strokeStyle=col+'aa';g.beginPath();g.moveTo(0,0);g.lineTo(0,7);g.stroke();
    g.restore();
    if(view.s>0.35){g.fillStyle='#e6e9f0';g.font='11px system-ui';g.textAlign='center';g.textBaseline='top';
      g.fillText(p.id+(p.controller?`  ${p.controller}:${p.port}`:''),sx,sy+9);}
  }
  // distances among selected + nearest neighbours of a single selection
  const S=[...sel].map(byId).filter(Boolean);
  g.font='11px ui-monospace,monospace';g.textAlign='center';g.textBaseline='middle';
  const line=(a,b,c)=>{const [ax,ay]=w2s(a.x,a.y),[bx,by]=w2s(b.x,b.y);g.strokeStyle=c;g.setLineDash([4,4]);g.lineWidth=1;g.beginPath();g.moveTo(ax,ay);g.lineTo(bx,by);g.stroke();g.setLineDash([]);
    const t=fmt(dist(a,b));const mx=(ax+bx)/2,my=(ay+by)/2-14;g.fillStyle='#0d0f14';const tw=g.measureText(t).width+8;g.fillRect(mx-tw/2,my-8,tw,16);g.fillStyle=c;g.fillText(t,mx,my);};
  if(S.length>=2){for(let i=0;i<S.length;i++)for(let j=i+1;j<S.length;j++)line(S[i],S[j],'#ffffff');}
  else if(S.length===1){const a=S[0];const nb=L.props.filter(p=>p!==a&&p.group===a.group).map(p=>[dist(a,p),p]).sort((u,v)=>u[0]-v[0]).slice(0,3);for(const [,p] of nb)line(a,p,'#8a93a6');}
  // scale bar
  {const ft=view.s*120;g.strokeStyle='#cfd6e4';g.lineWidth=2;g.beginPath();g.moveTo(W-ft-14,H-14);g.lineTo(W-14,H-14);g.stroke();g.fillStyle='#cfd6e4';g.font='11px system-ui';g.textAlign='right';g.textBaseline='bottom';g.fillText('10 ft',W-14,H-18);}
}

// ------------------------------------------------------------ 3D view
function project(x,y,z){ // camera orbiting (cx,cy,cz)
  const dx=x-cam.cx,dy=y-cam.cy,dz=z-cam.cz;
  const cy=Math.cos(cam.yaw),sy=Math.sin(cam.yaw),cp=Math.cos(cam.pitch),sp=Math.sin(cam.pitch);
  // yaw about z, then pitch about x
  const x1=dx*cy-dy*sy, y1=dx*sy+dy*cy;
  const y2=y1*cp-dz*sp, z2=y1*sp+dz*cp;   // z2 = up on screen
  const depth=y2+cam.dist; if(depth<=1)return null;
  const f=(c3.height/devicePixelRatio)*1.1/depth;
  return [x1*f+c3.width/devicePixelRatio/2, -z2*f+c3.height/devicePixelRatio/2, depth];
}
function draw3d(){
  const g=c3.getContext('2d');g.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  const W=c3.width/devicePixelRatio,H=c3.height/devicePixelRatio;
  g.fillStyle='#07080c';g.fillRect(0,0,W,H);
  // ground grid 5 ft
  let x0=1e9,x1=-1e9,y0=1e9,y1=-1e9;for(const p of L.props){x0=Math.min(x0,p.x);x1=Math.max(x1,p.x);y0=Math.min(y0,p.y);y1=Math.max(y1,p.y);}
  x0=Math.floor((x0-120)/60)*60;x1=Math.ceil((x1+120)/60)*60;y0=Math.floor((y0-240)/60)*60;y1=Math.ceil((y1+240)/60)*60;
  g.strokeStyle='#1a2030';g.lineWidth=1;
  const seg=(a,b)=>{const A=project(...a),B=project(...b);if(A&&B){g.beginPath();g.moveTo(A[0],A[1]);g.lineTo(B[0],B[1]);g.stroke();}};
  for(let x=x0;x<=x1;x+=60)seg([x,y0,0],[x,y1,0]);for(let y=y0;y<=y1;y+=60)seg([x0,y,0],[x1,y,0]);
  // pixels, painter-sorted by depth (per prop, cheap)
  const items=[];for(const p of L.props){const c=centre(p);const P=project(c[0],c[1],c[2]);if(P)items.push([P[2],p]);}
  items.sort((a,b)=>b[0]-a[0]);
  for(const [,p] of items){const w=propWorld(p),col=gcolor(p.group),isSel=sel.has(p.id);
    g.fillStyle=isSel?'#ffffff':col;
    for(let i=0;i<w.n;i++){const P=project(w.X[i],w.Y[i],w.Z[i]);if(!P)continue;const r=Math.max(0.8,140/P[2]);g.fillRect(P[0]-r/2,P[1]-r/2,r,r);}
    const P=project(p.x,p.y,p.z-6);if(P&&cam.dist<2500){g.fillStyle=col;g.font='10px system-ui';g.textAlign='center';g.fillText(p.id,P[0],P[1]);}
  }
}
function draw(){if(mode==='2d')draw2d();else draw3d();}

// ------------------------------------------------------------ interaction
function snapv(v){const s=+$('#snap').value;return s?Math.round(v/s)*s:Math.round(v*10)/10;}
c2.addEventListener('mousedown',e=>{const r=c2.getBoundingClientRect();const [wx,wy]=s2w(e.clientX-r.left,e.clientY-r.top);const p=hit(wx,wy);
  if(p&&e.button===0){if(e.shiftKey){sel.has(p.id)?sel.delete(p.id):sel.add(p.id);}else if(!sel.has(p.id)){sel=new Set([p.id]);}
    drag={kind:'move',wx,wy,start:[...sel].map(id=>{const q=byId(id);return [id,q.x,q.y];})};}
  else{drag={kind:'pan',px:e.clientX,py:e.clientY,vx:view.x,vy:view.y};if(!e.shiftKey&&e.button===0){sel.clear();}}
  refresh();});
window.addEventListener('mousemove',e=>{if(!drag)return;
  if(drag.kind==='pan'){view.x=drag.vx-(e.clientX-drag.px)/view.s;view.y=drag.vy+(e.clientY-drag.py)/view.s;draw();}
  else if(drag.kind==='move'){const r=c2.getBoundingClientRect();const [wx,wy]=s2w(e.clientX-r.left,e.clientY-r.top);
    for(const [id,x,y] of drag.start){const q=byId(id);q.x=snapv(x+wx-drag.wx);q.y=snapv(y+wy-drag.wy);}drag.moved=true;draw();selPanel();}
  else if(drag.kind==='orbit'){if(e.shiftKey){const k=cam.dist/600;cam.cx-=(e.clientX-drag.px)*k*Math.cos(cam.yaw);cam.cy+=(e.clientX-drag.px)*k*Math.sin(cam.yaw);cam.cz+=(e.clientY-drag.py)*k;}
    else{cam.yaw+=(e.clientX-drag.px)*0.006;cam.pitch=Math.max(0.05,Math.min(1.5,cam.pitch+(e.clientY-drag.py)*0.006));}drag.px=e.clientX;drag.py=e.clientY;draw();}
});
window.addEventListener('mouseup',()=>{if(drag&&drag.kind==='move'&&drag.moved)refresh();drag=null;});
c2.addEventListener('wheel',e=>{e.preventDefault();const r=c2.getBoundingClientRect();const [wx,wy]=s2w(e.clientX-r.left,e.clientY-r.top);
  view.s*=Math.exp(-e.deltaY*0.0015);view.s=Math.max(0.05,Math.min(20,view.s));const [nx,ny]=s2w(e.clientX-r.left,e.clientY-r.top);view.x+=wx-nx;view.y+=wy-ny;draw();},{passive:false});
c3.addEventListener('mousedown',e=>{drag={kind:'orbit',px:e.clientX,py:e.clientY};});
c3.addEventListener('wheel',e=>{e.preventDefault();cam.dist*=Math.exp(e.deltaY*0.0015);cam.dist=Math.max(60,Math.min(20000,cam.dist));draw();},{passive:false});
window.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'||e.target.tagName==='SELECT')return;const S=[...sel].map(byId);if(!S.length)return;
  const nud=e.shiftKey?12:1;let done=true;
  for(const p of S){switch(e.key){case 'r':case 'R':p.rot=(p.rot+90)%360;break;case 'm':case 'M':p.mirror=!p.mirror;break;
    case 'ArrowLeft':p.x-=nud;break;case 'ArrowRight':p.x+=nud;break;case 'ArrowUp':p.y+=nud;break;case 'ArrowDown':p.y-=nud;break;default:done=false;}}
  if(done){e.preventDefault();refresh();}});
$('#b2d').onclick=()=>{mode='2d';c2.hidden=false;c3.hidden=true;$('#hud').textContent=HUD2;$('#b2d').classList.add('on');$('#b3d').classList.remove('on');draw();};
$('#b3d').onclick=()=>{mode='3d';c2.hidden=true;c3.hidden=false;$('#hud').textContent=HUD3;$('#b3d').classList.add('on');$('#b2d').classList.remove('on');draw();};
$('#bfit').onclick=fit;
$('#snap').onchange=draw;

// ------------------------------------------------------------ controllers
function rigs(){const R={};for(const cid of Object.keys(L.controllers))R[cid]={ports:Array(PORTS).fill(null),px:0};
  for(const p of L.props){if(!p.controller)continue;R[p.controller]=R[p.controller]||{ports:Array(PORTS).fill(null),px:0};
    const r=R[p.controller];if(p.port>=1&&p.port<=PORTS){if(r.ports[p.port-1])r.dup=(r.dup||[]).concat([[p.port,r.ports[p.port-1].id,p.id]]);r.ports[p.port-1]=p;}r.px+=shape(p).n;}
  return R;}
function validate(){const out=[];const R=rigs();
  for(const p of L.props){const n=shape(p).n;if(!L.groups[p.group])out.push(['err',`${p.id}: group '${p.group}' not defined`]);
    if(n>MAXP)out.push(['err',`${p.id}: ${n} px exceeds ${MAXP}/port`]);
    if(!p.controller)out.push(['warn',`${p.id}: not assigned to a controller`]);
    else if(!(p.port>=1&&p.port<=PORTS))out.push(['err',`${p.id}: port ${p.port} not in 1..${PORTS}`]);}
  for(const [cid,r] of Object.entries(R)){if(r.px>MAXU)out.push(['err',`${cid}: ${r.px} px exceeds ${MAXU}/unit`]);
    for(const [port,a,b] of (r.dup||[]))out.push(['err',`${cid} port ${port}: both ${a} and ${b}`]);
    const gs=new Set(r.ports.filter(Boolean).map(p=>p.group));if(gs.size>1)out.push(['warn',`${cid}: spans groups ${[...gs].join(', ')}`]);
    if(r.px===0)out.push(['warn',`${cid}: declared but drives nothing`]);}
  return out;}
function autoAssign(group){ // mirrors Layout.auto_assign(): sort along x, pack 4, never across groups
  const groups=group?[group]:Object.keys(L.groups);
  for(const gid of groups){const g=L.groups[gid]||{},prefix=g.prefix||gid.slice(0,2).toUpperCase();
    const ps=L.props.filter(p=>p.group===gid).sort((a,b)=>a.x-b.x||a.y-b.y);
    for(const p of ps){p.controller=null;p.port=null;}
    for(const cid of Object.keys(L.controllers))if(L.controllers[cid].group===gid)delete L.controllers[cid];
    let n=0,cur=null,px=0,port=PORTS+1;
    for(const p of ps){const k=shape(p).n;if(k>MAXP)continue;
      if(cur===null||port>PORTS||px+k>MAXU){n++;cur=`${prefix}${String(n).padStart(2,'0')}`;px=0;port=1;L.controllers[cur]={model:'GC-6004',dmx_addr:1,group:gid};}
      p.controller=cur;p.port=port++;px+=k;}
    for(const cid of new Set(ps.map(p=>p.controller).filter(Boolean))){const mine=ps.filter(p=>p.controller===cid);
      L.controllers[cid].x=Math.round(mine.reduce((s,p)=>s+p.x,0)/mine.length*10)/10;L.controllers[cid].y=Math.round((mine.reduce((s,p)=>s+p.y,0)/mine.length-36)*10)/10;}
  }
  refresh();
}
$('#bassign').onclick=()=>{if(confirm('Re-assign ALL controllers and ports from the current positions? Existing assignments are replaced.'))autoAssign(null);};

// ------------------------------------------------------------ panels
function legend(){$('#legend').innerHTML=Object.entries(L.groups).map(([id,g])=>{const ps=L.props.filter(p=>p.group===id);
  return `<div><span class="sw" style="background:${g.color||'#fff'}"></span>${g.label||id} <span class="hint">${ps.length} props · ${ps.reduce((s,p)=>s+shape(p).n,0)} px</span></div>`;}).join('');}
function selPanel(){const S=[...sel].map(byId).filter(Boolean);const el=$('#sel');
  if(!S.length){el.innerHTML='<span class="hint">Click a prop on the map.</span>';return;}
  if(S.length>1){el.innerHTML=`<div>${S.length} selected: ${S.map(p=>p.id).join(', ')}</div><div class="hint">Distances are drawn on the map. R rotates all, arrows nudge all.</div>
    <div class="row"><label>group</label><select id="gsel"><option value="">— change all —</option>${Object.entries(L.groups).map(([id,g])=>`<option value="${id}">${g.label||id}</option>`).join('')}</select></div>`;
    $('#gsel').onchange=e=>{if(e.target.value){for(const p of S)p.group=e.target.value;refresh();}};return;}
  const p=S[0],s=shape(p);
  const gopts=Object.entries(L.groups).map(([id,g])=>`<option value="${id}"${id===p.group?' selected':''}>${g.label||id}</option>`).join('');
  const copts=['<option value="">— none —</option>'].concat(Object.keys(L.controllers).sort().map(c=>`<option${c===p.controller?' selected':''}>${c}</option>`)).join('');
  const popts=['<option value="">—</option>'].concat([1,2,3,4].map(k=>`<option${k===p.port?' selected':''}>${k}</option>`)).join('');
  el.innerHTML=`<div class="row"><b>${p.id}</b> <span class="tag mono">${p.mod}</span> <span class="hint">${s.n} px · ${s.w.toFixed(0)}×${s.h.toFixed(0)} in · pitch ${s.pitch_in.toFixed(2)} in</span></div>
  <div class="row"><label>label</label><input id="f_label" value="${p.label||''}" style="flex:1"></div>
  <div class="row"><label>group</label><select id="f_group">${gopts}</select></div>
  <div class="row"><label>x / y</label><input type="number" id="f_x" value="${p.x}" step="1"><input type="number" id="f_y" value="${p.y}" step="1"><span class="hint">in</span></div>
  <div class="row"><label>bottom z</label><input type="number" id="f_z" value="${p.z}" step="1"><label>rot</label><input type="number" id="f_rot" value="${p.rot}" step="15">°</div>
  <div class="row"><label>mirror</label><input type="checkbox" id="f_mirror"${p.mirror?' checked':''}><span class="hint">flip left–right (左/右 pairs)</span></div>
  <div class="row"><label>controller</label><select id="f_ctl">${copts}</select><label>port</label><select id="f_port">${popts}</select></div>
  <div class="row"><button id="f_newctl">New controller for this prop</button><button id="f_ctr">Centre view</button></div>`;
  const bind=(id,fn)=>{$('#'+id).onchange=e=>{fn(e.target);refresh();};};
  bind('f_label',t=>p.label=t.value);bind('f_group',t=>p.group=t.value);
  bind('f_x',t=>p.x=+t.value);bind('f_y',t=>p.y=+t.value);bind('f_z',t=>p.z=+t.value);bind('f_rot',t=>p.rot=((+t.value)%360+360)%360);
  bind('f_mirror',t=>p.mirror=t.checked);
  bind('f_ctl',t=>{p.controller=t.value||null;if(!p.controller)p.port=null;else if(!p.port){const used=new Set(L.props.filter(q=>q.controller===p.controller&&q!==p).map(q=>q.port));p.port=[1,2,3,4].find(k=>!used.has(k))||1;}});
  bind('f_port',t=>p.port=t.value?+t.value:null);
  $('#f_newctl').onclick=()=>{const g=L.groups[p.group]||{},prefix=g.prefix||p.group.slice(0,2).toUpperCase();let n=1;while(L.controllers[`${prefix}${String(n).padStart(2,'0')}`])n++;
    const cid=`${prefix}${String(n).padStart(2,'0')}`;L.controllers[cid]={model:'GC-6004',dmx_addr:1,group:p.group,x:p.x,y:p.y-36};p.controller=cid;p.port=1;refresh();};
  $('#f_ctr').onclick=()=>{view.x=p.x;view.y=p.y;cam.cx=p.x;cam.cy=p.y;draw();};
}
function propList(){const el=$('#proplist');const ps=[...L.props].sort((a,b)=>a.group.localeCompare(b.group)||a.x-b.x);
  el.innerHTML=ps.map(p=>`<div data-id="${p.id}" class="${sel.has(p.id)?'sel':''}"><span class="sw" style="background:${gcolor(p.group)}"></span><b>${p.id}</b><span class="hint" style="flex:1">${p.label||''}</span><span class="mono hint">${p.controller?p.controller+':'+p.port:'—'}</span></div>`).join('');
  $('#pcount').textContent=`${L.props.length} · ${L.props.reduce((s,p)=>s+shape(p).n,0)} px`;
  el.querySelectorAll('div[data-id]').forEach(d=>d.onclick=e=>{const id=d.dataset.id;if(e.shiftKey){sel.has(id)?sel.delete(id):sel.add(id);}else sel=new Set([id]);refresh();});}
function ctlTable(){const R=rigs();const tb=$('#ctl tbody');
  tb.innerHTML=Object.keys(R).sort().map(cid=>{const r=R[cid],g=(L.controllers[cid]||{}).group||[...new Set(r.ports.filter(Boolean).map(p=>p.group))].join('+');
    const cells=r.ports.map((p,i)=>p?`<span title="${shape(p).n} px">${p.id}</span>`:`<span class="hint">stub</span>`).join(' · ');
    const cls=r.px>MAXU?'err':(r.px>MAXU*0.9?'warn':'');
    return `<tr><td class="mono"><span class="sw" style="background:${gcolor(g)}"></span> ${cid}</td><td class="hint">${(L.groups[g]||{}).label||g||''}</td><td>${cells}</td><td class="mono ${cls}">${r.px}</td></tr>`;}).join('');}
function issues(){const v=validate();$('#issues').innerHTML=v.length?v.map(([k,m])=>`<div class="${k}">${k==='err'?'✖':'▲'} ${m}</div>`).join(''):'<div class="ok">✔ layout is exportable: every prop on a port, all limits met</div>';}
function refresh(){legend();selPanel();propList();ctlTable();issues();draw();}

// ------------------------------------------------------------ import / export
function exportJSON(){const d={version:L.version||1,units:'in',notes:L.notes||'',groups:L.groups,controllers:L.controllers,
  props:L.props.map(p=>({id:p.id,mod:p.mod,label:p.label,group:p.group,x:+p.x.toFixed(2),y:+p.y.toFixed(2),z:+p.z.toFixed(2),rot:+p.rot.toFixed(2),mirror:!!p.mirror,controller:p.controller||null,port:p.port||null}))};
  const blob=new Blob([JSON.stringify(d,null,1)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='layout.json';a.click();}
$('#bexport').onclick=exportJSON;
$('#bimport').onclick=()=>$('#file').click();
$('#file').onchange=e=>{const f=e.target.files[0];if(!f)return;const rd=new FileReader();rd.onload=()=>{try{const d=JSON.parse(rd.result);
  const missing=(d.props||[]).filter(p=>!SHAPES[p.mod]).map(p=>p.mod);if(missing.length){alert('These .mod shapes are not embedded in this editor -- rebuild it with make editor:\n'+missing.join(', '));return;}
  L=d;sel.clear();refresh();fit();}catch(err){alert('Could not read layout.json: '+err);}};rd.readAsText(f);e.target.value='';};
window.addEventListener('beforeunload',e=>{/* nothing persists: remind */});

resize();refresh();fit();
</script></body></html>
"""


def build(layout_path, out_path):
    L = Layout.load(layout_path)
    html = (HTML.replace("__SHAPES__", json.dumps(shapes_json(L), separators=(",", ":")))
                .replace("__LAYOUT__", json.dumps(L.to_json(), ensure_ascii=False))
                .replace("__PORTS__", str(PORTS)).replace("__MAXP__", str(MAX_PX_PORT))
                .replace("__MAXU__", str(MAX_PX_UNIT)).replace("__STUB__", str(STUB_PX)))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"{out_path}  {len(html)/1e6:.1f} MB  {len(L.props)} props embedded")


if __name__ == "__main__":
    lp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "assets", "layout.json")
    op = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "out", "layout_editor.html")
    build(lp, op)
