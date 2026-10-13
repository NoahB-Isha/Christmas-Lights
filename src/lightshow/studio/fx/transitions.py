"""
transitions.py -- how one animation hands over to the next.

fn(g, m, u, p, pal, A, B, st) -> frame.  u runs 0..1 over the transition clip.
A = the outgoing frame, B = the incoming frame (both already rendered).
"""

import math
import numpy as np

from .util import rng
from ..engine import effect, Slider, choice, toggle
from ...effects import lighten

CURVE = choice("curve", "Timing curve", "linear", ["linear", "ease in-out", "ease in", "ease out"])


def _mix(A, B, w):
    """Per-prop crossfade; w scalar or {pid: (n,) or scalar}."""
    out = {}
    for pid in A:
        ww = w[pid] if isinstance(w, dict) else w
        ww = np.asarray(ww, float)
        if ww.ndim == 1:
            ww = ww[:, None]
        out[pid] = A[pid] * (1 - ww) + B[pid] * ww
    return out


@effect("flash_in", "trans", "Flash in", pack="Transitions", params=[
    Slider("peak", "Flash brightness", 1.0, 0.3, 1.0, 0.05),
    Slider("attack", "Flash position (share of clip)", 0.0, 0.0, 0.9, 0.05),
    Slider("fall", "Fall time (share of clip)", 0.6, 0.1, 1.0, 0.05),
    choice("color", "Flash colour", "white", ["white", "palette", "warm white"]),
    toggle("cut_under", "Hard cut underneath (else crossfade)", True),
    Slider("flashes", "Number of flashes", 1, 1, 4, 1, kind="int"),
], doc="Everything hits white (or a colour), then the flash decays with the new animation underneath. Attack delays the hit into the clip; several flashes stutter like a strobe.")
def flash_in(g, m, u, p, pal, A, B, st):
    col = {"white": np.ones(3), "palette": pal.color(0), "warm white": np.array([1.0, 0.85, 0.6])}[p["color"]]
    nfl = int(p["flashes"])
    ua = (u - p["attack"]) / max(0.05, 1 - p["attack"])                  # 0..1 after the attack
    lvl = 0.0
    if ua >= 0:
        seg = (ua * nfl) % 1.0 if nfl > 1 else ua
        lvl = p["peak"] * math.exp(-seg / max(0.05, p["fall"]) * 4.0)
    w = 1.0 if (ua >= 0 and p["cut_under"]) else float(np.clip(u, 0, 1))
    out = {}
    for pid in B:
        n = B[pid].shape[0]
        base = A[pid] * (1 - w) + B[pid] * w
        out[pid] = lighten(base, np.broadcast_to(col * lvl, (n, 3)))
    return out


@effect("twinkle_burst", "trans", "Twinkle burst", pack="Transitions", params=[
    Slider("density", "Twinkle density", 0.35, 0.05, 1.0, 0.05),
    Slider("grain_s", "Grain life (s)", 0.35, 0.1, 1.0, 0.05, unit="s"),
    choice("color", "Twinkle colour", "white", ["white", "palette", "frost"]),
    Slider("dissolve", "Dissolve sharpness", 1.0, 0.2, 3.0, 0.1),
    CURVE,
], doc="A burst of twinkles sweeps over the props while the old picture dissolves into the new one; the burst is densest halfway through.")
def twinkle_burst(g, m, u, p, pal, A, B, st):
    env = math.sin(math.pi * u) ** 1.5                      # 0 -> peak -> 0
    out = {}
    for pr in g.props:
        r = rng(pr.idx * 977 + int(m.t / p["grain_s"] * 3))
        born = r.random(pr.n) < p["density"] * env
        age = ((m.t / p["grain_s"] * 3) % 1.0)
        tw = born * (1 - age) ** 1.2
        # per-pixel random dissolve: pixels flip from A to B at random times weighted by the burst
        flip = rng(pr.idx * 31 + 5).random(pr.n) < u ** (1 / p["dissolve"])
        base = np.where(flip[:, None], B[pr.id], A[pr.id])
        if p["color"] == "white":
            col = np.ones(3)
        elif p["color"] == "frost":
            col = np.array([0.7, 0.85, 1.0])
        else:
            col = pal.pick(np.arange(pr.n) % pal.k)
        out[pr.id] = lighten(base, col * tw[:, None])
    return out


