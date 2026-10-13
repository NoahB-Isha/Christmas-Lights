"""classic.py -- the Classic LED pack: stereotypical, bright, rich-colour LED effects."""

import math
import numpy as np

from ..engine import effect, Slider, choice, toggle
from ...effects import hsv, lighten

PACK = "Classic LED"


@effect("led_rainbow", "anim", "Rainbow wave", pack=PACK, params=[
    Slider("speed", "Speed", 1.0, 0.1, 4.0, 0.1),
    Slider("cycles", "Rainbows across the group", 1.0, 0.25, 4.0, 0.25),
    choice("axis", "Direction", "across", ["across", "up", "per prop"]),
    Slider("sat", "Saturation", 1.0, 0.6, 1.0, 0.05),
    toggle("beat_bump", "Brighten on the beat", True),
], doc="The full spectrum slides across the whole group in world inches (or up the props, or around each prop), fully saturated.")
def led_rainbow(g, m, t, p, pal, st):
    out = {}
    v = 1.0 if not p["beat_bump"] else 0.75 + 0.25 * m.pulse
    for pr in g.props:
        if p["axis"] == "across":
            u = g.x01(pr)
        elif p["axis"] == "up":
            u = g.z01(pr)
        else:
            u = pr.ang / 6.283 + pr.idx * 0.13
        h = u * p["cycles"] - t * p["speed"] * 0.25
        out[pr.id] = hsv(h, p["sat"], v)
    return out


