"""
classics.py -- the Christmas classics pack: the looks everybody recognises,
rebuilt (round 4) so every one has texture, depth and a bit of life.

    Candy cane       stripes along the wire (or diagonal in inches), soft edges, sugar sheen
    Tree & ornaments needles in several greens, shaded glass baubles that catch the light,
                     mini fairy lights, a tinsel garland and a star
    Wrapped present  every prop is a gift: patterned paper, a ribbon with a satin sweep, a bow
    Fairy lights     a string of mini lights: warm or multicolour, each fading on its own
    Garland          tinsel wrapped around each prop, shimmering
    Toy train        a lit train running along the group's whole wire, headlight first, smoke behind
    Shooting star    a white-hot star with a sparkling tail crossing the group
    Snow globe       shaken, swirls, settles -- and the snow piles up at the bottom
    Icicles          icicles of different lengths; drops swell at the tips and fall
"""

import math
import numpy as np

from ..engine import effect, Slider, choice, toggle
from ...effects import lighten, frost
from .util import noise, smoothstep, gradient, rng, glints, blob, baubles, wire_offsets

PACK = "Christmas classics"
WHITE = np.ones(3)
RED = np.array([1.0, 0.04, 0.04])
GREEN = np.array([0.05, 0.85, 0.18])
GOLD = np.array([1.0, 0.72, 0.12])
SILVER = np.array([0.85, 0.88, 1.0])
ICE = np.array([0.55, 0.82, 1.0])
WARM = np.array([1.0, 0.78, 0.45])

# the greens of a real tree: deep shadow needles, mid pine, sunlit tips; and a blue spruce
GREENS = {
    "forest mix": (np.array([0.0, 0.22, 0.05]), np.array([0.04, 0.55, 0.12]), np.array([0.32, 0.85, 0.15])),
    "blue spruce": (np.array([0.0, 0.18, 0.12]), np.array([0.05, 0.45, 0.35]), np.array([0.3, 0.75, 0.55])),
    "lime & pine": (np.array([0.0, 0.3, 0.03]), np.array([0.15, 0.7, 0.08]), np.array([0.55, 0.95, 0.12])),
}


def tree_body(pr, t, kind="forest mix", level=0.5, seed=0):
    """Needle texture: three greens mixed by two scales of noise in inches, lighter
    toward the tips of the prop, swaying gently. Never a flat green."""
    deep, mid, light = GREENS.get(kind, GREENS["forest mix"])
    n1 = noise(pr.wx / 9.0, pr.wz / 9.0, t * 0.05, seed + pr.idx)          # clumps of branches
    n2 = noise(pr.wx / 2.6, pr.wz / 2.6, t * 0.08, seed + pr.idx + 5)      # individual needles
    u = np.clip((0.55 * n1 + 0.45 * n2 - 0.5) * 1.9 + 0.5 + 0.22 * (pr.y01 - 0.5), 0, 1)
    body = np.where((u < 0.5)[:, None], deep * (1 - 2 * u)[:, None] + mid * (2 * u)[:, None],
                    mid * (2 - 2 * u)[:, None] + light * (2 * u - 1)[:, None])
    sway = 0.85 + 0.15 * noise(pr.wx / 30.0, pr.wz / 30.0, t * 0.3, seed + 9)
    return body * (level * sway)[:, None]


def fairy(pr, t, density=0.5, colours="warm white", pal=None, fade=1.0, seed=0):
    """Mini lights: a random subset of bulbs, each fading up and down on its own slow clock."""
    r = rng(pr.idx * 211 + seed)
    on = r.random(pr.n) < 0.04 + 0.16 * density
    ph = r.random(pr.n) * 6.283; sp = 0.5 + r.random(pr.n)
    lvl = (0.5 + 0.5 * np.sin(t * sp * fade + ph)) ** 2 * on
    if colours == "multicolour":
        cols = np.array([RED, GREEN, np.array([0.2, 0.4, 1.0]), GOLD, np.array([0.9, 0.2, 0.8])])
        c = cols[r.integers(0, len(cols), pr.n)]
    elif colours == "palette" and pal is not None:
        c = pal.chroma[r.integers(0, pal.k, pr.n)]
    elif colours == "cool white":
        c = np.broadcast_to(np.array([0.85, 0.92, 1.0]), (pr.n, 3))
    else:
        c = np.broadcast_to(WARM, (pr.n, 3))
    return c * lvl[:, None]