@effect("ice", "trans", "Ice up / down", pack="Transitions", params=[
    choice("direction", "Direction", "up", ["up", "down"]),
    Slider("edge_in", "Frost edge width (in)", 8.0, 2.0, 30.0, 1.0, unit="in"),
    Slider("melt", "Melt behind edge", 0.6, 0.0, 1.0, 0.05),
    Slider("edge_glow", "Edge brightness", 1.0, 0.2, 1.0, 0.05),
    choice("edge_color", "Edge colour", "ice", ["ice", "white", "palette"]),
    CURVE,
], doc="A bright white-blue freeze line climbs (or falls) across the group by real height; behind it the new animation is revealed, softened for a moment as if thawing.")
def ice(g, m, u, p, pal, A, B, st):
    ice_col = {"ice": np.array([0.75, 0.9, 1.0]), "white": np.ones(3), "palette": pal.color(0)}[p["edge_color"]] * p["edge_glow"]
    out = {}
    span = g.height + 2 * p["edge_in"]
    for pr in g.props:
        z = pr.wz - g.z0
        front = -p["edge_in"] + u * span if p["direction"] == "up" else g.height + p["edge_in"] - u * span
        d = (z - front) if p["direction"] == "up" else (front - z)   # >0 = not yet reached
        edge = np.exp(-(d / (p["edge_in"] * 0.5)) ** 2)
        done = np.clip(-d / p["edge_in"], 0, 1)                       # 0 at the edge -> 1 well behind
        soft = 1 - p["melt"] * (1 - done)                             # thawing behind the line
        base = np.where((d > 0)[:, None], A[pr.id], B[pr.id] * soft[:, None])
        out[pr.id] = lighten(base, ice_col * edge[:, None])
    return out


@effect("wipe", "trans", "Wipe", pack="Transitions", params=[
    choice("direction", "Direction", "left→right", ["left→right", "right→left", "bottom→top", "top→bottom", "centre out", "edges in"]),
    Slider("soft_in", "Edge softness (in)", 6.0, 0.0, 40.0, 1.0, unit="in"),
    Slider("edge_glow", "Edge glow", 0.5, 0.0, 1.0, 0.05),
    choice("edge_color", "Edge colour", "palette", ["palette", "white", "none"]),
    Slider("dark_gap_in", "Dark gap behind the edge (in)", 0.0, 0.0, 60.0, 2.0, unit="in"),
    CURVE,
], doc="The new animation replaces the old one along a straight edge that travels across the whole group in world inches -- across the row, up the props, or out from the middle.")
def wipe(g, m, u, p, pal, A, B, st):
    s = max(0.5, p["soft_in"])
    out = {}
    for pr in g.props:
        d = p["direction"]
        if d == "left→right":
            c = (pr.wx - g.x0) - u * (g.width + 2 * s) + s
        elif d == "right→left":
            c = (g.x1 - pr.wx) - u * (g.width + 2 * s) + s
        elif d == "bottom→top":
            c = (pr.wz - g.z0) - u * (g.height + 2 * s) + s
        elif d == "top→bottom":
            c = (g.z1 - pr.wz) - u * (g.height + 2 * s) + s
        elif d == "centre out":
            c = np.abs(pr.wx - (g.x0 + g.x1) / 2) - u * (g.width / 2 + 2 * s) + s
        else:
            c = (g.width / 2 - np.abs(pr.wx - (g.x0 + g.x1) / 2)) - u * (g.width / 2 + 2 * s) + s
        w = np.clip(0.5 - c / s, 0, 1)                                # 1 where B has arrived
        glow = np.exp(-(c / (s * 0.6)) ** 2) * p["edge_glow"]
        fr = A[pr.id] * (1 - w[:, None]) + B[pr.id] * w[:, None]
        if p["dark_gap_in"] > 0:                                       # a black band trails the edge
            gap = np.clip(1 - np.clip(-c, 0, p["dark_gap_in"]) / p["dark_gap_in"], 0, 1)
            gap = np.where(c < 0, 1 - gap, 1.0)
            fr = fr * np.where(c < 0, gap, 1.0)[:, None]
        ec = pal.color(0) if p["edge_color"] == "palette" else (np.ones(3) if p["edge_color"] == "white" else np.zeros(3))
        out[pr.id] = lighten(fr, np.broadcast_to(ec, (pr.n, 3)) * glow[:, None])
    return out


@effect("crossfade", "trans", "Crossfade", pack="Transitions", params=[CURVE,
    toggle("dip", "Dip to black in the middle", False)],
        doc="Plain dissolve, optionally dipping to black halfway.")
def crossfade(g, m, u, p, pal, A, B, st):
    if p["dip"]:
        k = 1 - math.sin(math.pi * u) ** 2 * 0.9
        return {pid: (A[pid] * (1 - u) + B[pid] * u) * k for pid in A}
    return _mix(A, B, u)


