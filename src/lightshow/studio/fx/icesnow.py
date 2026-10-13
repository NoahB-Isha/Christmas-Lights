"""icesnow.py -- the Ice & Snow pack: snowfall, freeze/shatter, crystals, aurora, frost breath."""

import math
import numpy as np

from ..engine import effect, Slider, choice, toggle
from ...effects import lighten, frost
from .util import noise, fbm, smoothstep, gradient, rng, glints

PACK = "Ice & Snow"
ICE = np.array([0.55, 0.8, 1.0]); WHITE = np.ones(3); DEEP = np.array([0.05, 0.15, 0.6])


@effect("snowfall", "anim", "Snowfall", pack=PACK, tags=["slow"], params=[
    Slider("flakes", "Flakes (per 10 ft)", 14, 2, 60, 1, kind="int"),
    Slider("speed", "Fall speed (in/s)", 14.0, 4.0, 80.0, 1.0, unit="in/s"),
    Slider("size_in", "Near flake size (in)", 3.5, 1.0, 12.0, 0.5, unit="in"),
    Slider("depth", "Depth (far layers)", 1.0, 0.0, 1.0, 0.05),
    Slider("wind", "Wind", 0.4, 0.0, 2.0, 0.1),
    Slider("gusts", "Gusts", 0.5, 0.0, 1.0, 0.05),
    Slider("sky", "Sky glow", 0.1, 0.0, 0.5, 0.02),
    choice("color", "Flake colour", "white", ["white", "frost", "palette"]),
], doc="Snow with depth: three layers of flakes in world inches -- near ones big, bright and fast with a slow tumble; mid; and a dusting of small, dim, slow far ones -- all leaning into the same wind, with gusts that come and go. The parallax is what makes it hypnotic from a car.")
def snowfall(g, m, t, p, pal, st):
    col = WHITE if p["color"] == "white" else (ICE if p["color"] == "frost" else pal.color(1))
    # layers: (count share, speed, size, brightness, sway)
    layers = [(1.0, 1.0, 1.0, 1.0, 1.0), (1.6 * p["depth"], 0.6, 0.6, 0.55, 0.7), (2.6 * p["depth"], 0.35, 0.38, 0.28, 0.45)]
    gust = 1 + p["gusts"] * 1.2 * (noise(t * 0.08, 0, 0, 3) - 0.5) * 2                     # slow, wandering wind strength
    out = {pr.id: DEEP[None, :] * (p["sky"] * (0.6 + 0.4 * pr.y01))[:, None] for pr in g.props}
    for li, (share, spd, size, bright, sway) in enumerate(layers):
        nf = max(1, int(p["flakes"] * share * g.width / 120))
        if share <= 0:
            continue
        r = rng(77 + li * 101)
        fx = g.x0 + r.random(nf) * g.width; fz0 = r.random(nf); fs = 0.75 + 0.5 * r.random(nf); ph = r.random(nf) * 6.283
        rad = p["size_in"] * size / 2
        span = g.height + 4 * rad
        z = g.z1 + 2 * rad - ((fz0 * span + t * p["speed"] * spd * fs) % span)
        x = fx + np.sin(t * 0.7 * fs * sway + ph) * 10 * p["wind"] * sway + t * 6 * p["wind"] * gust * spd
        x = g.x0 + (x - g.x0) % max(1.0, g.width)
        tumble = 0.75 + 0.25 * np.sin(t * 2.3 * fs + ph * 2)                                   # near flakes catch the light as they turn
        w = bright * (tumble if li == 0 else np.ones(nf))
        for pr in g.props:
            # only the flakes over this prop (3 radii of slack) -- the full distance matrix is 20x the work
            x0, x1 = pr.wx.min() - 3 * rad, pr.wx.max() + 3 * rad
            sel = (x >= x0) & (x <= x1)
            if not sel.any():
                continue
            d2 = (pr.wx[:, None] - x[sel][None, :]) ** 2 + (pr.wz[:, None] - z[sel][None, :]) ** 2
            v = (np.exp(-d2 / rad ** 2) * w[sel][None, :]).max(1)
            out[pr.id] = lighten(out[pr.id], col * v[:, None])
    return out


