#!/usr/bin/env python3
"""idle_wash.py -- an unmistakable IDLE scene for the bench: a slow, dim
colour wash (each prop a different hue, all drifting round the wheel over
60 s) with a gentle breath. Nothing like the show's opening, so "is it on
the show or on idle?" is answered at a glance.

    python3 tools/idle_wash.py --layout assets/bench.json --out out/sd_bench --scene 1
"""
import argparse, hashlib, json, os, sys
import numpy as np
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from lightshow.layout import Layout
from lightshow.formats.rgbfile import Show
from lightshow.effects import hsv, to_bytes
FPS, LOOP = 60, 60.0

ap = argparse.ArgumentParser()
ap.add_argument("--layout", default=os.path.join(ROOT, "assets", "bench.json"))
ap.add_argument("--out", default=os.path.join(ROOT, "out", "sd_bench"))
ap.add_argument("--scene", type=int, default=1)
ap.add_argument("--level", type=float, default=0.35)
a = ap.parse_args()
L = Layout.load(a.layout); rigs = L.controller_rigs()
props = list(L.props); order = {p.id: k for k, p in enumerate(sorted(props, key=lambda q: q.x))}
n_frames = int(LOOP * FPS)
fname = f"Sc-{a.scene:02d}-01.rgb"
res = {}
for cid, rig in rigs.items():
    show = Show(rig.channels())
    for f in range(n_frames):
        t = f / FPS
        buf = []
        for k, pr in enumerate(rig.ports):
            n = rig.channels()[k]
            if pr.placement is None:
                buf.append(np.zeros((n, 3))); continue
            hue = (t / LOOP + order[pr.placement.id] / max(1, len(props))) % 1.0
            ly = pr.placement.local()[:, 1]; y01 = ly / max(1e-6, ly.max())
            breath = 0.75 + 0.25 * np.sin(2 * np.pi * (t / 6.0 + 0.3 * y01))
            buf.append(hsv(hue + 0.06 * y01, 0.85, a.level * breath))
        show.frames.append(to_bytes(np.vstack(buf)).reshape(-1).tobytes())
    d = os.path.join(a.out, cid); os.makedirs(d, exist_ok=True)
    path = os.path.join(d, fname); show.save(path); data = open(path, "rb").read()
    res[cid] = {"file": f"{cid}/{fname}", "bytes": len(data), "md5": hashlib.md5(data).hexdigest()}
    print(cid, fname, f"{len(data)/1e6:.1f} MB")
print(json.dumps(res))