@effect("shatter", "trans", "Shatter", pack="Transitions", params=[
    Slider("pieces", "Pieces per prop", 6, 2, 20, 1, kind="int"),
    Slider("flash", "Flash on break", 0.6, 0.0, 1.0, 0.05),
    CURVE,
], doc="The outgoing picture breaks into pieces (runs along the wire) that drop out one by one, revealing the new animation; a white flash on the break.")
def shatter(g, m, u, p, pal, A, B, st):
    out = {}
    npc = int(p["pieces"])
    for pr in g.props:
        piece = (pr.i * npc // max(1, pr.n))
        order = rng(pr.idx * 17 + 3).permutation(npc)
        gone = order[piece] < u * npc
        fl = p["flash"] * math.exp(-u * 6)
        fr = np.where(gone[:, None], B[pr.id], A[pr.id])
        out[pr.id] = lighten(fr, np.broadcast_to(np.ones(3) * fl, (pr.n, 3)))
    return out


@effect("prop_dissolve", "trans", "Prop by prop", pack="Transitions", params=[
    choice("order", "Order", "left→right", ["left→right", "right→left", "centre out", "edges in", "random", "shuffled pairs"]),
    Slider("overlap", "Overlap between props", 0.4, 0.0, 1.0, 0.05),
    Slider("flash", "Flash as each prop switches", 0.4, 0.0, 1.0, 0.05),
    CURVE,
], doc="The props change over one at a time, in order along the row (or out from the middle, or at random), each with a small flash as it flips. The clearest way to show that something new is starting.")
def prop_dissolve(g, m, u, p, pal, A, B, st):
    P = max(1, g.P)
    out = {}
    for pr in g.props:
        if p["order"] == "right→left":
            k = P - 1 - pr.idx
        elif p["order"] == "centre out":
            k = int(abs(pr.idx - (P - 1) / 2) * 2)
        elif p["order"] == "edges in":
            k = P - 1 - int(abs(pr.idx - (P - 1) / 2) * 2)
        elif p["order"] == "random":
            k = int(rng(pr.idx * 977 + 5).integers(0, P))
        elif p["order"] == "shuffled pairs":
            k = int(rng(pr.idx // 2 * 31 + 11).integers(0, P))
        else:
            k = pr.idx
        span = 1.0 / P
        start = k * span * (1 - p["overlap"] * 0.9)
        w = float(np.clip((u - start) / max(1e-3, span + p["overlap"] * 0.3), 0, 1))
        fr = A[pr.id] * (1 - w) + B[pr.id] * w
        fl = p["flash"] * math.exp(-((w - 0.5) / 0.22) ** 2) if 0 < w < 1 else 0.0
        out[pr.id] = lighten(fr, np.broadcast_to(np.ones(3) * fl, (pr.n, 3)))
    return out


@effect("curtain", "trans", "Curtain", pack="Transitions", params=[
    choice("direction", "Curtain", "open", ["open", "close", "open then close"]),
    Slider("soft_in", "Edge softness (in)", 8.0, 0.0, 60.0, 1.0, unit="in"),
    Slider("edge_glow", "Edge glow", 0.5, 0.0, 1.0, 0.05),
    choice("edge_color", "Edge colour", "white", ["white", "palette", "none"]),
    CURVE,
], doc="Two halves part from the middle (or close in from the ends) revealing the new animation behind, with a glowing seam -- a stage curtain across the whole group.")
def curtain(g, m, u, p, pal, A, B, st):
    s = max(0.5, p["soft_in"])
    mid = (g.x0 + g.x1) / 2
    uu = u
    if p["direction"] == "close":
        uu = 1 - u
    elif p["direction"] == "open then close":
        uu = 1 - abs(1 - 2 * u)
    half = (g.width / 2 + s) * uu
    ec = {"white": np.ones(3), "palette": pal.color(0)}.get(p["edge_color"], np.zeros(3))
    out = {}
    for pr in g.props:
        d = np.abs(pr.wx - mid) - half                                   # <0 = curtain has opened here
        w = np.clip(0.5 - d / s, 0, 1)
        fr = A[pr.id] * (1 - w[:, None]) + B[pr.id] * w[:, None]
        glow = np.exp(-(d / (s * 0.6)) ** 2) * p["edge_glow"]
        out[pr.id] = lighten(fr, ec * glow[:, None])
    return out


@effect("spiral", "trans", "Spiral out", pack="Transitions", params=[
    Slider("turns", "Turns", 1.5, 0.5, 5.0, 0.25),
    choice("direction", "Direction", "clockwise", ["clockwise", "anticlockwise"]),
    Slider("soft", "Edge softness", 0.15, 0.02, 0.6, 0.01),
    Slider("edge_glow", "Edge glow", 0.4, 0.0, 1.0, 0.05),
    CURVE,
], doc="The new animation sweeps in like a clock hand spiralling out from the centre of every prop -- the wipe for round props (snowflakes, stars, wreaths).")
def spiral(g, m, u, p, pal, A, B, st):
    sgn = 1 if p["direction"] == "clockwise" else -1
    out = {}
    for pr in g.props:
        ang = (sgn * pr.ang / (2 * math.pi)) % 1.0
        prog = ang / max(0.01, p["turns"]) + pr.r01 * (1 - 1 / max(1.0, p["turns"]))
        d = prog - u * 1.1
        w = np.clip(0.5 - d / p["soft"], 0, 1)
        fr = A[pr.id] * (1 - w[:, None]) + B[pr.id] * w[:, None]
        glow = np.exp(-(d / (p["soft"] * 0.7)) ** 2) * p["edge_glow"]
        out[pr.id] = lighten(fr, pal.color(0) * glow[:, None])
    return out


@effect("blackout_cut", "trans", "Blackout cut", pack="Transitions", params=[
    Slider("dark", "Darkness", 1.0, 0.3, 1.0, 0.05),
    Slider("hold", "Dark share of the clip", 0.4, 0.05, 0.9, 0.05),
    Slider("snap_in", "Fade out (share before dark)", 0.15, 0.0, 0.5, 0.05),
    Slider("snap_out", "Fade in (share after dark)", 0.1, 0.0, 0.5, 0.05),
    toggle("flash_back", "Flash back in", True),
], doc="Everything drops to black for a moment, then the new animation snaps back. The pause is the point -- put it on a rest in the music and the next section lands twice as hard.")
def blackout_cut(g, m, u, p, pal, A, B, st):
    a0 = (1 - p["hold"]) / 2
    fo, fi = max(1e-3, p["snap_in"]), max(1e-3, p["snap_out"])
    if u < a0:
        lvl = 1 - p["dark"] * float(np.clip((u - (a0 - fo)) / fo, 0, 1))
        base, src = lvl, A
    elif u < a0 + p["hold"]:
        base, src = 1 - p["dark"], B if u > a0 + p["hold"] * 0.5 else A
    else:
        w = float(np.clip((u - (a0 + p["hold"])) / fi, 0, 1))
        base, src = (1 - p["dark"]) + p["dark"] * w, B
    fl = 0.0
    if p["flash_back"] and a0 + p["hold"] <= u < a0 + p["hold"] + fi:
        fl = 0.8 * math.exp(-((u - (a0 + p["hold"])) / fi) * 4)
    return {pid: lighten(src[pid] * base, np.broadcast_to(np.ones(3) * fl, (src[pid].shape[0], 3))) for pid in A}


@effect("melt", "trans", "Melt", pack="Transitions", params=[
    CURVE,
    Slider("ragged", "Ragged melt front", 0.12, 0.0, 0.3, 0.01),
    Slider("glow", "Heat glow at the front", 0.6, 0.0, 1.0, 0.05),
    Slider("drips", "Drops", 0.6, 0.0, 1.0, 0.05),
    toggle("up", "Melt upward instead", False),
], doc="The outgoing picture melts away from the top down (or up from the ground): a ragged front descends with a warm glow on its edge, drops of the old picture's colour fall ahead of it, and the new animation is what is underneath.")
def melt(g, m, u, p, pal, A, B, st):
    from .util import noise, smoothstep
    out = {}
    for pr in g.props:
        n = noise(pr.lx / 5.0, 0.0, 0.0, pr.idx * 3.1)
        y = (1 - pr.y01) if p["up"] else pr.y01
        line = 1.0 + p["ragged"] - u * (1 + 2 * p["ragged"]) + (n - 0.5) * 2 * p["ragged"]
        d = y - line                                                       # >0 above the front = already melted away
        keep = smoothstep(0.04, -0.04, d)
        fr = A[pr.id] * keep[:, None] + B[pr.id] * (1 - keep)[:, None]
        edge = np.exp(-(d / 0.04) ** 2) * p["glow"]
        hot = np.array([1.0, 0.55, 0.25])
        fr = lighten(fr, hot * edge[:, None])
        if p["drips"] > 0 and 0.02 < u < 0.98:                            # drops of the OLD colour fall ahead of the front
            r = rng(pr.idx * 13 + 99)
            xs = pr.lx.min() + r.random(6) * max(1e-3, np.ptp(pr.lx)); ph = r.random(6)
            for k in range(6):
                if r.random() > p["drips"]:
                    continue
                yd = line - ((u * 3 + ph[k]) % 1.0) * 0.6
                near = np.exp(-((pr.lx - xs[k]) / 1.5) ** 2) * np.exp(-((y - yd) * pr.h / 2.5) ** 2)
                col = A[pr.id][np.argmin(np.abs(y - line))]
                fr = lighten(fr, col * near[:, None])
        out[pr.id] = np.clip(fr, 0, 1)
    return out
