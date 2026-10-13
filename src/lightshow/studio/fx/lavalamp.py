"""lavalamp.py -- undulating blobs rising through the props."""

import numpy as np

from .util import rng
from ..engine import effect, Slider, choice
from ...effects import lighten


@effect("lavalamp", "anim", "Lava lamp", pack="Lava lamp", params=[
    Slider("bubbles", "Bubble count", 8, 1, 30, 1, kind="int"),
    Slider("speed", "Speed", 1.0, 0.1, 4.0, 0.1),
    Slider("size_in", "Bubble size (in)", 22.0, 6.0, 80.0, 1.0, unit="in"),
    choice("bubble", "Bubble colour", "palette 1", ["palette 1", "palette 2", "palette 3", "orange", "pink"]),
    choice("goop", "Goop colour", "palette 2", ["palette 1", "palette 2", "palette 3", "blue", "purple", "dark"]),
    Slider("goop_level", "Goop brightness", 0.35, 0.0, 1.0, 0.05),
    Slider("wobble", "Wobble", 1.0, 0.0, 3.0, 0.1),
], doc="Warm blobs drift upward through a dim coloured goop, merging and splitting like a lava lamp. Sized in real inches so a blob spans several bulbs on every prop and crosses the gaps between props.")
def lavalamp(g, m, t, p, pal, st):
    named = {"orange": [1.0, 0.45, 0.05], "pink": [1.0, 0.2, 0.55], "blue": [0.1, 0.25, 1.0],
             "purple": [0.5, 0.1, 1.0], "dark": [0.0, 0.0, 0.0]}

    def col(name):
        if name.startswith("palette"):
            return pal.color(int(name.split()[1]) - 1)
        return np.array(named[name])

    bub, goop = col(p["bubble"]), col(p["goop"]) * p["goop_level"]
    nb = int(p["bubbles"])
    r = rng(1234)
    bx = g.x0 + r.random(nb) * g.width
    bz0 = r.random(nb)
    bs = 0.6 + 0.8 * r.random(nb)                         # relative speed
    br = (0.6 + 0.8 * r.random(nb)) * p["size_in"] / 2   # radius, inches
    bw = r.random(nb) * 6.28
    span = g.height + 2 * p["size_in"]
    tt = t * p["speed"]
    # rising, wrapping
    bz = g.z0 - p["size_in"] + ((bz0 * span + tt * bs * 6.0) % span)
    bxx = bx + np.sin(tt * 0.4 * bs + bw) * 6.0 * p["wobble"]
    out = {}
    for pr in g.props:
        # metaball field: sum of gaussian blobs, then a soft threshold
        dx = pr.wx[:, None] - bxx[None, :]
        dz = pr.wz[:, None] - bz[None, :]
        field = np.exp(-(dx ** 2 + dz ** 2) / (br[None, :] ** 2)).sum(1)
        blob = np.clip((field - 0.35) / 0.4, 0, 1)
        core = np.clip((field - 0.9) / 0.6, 0, 1)         # hot centre a touch brighter / whiter
        colour = bub[None, :] * blob[:, None] + (np.ones(3) - bub)[None, :] * 0.35 * core[:, None]
        out[pr.id] = lighten(np.broadcast_to(goop, (pr.n, 3)), colour)
    return out
