#!/usr/bin/env python3
"""
scene_ladder.py -- a characterisation card set: ALL 62 scenes filled, each
one unmistakable, so we can read which scene the audio box selects for a
given audio level / beep.

Scene N (1..62):
  * a DIM solid colour (22 %), hue = N/62 around the wheel (1 red, ~16
    yellow-green, ~31 cyan, ~47 purple, 62 back to red)
  * every 6 s the rig counts the number out with SOFT pulses: TENS as slow
    green swells, then UNITS as quicker warm swells (47 = 4 green, 7 warm).
    Nothing goes above ~55 % -- comfortable to stare at.
Loop is 6 s per scene, 60 fps.

    python3 tools/scene_ladder.py --layout assets/bench.json --out out/sd_ladder
Copy A/ and B/ to the cards (replacing the show cards for the test).
"""

import argparse, hashlib, json, os, sys
from collections import OrderedDict

import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from lightshow.layout import Layout                      # noqa: E402
from lightshow.formats.rgbfile import Show               # noqa: E402
from lightshow.effects import hsv, to_bytes              # noqa: E402

FPS = 60
LOOP_S = 6.0


def level_at(t, n):
    """-> (kind, amount 0..1): a SOFT pulse timeline (no hard flashes).
    tens = slow green pulses, units = quicker warm pulses."""
    tens, units = divmod(n, 10)
    seq = []                                          # (start, dur, kind)
    tt = 0.5
    for _ in range(tens):
        seq.append((tt, 0.7, "tens")); tt += 0.9
    tt += 0.4
    for _ in range(units):
        seq.append((tt, 0.32, "units")); tt += 0.42
    for s, d, k in seq:
        if s <= t < s + d:
            x = (t - s) / d
            return k, float(np.sin(np.pi * x) ** 2)  # smooth in/out
    return "base", 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", default=os.path.join(ROOT, "assets", "bench.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "sd_ladder"))
    ap.add_argument("--scenes", type=int, default=62)
    a = ap.parse_args()
    L = Layout.load(a.layout)
    rigs = L.controller_rigs()
    man = OrderedDict(fps=FPS, loop_s=LOOP_S, scenes=OrderedDict())
    for n in range(1, a.scenes + 1):
        hue = (n - 1) / a.scenes
        base = np.array(hsv(hue, 0.9, np.array([0.22]))).reshape(3)          # dim, easy on the eyes
        colours = {"tens": np.array([0.1, 0.55, 0.1]), "units": np.array([0.6, 0.55, 0.45])}
        n_frames = int(LOOP_S * FPS)
        fname = f"Sc-{n:02d}-01.rgb"
        man["scenes"][n] = {"hue": round(hue, 3), "file": fname, "cards": {}}
        for cid, rig in rigs.items():
            show = Show(rig.channels())
            px = sum(rig.channels())
            for f in range(n_frames):
                k, amt = level_at(f / FPS, n)
                c = base if k == "base" else base * (1 - amt) + colours[k] * amt
                col = np.tile(c, (px, 1))
                show.frames.append(to_bytes(col).reshape(-1).tobytes())
            d = os.path.join(a.out, cid); os.makedirs(d, exist_ok=True)
            path = os.path.join(d, fname); show.save(path)
            data = open(path, "rb").read()
            man["scenes"][n]["cards"][cid] = {"bytes": len(data), "md5": hashlib.md5(data).hexdigest()}
    json.dump(man, open(os.path.join(a.out, "manifest.json"), "w"), indent=1)
    tot = sum(os.path.getsize(os.path.join(a.out, c, f)) for c in rigs for f in os.listdir(os.path.join(a.out, c)))
    print(f"{a.scenes} scenes x {len(rigs)} cards -> {a.out}  ({tot/1e6:.0f} MB total)")


if __name__ == "__main__":
    main()
