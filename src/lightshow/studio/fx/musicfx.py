"""
musicfx.py -- the Music-driven pack: the looks from the first Carol of the Bells
show (onset sparkle, hold-breath, the drop, the outline trace) rebuilt as
timeline clips, plus the EQ band visualiser.
"""

import math
import numpy as np

from ..engine import effect, Slider, choice, toggle
from ...effects import lighten, frost, hsv
from .util import follow, gradient, rng

PACK = "Music driven"
WHITE = np.ones(3)


@effect("music_sparkle", "anim", "Onset sparkle", pack=PACK, params=[
    Slider("sensitivity", "Sensitivity", 1.0, 0.3, 3.0, 0.1),
    Slider("grains", "Grains per hit (per 72 px)", 6, 1, 30, 1, kind="int"),
    Slider("life_s", "Grain life (s)", 0.35, 0.1, 1.5, 0.05, unit="s"),
    choice("color", "Grain colour", "frost", ["frost", "white", "palette"]),
    Slider("glow", "Background glow", 0.1, 0.0, 0.5, 0.02),
    toggle("high_only", "Only high-band hits (bells, hats)", False),
], doc="The Carol opening: every drum hit or bell pluck spawns bright grains on random bulbs that cool and fade. Quiet passages stay dark; the sparkle IS the music.")
def music_sparkle(g, m, t, p, pal, st):
    k = math.exp(-m.dt / p["life_s"] * 3)
    onset = m.hit_high if p["high_only"] else max(m.hit_high, m.hit * 0.85)
    fire = onset * p["sensitivity"] > 0.4 and st.get("prev", 0.0) * p["sensitivity"] <= 0.4
    st["prev"] = onset
    out = {}
    for pr in g.props:
        gr = st.get(pr.id)
        if gr is None or len(gr) != pr.n:
            gr = np.zeros(pr.n)
        gr = gr * k
        if fire:
            n = max(1, int(p["grains"] * pr.n / 72 * min(2.0, onset * p["sensitivity"])))
            r = rng(int(t * 1000) + pr.idx)
            gr[r.choice(pr.n, size=min(n, pr.n), replace=False)] = 1.0
        st[pr.id] = gr
        base = np.broadcast_to(pal.color(1) * p["glow"], (pr.n, 3))
        if p["color"] == "frost":
            sp = frost(gr)
        elif p["color"] == "white":
            sp = WHITE * gr[:, None]
        else:
            sp = pal.pick(rng(pr.idx).integers(0, pal.k, pr.n)) * gr[:, None]
        out[pr.id] = lighten(base, sp)
    return out


@effect("music_hold", "anim", "Hold your breath", pack=PACK, regions=True, params=[
    Slider("sensitivity", "Sensitivity", 1.0, 0.3, 3.0, 0.1),
    Slider("decay_s", "Decay (s)", 0.6, 0.1, 3.0, 0.05, unit="s"),
    Slider("floor", "Others (dim level)", 0.0, 0.0, 0.4, 0.02),
    choice("order", "Order", "shuffled", ["shuffled", "left→right", "right→left", "random"]),
    choice("colours", "Colour source", "painted", ["painted", "palette per prop", "white"]),
], doc="One prop per onset: each hit lights the next prop (fully, in its painted colours) while the others stay dark, and it decays until the next hit. The bench's favourite quiet-passage look.")
def music_hold(g, m, t, p, pal, st):
    from .incandescent import drawn
    onset = max(m.hit_high, m.hit * 0.85) * p["sensitivity"]
    if "flash" not in st or len(st["flash"]) != g.P:
        st["flash"] = np.zeros(g.P); st["i"] = 0; st["prev"] = 0.0
        st["order"] = list(rng(11).permutation(g.P))
    st["flash"] *= math.exp(-m.dt / p["decay_s"])
    if onset > 0.4 and st["prev"] <= 0.4:
        if p["order"] == "shuffled":
            k = st["order"][st["i"] % g.P]
        elif p["order"] == "left→right":
            k = st["i"] % g.P
        elif p["order"] == "right→left":
            k = g.P - 1 - st["i"] % g.P
        else:
            k = int(rng(int(t * 997)).integers(0, g.P))
        st["flash"][k] = 1.0; st["i"] += 1
    st["prev"] = onset
    out = {}
    for pr in g.props:
        lvl = max(p["floor"], st["flash"][pr.idx])
        pic = np.ones((pr.n, 3)) if p["colours"] == "white" else drawn(pr, pal, {"colours": p["colours"]})
        out[pr.id] = pic * lvl
    return out