@effect("led_blocks", "anim", "Colour blocks", pack=PACK, params=[
    Slider("shift_beats", "Beats per shift", 1, 1, 8, 1, kind="int"),
    choice("unit", "One colour per", "prop", ["prop", "region", "12 in band"]),
    toggle("reverse", "Reverse", False),
    Slider("level", "Brightness", 1.0, 0.3, 1.0, 0.05),
    Slider("blend", "Blend between steps (share of step)", 0.25, 0.0, 1.0, 0.05),
], doc="Each prop (or region, or 12-inch band) is one solid palette colour; the colours step along the row on the beat. Blend 0 = hard steps; higher = a smooth crossfade into each new colour.")
def led_blocks(g, m, t, p, pal, st):
    sb = max(1, int(p["shift_beats"]))
    step = (m.beat_index + m.beat_phase) / sb
    k0 = int(step) * (-1 if p["reverse"] else 1); k1 = k0 + (-1 if p["reverse"] else 1)
    f = (step - int(step))
    w = 0.0 if p["blend"] <= 0 else float(np.clip(f / p["blend"], 0, 1))     # crossfade at the START of each step
    w = 1.0 - w if p["blend"] > 0 else 0.0                                     # 1 = still showing the previous colour
    out = {}
    for pr in g.props:
        if p["unit"] == "prop":
            base = np.full(pr.n, pr.idx)
        elif p["unit"] == "region":
            base = np.zeros(pr.n, int)
            for k, nm in enumerate(pr.regions):
                base[pr.regions[nm]] = k + pr.idx
        else:
            base = ((pr.wx - g.x0) // 12).astype(int)
        cur = pal.pick(base + k0); prev = pal.pick(base + k0 - (1 if not p["reverse"] else -1))
        out[pr.id] = (cur * (1 - w) + prev * w) * p["level"]
    return out


@effect("led_chase", "anim", "Colour chase", pack=PACK, params=[
    Slider("bars", "Bars per sweep", 1, 0.5, 4, 0.5),
    Slider("width_in", "Band width (in)", 40.0, 10.0, 200.0, 5.0, unit="in"),
    choice("direction", "Direction", "left→right", ["left→right", "right→left", "bounce"]),
    Slider("floor", "Background level", 0.25, 0.0, 0.8, 0.05),
    toggle("new_colour_each", "New colour every sweep", True),
    toggle("smooth", "Soft band edges", True),
], doc="A bright band of palette colour sweeps smoothly across the row once per bar (or more), the rest of the group holding a dim version of the previous colour.")
def led_chase(g, m, t, p, pal, st):
    bars = m.bar_index + m.bar_phase
    u = (bars / p["bars"]) % 1.0
    sweep = int(bars / p["bars"])
    if p["direction"] == "right→left":
        u = 1 - u
    elif p["direction"] == "bounce":
        u = 1 - abs(1 - 2 * u)
    k = sweep if p["new_colour_each"] else 0
    c_now, c_prev = pal.color(k), pal.color(k - 1)
    span = g.width + 2 * p["width_in"]
    front = g.x0 - p["width_in"] + u * span
    out = {}
    for pr in g.props:
        d = (pr.wx - front) / (p["width_in"] / 2)
        band = np.exp(-d ** 2)
        if not p["smooth"]:
            band = np.where(band > 0.45, 1.0, 0.0)
        base = c_prev * p["floor"]
        out[pr.id] = lighten(np.broadcast_to(base, (pr.n, 3)), c_now * band[:, None])
    return out


@effect("led_fill", "anim", "Beat fill", pack=PACK, params=[
    Slider("beats", "Beats per fill", 4, 1, 8, 1, kind="int"),
    choice("direction", "Fill direction", "bottom→top", ["bottom→top", "top→bottom", "centre out", "wire order"]),
    toggle("drop", "Drop to dark before refilling", True),
    Slider("steps", "Steps per fill (0 = smooth)", 0, 0, 16, 1, kind="int"),
    Slider("edge", "Edge softness", 0.08, 0.0, 0.3, 0.01),
], doc="Every few beats each prop fills with the next palette colour -- bottom to top, top down, out from the centre, or along the wire -- then drops and refills in the next colour. Smooth by default; set steps for a hard staircase.")
def led_fill(g, m, t, p, pal, st):
    nb = max(1, int(p["beats"]))
    cyc = (m.beat_index % nb + m.beat_phase) / nb              # 0..1 over the fill
    k = m.beat_index // nb
    col = pal.color(k)
    prev = pal.color(k - 1)
    q = cyc if int(p["steps"]) == 0 else np.floor(cyc * int(p["steps"])) / int(p["steps"])
    out = {}
    for pr in g.props:
        if p["direction"] == "bottom→top":
            u = pr.y01
        elif p["direction"] == "top→bottom":
            u = 1 - pr.y01
        elif p["direction"] == "centre out":
            u = pr.r01
        else:
            u = pr.i / max(1, pr.n - 1)
        filled = np.clip((q - u) / max(1e-3, p["edge"]) + 0.5, 0, 1) if p["edge"] > 0 else (u <= q).astype(float)
        base = np.zeros(3) if p["drop"] else prev
        out[pr.id] = col * filled[:, None] + base * (1 - filled)[:, None]
    return out


# ------------------------------------------------------------- smooth looks
from .util import gradient, noise  # noqa: E402


@effect("led_gradient_flow", "anim", "Gradient flow", pack=PACK, params=[
    Slider("bars", "Bars per cycle", 4, 0.5, 16, 0.5),
    Slider("cycles", "Palette cycles across the group", 1.0, 0.25, 4.0, 0.25),
    choice("axis", "Direction", "across", ["across", "up", "diagonal"]),
    Slider("level", "Brightness", 1.0, 0.3, 1.0, 0.05),
    toggle("reverse", "Reverse", False),
], doc="The palette colours flow smoothly across the whole group as a continuous gradient -- no steps, no flashes -- one full cycle every few bars.")
def led_gradient_flow(g, m, t, p, pal, st):
    bars = m.bar_index + m.bar_phase
    ph = (bars / p["bars"]) * (-1 if p["reverse"] else 1)
    out = {}
    for pr in g.props:
        u = g.x01(pr) if p["axis"] == "across" else (g.z01(pr) if p["axis"] == "up" else (g.x01(pr) + g.z01(pr)) / 2)
        out[pr.id] = gradient(pal, u * p["cycles"] + ph) * p["level"]
    return out


@effect("led_breathe", "anim", "Colour breathe", pack=PACK, params=[
    Slider("bars", "Bars per breath", 2, 0.5, 8, 0.5),
    Slider("floor", "Dimmest level", 0.15, 0.0, 0.8, 0.05),
    toggle("stagger", "Props out of step", True),
    toggle("next_colour", "New colour every breath", True),
    Slider("shimmer", "Soft shimmer", 0.15, 0.0, 0.5, 0.05),
], doc="Every prop swells and fades smoothly through the palette -- a new colour each breath, props slightly out of step so the row ripples. Fully smooth; the LED counterpart of Warm breathe.")
def led_breathe(g, m, t, p, pal, st):
    bars = m.bar_index + m.bar_phase
    out = {}
    for pr in g.props:
        off = pr.idx / max(1, g.P) * 0.5 if p["stagger"] else 0.0
        cyc = bars / p["bars"] + off
        b = 0.5 - 0.5 * math.cos(2 * math.pi * cyc)
        k = int(cyc) if p["next_colour"] else pr.idx
        lvl = p["floor"] + (1 - p["floor"]) * b
        sh = 1 - p["shimmer"] * noise(pr.wx / 12, pr.wz / 12, t * 1.5, pr.idx)
        out[pr.id] = pal.color(k) * (lvl * sh)[:, None]
    return out


@effect("led_meteor", "anim", "Meteors", pack=PACK, params=[
    Slider("per_beat", "Meteors per beat", 1, 0.25, 4, 0.25),
    Slider("tail", "Tail length (share of wire)", 0.25, 0.05, 0.8, 0.05),
    Slider("speed", "Laps per second", 0.6, 0.1, 3.0, 0.1),
    Slider("floor", "Background", 0.05, 0.0, 0.4, 0.02),
    toggle("colour_each", "New colour per meteor", True),
], doc="Bright heads race along the wire of every prop with smooth fading tails, launched on the beat; each meteor a new palette colour over a dim background.")
def led_meteor(g, m, t, p, pal, st):
    out = {}
    bl = m.beat_len
    nper = p["per_beat"]
    for pr in g.props:
        fr = np.broadcast_to(pal.color(0) * p["floor"], (pr.n, 3)).copy()
        # meteors alive: launched at each 1/nper of a beat over the last few beats
        launches = []
        for back in range(6):
            bi = m.beat_index - back
            for j in range(max(1, int(round(nper)))):
                age = m.beat_phase * bl + back * bl - j * bl / max(1, int(round(nper)))
                if age >= 0:
                    launches.append((age, bi * 7 + j))
        u = pr.i / max(1, pr.n - 1)
        for age, seed in launches:
            head = (age * p["speed"] + (seed * 0.37) % 1.0) % 1.0
            d = (head - u) % 1.0
            tailv = np.where(d < p["tail"], (1 - d / p["tail"]) ** 2, 0.0)
            col = pal.color(seed) if p["colour_each"] else pal.color(pr.idx)
            fr = lighten(fr, col * tailv[:, None])
        out[pr.id] = fr
    return out


# ------------------------------------------------------------------- round 4
from .util import noise as _noise, smoothstep as _smoothstep, gradient as _gradient, rng as _rng, glints as _glints  # noqa: E402


@effect("bokeh", "anim", "Bokeh", pack=PACK, tags=["slow"], params=[
    Slider("count", "Discs across the group", 16, 3, 40, 1, kind="int"),
    Slider("size_in", "Disc size (in)", 14.0, 4.0, 60.0, 1.0, unit="in"),
    Slider("drift_in_s", "Drift (in/s)", 3.0, 0.0, 30.0, 0.5, unit="in/s"),
    Slider("ring", "Bright rim (lens look)", 0.5, 0.0, 1.0, 0.05),
    Slider("floor", "Background level", 0.04, 0.0, 0.3, 0.01),
    toggle("beat_bloom", "Bloom on the beat", False),
], doc="Out-of-focus Christmas lights: soft coloured discs, sized in inches, drifting slowly across the whole group and crossing the gaps between props, each a little brighter at its rim the way a lens draws them. Palette colours, overlapping with lighten. The photo look.")
def bokeh(g, m, t, p, pal, st):
    n = int(p["count"])
    r = _rng(4242)
    bx0 = r.random(n); bz0 = r.random(n); ph = r.random(n) * 6.283; sp = 0.5 + r.random(n)
    size = p["size_in"] * (0.6 + 0.8 * r.random(n))
    cols = pal.chroma[r.integers(0, pal.k, n)]
    span = g.width + 2 * p["size_in"]
    bx = g.x0 - p["size_in"] + ((bx0 * span + t * p["drift_in_s"] * sp) % span)
    bz = g.z0 + (bz0 + 0.08 * np.sin(t * 0.3 * sp + ph)) % 1.0 * g.height
    bloom = 1 + (0.35 * m.beat_env if p["beat_bloom"] else 0.0)
    out = {}
    for pr in g.props:
        fr = pal.color(0)[None, :] * (p["floor"] * (0.6 + 0.4 * _noise(pr.wx / 20, pr.wz / 20, t * 0.1, pr.idx)))[:, None]
        d01 = np.hypot(pr.wx[:, None] - bx[None, :], pr.wz[:, None] - bz[None, :]) / (size[None, :] / 2)
        prof = _smoothstep(1.05, 0.9, d01) * (0.55 + 0.45 * (1 - p["ring"]) + p["ring"] * 0.45 * _smoothstep(0.55, 0.95, d01))
        prof = prof * (0.75 + 0.25 * np.sin(t * 0.7 * sp[None, :] + ph[None, :])) * bloom
        for k in range(n):
            fr = lighten(fr, cols[k] * prof[:, k][:, None])
        out[pr.id] = np.clip(fr, 0, 1)
    return out


@effect("kaleidoscope", "anim", "Kaleidoscope", pack=PACK, tags=["slow"], params=[
    Slider("segments", "Mirror segments", 6, 2, 12, 1, kind="int"),
    Slider("bars", "Bars per rotation", 4, 0.5, 16, 0.5),
    Slider("rings", "Colour rings from the centre", 2.0, 0.5, 6.0, 0.5),
    Slider("sparkle", "Sparkle", 0.3, 0.0, 1.0, 0.05),
    toggle("beat_spin", "Spin steps on the beat", False),
], doc="Each prop becomes a kaleidoscope around its own centre: the palette folded into mirrored wedges and rings that rotate slowly -- built for the snowflakes and crosses, and it gives Santa and the bell a slow radial shimmer. Sized in the prop's own inches.")
def kaleidoscope(g, m, t, p, pal, st):
    bars = m.bar_index + m.bar_phase
    spin = (math.floor(bars * m.beats_per_bar) / m.beats_per_bar if p["beat_spin"] else bars) / p["bars"]
    segs = int(p["segments"])
    out = {}
    for pr in g.props:
        a = (pr.ang / (2 * math.pi) + spin) % 1.0
        fold = np.abs(((a * segs) % 1.0) - 0.5) * 2                     # 0..1 mirrored inside each wedge
        u = fold * 0.5 + pr.r01 * p["rings"] - spin * 0.5
        fr = _gradient(pal, u)
        shade = 0.55 + 0.45 * (0.5 + 0.5 * np.cos(fold * math.pi)) * (0.6 + 0.4 * _noise(pr.lx / 4, pr.ly / 4, t * 0.3, pr.idx))
        fr = fr * shade[:, None]
        if p["sparkle"] > 0:
            fr = lighten(fr, np.ones(3) * (p["sparkle"] * _glints(pr, t, 0.7, pr.idx + 21, 12.0) * (1 - pr.r01 * 0.5))[:, None])
        out[pr.id] = np.clip(fr, 0, 1)
    return out