@effect("ice_freeze", "anim", "Freeze & shatter", pack=PACK, params=[
    Slider("cycle_bars", "Bars per cycle", 8, 2, 32, 1, kind="int"),
    Slider("trace", "Trace share", 0.3, 0.1, 0.5, 0.05),
    Slider("freeze", "Freeze share", 0.3, 0.1, 0.5, 0.05),
    Slider("hold_level", "Frozen blue level", 0.45, 0.1, 1.0, 0.05),
    toggle("shatter", "Shatter to dark at the end", True),
    toggle("music", "Cycle restarts on the phrase", True),
], doc="The bench favourite: a bright white trace runs the wire of every prop, then the props freeze bottom→top behind a glowing edge, hold a soft blue, and shatter to dark before the next cycle.")
def ice_freeze(g, m, t, p, pal, st):
    cyc = int(p["cycle_bars"])
    u = ((m.bar_index + m.bar_phase) % cyc) / cyc if p["music"] else (t / (cyc * 2.0)) % 1.0
    a, b = p["trace"], p["trace"] + p["freeze"]
    out = {}
    for pr in g.props:
        if u < a:                                                 # trace along the wire, filling behind the head
            head = (u / a) * pr.n
            k = pr.i
            v = np.where(k <= head, 0.35 + 0.65 * np.exp(-((head - k) / (0.08 * pr.n)) ** 2), 0.0)
            fr = frost(v)
        elif u < b:                                               # freeze bottom -> top
            f = (u - a) / (b - a)
            front = f * 1.15 - 0.075
            d = pr.y01 - front
            edge = np.exp(-(d / 0.08) ** 2)
            frozen = np.where(d < 0, p["hold_level"], 0.35)
            depth = (0.7 + 0.3 * pr.y01)[:, None]
            fr = np.where(d[:, None] < 0, (ICE * depth + DEEP * (1 - depth)) * p["hold_level"], frost(np.full(pr.n, 0.35) * (0.8 + 0.2 * pr.y01)))
            fr = lighten(fr, WHITE * edge[:, None])
        else:                                                     # hold then shatter
            f = (u - b) / max(1e-6, 1 - b)
            lvl = p["hold_level"] * (1 + 0.08 * math.sin(t * 2))
            # frozen: deeper blue at the base, paler at the top, a few frost grains -- never a flat fill
            depth = (0.7 + 0.3 * pr.y01)[:, None]
            fr = (ICE * depth + DEEP * (1 - depth)) * lvl
            r = rng(int(t * 2) + pr.idx * 13)
            fr = lighten(fr, frost((r.random(pr.n) < 0.03) * 0.7))
            if p["shatter"] and f > 0.8:
                ff = (f - 0.8) / 0.2
                r = rng(pr.idx * 5 + 2)
                gone = r.random(pr.n) < ff
                fr = fr * (~gone)[:, None]
                if f < 0.85:
                    fr = lighten(fr, np.broadcast_to(WHITE * (1 - (f - 0.8) / 0.05) * 0.8, (pr.n, 3)))
        out[pr.id] = fr
    return out


@effect("ice_crystal", "anim", "Crystal growth", pack=PACK, params=[
    Slider("bars", "Bars per growth", 2, 1, 8, 1, kind="int"),
    Slider("tip_sparkle", "Tip sparkle", 0.6, 0.0, 1.0, 0.05),
    choice("color", "Crystal colour", "frost", ["frost", "palette"]),
    toggle("stagger", "Stagger props", True),
], doc="Ice crystals grow from the centre of every prop out to its tips over a couple of bars, tips glittering white, then recede and grow again. Snowflake-shaped props love this.")
def ice_crystal(g, m, t, p, pal, st):
    nb = int(p["bars"])
    out = {}
    for pr in g.props:
        off = pr.idx * 0.17 if p["stagger"] else 0.0
        u = ((m.bar_index + m.bar_phase) / nb + off) % 1.0
        grow = 1 - abs(1 - 2 * u)                                       # 0 -> 1 -> 0
        reach = grow * 1.1
        v = np.clip((reach - pr.r01) / 0.12 + 1, 0, 1) * (0.45 + 0.55 * (1 - pr.r01))
        edge = np.exp(-((pr.r01 - reach) / 0.06) ** 2)
        base = frost(v) if p["color"] == "frost" else pal.color(0) * v[:, None]
        sp = p["tip_sparkle"] * edge * (0.5 + 0.5 * np.sin(t * 9 + pr.i * 0.7))
        out[pr.id] = lighten(base, WHITE * sp[:, None])
    return out