@effect("music_drop", "anim", "The drop", pack=PACK, params=[
    Slider("threshold", "Energy threshold", 0.45, 0.1, 0.9, 0.05),
    Slider("quiet_glow", "Quiet glow", 0.08, 0.0, 0.4, 0.02),
    Slider("flood_s", "Flood flash (s)", 0.5, 0.1, 2.0, 0.05, unit="s"),
    Slider("lightning", "Lightning on hits", 0.8, 0.0, 1.0, 0.05),
    Slider("bass", "Bass drives level", 0.6, 0.0, 1.0, 0.05),
    choice("color", "Loud colours", "frost", ["frost", "palette"]),
], doc="Below the energy threshold the props hold a faint glow with grains; the moment the music drops in, everything floods white and settles into a bass-driven wash with lightning flashes on the hits.")
def music_drop(g, m, t, p, pal, st):
    loud = m.energy > p["threshold"]
    if loud and not st.get("was_loud", False):
        st["t_drop"] = t
    st["was_loud"] = loud
    since = t - st.get("t_drop", -99)
    flood = math.exp(-since / p["flood_s"] * 3) if since >= 0 else 0.0
    hit = m.hit if m.hit > 0.5 else 0.0
    out = {}
    for pr in g.props:
        if not loud:
            r = rng(int(t * 4) + pr.idx * 17)
            grains = (r.random(pr.n) < 0.02) * 0.6
            fr = lighten(frost(np.full(pr.n, p["quiet_glow"])), frost(grains))
        else:
            lvl = (1 - p["bass"]) + p["bass"] * (0.35 + 0.65 * m.low)
            from .util import noise
            sh = 0.7 + 0.3 * noise(pr.wx / 18, pr.wz / 18, t * 1.2, pr.idx)          # the storm behind the wash
            if p["color"] == "frost":
                fr = frost(np.clip(0.6 * lvl * sh, 0, 1))
            else:
                fr = pal.color(m.bar_index)[None, :] * (lvl * sh)[:, None]
            if hit and p["lightning"] > 0:
                r = rng(int(t * 30) + pr.idx)
                bolt = (r.random(pr.n) < 0.5) * hit * p["lightning"]
                fr = lighten(fr, WHITE * bolt[:, None])
        out[pr.id] = lighten(fr, np.broadcast_to(WHITE * flood, (pr.n, 3)))
    return out


@effect("music_trace", "anim", "Outline trace", pack=PACK, params=[
    Slider("bars", "Bars per lap", 2, 0.5, 8, 0.5),
    Slider("head", "Head brightness", 1.0, 0.3, 1.0, 0.05),
    Slider("fill", "Fill behind the head", 0.5, 0.0, 1.0, 0.05),
    toggle("energy", "Lap speed follows energy", True),
    choice("color", "Colour", "frost", ["frost", "palette"]),
], doc="A bright head runs the wire of every prop (the outline the manufacturer wired), filling in behind itself, then starts over; louder music runs it faster.")
def music_trace(g, m, t, p, pal, st):
    speed = (0.5 + 1.0 * m.energy) if p["energy"] else 1.0
    st["u"] = (st.get("u", 0.0) + m.dt * speed / max(0.1, p["bars"] * m.beat_len * m.beats_per_bar)) % 1.0
    out = {}
    for pr in g.props:
        head = st["u"] * pr.n
        behind = (pr.i <= head)
        v = np.where(behind, p["fill"] * (0.4 + 0.6 * (pr.i / max(1, pr.n))), 0.0)
        v = np.maximum(v, p["head"] * np.exp(-((pr.i - head) / (0.05 * pr.n)) ** 2))
        out[pr.id] = frost(v) if p["color"] == "frost" else pal.color(pr.idx) * v[:, None]
    return out


