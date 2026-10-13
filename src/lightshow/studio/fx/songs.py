"""
songs.py -- the Song themes pack: one signature look for each song of the
medley that had no home yet (docs/09-SHOW-DESIGN §9a).

    Candy stripes      Rockin' Around the Christmas Tree -- modern Christmas, candy stripes
    Tacky              Winter Wonderland -- everything at once, on purpose
    Romantic melt      Snowman -- reds and pinks; icy blues melted away top to bottom
    Pale elements      God Rest Ye Merry Gentlemen -- pale palette, brightness follows the musical elements
    Plum energy storm  Sugar Plum Fairy (trap remix)
"""

import math
import numpy as np

from ..engine import effect, Slider, choice, toggle
from ...effects import lighten, frost
from .util import noise, follow, gradient, smoothstep, rng, glints
from .incandescent import drawn

PACK = "Song themes"
WHITE = np.ones(3)


@effect("candy_stripes", "anim", "Candy stripes", pack=PACK, tags=["music"], params=[
    Slider("stripe_in", "Stripe width (in)", 8.0, 3.0, 30.0, 1.0, unit="in"),
    Slider("angle", "Stripe angle (°)", 45, 0, 170, 5, kind="int"),
    Slider("beats", "Beats per stripe step", 1, 0.5, 4, 0.5),
    choice("colours", "Colours", "red / white", ["red / white", "red / white / green", "palette"]),
    toggle("smooth", "Glide (else march in steps)", True),
    toggle("beat_pop", "White pop on the downbeat", True),
], doc="Red-and-white diagonal candy-cane stripes marching across the whole group in world inches, one stripe per beat -- the modern-Christmas look for Rockin' Around the Christmas Tree.")
def candy_stripes(g, m, t, p, pal, st):
    a = math.radians(p["angle"])
    beats = m.beat_index + m.beat_phase
    step = beats / p["beats"]
    if not p["smooth"]:
        step = math.floor(step)
    if p["colours"] == "red / white":
        cols = np.array([[1.0, 0.05, 0.05], [1.0, 1.0, 1.0]])
    elif p["colours"] == "red / white / green":
        cols = np.array([[1.0, 0.05, 0.05], [1.0, 1.0, 1.0], [0.05, 0.85, 0.2], [1.0, 1.0, 1.0]])
    else:
        cols = pal.rgb
    pop = 0.35 * m.downbeat_env if p["beat_pop"] else 0.0
    out = {}
    for pr in g.props:
        u = (pr.wx * math.cos(a) + pr.wz * math.sin(a)) / p["stripe_in"] - step
        k = np.floor(u).astype(int) % len(cols)
        fr = cols[k]
        if p["smooth"]:                                            # soften the stripe edge over ~15 % of a stripe
            f = u - np.floor(u)
            nxt = cols[(k + 1) % len(cols)]
            w = smoothstep(0.85, 1.0, f)[:, None]
            fr = fr * (1 - w) + nxt * w
        out[pr.id] = lighten(fr, np.broadcast_to(WHITE * pop, (pr.n, 3)))
    return out


