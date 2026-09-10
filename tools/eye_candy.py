#!/usr/bin/env python3
"""
eye_candy.py -- a 90-second no-music demo for any layout. Fun first, rigor later.

    python tools/eye_candy.py                                # bench -> out/eye_candy/<CTRL>/EyeCandy-02.rgb
    python tools/eye_candy.py --layout assets/layout.json --out out/eye_candy_yard

Sections (each ~10 s, crossfaded):
  1 frost sparkle      white-hot grains cooling to blue over a soft ice wash
  2 rainbow room wave  one hue wave travelling through every prop in world x
  3 ripple tag         a pulse leaves one prop and ripples to its neighbours by real distance
  4 candy stripes      diagonal red/white stripes marching across all props at once
  5 wire chase         a comet runs the wire of every prop, ends meet on the beat
  6 radial bursts      rings expand from each prop's centre, staggered along the row
  7 gold sparkle       warm gold wash with white glints
  8 fireworks finale   all of the above stacked, brighter, faster
  9 slow fade-to-glow  settle to a steady warm glow (the loop point)

Every look is sized in inches and reads the layout, so the same file renders
for the bench or the whole yard. Written as scene 2 by default so scene 1
stays the show.
"""

import argparse, hashlib, json, math, os, sys
from collections import OrderedDict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from lightshow.layout import Layout                        # noqa: E402
from lightshow.formats.rgbfile import Show                 # noqa: E402
from lightshow.effects import hsv, frost, lighten, to_bytes  # noqa: E402

FPS = 60
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


class P:
    """Per-prop geometry in inches: local, world, polar, wire index."""
    def __init__(self, placement, idx):
        self.pl, self.idx = placement, idx
        self.n = placement.n
        self.i = np.arange(self.n)
        loc = placement.local(); self.lx, self.ly = loc[:, 0], loc[:, 1]
        W = placement.world(); self.wx, self.wy, self.wz = W[:, 0], W[:, 1], W[:, 2]
        self.cx, self.cy, self.cz = placement.centre()
        self.r = np.hypot(self.lx, self.ly - (self.ly.max() / 2))
        self.ang = np.arctan2(self.ly - self.ly.max() / 2, self.lx)
        self.rng = np.random.default_rng(1000 + idx)
        self.h = placement.shape()["h"]


def env_pulse(t, period, width=0.25):
    ph = (t / period) % 1.0
    return math.exp(-(ph / width) ** 2)


# ------------------------------------------------------------------ looks
def frost_sparkle(t, p, props, world):
    wash = frost(np.full(p.n, 0.55 + 0.1 * math.sin(2 * math.pi * t / 6 + p.idx)), hue=0.58, bias=1.0)
    grains = np.zeros(p.n)
    for k in range(6):
        seed = int(t / 0.8) + k * 97 + p.idx * 13
        r = np.random.default_rng(seed)
        j = r.integers(0, p.n); ph = ((t / 0.8) % 1.0)
        grains[j] = max(grains[j], (1 - ph) ** 1.5)
    return lighten(wash, frost(grains, hue=0.55, bias=1.2))


def rainbow_wave(t, p, props, world):
    x0, x1 = world
    ph = (p.wx - x0) / max(1.0, x1 - x0)
    hue = (ph * 0.8 - t * 0.18) % 1.0
    v = 0.75 + 0.25 * np.sin(2 * np.pi * (ph * 2 - t * 0.5))
    return hsv(hue, 0.95, v)


def ripple_tag(t, p, props, world):
    period = 3.0
    k = int(t / period) % len(props)
    src = props[k]
    t0 = (t % period)
    d = math.hypot(p.cx - src.cx, p.cy - src.cy, p.cz - src.cz)   # inches, prop to prop
    speed = 90.0                                                   # in/s
    ring = np.exp(-((d - t0 * speed) / 24.0) ** 2)
    base = hsv(0.58, 0.8, 0.58)
    if p is src:
        flash = max(0.0, 1 - t0 / 0.6)
        base = lighten(base, hsv(0.12, 0.3, 0.6 + 0.4 * flash))
    return lighten(base, hsv(0.13, 0.9, ring * 1.0))


def candy_stripes(t, p, props, world):
    stripe = (p.wx + p.wz - t * 24.0) / 8.0                        # 8 in stripes
    s = (np.floor(stripe) % 2).astype(bool)
    out = np.where(s[:, None], np.array([[1.0, 0.08, 0.08]]), np.array([[1.0, 1.0, 1.0]]))
    return out * 0.9


