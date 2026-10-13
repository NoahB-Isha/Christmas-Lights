"""fire.py -- the Fire pack, rebuilt (round 5) so it reads as FIRE from the road.

What makes fire read: everything moves UP and fast; the base is a near-solid
yellow-white core; tongues detach, rise, thin out and vanish; the flicker is
several Hz, not a slow wobble; and the top of the flame is ragged, never a
smooth gradient. The model here: a per-column flame height that flickers
(fast noise), upward-scrolling fractal noise that carves tongues out of the
body, a hot core near the base, and a colour ramp with real yellow-white.

    Flames            the model above
    Embers rising     a dark bed of pulsing coals; sparse sparks lift off, wander and fade (slow, striking)
    Reignite          flames on all props; one dies to coals and is relit with a flash, round the row
    Candle flicker    the painted picture under a soft candle flicker (unchanged)
"""

import math
import numpy as np

from ..engine import effect, Slider, choice, toggle
from ...effects import lighten
from .util import noise, fbm, heat, smoothstep, rng
from .incandescent import drawn

PACK = "Fire"
HEAT = choice("heat", "Flame colours", "fire", ["fire", "gas", "green", "palette"])
#          black   deep red  red     red-orange orange   amber   hot amber  warm white (core only)
FIRE_K = [0.00,   0.12,     0.28,   0.42,      0.58,    0.74,   0.90,      1.00]
FIRE_R = [0.00,   0.30,     0.85,   1.00,      1.00,    1.00,   1.00,      1.00]
FIRE_G = [0.00,   0.00,     0.04,   0.14,      0.32,    0.52,   0.68,      0.85]
FIRE_B = [0.00,   0.00,     0.00,   0.00,      0.00,    0.00,   0.10,      0.45]


def _heat(v, kind, pal):
    v = np.clip(v, 0, 1)
    if kind == "palette":
        from .util import gradient
        return gradient(pal, v * 0.999) * (v[:, None] ** 0.6)
    if kind == "fire":
        # a real wood-fire ramp as it reads on RGB LEDs: deep red edges, red-orange, orange body, amber core;
        # yellow stays amber (pure LED yellow goes lime), and warm white only at the very hottest point
        return np.stack([np.interp(v, FIRE_K, FIRE_R), np.interp(v, FIRE_K, FIRE_G), np.interp(v, FIRE_K, FIRE_B)], 1)
    return heat(v, kind)


def flame_field(pr, t, speed=1.0, height=0.8, turbulence=1.0, scale_in=8.0, flicker=1.0, seed=0):
    """Heat 0..1 per bulb for one prop. Local inches: x across the prop, y01 up it."""
    tt = t * speed
    x = pr.lx / scale_in
    # 1. per-column flame height: slow sway + fast flicker (several Hz)
    hcol = height * (0.75 + 0.35 * noise(x * 0.8, 0, tt * 1.5, seed) + 0.25 * (noise(x * 2.5, 0, tt * 7.0, seed + 11) - 0.5) * flicker)
    rel = pr.y01 / np.maximum(0.05, hcol)                                  # 0 at the base, 1 at the tongue tip
    body = np.clip(1 - rel, 0, 1)
    # 2. tongues: fractal noise scrolling UP fast carves the body; stronger carving higher up
    tex = fbm(x * 1.6, pr.ly / scale_in * 1.1 - tt * 3.0, tt * 0.8, seed + 5, octaves=3)
    carve = (0.35 + 0.65 * rel) * turbulence
    v = body * (1.15 - carve * (1 - tex) * 1.3)
    # 3. hot core: the lower third is nearly solid, brightest at the centre column
    core = np.clip(1 - rel * 2.2, 0, 1) * (0.7 + 0.3 * np.exp(-(pr.lx / max(4.0, pr.w * 0.3)) ** 2))
    v = np.maximum(v, core * (0.72 + 0.2 * noise(x * 3, 0, tt * 9, seed + 2)))
    return np.clip(v, 0, 1)


@effect("fire_flames", "anim", "Flames", pack=PACK, params=[
    Slider("speed", "Speed", 1.0, 0.3, 2.5, 0.1),
    Slider("height", "Flame height (share of prop)", 0.85, 0.3, 1.5, 0.05),
    Slider("turbulence", "Turbulence", 1.0, 0.3, 2.0, 0.1),
    Slider("scale_in", "Tongue size (in)", 8.0, 3.0, 30.0, 1.0, unit="in"),
    Slider("flicker", "Flicker", 1.0, 0.0, 2.0, 0.1),
    HEAT,
    toggle("music", "Flare on the beat", True),
], doc="Fire that reads as fire: a near-white core at the base, tongues that tear loose, race upward and thin out, a ragged flickering top. Sized in inches so a tongue is a tongue on every prop. Flares on the beat if you like.")
def fire_flames(g, m, t, p, pal, st):
    flare = 1 + 0.3 * m.beat_env if p["music"] else 1.0
    out = {}
    for pr in g.props:
        v = flame_field(pr, t, p["speed"], p["height"] * flare, p["turbulence"], p["scale_in"], p["flicker"], pr.idx * 7)
        out[pr.id] = _heat(v, p["heat"], pal)
    return out


