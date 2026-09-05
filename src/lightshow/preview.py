#!/usr/bin/env python3
"""
preview.py -- turn any layout file into a standalone interactive HTML viewer.

    python -m lightshow.preview <file-or-dir> [out.html]

Accepts .mod, .moc, Colorloong .xml, or a directory of .mod files. Writes a
single self-contained HTML file: no server, no build step, no install.
Opens in Safari or Chrome on either machine, which is the point --
cross-platform from day one.

Effects run live in JS against the real pixel coordinates, so what you see
is the actual spatial evaluation the renderer will do, not a mock-up.
"""

import json, os, sys
from . import rig

HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__NAME__ — layout preview</title>
<style>
  :root{
    --void:#0A0E1A; --panel:#131A2B; --line:#24304A;
    --text:#C9D4E8; --dim:#6B7A96; --instr:#7FD4E8;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:var(--void);color:var(--text);
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
    font-variant-numeric:tabular-nums;overflow:hidden}
  #app{display:grid;grid-template-columns:232px 1fr;height:100%}
  aside{background:var(--panel);border-right:1px solid var(--line);
    display:flex;flex-direction:column;min-height:0}
  aside h1{font-size:15px;font-weight:600;letter-spacing:-.01em;
    margin:0;padding:16px 16px 4px}
  aside .meta{padding:0 16px 14px;color:var(--dim);font-size:12.5px;line-height:1.5}
  #ports{overflow-y:auto;flex:1;padding:4px 8px 12px;min-height:0}
  .port{display:flex;align-items:center;gap:9px;padding:6px 8px;border-radius:5px;
    cursor:pointer;font-size:13px;line-height:1.2}
  .port:hover{background:#1B2438}
  .port.off{opacity:.34}
  .port .sw{width:9px;height:9px;border-radius:50%;flex:none}
  .port .n{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .port .c{color:var(--dim);font-size:12px}
  .port.empty .n{color:var(--dim);font-style:italic}
  main{position:relative;min-width:0;display:flex;flex-direction:column}
  canvas{flex:1;display:block;width:100%;min-height:0}
  #bar{border-top:1px solid var(--line);background:var(--panel);
    display:flex;align-items:center;gap:14px;padding:10px 16px;flex-wrap:wrap}
  button,select{background:#1C2740;color:var(--text);border:1px solid var(--line);
    border-radius:6px;padding:7px 13px;font:inherit;font-size:13px;cursor:pointer}
  button:hover,select:hover{border-color:var(--instr)}
  button:focus-visible,select:focus-visible,input:focus-visible{
    outline:2px solid var(--instr);outline-offset:2px}
  #play{min-width:74px;color:var(--instr);border-color:#2F4260}
  label{display:flex;align-items:center;gap:7px;font-size:12.5px;color:var(--dim)}
  input[type=range]{width:118px;accent-color:var(--instr)}
  #read{margin-left:auto;font-size:12.5px;color:var(--dim)}
  #read b{color:var(--text);font-weight:600}
  #tip{position:absolute;pointer-events:none;background:#0D1424;
    border:1px solid var(--line);border-radius:5px;padding:5px 8px;
    font-size:12px;opacity:0;transition:opacity .12s}
  @media (prefers-reduced-motion:reduce){#tip{transition:none}}
</style></head><body>
<div id="app">
  <aside>
    <h1>__NAME__</h1>
    <div class="meta" id="meta"></div>
    <div id="ports"></div>
  </aside>
  <main>
    <canvas id="cv"></canvas>
    <div id="bar">
      <button id="play">Pause</button>
      <select id="fx"></select>
      <label>Speed <input type="range" id="spd" min="0.1" max="3" step="0.1" value="1"></label>
      <label>Glow <input type="range" id="glow" min="0" max="3" step="0.1" value="1.4"></label>
      <label><input type="checkbox" id="wire"> Wire order</label>
      <div id="read"></div>
    </div>
  </main>
</div>
<div id="tip"></div>
<script>
const RIG = __RIG__;
const cv=document.getElementById('cv'), ctx=cv.getContext('2d');
let frame=0, playing=true, hover=null;

/* ---- effects: (u,v,t,i,n) -> [r,g,b] 0..1
   u,v are rig coordinates mapped to -1..1 on the longest axis, y up.
   i is the pixel's index within its port, n the port length. ---- */
function hsv(h,s,v){h=((h%1)+1)%1;const i=Math.floor(h*6)%6,f=h*6-Math.floor(h*6),
  p=v*(1-s),q=v*(1-s*f),t=v*(1-s*(1-f));
  return [[v,t,p],[q,v,p],[p,v,t],[p,q,v],[t,p,v],[v,p,q]][i];}
const FX={
 "Rainbow sweep":(u,v,t)=>hsv(u*0.5-t,1,1),
 "Rising fill":(u,v,t)=>{const e=-1.25+2.6*(t%1),d=e-v;
   return d<0?[0,0,0]:hsv(0.33+0.15*v,0.9,Math.max(0,1-d/0.5));},
 "Radial pulse":(u,v,t)=>{const r=Math.hypot(u,v),
   k=0.5+0.5*Math.sin(2*Math.PI*(r*2-t*1.2));return hsv(0.55+0.2*r,0.85,k*k);},
 "Pinwheel":(u,v,t)=>hsv(Math.atan2(v,u)/(2*Math.PI)+t*0.5,1,1),
 "Plasma":(u,v,t)=>{const f=Math.sin(u*3.1+t*6)+Math.sin(v*2.7-t*4.5)+Math.sin((u+v)*2.2+t*3.3);
   return hsv(0.08+f*0.12,0.95,0.55+0.45*Math.sin(f*1.3));},
 "Rain":(u,v,t)=>{let best=0;for(let k=0;k<9;k++){
   const cx=Math.sin(k*12.9898)*1.0, ph=(Math.sin(k*78.233)+1)/2;
   const y=1.3-((t*0.55+ph)%1)*2.6, d=Math.hypot((u-cx)*1.8,v-y);
   best=Math.max(best,Math.max(0,1-d/0.30));}
   return hsv(0.52,0.55,Math.pow(best,1.5));},
 "Chase by wire order":(u,v,t,i,n)=>{const h=((t*n*1.5)%(n+30))-15,d=h-i;
   return d>=0&&d<20?hsv(0.09,0.85,Math.pow(1-d/20,2)):[0,0,0];},
 "Index gradient":(u,v,t,i,n)=>hsv(i/n*0.8,0.9,1),
 "All white":()=>[1,1,1],
};

/* ---- geometry: normalize to -1..1 on the longest axis, y up ---- */
const [bx0,by0,bx1,by1]=RIG.bounds;
const cx=(bx0+bx1)/2, cy=(by0+by1)/2;
const sc=Math.max(bx1-bx0,by1-by0)/2 || 1;
const SPAN=sc;                       // rig units per normalized 1.0
RIG.ports.forEach(p=>{p.on=true; p.uv=p.pixels.map(([x,y])=>[(x-cx)/sc,(y-cy)/sc]);});
const PORT_HUE=RIG.ports.map((p,i)=>i/Math.max(1,RIG.ports.length));

/* ---- sidebar ---- */
const nReal=RIG.ports.filter(p=>!p.empty).length;
{
  const upi=RIG.unitsPerInch||20;
  const wIn=(bx1-bx0)/upi, hIn=(by1-by0)/upi;
  document.getElementById('meta').textContent =
    `${RIG.ports.length} ports · ${RIG.ports.reduce((a,p)=>a+p.pixels.length,0)} pixels`
    + (nReal<RIG.ports.length ? ` · ${RIG.ports.length-nReal} empty` : '')
    + ` · ${wIn.toFixed(0)}×${hIn.toFixed(0)} in`;
}
const list=document.getElementById('ports');
RIG.ports.forEach((p,i)=>{
  const d=document.createElement('div');
  d.className='port'+(p.empty?' empty':'');
  d.innerHTML=`<span class="sw"></span><span class="n"></span><span class="c"></span>`;
  const [r,g,b]=hsv(PORT_HUE[i],0.55,1);
  d.querySelector('.sw').style.background=`rgb(${r*255|0},${g*255|0},${b*255|0})`;
  d.querySelector('.n').textContent=p.name;
  d.querySelector('.c').textContent=p.empty?'stub 32':p.pixels.length;
  d.tabIndex=0;
  const flip=()=>{p.on=!p.on;d.classList.toggle('off',!p.on);};
  d.onclick=flip;
  d.onkeydown=e=>{if(e.key===' '||e.key==='Enter'){e.preventDefault();flip();}};
  list.appendChild(d);
});
const sel=document.getElementById('fx');
Object.keys(FX).forEach(k=>{const o=document.createElement('option');
  o.value=k;o.textContent=k;sel.appendChild(o);});

/* ---- render ---- */
let W=0,H=0,dpr=1,view={s:1,ox:0,oy:0};
function resize(){
  dpr=Math.min(2,window.devicePixelRatio||1);
  const r=cv.getBoundingClientRect();
  W=r.width;H=r.height;
  cv.width=W*dpr;cv.height=H*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);
  const pad=34, s=Math.min((W-2*pad)/2,(H-2*pad)/2);
  view={s:s,ox:W/2,oy:H/2};
  /* bulbs are ~0.5in across on a 0.5-2in pitch, so draw them at TRUE size
     relative to spacing -- an arbitrary dot size hides how sparse a prop
     really is, which is exactly how an effect gets tuned too fine. */
  const bulbUnits = RIG.bulbDiameterUnits || 10;
  view.bulbR = Math.max(1.1, (bulbUnits/2) / SPAN * s);
}
new ResizeObserver(resize).observe(cv);