def wire_chase(t, p, props, world):
    tail = max(8, p.n // 6)
    head = (t * (p.n / 2.5)) % (p.n + tail)
    d = head - p.i
    v = np.clip(1 - d / tail, 0, 1) ** 1.2; v[d < 0] = 0
    hue = (0.33 + 0.5 * (p.idx / max(1, len(props) - 1))) % 1.0
    return lighten(hsv(hue, 0.9, 0.5), hsv(hue, 0.4, v))


def radial_bursts(t, p, props, world):
    period = 2.0
    ph = ((t - p.idx * 0.25) / period) % 1.0
    ring = np.exp(-((p.r - ph * (p.r.max() + 6)) / 5.0) ** 2)
    base = hsv(0.7 + 0.1 * p.idx, 0.85, 0.58)
    return lighten(base, hsv(0.12, 0.2, ring))


def gold_sparkle(t, p, props, world):
    wash = hsv(0.11 + 0.02 * np.sin(p.ly / 10 + t), 0.9, 0.7 + 0.15 * np.sin(2 * np.pi * t / 4 + p.lx / 20))
    gl = np.zeros(p.n)
    for k in range(4):
        r = np.random.default_rng(int(t / 0.5) + k * 31 + p.idx * 7)
        gl[r.integers(0, p.n)] = 1 - ((t / 0.5) % 1.0)
    return lighten(wash, hsv(0.13, 0.15, gl))


def finale(t, p, props, world):
    a = rainbow_wave(t * 1.6, p, props, world) * 0.8
    b = radial_bursts(t * 1.5, p, props, world)
    c = frost_sparkle(t * 2, p, props, world) * 0.7
    return lighten(a, b, c)


def settle(t, p, props, world):
    return hsv(np.full(p.n, 0.09), 0.75, 0.7 + 0.05 * math.sin(2 * math.pi * t / 5))


SECTIONS = [(frost_sparkle, 10), (rainbow_wave, 10), (ripple_tag, 12), (candy_stripes, 10),
            (wire_chase, 10), (radial_bursts, 10), (gold_sparkle, 8), (finale, 12), (settle, 8)]
XFADE = 1.2


def render_frame(t, props, world):
    """-> list of (n,3) perceptual arrays, one per prop, with crossfades."""
    acc, out = 0.0, [None] * len(props)
    total = sum(d for _, d in SECTIONS)
    t = t % total
    for k, (fn, dur) in enumerate(SECTIONS):
        if acc <= t < acc + dur:
            local = t - acc
            cur = [np.broadcast_to(np.asarray(fn(local, p, props, world), float), (p.n, 3)) for p in props]
            if local < XFADE and k > 0:
                pf, pd = SECTIONS[k - 1]
                prev = [np.broadcast_to(np.asarray(pf(pd + local, p, props, world), float), (p.n, 3)) for p in props]
                a = local / XFADE
                cur = [pv * (1 - a) + cv * a for pv, cv in zip(prev, cur)]
            return cur
        acc += dur
    return [np.zeros((p.n, 3)) for p in props]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", default=os.path.join(ROOT, "assets", "bench.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "eye_candy"))
    ap.add_argument("--scene", type=int, default=2)
    ap.add_argument("--name", default="EyeCandy")
    a = ap.parse_args()
    L = Layout.load(a.layout)
    rigs = L.controller_rigs()
    props = [P(pl, i) for i, pl in enumerate(L.props)]
    by_id = {p.pl.id: p for p in props}
    xs = np.concatenate([p.wx for p in props]); world = (float(xs.min()), float(xs.max()))
    total = sum(d for _, d in SECTIONS); n_frames = int(total * FPS)

    shows = {cid: Show(rig.channels()) for cid, rig in rigs.items()}
    offs = {cid: np.cumsum([0] + rig.channels()) * 3 for cid, rig in rigs.items()}
    bright = []
    for f in range(n_frames):
        t = f / FPS
        frames = render_frame(t, props, world)
        bright.append(np.mean([fr.max(1).mean() for fr in frames]))
        for cid, rig in rigs.items():
            buf = np.zeros(shows[cid].frame_size, np.uint8)
            for k, pr in enumerate(rig.ports):
                if pr.placement is None:
                    continue
                b = to_bytes(frames[by_id[pr.placement.id].idx]).reshape(-1)
                buf[offs[cid][k]:offs[cid][k] + len(b)] = b
            shows[cid].frames.append(buf.tobytes())
    os.makedirs(a.out, exist_ok=True)
    man = OrderedDict(fps=FPS, frames=n_frames, seconds=total, scene=a.scene, cards=OrderedDict())
    fname = f"Sc-{a.scene:02d}-01.rgb"   # Sc-<scene>-<part>.rgb, confirmed on the GC-6004
    for cid, s in shows.items():
        d = os.path.join(a.out, cid); os.makedirs(d, exist_ok=True)
        path = os.path.join(d, fname); s.save(path)
        data = open(path, "rb").read()
        man["cards"][cid] = {"file": f"{cid}/{fname}", "bytes": len(data), "md5": hashlib.md5(data).hexdigest(),
                             "channels": rigs[cid].channels(), "frames": len(s.frames)}
        print(f"{cid}: {fname} {rigs[cid].channels()} {len(data)/1e6:.1f} MB")
    json.dump(man, open(os.path.join(a.out, "manifest.json"), "w"), indent=1)
    b = np.array(bright)
    print(f"{n_frames} frames ({total} s). mean perceptual brightness {b.mean():.2f}; "
          f">=0.6 for {100*(b>=0.6).mean():.0f}% of the time")


if __name__ == "__main__":
    main()
