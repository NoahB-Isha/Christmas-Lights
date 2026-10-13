"""techno.py -- the Techno pack: hard, monochrome, quantised."""

import math
import numpy as np

from .util import rng
from ..engine import effect, Slider, choice, toggle
from ...effects import lighten

PACK = "Techno"


def _col(pal, p, k):
    if p.get("mono", False):
        return pal.color(0)
    return pal.color(k)


@effect("techno_scan", "anim", "Scanner", pack=PACK, params=[
    Slider("width_in", "Bar width (in)", 18.0, 4.0, 80.0, 2.0, unit="in"),
    Slider("beats", "Beats per pass", 1, 0.5, 4, 0.5),
    toggle("bounce", "Bounce (else wrap)", True),
    toggle("mono", "Single colour", True),
    Slider("floor", "Background", 0.0, 0.0, 0.3, 0.02),
    toggle("trail", "Trail", True),
], doc="A hard-edged bar scans across the row once per beat (or per few beats), bouncing or wrapping, in one colour on black. Cold and mechanical.")
def techno_scan(g, m, t, p, pal, st):
    beats = m.beat_index + m.beat_phase
    u = (beats / p["beats"]) % 1.0
    if p["bounce"]:
        u = 1 - abs(1 - 2 * u)
    x = g.x0 + u * g.width
    col = _col(pal, p, m.bar_index)
    out = {}
    for pr in g.props:
        d = np.abs(pr.wx - x)
        bar = (d < p["width_in"] / 2).astype(float)
        if p["trail"]:
            bar = np.maximum(bar, np.clip(1 - d / (p["width_in"] * 2.5), 0, 1) ** 3 * 0.5)
        fr = np.broadcast_to(col * p["floor"], (pr.n, 3)).copy()
        out[pr.id] = lighten(fr, col * bar[:, None])
    return out


@effect("techno_grid", "anim", "Grid flicker", pack=PACK, params=[
    Slider("cell_in", "Cell size (in)", 12.0, 4.0, 48.0, 2.0, unit="in"),
    choice("rate", "Flicker rate", "16ths", ["8ths", "16ths", "32nds"]),
    Slider("density", "Share of cells on", 0.4, 0.05, 0.9, 0.05),
    toggle("mono", "Single colour", False),
    Slider("colour_bars", "Bars per colour", 1, 1, 8, 1, kind="int"),
], doc="The props are cut into square cells that switch on and off in a new random pattern every 16th note; colour steps every bar. Pure machine rhythm.")
def techno_grid(g, m, t, p, pal, st):
    sub = {"8ths": 2, "16ths": 4, "32nds": 8}[p["rate"]]
    tick = int((m.beat_index + m.beat_phase) * sub)
    col = _col(pal, p, m.bar_index // max(1, int(p["colour_bars"])))
    out = {}
    for pr in g.props:
        cx = np.floor((pr.wx - g.x0) / p["cell_in"]).astype(int); cz = np.floor((pr.wz - g.z0) / p["cell_in"]).astype(int)
        h = ((cx * 73856093) ^ (cz * 19349663) ^ (tick * 83492791)) % 1000 / 1000.0
        on = h < p["density"]
        out[pr.id] = col * on[:, None]
    return out


@effect("techno_laser", "anim", "Lasers", pack=PACK, params=[
    Slider("lines", "Lines per beat", 2, 1, 6, 1, kind="int"),
    Slider("width_in", "Line width (in)", 4.0, 1.0, 20.0, 0.5, unit="in"),
    Slider("speed_in_s", "Speed (in/s)", 600.0, 100.0, 2000.0, 50.0, unit="in/s"),
    Slider("decay_s", "Decay (s)", 0.35, 0.1, 1.5, 0.05, unit="s"),
    toggle("mono", "Single colour", False),
    choice("angle", "Angle", "diagonal", ["vertical", "diagonal", "horizontal"]),
], doc="Thin bright lines shoot across the whole group on every beat and fade -- vertical, diagonal or horizontal -- like lasers cutting through fog.")
def techno_laser(g, m, t, p, pal, st):
    out = {}
    nl = int(p["lines"])
    bl = m.beat_len
    age = m.beat_phase * bl
    ang = {"vertical": 0.0, "diagonal": 0.6, "horizontal": 1.4}[p["angle"]]
    for pr in g.props:
        fr = np.zeros((pr.n, 3))
        # lines from this beat and the previous one (they may still be decaying)
        for back in (0, 1):
            a = age + back * bl
            bi = m.beat_index - back
            r = rng(bi * 31 + 7)
            for k in range(nl):
                start = g.x0 - 20 + r.random() * (g.width + 40)
                dirn = 1 if r.random() < 0.5 else -1
                x = start + dirn * a * p["speed_in_s"] * (0.6 + 0.8 * r.random())
                # line coordinate: x shifted by height for the angle
                c = pr.wx + math.tan(ang) * (pr.wz - g.z0) * (1 if k % 2 else -1) - x
                line = np.exp(-(c / (p["width_in"] / 2)) ** 2) * math.exp(-a / p["decay_s"])
                fr = lighten(fr, _col(pal, p, bi * nl + k) * line[:, None])
        out[pr.id] = fr
    return out


@effect("techno_pulse", "anim", "Hard pulse", pack=PACK, params=[
    Slider("decay", "Decay (share of beat)", 0.6, 0.2, 1.0, 0.05),
    Slider("floor", "Floor level", 0.05, 0.0, 0.5, 0.05),
    toggle("mono", "Single colour", True),
    toggle("white_downbeat", "White on the downbeat", True),
    choice("shape", "Shape", "from bottom", ["whole prop", "from bottom", "from centre"]),
    Slider("spread", "Row spread (delay across the row, share of beat)", 0.1, 0.0, 0.5, 0.05),
], doc="Every beat the whole group slams on and decays; the bar's downbeat hits white. Optionally the pulse rises from the bottom or bursts from the centre of each prop.")
def techno_pulse(g, m, t, p, pal, st):
    on_down = m.beat_index % m.beats_per_bar == 0
    col = np.ones(3) if (on_down and p["white_downbeat"]) else _col(pal, p, m.bar_index)
    out = {}
    for pr in g.props:
        # the pulse travels along the row: each prop fires a little later than the one to its left
        ph = np.clip(m.beat_phase - p["spread"] * g.rank[pr.idx], 0, 1)
        lvl = p["floor"] + (1 - p["floor"]) * math.exp(-ph / max(0.05, p["decay"]) * 3.5)
        if p["shape"] == "from bottom":
            shape = np.clip(1.4 - pr.y01 - ph * 0.8, 0, 1)
        elif p["shape"] == "from centre":
            shape = np.clip(1.4 - pr.r01 - ph * 0.8, 0, 1)
        else:
            shape = np.ones(pr.n)
        out[pr.id] = col * (lvl * shape)[:, None]
    return out