def tinsel(pr, t, spacing=14.0, width=1.6, angle=35.0, col=SILVER, drift=0.0, sparkle=0.7, seed=0):
    """Diagonal shimmering bands wrapped around the prop in LOCAL inches."""
    a = math.radians(angle)
    c = pr.lx * math.sin(a) + pr.ly * math.cos(a) + drift * t
    d = np.abs(((c + spacing / 2) % spacing) - spacing / 2)
    band = np.exp(-(d / width) ** 2)
    sh = 0.45 + 0.55 * noise(pr.lx / 1.5, pr.ly / 1.5, t * 3.0, seed) * (1 - sparkle) + sparkle * glints(pr, t, 1.2, seed + 3, 9.0)
    return col[None, :] * (band * (0.35 + 0.65 * sh))[:, None]


# --------------------------------------------------------------------- candy cane
@effect("candy_cane", "anim", "Candy cane", pack=PACK, tags=[], params=[
    choice("style", "Stripes run", "along the wire", ["along the wire", "diagonal across the prop"]),
    Slider("stripe_px", "Stripe length (bulbs / in)", 6, 2, 30, 1, kind="int"),
    Slider("beats", "Beats per stripe step", 1, 0.25, 4, 0.25),
    choice("colours", "Colours", "red / white", ["red / white", "green / white", "red / green / white", "palette"]),
    toggle("reverse", "Reverse direction", False),
    Slider("soft", "Edge softness", 0.3, 0.0, 1.0, 0.05),
    Slider("sheen", "Sugar sheen", 0.35, 0.0, 1.0, 0.05),
    toggle("hold", "Hold between steps (else glide)", False),
], doc="Candy-cane stripes marching along the wire of every prop (a quarter stripe per beat, like a real candy-cane rope light) or diagonally across it in inches. Soft edges and a glossy sugar sheen so the white stripes read as candy, not as a flat bar.")
def candy_cane(g, m, t, p, pal, st):
    if p["colours"] == "red / white":
        cols = np.array([RED, WHITE])
    elif p["colours"] == "green / white":
        cols = np.array([GREEN, WHITE])
    elif p["colours"] == "red / green / white":
        cols = np.array([RED, WHITE, GREEN, WHITE])
    else:
        cols = pal.rgb
    step = (m.beat_index + m.beat_phase) / p["beats"]
    if p["hold"]:
        step = math.floor(step)
    shift = step * p["stripe_px"] * (-1 if p["reverse"] else 1)
    out = {}
    for pr in g.props:
        if p["style"] == "along the wire":
            u = (pr.i - shift) / p["stripe_px"]
        else:
            u = ((pr.lx + pr.ly) * 0.7071 - shift) / p["stripe_px"]
        k = np.floor(u).astype(int) % len(cols)
        fr = cols[k].astype(float)
        f = u - np.floor(u)
        if p["soft"] > 0:
            w = smoothstep(1 - 0.5 * p["soft"], 1.0, f)[:, None]
            fr = fr * (1 - w) + cols[(k + 1) % len(cols)] * w
        # glossy highlight: a bright line sliding along each stripe, plus a faint sugar sparkle
        gloss = np.exp(-((f - 0.5) / 0.18) ** 2) * 0.25 + 0.12 * glints(pr, t, 0.8, 4, 10.0)
        fr = fr * (1 - 0.18 * p["sheen"]) + fr * (p["sheen"] * gloss)[:, None] * 1.4
        out[pr.id] = np.clip(fr, 0, 1)
    return out