@effect("aurora", "anim", "Northern lights", pack=PACK, params=[
    Slider("speed", "Drift speed", 1.0, 0.2, 3.0, 0.1),
    Slider("curtain_in", "Curtain width (in)", 40.0, 10.0, 200.0, 5.0, unit="in"),
    choice("colours", "Colours", "green / violet", ["green / violet", "palette", "teal / pink"]),
    Slider("level", "Brightness", 0.9, 0.3, 1.0, 0.05),
], doc="Curtains of green and violet drift across the group and ripple up the props, sized in real inches so they hang across several props at once.")
def aurora(g, m, t, p, pal, st):
    tt = t * p["speed"]
    c1, c2 = {"green / violet": ([0.1, 1.0, 0.35], [0.55, 0.15, 1.0]), "teal / pink": ([0.0, 0.9, 0.8], [1.0, 0.2, 0.7]),
              "palette": (pal.color(0), pal.color(1))}[p["colours"]]
    c1, c2 = np.asarray(c1, float), np.asarray(c2, float)
    out = {}
    for pr in g.props:
        x = pr.wx / p["curtain_in"]; z = pr.y01
        n1 = noise(x * 2.0, z * 1.5, tt * 0.5, 1.0)
        n2 = noise(x * 3.1 + 7, z * 2.4, tt * 0.8, 4.0)
        band = np.exp(-((z - 0.35 - 0.3 * (n1 - 0.5)) / 0.28) ** 2)
        mix = n2[:, None]
        col = c1 * (1 - mix) + c2 * mix
        v = np.clip(band * (0.5 + 0.7 * n1), 0, 1) * p["level"]
        out[pr.id] = col * v[:, None]
    return out


@effect("frost_breath", "anim", "Frost breath", pack=PACK, params=[
    Slider("period_s", "Breath period (s)", 10.0, 3.0, 30.0, 0.5, unit="s"),
    Slider("floor", "Dimmest level", 0.25, 0.0, 0.8, 0.05),
    Slider("sparkle", "Sparkle", 0.25, 0.0, 1.0, 0.05),
    toggle("stagger", "Props breathe out of step", True),
], doc="A slow icy breath: each prop swells from deep blue to white-cored frost and back over many seconds, a few grains sparkling on top. The calm ambient look.")
def frost_breath(g, m, t, p, pal, st):
    out = {}
    for pr in g.props:
        ph = pr.idx * 0.9 if p["stagger"] else 0.0
        b = 0.5 + 0.5 * math.sin(2 * math.pi * t / p["period_s"] + ph)
        lvl = p["floor"] + (1 - p["floor"]) * b
        v = lvl * (0.75 + 0.25 * (1 - pr.r01))
        fr = frost(v)
        r = rng(int(t * 3) + pr.idx * 91)
        sp = (r.random(pr.n) < 0.03 * p["sparkle"]) * (0.6 + 0.4 * r.random(pr.n))
        out[pr.id] = lighten(fr, WHITE * sp[:, None])
    return out