function draw(){
  const t=frame/240, fx=FX[sel.value]||FX["Rainbow sweep"];
  const glow=parseFloat(document.getElementById('glow').value);
  const wireMode=document.getElementById('wire').checked;
  ctx.fillStyle='#0A0E1A';ctx.fillRect(0,0,W,H);
  ctx.globalCompositeOperation='lighter';
  const rad=view.bulbR;
  RIG.ports.forEach((p,pi)=>{
    if(!p.on)return;
    const n=p.uv.length;
    for(let i=0;i<n;i++){
      const [u,v]=p.uv[i];
      let c = wireMode ? hsv(PORT_HUE[pi],0.5,0.25+0.75*i/Math.max(1,n-1))
                       : fx(u,v,t,i,n);
      const X=view.ox+u*view.s, Y=view.oy-v*view.s;
      const lum=(c[0]+c[1]+c[2])/3;
      if(lum>0.02&&glow>0){
        const g=ctx.createRadialGradient(X,Y,0,X,Y,rad*(2.2+3.2*glow));
        g.addColorStop(0,`rgba(${c[0]*255|0},${c[1]*255|0},${c[2]*255|0},${0.34*glow*lum})`);
        g.addColorStop(1,'rgba(0,0,0,0)');
        ctx.fillStyle=g;ctx.beginPath();ctx.arc(X,Y,rad*(2.2+3.2*glow),0,6.284);ctx.fill();
      }
      ctx.fillStyle=`rgb(${c[0]*255|0},${c[1]*255|0},${c[2]*255|0})`;
      ctx.beginPath();ctx.arc(X,Y,rad,0,6.284);ctx.fill();
    }
  });
  ctx.globalCompositeOperation='source-over';
  document.getElementById('read').innerHTML =
    `frame <b>${frame}</b> · <b>${(frame/60).toFixed(2)}</b>s if 60fps`;
}
function loop(){
  if(playing)frame+=parseFloat(document.getElementById('spd').value);
  draw();requestAnimationFrame(loop);
}
document.getElementById('play').onclick=e=>{
  playing=!playing;e.target.textContent=playing?'Pause':'Play';};