@effect("fire_embers", "anim", "Embers rising", pack=PACK, tags=["slow"], params=[
    Slider("bed", "Coal bed level", 0.3, 0.0, 0.8, 0.05),
    Slider("bed_height", "Coal bed height (share of prop)", 0.25, 0.05, 0.6, 0.05),
    Slider("sparks", "Sparks per prop", 6, 1, 30, 1, kind="int"),
    Slider("rise", "Rise speed (in/s)", 14.0, 4.0, 60.0, 1.0, unit="in/s"),
    Slider("wander", "Sideways wander", 0.6, 0.0, 2.0, 0.1),
    Slider("bright", "Bright ones", 0.25, 0.0, 1.0, 0.05),
    HEAT,
], doc="A campfire seen from the road: a dark bed of coals that pulse red and orange at the bottom, and a few sparks at a time that lift off, drift sideways, twinkle and fade before they reach the top. Mostly dark, each spark on its own clock -- the Starfield recipe, in warm colours.")
def fire_embers(g, m, t, p, pal, st):
    out = {}
    for pr in g.props:
        r = rng(pr.idx * 7 + 11)
        # coal bed: slow breathing lumps, brightest at the very bottom
        lumps = fbm(pr.lx / 4.0, pr.ly / 4.0, t * 0.25, pr.idx + 1, octaves=2)
        bed = p["bed"] * np.clip(1 - pr.y01 / max(0.05, p["bed_height"]), 0, 1) ** 0.8 * (0.35 + 0.65 * lumps) * (0.85 + 0.15 * math.sin(t * 0.7 + pr.idx))
        fr = _heat(bed, p["heat"], pal)
        # sparks: each has its own life (3-7 s), birth x, drift and twinkle
        ns = int(p["sparks"])
        ph = r.random(ns); life = 3.0 + 4.0 * r.random(ns); seedk = r.integers(0, 1 << 30, ns)
        for k in range(ns):
            cyc = t / life[k] + ph[k]; n = int(cyc); age = (cyc - n) * life[k]
            rs = rng(seedk[k] + n * 7919)
            x0 = pr.lx.min() + rs.random() * max(1e-3, np.ptp(pr.lx)); wobble = rs.random() * 6.283; big = rs.random() < p["bright"]
            z = p["bed_height"] * pr.h * 0.6 + age * p["rise"] * (0.8 + 0.4 * rs.random())
            x = x0 + p["wander"] * (6 * math.sin(age * 1.3 + wobble) + 3 * math.sin(age * 3.1 + wobble * 2))
            if z > pr.h * 1.05:
                continue
            u = z / pr.h
            fade = (1 - smoothstep(0.55, 1.0, u)) * smoothstep(0.0, 0.08, age)
            tw = 0.6 + 0.4 * math.sin(age * (7 + 5 * rs.random()) + wobble)
            d = np.hypot(pr.lx - x, pr.ly - z)
            spot = np.exp(-(d / (2.2 if big else 1.4)) ** 2) * fade * tw * (1.0 if big else 0.7)
            col = np.array([1.0, 0.95, 0.75]) if big else np.array([1.0, 0.6, 0.2])
            fr = lighten(fr, col * spot[:, None])
        out[pr.id] = np.clip(fr, 0, 1)
    return out


@effect("fire_reignite", "anim", "Reignite", pack=PACK, params=[
    Slider("cycle_bars", "Bars per cycle", 4, 2, 16, 1, kind="int"),
    Slider("die", "Share of cycle dying down", 0.35, 0.1, 0.6, 0.05),
    Slider("flash", "Reignite flash", 0.8, 0.0, 1.0, 0.05),
    HEAT,
], doc="All props burn; one prop at a time dies down to coals over a few bars and is reignited with a flash that hands the fire to the next prop along the row.")
def fire_reignite(g, m, t, p, pal, st):
    cyc = int(p["cycle_bars"])
    bars = m.bar_index + m.bar_phase
    k = int(bars // cyc) % max(1, g.P)
    u = (bars % cyc) / cyc
    out = {}
    for pr in g.props:
        if pr.idx == k:
            if u < p["die"]:
                hgt = 0.85 * (1 - 0.8 * smoothstep(0, p["die"], u))
            else:
                hgt = 0.17 + 0.68 * smoothstep(p["die"], p["die"] + 0.15, u)
        else:
            hgt = 0.85
        v = flame_field(pr, t, 1.0, hgt, 1.0, 8.0, 1.0, pr.idx * 7)
        fr = _heat(v, p["heat"], pal)
        if pr.idx == k and p["die"] <= u < p["die"] + 0.12:
            fl = p["flash"] * (1 - (u - p["die"]) / 0.12)
            fr = lighten(fr, np.broadcast_to(np.array([1.0, 0.9, 0.7]) * fl, (pr.n, 3)))
        out[pr.id] = fr
    return out


@effect("fire_candle", "anim", "Candle flicker", pack=PACK, lamp="incandescent", regions=True, params=[
    Slider("level", "Level", 0.85, 0.3, 1.0, 0.05),
    Slider("flicker", "Flicker depth", 0.25, 0.0, 0.6, 0.05),
    Slider("rate", "Flicker rate", 1.0, 0.3, 3.0, 0.1),
    choice("colours", "Colour source", "painted", ["painted", "palette per prop", "warm white"]),
    Slider("amber", "Amber shift when dim", 1.0, 0.0, 1.0, 0.05),
], doc="Slow, soft candle-light flicker over the whole picture -- each prop breathes on its own irregular rhythm, colours drifting warm as they dim. Calm; good under quiet passages.")
def fire_candle(g, m, t, p, pal, st):
    out = {}
    for pr in g.props:
        r = rng(pr.idx * 3 + 1)
        f = 0.5 + 0.5 * (np.sin(t * 1.9 * p["rate"] + r.random() * 6) * 0.6 + np.sin(t * 4.7 * p["rate"] + r.random() * 6) * 0.4)
        lvl = p["level"] * (1 - p["flicker"] * f)
        pic = np.broadcast_to(np.array([1.0, 0.8, 0.5]), (pr.n, 3)).copy() if p["colours"] == "warm white" else drawn(pr, pal, {"colours": p["colours"]})
        out[pr.id] = pic * lvl
    return out