@effect("ice_sculpture", "anim", "Ice sculpture", pack=PACK, tags=["slow"], params=[
    Slider("level", "Level", 0.8, 0.3, 1.0, 0.05),
    Slider("blue", "Blue depth", 0.6, 0.0, 1.0, 0.05),
    Slider("clarity", "Clarity (clear ↔ cloudy)", 0.5, 0.0, 1.0, 0.05),
    Slider("veins", "Veins & inclusions", 0.5, 0.0, 1.0, 0.05),
    Slider("sheen_s", "Seconds per light sweep", 14.0, 4.0, 40.0, 1.0, unit="s"),
    Slider("sparkle", "Frost sparkle", 0.4, 0.0, 1.0, 0.05),
    Slider("cracks", "Crack flashes", 0.4, 0.0, 1.0, 0.05),
], doc="The prop as if carved from a block of ice: a translucent blue-white body, denser and bluer toward the base, with cloudy and clear patches that drift very slowly; thin bright veins and inclusions inside; a soft white highlight that sweeps around the sculpture as if a light were circling it; frost glints that flash white and cool to blue; and now and then a crack flashes across the ice and fades. Nothing moves faster than a slow breath.")
def ice_sculpture(g, m, t, p, pal, st):
    deep = np.array([0.08, 0.32, 0.9]); pale = np.array([0.62, 0.86, 1.0]); white = np.ones(3)
    out = {}
    for pr in g.props:
        sd = pr.idx * 5.3
        # body: clear vs cloudy patches (very slow), denser blue toward the base
        cloud = fbm(pr.lx / 7.0, pr.ly / 7.0, t * 0.02, sd, octaves=3)
        clear = smoothstep(0.35 - 0.25 * p["clarity"], 0.65 + 0.25 * p["clarity"], cloud)
        depth = p["blue"] * (0.35 + 0.65 * (1 - pr.y01))
        body = pale[None, :] * (1 - depth)[:, None] + deep[None, :] * depth[:, None]
        body = body * (0.45 + 0.55 * clear)[:, None] * p["level"]
        # veins: thin bright lines where a slow noise field crosses its middle value
        vn = fbm(pr.lx / 4.0 + 7, pr.ly / 4.0, t * 0.015, sd + 2, octaves=2)
        vein = np.exp(-((vn - 0.5) / 0.035) ** 2) * p["veins"] * (0.5 + 0.5 * clear)
        body = lighten(body, (white * 0.6 + pale * 0.4) * (vein * 0.8)[:, None])
        # specular sweep: a light circling the sculpture; the highlight is a soft band across the prop
        th = 2 * math.pi * (t / p["sheen_s"] + pr.idx * 0.13)
        proj = (pr.lx * math.cos(th) + (pr.ly - pr.h / 2) * math.sin(th)) / max(1.0, max(pr.w, pr.h) / 2)   # -1..1
        c = math.sin(th * 0.5 + 1.0)                                                   # the band drifts across
        hi = np.exp(-((proj - c) / 0.22) ** 2) * (0.55 + 0.45 * clear)
        body = lighten(body, white * (hi * 0.75 * p["level"])[:, None])
        # frost glints: born white, cool into blue
        if p["sparkle"] > 0:
            gl = glints(pr, t, 0.18, pr.idx + 31, 10.0) * (0.35 + 0.65 * clear)
            r = rng(pr.idx * 17 + 3); keep = r.random(pr.n) < 0.25
            body = lighten(body, frost(gl * keep * p["sparkle"]))
        # cracks: every so often a thin line flashes across the prop and fades over a second
        if p["cracks"] > 0:
            period = 9.0 + 7.0 * ((pr.idx * 0.618) % 1.0)
            n = int(t / period); age = t - n * period
            rc = rng(n * 7919 + pr.idx * 131)
            if rc.random() < p["cracks"] and age < 1.4:
                a = rc.random() * math.pi; off = (rc.random() - 0.5) * 0.8 * max(pr.w, pr.h)
                d = np.abs((pr.lx * math.cos(a) + (pr.ly - pr.h / 2) * math.sin(a)) - off)
                line = np.exp(-(d / 1.6) ** 2) * math.exp(-age * 2.5) * smoothstep(0.0, 0.08, age)
                body = lighten(body, white * line[:, None])
        out[pr.id] = np.clip(body, 0, 1)
    return out