@effect("music_fill", "anim", "Energy fill", pack=PACK, params=[
    Slider("attack_s", "Attack (s)", 0.08, 0.02, 0.5, 0.01, unit="s"),
    Slider("release_s", "Release (s)", 0.5, 0.05, 3.0, 0.05, unit="s"),
    choice("source", "Follows", "energy", ["energy", "loudness", "bass", "highs"]),
    choice("direction", "Direction", "bottom→top", ["bottom→top", "centre out", "top→bottom"]),
    Slider("floor", "Minimum fill", 0.1, 0.0, 0.6, 0.05),
    toggle("gradient", "Palette gradient along the fill", True),
], doc="Each prop fills up with the loudness of the music -- bottom to top, out from the centre -- with attack and release like a VU meter; the fill is a palette gradient.")
def music_fill(g, m, t, p, pal, st):
    src = {"energy": m.energy, "loudness": m.rms, "bass": m.low, "highs": m.high}[p["source"]]
    lvl = float(follow(st, "lvl", np.array([src]), m.dt, p["attack_s"], p["release_s"])[0])
    h = p["floor"] + (1 - p["floor"]) * lvl
    out = {}
    for pr in g.props:
        u = pr.y01 if p["direction"] == "bottom→top" else (pr.r01 if p["direction"] == "centre out" else 1 - pr.y01)
        on = np.clip((h - u) / 0.05 + 0.5, 0, 1)
        col = gradient(pal, u * 0.8) if p["gradient"] else np.broadcast_to(pal.color(0), (pr.n, 3))
        out[pr.id] = col * on[:, None]
    return out


@effect("music_eq", "anim", "EQ visualiser", pack=PACK, params=[
    choice("assign", "Band per prop", "left→right low→high", ["left→right low→high", "left→right high→low", "centre = bass", "all props: bass", "all props: mids", "all props: highs", "rotate per bar"]),
    Slider("attack_s", "Attack (s)", 0.04, 0.01, 0.4, 0.01, unit="s"),
    Slider("release_s", "Release (s)", 0.35, 0.05, 2.0, 0.05, unit="s"),
    Slider("gain", "Gain", 1.2, 0.5, 3.0, 0.1),
    choice("direction", "Meter direction", "bottom→top", ["bottom→top", "centre out", "along the wire"]),
    choice("colours", "Meter colours", "palette gradient", ["palette gradient", "green / yellow / red", "one colour per band", "frost"]),
    toggle("peak", "Peak-hold dot", True),
    Slider("floor", "Idle level", 0.06, 0.0, 0.3, 0.02),
], doc="A DAW-style analyser: every prop is one EQ band (bass on the left, air on the right, or all props on one band) and its fill height follows that band's level with attack/release and a peak-hold dot.")
def music_eq(g, m, t, p, pal, st):
    bands = np.asarray(m.bands, float) * p["gain"]
    nb = len(bands)
    P = max(1, g.P)
    idx = np.zeros(P, int)
    if p["assign"] == "left→right low→high":
        idx = (np.arange(P) * nb // P)
    elif p["assign"] == "left→right high→low":
        idx = nb - 1 - (np.arange(P) * nb // P)
    elif p["assign"] == "centre = bass":
        idx = (np.abs(np.arange(P) - (P - 1) / 2) * 2 * (nb - 1) / max(1, P - 1)).astype(int)
    elif p["assign"] == "all props: bass":
        idx[:] = 0
    elif p["assign"] == "all props: mids":
        idx[:] = nb // 2
    elif p["assign"] == "all props: highs":
        idx[:] = nb - 1
    else:
        idx = (np.arange(P) + m.bar_index) % nb
    idx = np.clip(idx, 0, nb - 1)
    target = np.clip(bands[idx], 0, 1)
    lvl = follow(st, "lvl", target, m.dt, p["attack_s"], p["release_s"])
    pk = st.get("peak")
    if pk is None or len(pk) != P:
        pk = np.zeros(P)
    pk = np.maximum(lvl, pk - m.dt * 0.6)                          # peak falls slowly
    st["peak"] = pk
    out = {}
    for pr in g.props:
        h = p["floor"] + (1 - p["floor"]) * lvl[pr.idx]
        if p["direction"] == "bottom→top":
            u = pr.y01
        elif p["direction"] == "centre out":
            u = pr.r01
        else:
            u = pr.i / max(1, pr.n - 1)
        on = np.clip((h - u) / 0.04 + 0.5, 0, 1)
        if p["colours"] == "green / yellow / red":
            col = np.stack([np.clip(u * 2.2 - 0.6, 0, 1), np.clip(2.0 - u * 2.2, 0, 1), np.zeros(pr.n)], 1)
        elif p["colours"] == "one colour per band":
            col = np.broadcast_to(pal.color(idx[pr.idx]), (pr.n, 3))
        elif p["colours"] == "frost":
            col = frost(np.clip(on * (0.4 + 0.6 * u), 0, 1)); on = np.ones(pr.n)
        else:
            col = gradient(pal, u * 0.85)
        fr = col * on[:, None]
        if p["peak"]:
            dot = np.exp(-((u - (p["floor"] + (1 - p["floor"]) * pk[pr.idx])) / 0.03) ** 2)
            fr = lighten(fr, WHITE * dot[:, None])
        out[pr.id] = fr
    return out
