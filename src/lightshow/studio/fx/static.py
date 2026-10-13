"""static.py -- the Static pack: a fixed picture that just stays on."""

import math
import numpy as np

from ..engine import effect, Slider, choice, toggle
from .incandescent import drawn

PACK = "Static"


@effect("static_picture", "anim", "Static picture", pack=PACK, regions=True, params=[
    choice("colours", "Colour source", "painted", ["painted", "palette per prop", "palette per region", "single colour", "white"]),
    Slider("brightness", "Brightness", 1.0, 0.05, 1.0, 0.05),
    Slider("breathe", "Slow breathe depth", 0.0, 0.0, 0.6, 0.05),
    Slider("breathe_s", "Breathe period (s)", 8.0, 2.0, 30.0, 0.5, unit="s"),
    choice("lamp", "Lamp model", "led", ["led", "incandescent", "twinkle"]),
    Slider("twinkle_frac", "Twinkle bulbs (twinkle lamp)", 0.18, 0.02, 0.6, 0.02),
    Slider("amber", "Amber shift when dim", 0.6, 0.0, 1.0, 0.05),
], doc="A static view: every prop shows its painted picture (or a palette colour) and stays on. Optional slow breathe and incandescent / twinkle-bulb lamp model. Use it for decorations that are not choreographed, or as the resting look between numbers.")
def static_picture(g, m, t, p, pal, st):
    out = {}
    br = p["brightness"]
    if p["breathe"] > 0:
        br *= 1 - p["breathe"] * 0.5 * (1 + math.sin(2 * math.pi * t / p["breathe_s"]))
    for pr in g.props:
        if p["colours"] == "single colour":
            pic = np.broadcast_to(pal.color(0), (pr.n, 3)).copy()
        elif p["colours"] == "white":
            pic = np.ones((pr.n, 3))
        else:
            pic = drawn(pr, pal, {"colours": p["colours"]})
        out[pr.id] = pic * br
    return out
