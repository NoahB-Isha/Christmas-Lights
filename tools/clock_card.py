#!/usr/bin/env python3
"""clock_card.py -- a stopwatch scene to measure the controller's real
playback speed (e.g. when the GC-102C pins the DMX speed channel).

60 s loop at 60 fps:  a long GREEN flash at t=0 of every loop, a short WHITE
blip every second, a longer BLUE blip every 10 s. Time green-to-green with a
stopwatch: nominal 60.0 s. factor = measured / 60. Written as Sc-01..07 so
whatever position the box selects shows the clock.

    python3 tools/clock_card.py --layout assets/bench.json --out out/sd_clock
"""
import argparse, os, sys
import numpy as np
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from lightshow.layout import Layout
from lightshow.formats.rgbfile import Show
from lightshow.effects import to_bytes
FPS = 60

ap = argparse.ArgumentParser()
ap.add_argument("--layout", default=os.path.join(ROOT, "assets", "bench.json"))
ap.add_argument("--out", default=os.path.join(ROOT, "out", "sd_clock"))
ap.add_argument("--scenes", type=int, default=7)
a = ap.parse_args()
rigs = Layout.load(a.layout).controller_rigs()
for cid, rig in rigs.items():
    px = sum(rig.channels()); show = Show(rig.channels())
    for f in range(60 * FPS):
        t = f / FPS; sec = int(t); frac = t - sec
        col = np.array([0.04, 0.03, 0.02])                                   # dim warm base
        if sec == 0 and frac < 0.5:  col = np.array([0.1, 0.9, 0.1])        # loop start: long green
        elif sec % 10 == 0 and frac < 0.25: col = np.array([0.2, 0.3, 1.0])  # every 10 s: blue
        elif frac < 0.08:            col = np.array([0.8, 0.8, 0.8])        # every second: white blip
        show.frames.append(to_bytes(np.tile(col, (px, 1))).reshape(-1).tobytes())
    d = os.path.join(a.out, cid); os.makedirs(d, exist_ok=True)
    show.save(os.path.join(d, "Sc-01-01.rgb"))
    data = open(os.path.join(d, "Sc-01-01.rgb"), "rb").read()
    for n in range(2, a.scenes + 1):
        open(os.path.join(d, f"Sc-{n:02d}-01.rgb"), "wb").write(data)
    print(cid, f"{len(data)/1e6:.1f} MB x {a.scenes}")
