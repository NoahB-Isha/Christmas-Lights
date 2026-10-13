"""starfield.py -- the ambient sparkle field that survived the bench."""

import math
import numpy as np

from .util import rng
from ..engine import effect, Slider, choice, toggle
from ...effects import lighten, frost


def grains(t, p, density, life, seed):
    """Deterministic sparkle field: `density` grains per prop per second,
    born bright, decaying over `life` seconds."""
    g = np.zeros(p.n)
    births = max(1, int(density * life))
    k = np.arange(births)
    tk = t + k * life / births
    slot = (tk / life).astype(np.int64)
    age = (tk % life) / life
    # one cheap hash per grain instead of one Generator per grain
    h = (slot * 1000003 + k * 7 + p.idx * 131 + seed) * 2654435761 % (2 ** 32)
    j = (h % p.n).astype(int)
    np.maximum.at(g, j, (1 - age) ** 1.4)
    return g


@effect("starfield", "anim", "Starfield", pack="Starfield", params=[
    Slider("stars", "Star count (per prop / s)", 6.0, 1.0, 40.0, 1.0),
    Slider("speed", "Speed", 1.0, 0.2, 4.0, 0.1),
    choice("color", "Star colour", "frost", ["frost", "white", "palette", "gold"]),
    Slider("glow", "Background glow", 0.15, 0.0, 0.6, 0.01),
    toggle("breathe", "Props breathe in and out", True),
    toggle("music", "Extra stars on the beat", False),
], doc="Calm pixel twinkle over a faint coloured glow, whole props slowly fading in and out. Reads as an intro / ambient texture; not music-reactive unless asked.")
def starfield(g, m, t, p, pal, st):
    out = {}
    tt = t * p["speed"]
    for pr in g.props:
        dens = p["stars"] + (8.0 * m.beat_env if p["music"] else 0.0)
        gr = grains(tt, pr, dens, 1.6, 11) + 0.5 * grains(tt, pr, dens * 0.5, 2.6, 13)
        gr = np.clip(gr, 0, 1)
        whole = 0.5 + 0.5 * math.sin(2 * math.pi * (tt / (9 + pr.idx % 3) + pr.idx * 0.37)) if p["breathe"] else 1.0
        base_col = pal.color(1) if p["color"] == "palette" else (np.array([1.0, 0.7, 0.2]) if p["color"] == "gold" else np.array([0.3, 0.5, 1.0]))
        base = np.broadcast_to(base_col * p["glow"] * (0.4 + 0.6 * whole ** 2), (pr.n, 3))
        if p["color"] == "frost":
            stars = frost(gr)
        elif p["color"] == "white":
            stars = np.broadcast_to(gr[:, None], (pr.n, 3))
        elif p["color"] == "gold":
            stars = np.array([1.0, 0.75, 0.25]) * gr[:, None]
        else:
            stars = pal.pick(rng(pr.idx).integers(0, pal.k, pr.n)) * gr[:, None]
        out[pr.id] = lighten(base, stars)
    return out
