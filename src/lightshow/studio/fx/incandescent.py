"""
incandescent.py -- the Incandescent pack: 1950s-60s Times-Square-sign
programs. Props are DRAWN as what they are (paint regions in their painted
colours; unpainted props take a palette colour) and switched hard on and
off on the beat grid. The LampBank adds the filament attack/afterglow and
the amber shift, so everything here is crisp 0/1 levels.
"""

import math
import numpy as np

from .util import rng
from ..engine import effect, Slider, choice, toggle
from ...effects import lighten

PACK = "Incandescent"
COMMON = [
    Slider("brightness", "Brightness", 1.0, 0.2, 1.0, 0.05),
    Slider("amber", "Amber shift when dim", 1.0, 0.0, 1.0, 0.05),
    choice("colours", "Colour source", "painted", ["painted", "palette per prop", "palette per region"]),
]


def drawn(pr, pal, p):
    """(n,3) full-level picture of one prop."""
    mode = p.get("colours", "painted")
    out = np.zeros((pr.n, 3))
    names = list(pr.regions.keys())
    if mode == "palette per prop" or (mode == "painted" and not pr.region_names):
        out[:] = pal.color(pr.idx)
        return out
    for k, name in enumerate(names):
        mask = pr.regions[name]
        if mode == "painted" and name in pr.region_color:
            out[mask] = pr.region_color[name]
        else:
            out[mask] = pal.color(k)
    return out


def whole(g, pal, p, levels):
    """levels: (P,) per-prop 0..1 -> frame."""
    return {pr.id: drawn(pr, pal, p) * levels[pr.idx] * p["brightness"] for pr in g.props}


def _buckets(g, max_b=8):
    """Props bucketed left -> right (<= max_b buckets) so a program written
    for 6 bench props scales to 25 in the yard."""
    nb = min(max_b, g.P)
    return np.minimum(nb - 1, (g.rank * nb).astype(int)), nb