@effect("tacky", "anim", "Tacky", pack=PACK, tags=["music"], regions=True, params=[
    Slider("busy", "Busyness", 0.7, 0.2, 1.0, 0.05),
    Slider("change_bars", "Bars before each prop changes its pattern", 2, 1, 8, 1, kind="int"),
    toggle("clash", "Clashing colours (ignore palette)", True),
    Slider("level", "Brightness", 1.0, 0.4, 1.0, 0.05),
], doc="Winter Wonderland: every prop runs a different cheap 1990s string-light program at once -- blink, chase, twinkle, alternate, colour cycle -- and swaps programs every couple of bars. Deliberately too much.")
def tacky(g, m, t, p, pal, st):
    gaudy = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0], [1, 0, 1], [0, 1, 1], [1, 0.5, 0], [1, 1, 1]], float)
    cols = gaudy if p["clash"] else pal.rgb
    slot = m.bar_index // max(1, int(p["change_bars"]))
    beats = m.beat_index + m.beat_phase
    out = {}
    for pr in g.props:
        r = rng(slot * 31 + pr.idx * 7)
        prog = int(r.integers(0, 6)); c1, c2 = cols[int(r.integers(0, len(cols)))], cols[int(r.integers(0, len(cols)))]
        i = pr.i
        if prog == 0:                                              # blink whole prop on the beat
            fr = np.broadcast_to(c1 if m.beat_phase < 0.5 else c2, (pr.n, 3)).copy()
        elif prog == 1:                                            # chase every 3rd bulb on 8ths
            on = ((i - int(beats * 2)) % 3) == 0
            fr = np.where(on[:, None], c1, c2 * 0.15)
        elif prog == 2:                                            # random twinkle
            rr = rng(int(t * 8 * p["busy"]) + pr.idx)
            fr = np.where((rr.random(pr.n) < 0.5)[:, None], c1, c2)
        elif prog == 3:                                            # alternate halves by height
            top = pr.y01 > 0.5
            fr = np.where((top ^ (m.beat_index % 2 == 0))[:, None], c1, c2)
        elif prog == 4:                                            # colour cycle sweep along the wire
            fr = cols[((i // 6) + int(beats * 2)) % len(cols)]
        else:                                                      # regions alternate (drawn picture flashing)
            pic = drawn(pr, pal, {"colours": "painted"})
            names = list(pr.regions.keys()); keep = np.zeros(pr.n, bool)
            for k, nm in enumerate(names):
                if k % 2 == m.beat_index % 2 or len(names) == 1:
                    keep |= pr.regions[nm]
            fr = np.where(keep[:, None], pic, c2 * 0.3)
        out[pr.id] = fr * p["level"]
    return out


def melt_line(pr, u, ragged=0.12, seed=0.0):
    """Height (y01, 0 = ground) of a ragged melt front that has descended `u` (0..1) of the prop.
    The raggedness is fixed per bulb column, so the front keeps its shape as it sinks."""
    n = noise(pr.lx / 5.0, 0.0, 0.0, seed)                         # per-column, still
    # u=0: the front sits above the prop (all frozen); u=1: below it (all melted)
    return 1.0 + ragged - u * (1 + 2 * ragged) + (n - 0.5) * 2 * ragged


def melt_scene(pr, t, m, u, warm, ice_col, ragged, drips_st, drip_rate, seed, dt):
    """Shared by Romantic melt and the Melt transition. -> (frozen 0..1, warm-side rgb, ice-side rgb,
    edge glow 0..1, drops 0..1, puddle 0..1). Drops are simulated in `drips_st` (a list of
    [x, y_in, vy]) in LOCAL inches with gravity, born at the front, splashing at the ground."""
    line = melt_line(pr, u, ragged, seed)
    d = pr.y01 - line                                              # >0 above the front = already melted
    frozen = smoothstep(0.04, -0.04, d)
    # frozen side: crystalline -- brighter facets that glint, bluer deep inside
    facets = 0.55 + 0.45 * noise(pr.lx / 2.2, pr.ly / 2.2, t * 0.15, seed + 3)
    crystal = facets * (0.55 + 0.45 * glints(pr, t, 0.3, int(seed) + 11, 16.0) * 0.6)
    ice = ice_col[None, :] * (0.5 + 0.5 * crystal)[:, None]
    ice = np.maximum(ice, np.ones(3)[None, :] * (0.5 * glints(pr, t, 0.3, int(seed) + 11, 16.0) * facets)[:, None])
    # melted side: warm convection, a little brighter just under the front where the heat is
    conv = 0.7 + 0.3 * noise(pr.lx / 6.0, pr.ly / 6.0 - t * 0.12, t * 0.25, seed + 7)
    heat_up = np.exp(-np.clip(d, 0, 1) / 0.18)                     # 1 at the front, fading up into the melted part
    hot = warm * 0.6 + np.array([1.0, 0.6, 0.55]) * 0.4            # rosier where it is freshly melted
    warm_rgb = (warm[None, :] * (1 - heat_up)[:, None] + hot[None, :] * heat_up[:, None]) * conv[:, None]
    # heat shimmer just BELOW the front: the ice goes translucent pink before it gives way
    seep = np.exp(-np.clip(-d, 0, 1) / 0.07) * (0.5 + 0.5 * noise(pr.lx / 3, 0, t * 2.0, seed + 5))
    edge = np.exp(-(d / 0.035) ** 2)
    # drops: born along the front, fall with gravity (in/s^2), splash into a puddle
    drops = np.zeros(pr.n)
    r = rng(int(t * 30) + int(seed) * 7 + pr.idx)
    if 0.02 < u < 0.98 and r.random() < drip_rate * dt * 4:
        i = int(r.integers(0, pr.n))
        drips_st.append([pr.lx[i] + (r.random() - 0.5) * 2, line[i] * pr.h, 0.0])
    for dr in drips_st:
        dr[2] += 386.0 * 0.25 * dt                                  # gentle gravity (quarter g reads better at this scale)
        dr[1] -= dr[2] * dt
        dd = np.hypot(pr.lx - dr[0], pr.ly - dr[1])
        drops = np.maximum(drops, np.exp(-(dd / 1.6) ** 2) * (0.7 + 0.3 * min(1.0, dr[2] / 40)))
        trail = np.exp(-((pr.lx - dr[0]) / 1.2) ** 2) * np.where((pr.ly > dr[1]) & (pr.ly < dr[1] + 6), 1 - (pr.ly - dr[1]) / 6, 0.0)
        drops = np.maximum(drops, 0.35 * trail)
    del drips_st[:-6]
    drips_st[:] = [dr for dr in drips_st if dr[1] > -2.0]
    # puddle: grows with the melt, ripples when a drop lands
    pud = smoothstep(0.16 * u + 0.02, 0.0, pr.y01) * (0.6 + 0.4 * noise(pr.lx / 3, 0, t * 0.8, seed + 2))
    return frozen, warm_rgb, ice, edge, seep, drops, pud


@effect("romantic_melt", "anim", "Romantic melt", pack=PACK, tags=["slow"], params=[
    Slider("bars", "Bars per melt cycle", 8, 2, 32, 1, kind="int"),
    Slider("warmth", "Warmth (pink ↔ red)", 0.5, 0.0, 1.0, 0.05),
    Slider("ragged", "Ragged melt front", 0.12, 0.0, 0.3, 0.01),
    Slider("drips", "Drops", 0.6, 0.0, 1.0, 0.05),
    Slider("breathe", "Warm breathe depth", 0.25, 0.0, 0.6, 0.05),
    toggle("refreeze", "Freeze again at the end of the cycle", True),
    toggle("music_heat", "Melt faster when the music swells", True),
], doc="Snowman: every prop starts as crystalline ice -- faceted, glinting, bluer inside -- and a ragged melt front works its way down. Just above the front the ice goes translucent pink; below it the colour is warm red and rose, hottest where it has just melted, slowly churning. Drops form on the front, fall with gravity in real inches leaving a trail, and land in a growing puddle. Then, if you like, it freezes again from the ground up.")
def romantic_melt(g, m, t, p, pal, st):
    ice = np.array([0.5, 0.78, 1.0]); red = np.array([1.0, 0.05, 0.1]); pink = np.array([1.0, 0.25, 0.55])
    warm = red * p["warmth"] + pink * (1 - p["warmth"])
    cyc = int(p["bars"])
    u_bar = ((m.bar_index + m.bar_phase) % cyc) / cyc
    if p["music_heat"]:                                                          # the swell of the song pushes the melt along
        u_bar = np.clip(u_bar + 0.08 * (m.energy - 0.5), 0, 1)
    if p["refreeze"]:
        melt = smoothstep(0.0, 0.7, u_bar) * (1 - smoothstep(0.8, 1.0, u_bar))     # melt, hold, refreeze from the ground up
        refreezing = u_bar > 0.8
    else:
        melt = smoothstep(0.0, 0.85, u_bar); refreezing = False
    breathe = 1 - p["breathe"] * 0.5 * (1 + math.sin(2 * math.pi * t / 5.0))
    out = {}
    for pr in g.props:
        dr = st.setdefault(("drips", pr.id), [])
        frozen, warm_rgb, ice_rgb, edge, seep, drops, pud = melt_scene(pr, t, m, float(melt), warm, ice, p["ragged"], dr, p["drips"], pr.idx * 3.1, m.dt)
        if refreezing:                                                           # crystals climb back up from the ground
            climb = smoothstep(0.8, 1.0, u_bar)
            frozen = np.maximum(frozen, smoothstep(climb + 0.05, climb - 0.05, pr.y01) * (0.7 + 0.3 * noise(pr.lx / 3, pr.ly / 3, t, 4)))
        fr = ice_rgb * frozen[:, None] + warm_rgb * breathe * (1 - frozen)[:, None]
        fr = lighten(fr, pink * (seep * 0.8 * frozen)[:, None])
        fr = lighten(fr, WHITE * (edge * 0.6)[:, None])
        fr = lighten(fr, ice * (drops * 0.9)[:, None])
        fr = lighten(fr, (pink * 0.7 + WHITE * 0.3) * (pud * (1 - frozen) * 0.8)[:, None])
        out[pr.id] = np.clip(fr, 0, 1)
    return out


@effect("pale_elements", "anim", "Pale elements", pack=PACK, tags=["music"], regions=True, params=[
    Slider("attack_s", "Attack (s)", 0.05, 0.01, 0.5, 0.01, unit="s"),
    Slider("release_s", "Release (s)", 0.6, 0.1, 3.0, 0.05, unit="s"),
    Slider("floor", "Resting level", 0.2, 0.0, 0.6, 0.05),
    choice("mapping", "Elements go to", "bass low · mids middle · highs top", ["bass low · mids middle · highs top", "bass regions · highs trim", "per prop: bass left → highs right"]),
    Slider("tint", "Tint (white ↔ pale gold / blue)", 0.5, 0.0, 1.0, 0.05),
], doc="God Rest Ye Merry Gentlemen: a pale palette -- whites, pale gold, pale blue -- whose brightness follows the musical elements: bass lights the lower parts, mids the middle, highs the tips, each with its own attack and release.")
def pale_elements(g, m, t, p, pal, st):
    lv = follow(st, "lv", np.array([m.low, m.mid, m.high]), m.dt, p["attack_s"], p["release_s"])
    gold = np.array([1.0, 0.9, 0.7]); blue = np.array([0.8, 0.9, 1.0])
    out = {}
    for pr in g.props:
        if p["mapping"] == "per prop: bass left → highs right":
            k = int(round(g.rank[pr.idx] * 2)) if g.P > 1 else 1
            w = np.full(pr.n, lv[k])
        elif p["mapping"] == "bass regions · highs trim" and pr.region_names:
            w = np.full(pr.n, lv[1])
            for nm in pr.region_names:
                c = pr.region_color.get(nm)
                is_trim = c is not None and c.min() > 0.85
                w[pr.regions[nm]] = lv[2] if is_trim else lv[0]
        else:
            y = pr.y01
            w = lv[0] * np.clip(1 - y * 2.2, 0, 1) + lv[1] * np.exp(-((y - 0.5) / 0.22) ** 2) + lv[2] * np.clip(y * 2.2 - 1.2, 0, 1)
        w = p["floor"] + (1 - p["floor"]) * np.clip(w, 0, 1)
        tint = WHITE * (1 - p["tint"]) + (gold * (1 - pr.y01)[:, None] + blue * pr.y01[:, None]) * p["tint"]
        out[pr.id] = tint * w[:, None]
    return out


@effect("plum_storm", "anim", "Plum energy storm", pack=PACK, tags=["music", "geometry"], params=[
    Slider("base", "Plum base level", 0.35, 0.05, 0.8, 0.05),
    Slider("wave_in_s", "Bass shockwave speed (in/s)", 400.0, 100.0, 1200.0, 20.0, unit="in/s"),
    Slider("wave_width_in", "Shockwave width (in)", 40.0, 10.0, 150.0, 5.0, unit="in"),
    Slider("grains", "Hi-hat grains", 0.6, 0.0, 1.0, 0.05),
    Slider("drop_threshold", "Drop threshold (energy)", 0.55, 0.2, 0.9, 0.05),
    choice("colours", "Colours", "plum / magenta / pink", ["plum / magenta / pink", "palette"]),
], doc="Sugar Plum Fairy (trap remix): a deep plum base; every 808 hit sends a magenta shockwave across the group from the nearest prop using the real distances; hi-hats sprinkle pink grains; the drop floods everything white-pink.")
def plum_storm(g, m, t, p, pal, st):
    if p["colours"] == "palette":
        plum, mag, pink = pal.color(0) * 0.5, pal.color(1), pal.color(2)
    else:
        plum, mag, pink = np.array([0.35, 0.0, 0.5]), np.array([1.0, 0.1, 0.8]), np.array([1.0, 0.45, 0.8])
    # bass hits launch waves (keep the last 3)
    waves = st.setdefault("waves", [])
    if m.low > 0.6 and m.hit > 0.5 and st.get("prev", 0.0) <= 0.5:
        src = int(rng(int(t * 1000)).integers(0, max(1, g.P)))
        waves.append((t, src)); del waves[:-3]
    st["prev"] = m.hit
    loud = m.energy > p["drop_threshold"]
    if loud and not st.get("loud", False):
        st["t_drop"] = t
    st["loud"] = loud
    flood = math.exp(-(t - st.get("t_drop", -9)) / 0.4 * 3) if t >= st.get("t_drop", -9) else 0.0
    out = {}
    for pr in g.props:
        sh = 0.75 + 0.25 * noise(pr.wx / 20, pr.wz / 20, t * 0.7, pr.idx)
        fr = plum[None, :] * (p["base"] * sh)[:, None]
        for (t0, src) in waves:
            age = t - t0
            if age > 2.0 or not g.P:
                continue
            d = np.hypot(pr.wx - g.C[src][0], pr.wz - g.C[src][2])
            ring = np.exp(-((d - age * p["wave_in_s"]) / (p["wave_width_in"] / 2)) ** 2) * math.exp(-age * 1.5)
            fr = lighten(fr, mag * ring[:, None])
        if p["grains"] > 0 and m.hit_high > 0.3:
            r = rng(int(t * 40) + pr.idx)
            gr = (r.random(pr.n) < 0.04 * p["grains"] * m.hit_high) * 1.0
            fr = lighten(fr, pink * gr[:, None])
        out[pr.id] = lighten(fr, np.broadcast_to((WHITE * 0.6 + pink * 0.4) * flood, (pr.n, 3)))
    return out
