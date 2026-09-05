#!/usr/bin/env python3
"""
make_2d.py -- author .rgb shows in real 2D space using .moc/.mod geometry.

Without the prop files you can only address pixels by chain index, so
effects come out as 1D chases. With the coordinates from a .moc you can
evaluate a spatial function at each LED's true (x, y) and get effects
that actually sweep across the prop: rising fills, radial pulses,
pinwheels, falling rain.

Geometry comes straight from the .moc, so the generated .rgb header
always matches the rig by construction:
    rgb channel pixels == moc port dotCount

FRAME RATE: measured at 60 fps via FpsTest.rgb (1800 frames took 30.0 s;
the 24-blink cross-check gave 1.00 blink/s). It is a DEVICE setting, not
stored in the file, so it must stay 60 on the controller for these speeds
to be right.
"""

import math, random, sys, os
from rgbfile import Show, FrameBuf
from props import load_moc, rgb_channels

FPS = 60          # MEASURED: 1800 frames in 30.0 s (FpsTest.rgb)
C = 255


def hsv(h, s=1.0, v=1.0, cap=C):
    h = h % 1.0
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    r, g, b = [(v, t, p), (q, v, p), (p, v, t),
               (p, q, v), (t, p, v), (v, p, q)][i]
    return r * cap, g * cap, b * cap


def build(moc_path, seconds_per_effect=5.0, loops=1, space="global"):
    """space="global": one effect spanning the whole rig, using the .moc's
    shared absolute coordinates (correct for adjacent props -- the ports in
    a .moc are already laid out side by side in one coordinate system).
    space="prop": each port centred on itself, so the effect repeats
    identically on every prop. Use only when you want that deliberately."""
    props, meta = load_moc(moc_path)
    chans = rgb_channels(props)
    s = Show(chans)
    if space == "prop":
        coords = [p.centered() for p in props]
    else:
        allxy = [p for pr in props for p in pr.xy]
        xs = [p[0] for p in allxy]; ys = [p[1] for p in allxy]
        cx, cy = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2
        sc = max(max(xs)-min(xs), max(ys)-min(ys)) / 2 or 1
        coords = [[((x-cx)/sc, (y-cy)/sc) for x, y in pr.xy] for pr in props]
    seg = max(1, int(seconds_per_effect * FPS))

    def rising(u, v, t):
        """fill sweeps bottom -> top, soft edge"""
        edge = -1.2 + 2.6 * (t % 1.0)
        d = edge - v
        if d < 0:
            return (0, 0, 0)
        k = max(0.0, 1 - d / 0.5)
        return hsv(0.33 + 0.15 * v, 0.9, k)

    def radial(u, v, t):
        """concentric pulses out from the centre"""
        r = math.hypot(u, v)
        k = 0.5 + 0.5 * math.sin(2 * math.pi * (r * 2.0 - t * 1.2))
        return hsv(0.55 + 0.2 * r, 0.85, k ** 2)

    def pinwheel(u, v, t):
        """hue by angle -> rotating colour wheel"""
        a = math.atan2(v, u) / (2 * math.pi)
        return hsv(a + t * 0.5, 1.0, 1.0)

    def plasma(u, v, t):
        """classic sin-field plasma in real space"""
        f = (math.sin(u * 3.1 + t * 2.0)
             + math.sin(v * 2.7 - t * 1.5)
             + math.sin((u + v) * 2.2 + t * 1.1))
        return hsv(0.08 + f * 0.12, 0.95, 0.55 + 0.45 * math.sin(f * 1.3))

    def rain(u, v, t):
        """droplets falling by real y"""
        val = 0.0
        for k in range(9):
            random.seed(k * 7717)
            cx = random.uniform(-1, 1)
            ph = random.random()
            y = 1.3 - ((t * 0.55 + ph) % 1.0) * 2.6
            d = math.hypot((u - cx) * 1.8, v - y)
            val = max(val, max(0.0, 1 - d / 0.30))
        return hsv(0.52, 0.55, val ** 1.5)

    effects = [("rising fill", rising), ("radial pulse", radial),
               ("pinwheel", pinwheel), ("plasma", plasma), ("rain", rain)]
    log = []
    for _ in range(loops):
        for name, fn in effects:
            log.append((len(s.frames), seg, name))
            for i in range(seg):
                t = i / seg
                fb = FrameBuf(s, C)
                for ch, uv in enumerate(coords):
                    for j, (u, v) in enumerate(uv):
                        fb.set(ch, j, *fn(u, v, t))
                s.frames.append(fb.bytes())
    return s, props, meta, log


def preview(s, props, path, ncols=8):
    """render sampled frames as 2D scatter so the effects can be checked"""
    from PIL import Image, ImageDraw
    coords = [p.xy for p in props]
    allx = [x for c in coords for x, y in c]
    ally = [y for c in coords for x, y in c]
    x0, x1, y0, y1 = min(allx), max(allx), min(ally), max(ally)
    CELL = 150
    idx = [int(k * (len(s.frames) - 1) / (ncols * 2 - 1)) for k in range(ncols * 2)]
    img = Image.new("RGB", (ncols * CELL, 2 * CELL), (10, 10, 12))
    dr = ImageDraw.Draw(img)
    sc = min((CELL - 12) / ((x1 - x0) or 1), (CELL - 12) / ((y1 - y0) or 1))
    for k, f in enumerate(idx):
        ox = (k % ncols) * CELL + CELL / 2 - (x0 + x1) / 2 * sc
        oy = (k // ncols) * CELL + CELL / 2 + (y0 + y1) / 2 * sc
        frame = s.frames[f]
        for ch, c in enumerate(coords):
            base = sum(len(coords[m]) for m in range(ch))
            for j, (x, y) in enumerate(c):
                o = (base + j) * 3
                col = (frame[o], frame[o + 1], frame[o + 2])
                X = ox + x * sc; Y = oy - y * sc
                dr.ellipse([X - 1.3, Y - 1.3, X + 1.3, Y + 1.3], fill=col)
    img.save(path)


if __name__ == "__main__":
    moc = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "."
    space = sys.argv[3] if len(sys.argv) > 3 else "global"
    s, props, meta, log = build(moc, space=space)
    name = "Show2D.rgb"
    s.save(os.path.join(out, name))
    n = len(s.frames)
    print(f"rig: {os.path.basename(moc)}  controlType={meta['controlType']} "
          f"ports={meta['portCount']}")
    print(s.info())
    print(f"   space = {space}")
    print(f"\n{name}  {n} frames  "
          f"{(s.header_size + n*s.frame_size)/1e6:.2f} MB  "
          f"= {n/FPS:.1f} s at {FPS} fps")
    for st, cnt, nm in log:
        print(f"   frame {st:5d} +{cnt:4d}  {nm}")
    preview(s, props, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "show2d.png"))