document.addEventListener('keydown',e=>{
  if(e.key===' '){e.preventDefault();document.getElementById('play').click();}});

/* ---- hover: identify a pixel ---- */
const tip=document.getElementById('tip');
cv.addEventListener('mousemove',ev=>{
  const r=cv.getBoundingClientRect(), mx=ev.clientX-r.left, my=ev.clientY-r.top;
  let best=null,bd=14*14;
  RIG.ports.forEach((p,pi)=>{ if(!p.on)return;
    p.uv.forEach(([u,v],i)=>{
      const dx=view.ox+u*view.s-mx, dy=view.oy-v*view.s-my, d=dx*dx+dy*dy;
      if(d<bd){bd=d;best={port:p,pi:pi,i:i};}});});
  if(best){
    tip.style.opacity=1;
    tip.style.left=(ev.clientX+12)+'px';tip.style.top=(ev.clientY+12)+'px';
    const upi=RIG.unitsPerInch||20;
    const px=best.port.pixels[best.i];
    tip.textContent=`${best.port.name} · pixel ${best.i} of ${best.port.pixels.length}`
      +` · ${(px[0]/upi).toFixed(1)}, ${(px[1]/upi).toFixed(1)} in`;
  } else tip.style.opacity=0;
});
cv.addEventListener('mouseleave',()=>tip.style.opacity=0);
resize();loop();
</script></body></html>
"""


def build(path, out=None, gap=120.0):
    r = rig.load(path, gap=gap) if os.path.isdir(path) else rig.load(path)
    html = (HTML.replace("__RIG__", json.dumps(r.to_json()))
                .replace("__NAME__", r.name))
    out = out or f"{r.name}_preview.html"
    d = os.path.dirname(os.path.abspath(out))
    os.makedirs(d, exist_ok=True)      # don't fail on a fresh clone
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    return r, out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    r, out = build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(f"{r.name}: {len(r.ports)} ports, {r.total_pixels()} px")
    print(f"rgb channels {r.rgb_channels()}")
    print(f"wrote {out}  ({os.path.getsize(out)/1024:.0f} KB)")