# ------------------------------------------------------------------- tree & ornaments
@effect("ornaments", "anim", "Tree & ornaments", pack=PACK, tags=["slow"], params=[
    choice("greens", "Needles", "forest mix", list(GREENS)),
    Slider("green", "Tree level", 0.65, 0.1, 1.0, 0.05),
    Slider("density", "Ornaments per prop", 8, 0, 30, 1, kind="int"),
    Slider("size_in", "Ornament size (in)", 3.5, 1.5, 12.0, 0.5, unit="in"),
    choice("colours", "Ornament colours", "gold / red / blue / silver", ["gold / red / blue / silver", "red / gold", "palette", "silver & white"]),
    Slider("glint", "Ornaments catch the light", 0.6, 0.0, 1.0, 0.05),
    Slider("fairy", "Mini lights", 0.45, 0.0, 1.0, 0.05),
    toggle("garland", "Tinsel garland", True),
    toggle("star", "Star on top", True),
    Slider("move_bars", "Bars before ornaments move", 0, 0, 16, 1, kind="int"),
], doc="A real tree, not a green fill: needles in three greens mixed at two scales, lighter toward the tips and swaying. Shaded glass baubles sized in inches sit on it -- dark rim, bright colour, a white highlight -- and now and then one catches the light and flashes; a tinsel garland wraps diagonally, warm mini lights fade in and out between them, and the topmost bulbs are the star.")
def ornaments(g, m, t, p, pal, st):
    if p["colours"] == "gold / red / blue / silver":
        cols = np.array([GOLD, RED, np.array([0.15, 0.35, 1.0]), SILVER])
    elif p["colours"] == "red / gold":
        cols = np.array([RED, GOLD])
    elif p["colours"] == "silver & white":
        cols = np.array([SILVER, WHITE * 0.9, np.array([0.7, 0.8, 1.0])])
    else:
        cols = pal.chroma
    slot = int(m.bar_index // p["move_bars"]) if p["move_bars"] >= 1 else 0
    out = {}
    for pr in g.props:
        fr = tree_body(pr, t, p["greens"], p["green"])
        if p["garland"]:
            fr = lighten(fr, tinsel(pr, t, spacing=max(10.0, pr.h / 3.5), width=1.4, angle=32, drift=0.6, sparkle=0.6, seed=pr.idx) * 0.55)
        if p["fairy"] > 0:
            fr = lighten(fr, fairy(pr, t, p["fairy"], "warm white", pal, 0.9, seed=3))
        r = rng(pr.idx * 47 + slot * 911)
        n_orn = int(p["density"])
        if n_orn and pr.n:
            centres = r.integers(0, pr.n, n_orn)                     # baubles hang where there are bulbs
            which = r.integers(0, len(cols), n_orn)
            ph = r.random(n_orn); rate = 0.08 + 0.1 * r.random(n_orn)
            u = (t * rate + ph) % 1.0
            ks = np.arange(n_orn)
            gl = p["glint"] * (np.exp(-u * 18) * 0.9 + 0.25 * m.downbeat_env * (ks % 3 == m.bar_index % 3))
            rgb, cover = baubles(pr, pr.lx[centres], pr.ly[centres], p["size_in"] / 2, cols[which], gl)
            fr = fr * (1 - cover)[:, None] + rgb                      # baubles sit IN FRONT of the needles
        if p["star"]:
            top = smoothstep(0.9, 1.0, pr.y01)
            star = (0.75 + 0.25 * math.sin(t * 1.7 + pr.idx)) * top
            fr = lighten(fr, GOLD * star[:, None])
            fr = lighten(fr, WHITE * (0.6 * glints(pr, t, 0.5, 11, 12.0) * top)[:, None])
        out[pr.id] = np.clip(fr, 0, 1)
    return out


# --------------------------------------------------------------------- present
@effect("ribbon", "anim", "Wrapped present", pack=PACK, tags=[], params=[
    choice("colours", "Ribbon / paper", "gold on red", ["gold on red", "red on white", "silver on blue", "red on green", "palette", "random per prop", "random per prop (palette)"]),
    choice("pattern", "Paper pattern", "polka dots", ["polka dots", "stripes", "plain satin", "mixed (per prop)"]),
    Slider("reshuffle_bars", "Bars before random presents re-wrap (0 = never)", 0, 0, 32, 1, kind="int"),
    Slider("ribbon_in", "Ribbon width (in)", 4.0, 1.5, 14.0, 0.5, unit="in"),
    Slider("bars", "Bars per satin sweep", 2, 0.5, 8, 0.5),
    Slider("bow", "Bow size", 1.0, 0.0, 2.0, 0.1),
    toggle("cross", "Ribbon both ways", True),
    Slider("paper_level", "Paper level", 0.55, 0.2, 1.0, 0.05),
], doc="Every prop becomes a gift: patterned paper (dots, stripes or satin in inches), a ribbon crossing it through the middle both ways, a bright sweep of light sliding along the ribbon every couple of bars, and a bow at the crossing whose loops glint. Sized in inches, so it fits the snowflake and Santa alike. 'Random per prop' gives every prop one of the preset paper / ribbon combinations (or a pair drawn from the palette) and can re-wrap them every few bars.")
def ribbon(g, m, t, p, pal, st):
    pairs = {"gold on red": (GOLD, RED), "red on white": (RED, WHITE * 0.85),
             "silver on blue": (SILVER, np.array([0.1, 0.25, 0.9])), "red on green": (RED, np.array([0.05, 0.5, 0.12]))}
    wraps = list(pairs.values())                                          # random presents draw from the preset combinations above
    patterns = ["polka dots", "stripes", "plain satin"]
    rib0, paper0 = pairs.get(p["colours"], (pal.color(0), pal.color(1)))
    slot = int(m.bar_index // p["reshuffle_bars"]) if p["reshuffle_bars"] >= 1 else 0
    bars = m.bar_index + m.bar_phase
    u = (bars / p["bars"]) % 1.0
    out = {}
    for pr in g.props:
        rib, paper, pattern = rib0, paper0, p["pattern"]
        r = rng(pr.idx * 977 + slot * 7919 + 13)
        if p["colours"] == "random per prop":
            rib, paper = wraps[int(r.integers(0, len(wraps)))]
        elif p["colours"] == "random per prop (palette)":
            i = int(r.integers(0, pal.k)); j = (i + 1 + int(r.integers(0, max(1, pal.k - 1)))) % pal.k if pal.k > 1 else i
            paper = pal.chroma[i]; rib = pal.chroma[j] if pal.k > 1 else GOLD
            if np.abs(rib - paper).max() < 0.35:                          # too similar to read as a ribbon -> metallic ribbon
                rib = GOLD if paper[2] > paper[0] else SILVER
        if pattern == "mixed (per prop)":
            pattern = patterns[int(r.integers(0, len(patterns)))]
        # --- paper
        if pattern == "polka dots":
            d = np.hypot(((pr.lx + 3) % 6) - 3, ((pr.ly + 3) % 6) - 3)
            pat = 0.6 + 0.4 * smoothstep(2.0, 1.1, d)
        elif pattern == "stripes":
            pat = 0.6 + 0.4 * smoothstep(0.35, 0.65, 0.5 + 0.5 * np.sin((pr.lx + pr.ly) * 0.9))
        else:
            pat = 0.7 + 0.3 * noise(pr.lx / 6, pr.ly / 6, t * 0.3, pr.idx)
        fr = paper[None, :] * (p["paper_level"] * pat)[:, None]
        # --- ribbon: vertical through the centre, horizontal a little above the middle
        w = p["ribbon_in"] / 2
        cy = pr.h * 0.55
        v_band = smoothstep(w * 1.3, w * 0.7, np.abs(pr.lx))
        h_band = smoothstep(w * 1.3, w * 0.7, np.abs(pr.ly - cy)) if p["cross"] else np.zeros(pr.n)
        band = np.maximum(v_band, h_band)
        # satin: fine weave shimmer plus a bright sweep travelling along the ribbon once per cycle
        weave = 0.55 + 0.25 * np.sin(pr.ly * 2.1 + t * 2.0) * v_band + 0.25 * np.sin(pr.lx * 2.1 - t * 2.0) * h_band
        sweep_v = np.exp(-((pr.ly - u * pr.h * 1.2 + 0.1 * pr.h) / (0.09 * pr.h)) ** 2)
        sweep_h = np.exp(-((pr.lx + pr.w / 2 - u * pr.w * 1.2 + 0.1 * pr.w) / (0.09 * pr.w)) ** 2) if p["cross"] else 0.0
        sweep = np.maximum(sweep_v * v_band, sweep_h * h_band)
        ribbon_rgb = rib[None, :] * (weave * band)[:, None]
        ribbon_rgb = np.maximum(ribbon_rgb, WHITE[None, :] * (0.8 * sweep)[:, None])
        fr = fr * (1 - band)[:, None] + ribbon_rgb
        # --- bow at the crossing: two loops and a knot, glinting
        if p["bow"] > 0:
            R = p["ribbon_in"] * 1.4 * p["bow"]
            loops = np.maximum(blob(pr, -R * 0.9, cy + R * 0.45, R), blob(pr, R * 0.9, cy + R * 0.45, R))
            knot = blob(pr, 0, cy, R * 0.5)
            bow = np.maximum(loops ** 0.8, knot)
            gl = glints(pr, t, 0.35, pr.idx + 7, 12.0)
            bow_rgb = rib[None, :] * (bow * (0.7 + 0.3 * gl))[:, None]
            bow_rgb = np.maximum(bow_rgb, WHITE[None, :] * (bow * gl * 0.7)[:, None])
            fr = fr * (1 - bow)[:, None] + bow_rgb
        out[pr.id] = np.clip(fr, 0, 1)
    return out


# ------------------------------------------------------------------- fairy lights
@effect("fairy_lights", "anim", "Fairy lights", pack=PACK, tags=["slow"], params=[
    Slider("density", "How many are lit", 0.5, 0.05, 1.0, 0.05),
    choice("colours", "Lights", "warm white", ["warm white", "cool white", "multicolour", "palette"]),
    Slider("fade", "Fade speed", 1.0, 0.1, 4.0, 0.1),
    choice("behind", "Behind them", "dark tree", ["dark tree", "off", "painted (dim)", "palette (dim)"]),
    Slider("behind_level", "Background level", 0.25, 0.0, 0.6, 0.05),
    toggle("beat_glow", "Swell a little on the bar", False),
], doc="The plain string of mini lights everyone's grandmother had: a random share of the bulbs lit, every one fading up and down on its own slow clock, warm or multicolour, over a dark tree, the painted picture or nothing. A building block -- put a modifier on it or use it as the calm before a louder clip.")
def fairy_lights(g, m, t, p, pal, st):
    from .incandescent import drawn
    out = {}
    swell = 1 + (0.25 * m.downbeat_env if p["beat_glow"] else 0.0)
    for pr in g.props:
        if p["behind"] == "dark tree":
            fr = tree_body(pr, t, "forest mix", p["behind_level"] * 0.8)
        elif p["behind"] == "painted (dim)":
            fr = drawn(pr, pal, {"colours": "painted"}) * p["behind_level"] * (0.8 + 0.2 * noise(pr.wx / 8, pr.wz / 8, t * 0.2, pr.idx))[:, None]
        elif p["behind"] == "palette (dim)":
            fr = pal.color(1)[None, :] * (p["behind_level"] * (0.75 + 0.25 * noise(pr.wx / 8, pr.wz / 8, t * 0.2, pr.idx)))[:, None]
        else:
            fr = np.zeros((pr.n, 3))
        out[pr.id] = np.clip(lighten(fr, fairy(pr, t, p["density"], p["colours"], pal, p["fade"]) * swell), 0, 1)
    return out


# ----------------------------------------------------------------------- garland
@effect("garland", "anim", "Garland", pack=PACK, tags=["slow"], params=[
    Slider("spacing_in", "Wrap spacing (in)", 12.0, 5.0, 40.0, 1.0, unit="in"),
    Slider("width_in", "Tinsel width (in)", 1.8, 0.8, 6.0, 0.2, unit="in"),
    Slider("angle", "Wrap angle (°)", 35, 0, 90, 5, kind="int"),
    choice("colour", "Tinsel", "silver", ["silver", "gold", "red", "palette"]),
    Slider("sparkle", "Sparkle", 0.7, 0.0, 1.0, 0.05),
    Slider("drift", "Slide (in/s)", 1.0, 0.0, 8.0, 0.25, unit="in/s"),
    choice("behind", "Behind it", "dark tree", ["dark tree", "off", "painted (dim)"]),
], doc="Tinsel garland wound diagonally around every prop, in inches: shimmering bands that sparkle bulb by bulb and slowly slide along the prop, over a dark tree or the painted picture. Another building block; stack Sparkle overlay or a colour shift on it.")
def garland(g, m, t, p, pal, st):
    from .incandescent import drawn
    col = {"silver": SILVER, "gold": GOLD, "red": RED}.get(p["colour"], pal.color(0))
    out = {}
    for pr in g.props:
        if p["behind"] == "dark tree":
            fr = tree_body(pr, t, "forest mix", 0.3)
        elif p["behind"] == "painted (dim)":
            fr = drawn(pr, pal, {"colours": "painted"}) * 0.25 * (0.8 + 0.2 * noise(pr.wx / 8, pr.wz / 8, t * 0.2, pr.idx))[:, None]
        else:
            fr = np.zeros((pr.n, 3))
        out[pr.id] = np.clip(lighten(fr, tinsel(pr, t, p["spacing_in"], p["width_in"], p["angle"], col, p["drift"], p["sparkle"], pr.idx)), 0, 1)
    return out


# --------------------------------------------------------------------- toy train
@effect("toy_train", "anim", "Toy train", pack=PACK, tags=["geometry"], params=[
    Slider("bars", "Bars per lap", 8, 1, 32, 1, kind="int"),
    Slider("cars", "Carriages", 4, 1, 10, 1, kind="int"),
    Slider("car_px", "Carriage length (bulbs)", 6, 3, 20, 1, kind="int"),
    choice("colours", "Carriages", "classic", ["classic", "palette"]),
    Slider("smoke", "Smoke", 0.6, 0.0, 1.0, 0.05),
    Slider("track", "Track level", 0.1, 0.0, 0.3, 0.01),
    toggle("reverse", "Run right to left", False),
], doc="A lit toy train runs along the group's whole wire from the left-most prop to the right-most and back round: a bright white headlight, a red engine, coloured carriages with lighter windows and dark couplings, and puffs of grey smoke drifting off behind. One lap every few bars, so it arrives on a downbeat.")
def toy_train(g, m, t, p, pal, st):
    off, total = wire_offsets(g)
    if total == 0:
        return g.zeros()
    if p["colours"] == "classic":
        cars = np.array([np.array([0.1, 0.8, 0.2]), np.array([0.15, 0.35, 1.0]), GOLD, np.array([0.9, 0.2, 0.7]), np.array([0.2, 0.9, 0.9])])
    else:
        cars = pal.chroma
    L = int(p["car_px"]); nc = int(p["cars"])
    train_len = 2 + L + nc * (L + 1)                                   # headlight, engine, cars with couplings
    lap = total + train_len
    bars = m.bar_index + m.bar_phase
    head = ((bars / p["bars"]) % 1.0) * lap                            # position of the headlight along the wire
    out = {}
    for pr in g.props:
        gi = off[pr.id] + pr.i                                          # global wire index
        if p["reverse"]:
            gi = total - 1 - gi
        d = head - gi                                                   # >=0: this bulb is behind the headlight
        fr = np.array([0.5, 0.5, 0.55])[None, :] * (p["track"] * (0.6 + 0.4 * noise(pr.wx / 5, pr.wz / 5, t * 0.5, pr.idx)))[:, None]
        # headlight: 2 bulbs, plus a beam fading out ahead
        beam = np.where(d < 0, np.exp(d / 4.0) * 0.5, 0.0) + np.where((d >= 0) & (d < 2), 1.0, 0.0)
        fr = lighten(fr, WHITE * beam[:, None])
        # engine
        eng = (d >= 2) & (d < 2 + L)
        fr = np.where(eng[:, None], RED * 0.9, fr)
        # firebox glow flickering at the back of the engine
        fb = (d >= 2 + L - 2) & (d < 2 + L)
        fr = np.where(fb[:, None], GOLD * (0.6 + 0.4 * noise(pr.i * 0.5, 0, t * 6, 3))[:, None], fr)
        for k in range(nc):
            s = 2 + L + k * (L + 1) + 1                                 # 1 dark coupling before each car
            car = (d >= s) & (d < s + L)
            c = cars[k % len(cars)]
            win = ((gi % 2) == 0) & (d > s) & (d < s + L - 1)           # lighter windows every other bulb
            body = np.where(win[:, None], c * 0.55 + WARM * 0.45, c * 0.8)
            fr = np.where(car[:, None], body, fr)
        # smoke: grey puffs drifting off behind the train, fading with distance
        if p["smoke"] > 0:
            back = d - train_len
            puffs = np.where(back > 0, np.exp(-np.clip(back, 0, None) / (12.0 * p["smoke"])) * (0.5 + 0.5 * np.sin(back * 1.3 - t * 3)) ** 2, 0.0)
            fr = lighten(fr, np.array([0.6, 0.6, 0.65]) * (0.5 * puffs)[:, None])
        out[pr.id] = np.clip(fr, 0, 1)
    return out


# ------------------------------------------------------------------ shooting star
@effect("shooting_star", "anim", "Shooting star", pack=PACK, tags=["geometry"], params=[
    Slider("per_bar", "Stars per bar", 1.0, 0.25, 4.0, 0.25),
    Slider("speed_in_s", "Speed (in/s)", 500.0, 100.0, 2000.0, 20.0, unit="in/s"),
    Slider("tail_in", "Tail length (in)", 60.0, 10.0, 300.0, 5.0, unit="in"),
    Slider("sky", "Night-sky level", 0.14, 0.0, 0.5, 0.02),
    choice("color", "Tail colour", "gold", ["white", "gold", "frost", "palette"]),
    Slider("sparks", "Sparks in the tail", 0.6, 0.0, 1.0, 0.05),
    toggle("both_ways", "Stars come from both ends", True),
], doc="A white-hot star streaks across the whole group in real inches with a coloured tail that breaks up into sparks, over a night sky that is darker at the ground and twinkles near the top. Rare, fast and unmistakable.")
def shooting_star(g, m, t, p, pal, st):
    col = {"white": WHITE, "gold": GOLD, "frost": ICE}.get(p["color"], pal.color(0))
    bars = m.bar_index + m.bar_phase
    span = g.width + 2 * p["tail_in"]
    flight = span / max(1.0, p["speed_in_s"])
    out = {}
    for pr in g.props:
        r = rng(pr.idx * 61 + 2)
        ph = r.random(pr.n) * 6.283
        tw = 0.35 + 0.65 * (0.5 + 0.5 * np.sin(t * (0.5 + 0.8 * r.random(pr.n)) + ph)) ** 3
        z = g.z01(pr)
        sky = np.array([0.1, 0.15, 0.4])[None, :] * (p["sky"] * (0.35 + 0.65 * z) * tw)[:, None]
        stars = (r.random(pr.n) < 0.06) * (0.3 + 0.7 * glints(pr, t, 0.25, 9, 6.0)) * p["sky"] * 4   # a few real stars
        out[pr.id] = lighten(sky, WHITE * np.clip(stars, 0, 0.7)[:, None])
    n_live = int(math.ceil(p["per_bar"] * 2)) + 1
    for back in range(n_live):
        k = int(bars * p["per_bar"]) - back
        if k < 0:
            continue
        launch_bars = k / p["per_bar"]
        age = (bars - launch_bars) * m.beat_len * m.beats_per_bar
        if age < 0 or age > flight:
            continue
        r = rng(k * 7717)
        dirn = 1 if (not p["both_ways"] or r.random() < 0.5) else -1
        head = (g.x0 - p["tail_in"] + age * p["speed_in_s"]) if dirn > 0 else (g.x1 + p["tail_in"] - age * p["speed_in_s"])
        zc = g.z0 + (0.4 + 0.5 * r.random()) * g.height
        for pr in g.props:
            d = (pr.wx - head) * -dirn                       # >0 = behind the head (the tail)
            near = np.exp(-((pr.wz - zc) / max(6.0, g.height * 0.35)) ** 2)
            core = np.exp(-(d / 6.0) ** 2) * near            # white-hot head, ~6 in
            tail = np.where(d >= 0, np.clip(1 - d / p["tail_in"], 0, 1) ** 2, 0.0) * near
            if p["sparks"] > 0:                              # the tail breaks into sparks that fall behind
                rr = rng(k * 31 + pr.idx * 7)
                grain = rr.random(pr.n) < 0.35
                sp = np.where(grain, 1.0, 0.45) * (0.6 + 0.4 * np.sin(d * 0.8 - t * 25 + rr.random(pr.n) * 6.283))
                tail = tail * (1 - p["sparks"] + p["sparks"] * sp)
            out[pr.id] = lighten(out[pr.id], col * tail[:, None])
            out[pr.id] = lighten(out[pr.id], WHITE * core[:, None])
    return {k: np.clip(v, 0, 1) for k, v in out.items()}


# --------------------------------------------------------------------- snow globe
@effect("snow_globe", "anim", "Snow globe", pack=PACK, tags=["music"], params=[
    Slider("bars", "Bars per shake", 8, 2, 32, 1, kind="int"),
    Slider("flakes", "Flakes per prop", 18, 3, 60, 1, kind="int"),
    Slider("swirl", "Swirl strength", 1.0, 0.2, 3.0, 0.1),
    Slider("settle_s", "Settle time (s)", 4.0, 1.0, 15.0, 0.5, unit="s"),
    choice("scene", "Scene behind the snow", "painted", ["painted", "green tree", "night sky", "palette"]),
    Slider("pile", "Snow piles up", 0.6, 0.0, 1.0, 0.05),
    toggle("shake_on_hit", "Shake on a big hit instead of on the bar", False),
], doc="Somebody shakes the globe: the snow flies up in a swirl of flakes big and small, then drifts back down and piles up along the bottom of the scene with a bumpy white surface; the glass catches a highlight at the top. Shakes every few bars, or whenever the music hits hard.")
def snow_globe(g, m, t, p, pal, st):
    from .incandescent import drawn
    if p["shake_on_hit"]:
        if m.hit > 0.7 and st.get("prev", 0.0) <= 0.7 and t - st.get("t0", -9) > 1.5:
            st["t0"] = t
        st["prev"] = m.hit
        t0 = st.get("t0", 0.0)
    else:
        t0 = t - ((m.bar_index % p["bars"]) + m.bar_phase) * m.beat_len * m.beats_per_bar
    age = max(0.0, t - t0)
    shake = math.exp(-age / max(0.2, p["settle_s"]) * 2.2)                  # 1 just after the shake -> 0
    settle = 1 - shake
    out = {}
    for pr in g.props:
        if p["scene"] == "green tree":
            scene = tree_body(pr, t, "forest mix", 0.4)
        elif p["scene"] == "night sky":
            scene = np.array([0.05, 0.1, 0.4])[None, :] * (0.25 + 0.3 * pr.y01 + 0.1 * noise(pr.wx / 10, pr.wz / 10, t * 0.2, pr.idx))[:, None]
        elif p["scene"] == "palette":
            scene = pal.color(1)[None, :] * (0.2 + 0.15 * noise(pr.wx / 10, pr.wz / 10, t * 0.2, pr.idx))[:, None]
        else:
            scene = drawn(pr, pal, {"colours": "painted"}) * 0.45
        r = rng(pr.idx * 131 + 5)
        nf = int(p["flakes"])
        fx0 = r.random(nf); fz0 = r.random(nf); ph = r.random(nf) * 6.283; sp = 0.6 + 0.8 * r.random(nf)
        size = 1.6 + 2.2 * r.random(nf)                                     # flake radius in inches
        # while shaking they swirl all over the prop; as it dies they sink toward the bottom
        fz = fz0 * shake + (0.03 + 0.12 * fz0) * settle
        fx = fx0 + shake * 0.25 * p["swirl"] * np.sin(t * 2.0 * sp + ph)
        fz = fz + shake * 0.15 * p["swirl"] * np.cos(t * 2.6 * sp + ph)
        px = pr.lx.min() + (fx % 1.0) * max(1e-3, np.ptp(pr.lx))
        pz = np.clip(fz, 0, 1) * pr.h
        d2 = (pr.lx[:, None] - px[None, :]) ** 2 + (pr.ly[:, None] - pz[None, :]) ** 2
        snow = (np.exp(-d2 / size[None, :] ** 2) * (0.6 + 0.4 * (size[None, :] - 1.6) / 2.2)).max(1)
        # snow piled along the bottom: a bumpy surface that grows as the flakes settle
        depth = p["pile"] * settle * (0.12 + 0.06 * noise(pr.lx / 4, 0, t * 0.1, pr.idx))
        pile = smoothstep(depth + 0.03, depth - 0.02, pr.y01)
        glass = 0.12 * smoothstep(0.86, 1.0, pr.y01) * smoothstep(0.1, 0.5, 0.5 - pr.lx / max(1e-3, pr.w))
        fr = lighten(scene, WHITE * np.maximum(snow, pile * (0.8 + 0.2 * noise(pr.lx / 2, pr.ly / 2, 0, 1)))[:, None])
        out[pr.id] = np.clip(lighten(fr, ICE * glass[:, None]), 0, 1)
    return out


# ----------------------------------------------------------------------- icicles
@effect("icicles", "anim", "Icicles", pack=PACK, tags=["slow"], params=[
    Slider("spacing_in", "Icicle spacing (in)", 6.0, 2.0, 16.0, 0.5, unit="in"),
    Slider("length", "Longest icicle (share of prop)", 0.6, 0.15, 1.0, 0.05),
    Slider("drip_s", "Seconds between drops", 3.0, 0.5, 12.0, 0.5, unit="s"),
    Slider("hang", "Ice level", 0.8, 0.1, 1.0, 0.05),
    Slider("sparkle", "Sparkle", 0.5, 0.0, 1.0, 0.05),
    choice("color", "Colour", "frost", ["frost", "white", "palette"]),
], doc="Icicles of different lengths hang from the top edge of every prop -- long, short, long -- brighter at the root and glassy toward the tip. At each tip a drop swells, brightens, lets go and falls straight down, fading as it goes. Sparkle where the light catches the ice.")
def icicles(g, m, t, p, pal, st):
    col = {"white": WHITE, "frost": ICE}.get(p["color"], pal.color(0))
    out = {}
    for pr in g.props:
        # icicle columns in local inches: each column has its own length (noise over x)
        sp = p["spacing_in"]
        colx = np.round(pr.lx / sp) * sp                                   # centre x of the nearest icicle
        seed = np.sin(colx * 12.9898 + pr.idx * 7.1) * 43758.5453
        L = (0.35 + 0.65 * (seed - np.floor(seed))) * p["length"]          # 0..length of the prop, per column
        near = np.exp(-((pr.lx - colx) / (sp * 0.34)) ** 2)                # thin columns
        top = 1 - pr.y01                                                   # 0 at the top edge, 1 at the ground
        inside = smoothstep(L + 0.03, L - 0.02, top)                       # bulb lies within the icicle
        taper = 1 - 0.4 * np.clip(top / np.maximum(L, 1e-3), 0, 1)         # brighter at the root
        glaze = smoothstep(0.35, 0.0, top) * 0.45 * (0.7 + 0.3 * noise(pr.lx / 3, pr.ly / 3, t * 0.2, pr.idx))  # rime along the top edge between icicles
        ice = np.maximum(inside * near * taper, glaze) * p["hang"]
        fr = lighten(frost(ice), ICE * (ice * 0.7)[:, None]) if p["color"] == "frost" else col * ice[:, None]
        # drops: each column has its own clock; the drop swells at the tip then falls
        cyc = (t / p["drip_s"] + (seed - np.floor(seed)) * 3.7) % 1.0
        swell = smoothstep(0.0, 0.6, cyc) * (cyc < 0.62)                    # grows for 60 % of the cycle
        fall = (cyc - 0.62) / 0.38                                         # 0..1 while falling
        y_drop = np.where(cyc < 0.62, L, L + fall * (1 - L) * 1.05)         # depth of the drop from the top
        drop = np.exp(-((top - y_drop) * pr.h / 2.2) ** 2) * near * np.where(cyc < 0.62, 0.3 + 0.7 * swell, np.clip(1 - fall * 1.1, 0, 1))
        fr = lighten(fr, WHITE * drop[:, None])
        if p["sparkle"] > 0:
            fr = lighten(fr, WHITE * (p["sparkle"] * 0.8 * glints(pr, t, 0.6, pr.idx + 5, 14.0) * inside * near)[:, None])
        out[pr.id] = np.clip(fr, 0, 1)
    return out