@effect("inc_walk", "anim", "Sign walk", pack=PACK, lamp="incandescent", regions=True, params=COMMON + [
    Slider("step_beats", "Beats per step", 2, 1, 8, 1, kind="int"),
    toggle("all_on_last_bar", "All on in the last bar of each phrase", True),
    toggle("trail", "Leave a dim trail", False),
], doc="One prop (bucket) lit at a time, stepping along the row on the beat grid; in the last bar of every 4-bar phrase everything comes on together. Walking at half speed (2 beats per step) read best on the bench.")
def inc_walk(g, m, t, p, pal, st):
    b, nb = _buckets(g)
    step = (m.beat_index // max(1, int(p["step_beats"]))) % nb
    lv = (b == step).astype(float)
    if p["trail"]:
        prev = (b == (step - 1) % nb)
        lv = np.maximum(lv, prev * 0.35)
    if p["all_on_last_bar"] and (m.beat_index % (m.beats_per_bar * 4)) >= m.beats_per_bar * 3:
        lv[:] = 1.0
    return whole(g, pal, p, lv)


@effect("inc_build", "anim", "Build", pack=PACK, lamp="incandescent", regions=True, params=COMMON + [
    Slider("phrase_bars", "Bars per cycle", 4, 2, 8, 1, kind="int"),
    Slider("flashes", "Flashes at the end", 3, 0, 6, 1, kind="int"),
    choice("order", "Build order", "left→right", ["left→right", "right→left", "centre out", "random"]),
], doc="Props come on one per beat until the row is full, hold, flash together, go dark, and start again on the next cycle. The classic sign build.")
def inc_build(g, m, t, p, pal, st):
    b, nb = _buckets(g)
    cyc_beats = int(p["phrase_bars"]) * m.beats_per_bar
    k = m.beat_index % cyc_beats
    if p["order"] == "right→left":
        b = nb - 1 - b
    elif p["order"] == "centre out":
        b = np.abs(b - (nb - 1) / 2.0).astype(int)
    elif p["order"] == "random":
        perm = rng(g.P).permutation(nb); b = perm[b]
    nflash = int(p["flashes"])
    flash_beats = math.ceil(nflash / 2) if nflash else 0
    build_beats = min(nb, cyc_beats - flash_beats - 1)
    if k < build_beats:                                    # building
        lv = (b <= k * (nb - 1) / max(1, build_beats - 1)).astype(float)
    elif k < cyc_beats - flash_beats - 1:                   # hold
        lv = np.ones(g.P)
    elif k < cyc_beats - 1:                                 # flashes on 8ths
        on = (m.beat_phase < 0.5)
        lv = np.full(g.P, 1.0 if on else 0.0)
    else:                                                   # dark beat before the next build
        lv = np.zeros(g.P)
    return whole(g, pal, p, lv)


@effect("inc_alternate", "anim", "Alternate", pack=PACK, lamp="incandescent", regions=True, params=COMMON + [
    Slider("swap_beats", "Beats per swap", 1, 1, 4, 1, kind="int"),
    choice("split", "Alternate", "odd / even props", ["odd / even props", "halves", "regions within each prop"]),
], doc="Two halves of the picture swap on the beat: odd/even props, left/right halves, or the regions inside each prop (Santa's suit vs trim).")
def inc_alternate(g, m, t, p, pal, st):
    phase = (m.beat_index // max(1, int(p["swap_beats"]))) % 2
    if p["split"] == "regions within each prop":
        out = {}
        for pr in g.props:
            pic = drawn(pr, pal, p) * p["brightness"]
            names = list(pr.regions.keys())
            keep = np.zeros(pr.n, bool)
            for k, name in enumerate(names):
                if k % 2 == phase or len(names) == 1:
                    keep |= pr.regions[name]
            out[pr.id] = pic * keep[:, None]
        return out
    if p["split"] == "halves":
        lv = ((g.rank >= 0.5).astype(int) == phase).astype(float)
    else:
        lv = ((np.arange(g.P) % 2) == phase).astype(float)
    return whole(g, pal, p, lv)


@effect("inc_marquee", "anim", "Marquee chase", pack=PACK, lamp="incandescent", regions=True, params=COMMON + [
    Slider("every", "Every Nth bulb lit", 3, 2, 6, 1, kind="int"),
    choice("rate", "Chase rate", "8ths", ["quarter notes", "8ths", "16ths"]),
    toggle("reverse", "Reverse direction", False),
    toggle("outline_only", "Only the prop's largest region", False),
], doc="The bulbs chase along the wire like a theatre marquee -- every Nth bulb lit, marching one bulb per note. Each prop keeps its drawn colours.")
def inc_marquee(g, m, t, p, pal, st):
    sub = {"quarter notes": 1, "8ths": 2, "16ths": 4}[p["rate"]]
    tick = int((m.beat_index + m.beat_phase) * sub)
    n_every = int(p["every"])
    out = {}
    for pr in g.props:
        pic = drawn(pr, pal, p) * p["brightness"]
        i = np.arange(pr.n)
        k = (i - tick) if not p["reverse"] else (i + tick)
        on = (k % n_every) == 0
        if p["outline_only"] and pr.region_names:
            big = max(pr.region_names, key=lambda nm: pr.regions[nm].sum())
            on &= pr.regions[big]
        out[pr.id] = pic * on[:, None]
    return out


@effect("inc_drawn", "anim", "Drawn picture", pack=PACK, lamp="incandescent", regions=True, params=COMMON + [
    Slider("blink", "Region blink strength", 0.7, 0.0, 1.0, 0.05),
    Slider("blink_beats", "Beats per region", 1, 1, 4, 1, kind="int"),
    toggle("trim_twinkle", "White trim twinkles", True),
    Slider("pop", "Bar-downbeat pop", 0.5, 0.0, 1.0, 0.05),
], doc="The whole picture stays on in its painted colours; one region at a time pops brighter on the beat (Santa's hat, then face, then coat...), white trim twinkles, and every bar downbeat gives a warm pop.")
def inc_drawn(g, m, t, p, pal, st):
    out = {}
    pop = p["pop"] * m.downbeat_env * 0.4
    for pr in g.props:
        pic = drawn(pr, pal, p)
        names = pr.region_names or list(pr.regions.keys())
        lv = np.full(pr.n, 1.0 - 0.45 * p["blink"])
        which = (m.beat_index // max(1, int(p["blink_beats"])) + pr.idx) % max(1, len(names))
        lv[pr.regions[names[which]]] = 1.0
        if p["trim_twinkle"]:
            for nm in pr.region_names:
                c = pr.region_color.get(nm)
                if c is not None and c.min() > 0.85:                     # a white-ish region = trim
                    r = rng(int(m.t * 6) + pr.idx * 17)
                    mask = pr.regions[nm]
                    lv[mask] = np.where(r.random(mask.sum()) < 0.75, 1.0, 0.15)
        fr = pic * (lv * p["brightness"])[:, None]
        out[pr.id] = lighten(fr, np.array([1.0, 0.75, 0.4]) * pop)
    return out


# ------------------------------------------------------------- slower looks
@effect("inc_glow_breathe", "anim", "Warm breathe", pack=PACK, lamp="incandescent", regions=True, params=COMMON + [
    Slider("period_s", "Breath period (s)", 6.0, 2.0, 30.0, 0.5, unit="s"),
    Slider("depth", "Depth", 0.5, 0.1, 0.9, 0.05),
    toggle("stagger", "Props out of step", True),
    toggle("bar_lock", "Lock the period to 2 bars", False),
], doc="The whole picture stays lit and breathes slowly -- a long, warm swell and fade, the filaments going amber as they dim. The slow one for verses.")
def inc_glow_breathe(g, m, t, p, pal, st):
    out = {}
    for pr in g.props:
        ph = pr.idx * 0.8 if p["stagger"] else 0.0
        if p["bar_lock"]:
            u = ((m.bar_index + m.bar_phase) / 2.0) % 1.0
            b = 0.5 - 0.5 * math.cos(2 * math.pi * u + ph)
        else:
            b = 0.5 + 0.5 * math.sin(2 * math.pi * t / p["period_s"] + ph)
        lvl = (1 - p["depth"]) + p["depth"] * b
        out[pr.id] = drawn(pr, pal, p) * lvl * p["brightness"]
    return out


@effect("inc_slow_wave", "anim", "Slow wave", pack=PACK, lamp="incandescent", regions=True, params=COMMON + [
    Slider("bars", "Bars per crossing", 4, 1, 16, 1, kind="int"),
    Slider("width", "Wave width (share of row)", 0.5, 0.15, 1.5, 0.05),
    Slider("floor", "Dim level", 0.25, 0.0, 0.8, 0.05),
    choice("direction", "Direction", "left→right", ["left→right", "right→left", "bounce"]),
], doc="A soft crest of brightness drifts along the row over several bars; props ahead of and behind it rest at a dim amber glow. Gentle, readable from a moving car.")
def inc_slow_wave(g, m, t, p, pal, st):
    bars = m.bar_index + m.bar_phase
    u = (bars / max(1, int(p["bars"]))) % 1.0
    if p["direction"] == "right→left":
        u = 1 - u
    elif p["direction"] == "bounce":
        u = 1 - abs(1 - 2 * u)
    centre = -p["width"] / 2 + u * (1 + p["width"])
    lv = p["floor"] + (1 - p["floor"]) * np.exp(-((g.rank - centre) / (p["width"] / 2.5)) ** 2)
    return whole(g, pal, p, lv)


@effect("inc_twinkle_bulbs", "anim", "Twinkle bulbs", pack=PACK, lamp="twinkle", regions=True, params=COMMON + [
    Slider("twinkle_frac", "Share of twinkle bulbs", 0.2, 0.05, 0.6, 0.05),
    Slider("level", "Level", 0.9, 0.3, 1.0, 0.05),
], doc="The classic bimetal-strip string: the picture stays on while a fixed random subset of bulbs blink on their own slow, irregular cycles. Nothing to do with the beat -- that is the charm.")
def inc_twinkle_bulbs(g, m, t, p, pal, st):
    return whole(g, pal, p, np.full(g.P, p["level"]))


@effect("inc_region_wander", "anim", "Region wander", pack=PACK, lamp="incandescent", regions=True, params=COMMON + [
    Slider("period_s", "Wander period (s)", 12.0, 3.0, 40.0, 0.5, unit="s"),
    Slider("depth", "How far toward warm white", 0.6, 0.1, 1.0, 0.05),
    toggle("dim_too", "Dim as well as recolour", True),
], doc="Each painted region slowly drifts between its painted colour and warm white on its own long cycle, so the picture keeps shifting without ever flashing. Very slow; for the quiet moments.")
def inc_region_wander(g, m, t, p, pal, st):
    warm = np.array([1.0, 0.82, 0.55])
    out = {}
    for pr in g.props:
        pic = drawn(pr, pal, p)
        names = list(pr.regions.keys())
        fr = pic.copy()
        for k, nm in enumerate(names):
            ph = (k * 1.7 + pr.idx * 0.9)
            w = 0.5 + 0.5 * math.sin(2 * math.pi * t / p["period_s"] + ph)
            mask = pr.regions[nm]
            mix = p["depth"] * w
            fr[mask] = pic[mask] * (1 - mix) + warm * mix
            if p["dim_too"]:
                fr[mask] *= 0.6 + 0.4 * (1 - w)
        out[pr.id] = fr * p["brightness"]
    return out
