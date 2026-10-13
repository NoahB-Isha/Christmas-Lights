"""
choreo.py -- the Choreography pack: multi-prop effects from the original
brief (docs/09 §6). They treat the group as a cast: a feature prop, halves that
answer each other, pulses that travel the real distances between props.
"""

import math
import numpy as np

from ..engine import effect, Slider, choice, toggle, prop_pick
from ...effects import lighten
from .util import smoothstep, rng, noise
from .incandescent import drawn

PACK = "Choreography"
WHITE = np.ones(3)
FEATURE = choice("feature", "Feature prop", "pass along", ["specific prop", "centre", "left end", "right end", "largest", "pass along", "random per phrase"])
PROP = prop_pick("prop", "…which prop (for 'specific prop')")
EVERY = Slider("every_bars", "Bars before the feature moves", 2, 1, 16, 1, kind="int")
COLOURS = choice("colours", "Colours", "painted", ["painted", "palette per prop", "palette colour 1"])


def _pic(pr, pal, p):
    if p.get("colours") == "palette colour 1":
        return np.broadcast_to(pal.color(0), (pr.n, 3)).copy()
    return drawn(pr, pal, {"colours": p.get("colours", "painted")})


@effect("emphasise", "anim", "Feature prop", pack=PACK, tags=["geometry", "regions"], regions=True, params=[
    FEATURE, PROP, EVERY, COLOURS,
    Slider("floor", "Others (dim level)", 0.15, 0.0, 0.6, 0.05),
    toggle("pulse", "Feature pulses on the beat", True),
    Slider("handover_s", "Handover fade (s)", 0.4, 0.0, 2.0, 0.05, unit="s"),
], doc="One prop is the star: full brightness in its painted colours, pulsing on the beat, while the rest rest at a dim floor. The star is handed along the row every few bars with a soft crossfade.")
def emphasise(g, m, t, p, pal, st):
    k = g.feature(p["feature"], m, int(p["every_bars"]), p.get("prop"))
    target = np.full(g.P, p["floor"]); target[k] = 1.0
    cur = st.get("lv")
    if cur is None or len(cur) != g.P:
        cur = target.copy()
    a = 1 - math.exp(-m.dt / max(0.02, p["handover_s"]))
    cur = cur + (target - cur) * a
    st["lv"] = cur
    pulse = (0.8 + 0.2 * m.pulse) if p["pulse"] else 1.0
    out = {}
    for pr in g.props:
        lvl = cur[pr.idx] * (pulse if pr.idx == k else 1.0)
        out[pr.id] = _pic(pr, pal, p) * lvl
    return out


@effect("shockwave", "anim", "Shockwave", pack=PACK, tags=["geometry", "music"], params=[
    FEATURE, PROP, EVERY,
    choice("trigger", "Trigger", "every bar", ["every beat", "every bar", "on hits"]),
    Slider("speed_in_s", "Speed (in/s)", 300.0, 60.0, 1200.0, 10.0, unit="in/s"),
    Slider("width_in", "Ring width (in)", 36.0, 8.0, 150.0, 2.0, unit="in"),
    Slider("floor", "Background level", 0.12, 0.0, 0.5, 0.02),
    toggle("colour_each", "New colour every wave", True),
], doc="A bright ring bursts out of the feature prop and races across the group at a real speed in inches per second, lighting each prop as it arrives -- the shockwave from the brief, exp(-((d - v·t)/w)²).")
def shockwave(g, m, t, p, pal, st):
    if not g.P:
        return g.zeros()
    k = g.feature(p["feature"], m, int(p["every_bars"]), p.get("prop"))
    if p["trigger"] == "every beat":
        age, n = m.beat_phase * m.beat_len, m.beat_index
    elif p["trigger"] == "every bar":
        age, n = m.bar_phase * m.beat_len * m.beats_per_bar, m.bar_index
    else:
        if m.hit > 0.55 and st.get("prev", 0.0) <= 0.55:
            st["t_hit"] = t; st["n"] = st.get("n", 0) + 1
        st["prev"] = m.hit
        age, n = t - st.get("t_hit", -9), st.get("n", 0)
    col = pal.color(n if p["colour_each"] else 0)
    src = g.C[k]
    out = {}
    for pr in g.props:
        d = np.hypot(pr.wx - src[0], pr.wz - src[2])
        ring = np.exp(-((d - age * p["speed_in_s"]) / (p["width_in"] / 2)) ** 2)
        sh = 0.7 + 0.3 * noise(pr.wx / 22, pr.wz / 22, t * 0.6, pr.idx)
        base = pal.color(n - 1)[None, :] * (p["floor"] * sh)[:, None]
        out[pr.id] = lighten(base, col * ring[:, None])
    return out


@effect("converge", "anim", "Converge", pack=PACK, tags=["geometry"], params=[
    FEATURE, PROP, EVERY,
    Slider("bars", "Bars per run", 1, 0.5, 4, 0.5),
    Slider("width_in", "Pulse width (in)", 30.0, 8.0, 120.0, 2.0, unit="in"),
    Slider("flash", "Flash on arrival", 0.8, 0.0, 1.0, 0.05),
    Slider("floor", "Background level", 0.1, 0.0, 0.5, 0.02),
], doc="The opposite of the shockwave: a pulse runs inward from the far ends toward the feature prop and the feature flashes as it lands, once per bar. Good for a build into a downbeat.")
def converge(g, m, t, p, pal, st):
    if not g.P:
        return g.zeros()
    k = g.feature(p["feature"], m, int(p["every_bars"]), p.get("prop"))
    bars = m.bar_index + m.bar_phase
    u = (bars / p["bars"]) % 1.0
    src = g.C[k]
    dmax = max(1.0, max(np.hypot(pr.wx - src[0], pr.wz - src[2]).max() for pr in g.props))
    r_now = dmax * (1 - u)                                             # radius shrinking toward the feature
    col = pal.color(int(bars / p["bars"]))
    fl = p["flash"] * math.exp(-u * 8) if u < 0.3 else 0.0
    out = {}
    for pr in g.props:
        d = np.hypot(pr.wx - src[0], pr.wz - src[2])
        ring = np.exp(-((d - r_now) / (p["width_in"] / 2)) ** 2)
        sh = 0.7 + 0.3 * noise(pr.wx / 22, pr.wz / 22, t * 0.6, pr.idx)
        fr = lighten(col[None, :] * (p["floor"] * sh)[:, None], col * ring[:, None])
        if pr.idx == k:
            fr = lighten(fr, np.broadcast_to(WHITE * fl, (pr.n, 3)))
        out[pr.id] = fr
    return out


@effect("scatter", "anim", "Scatter", pack=PACK, tags=["geometry", "regions"], regions=True, params=[
    Slider("density", "Share of props lit", 0.5, 0.1, 1.0, 0.05),
    Slider("hold_beats", "Beats per change", 1, 0.5, 8, 0.5),
    Slider("floor", "Unlit level", 0.1, 0.0, 0.5, 0.02),
    COLOURS,
    toggle("fade", "Fade between states", True),
    Slider("fade_s", "Fade time (s)", 0.25, 0.05, 1.5, 0.05, unit="s"),
], doc="Random props step up to full and back down in their painted colours on the beat grid -- a different subset each time, like lights scattered across the yard switching in and out.")
def scatter(g, m, t, p, pal, st):
    slot = int((m.beat_index + m.beat_phase) / p["hold_beats"])
    r = rng(slot * 101 + 7)
    target = np.where(r.random(g.P) < p["density"], 1.0, p["floor"])
    if p["fade"]:
        cur = st.get("lv")
        if cur is None or len(cur) != g.P:
            cur = target.copy()
        cur = cur + (target - cur) * (1 - math.exp(-m.dt / max(0.02, p["fade_s"])))
        st["lv"] = cur
    else:
        cur = target
    return {pr.id: _pic(pr, pal, p) * cur[pr.idx] for pr in g.props}


@effect("call_response", "anim", "Call & response", pack=PACK, tags=["geometry", "music", "regions"], regions=True, params=[
    choice("split", "Two sides", "left half / right half", ["left half / right half", "odd / even props", "ends / middle"]),
    Slider("phrase_beats", "Beats per side", 4, 1, 16, 1, kind="int"),
    choice("motif", "Motif", "flash & decay", ["flash & decay", "chase along the wire", "build up", "twinkle"]),
    COLOURS,
    Slider("floor", "Listening side level", 0.1, 0.0, 0.5, 0.02),
], doc="Two halves of the group talk: one side plays a short motif for a phrase while the other listens dimly, then they swap -- the light conversation from the brief.")
def call_response(g, m, t, p, pal, st):
    pb = max(1, int(p["phrase_beats"]))
    side = (m.beat_index // pb) % 2
    in_phrase = ((m.beat_index % pb) + m.beat_phase) / pb                 # 0..1 through the phrase
    out = {}
    for pr in g.props:
        if p["split"] == "odd / even props":
            mine = (pr.idx % 2) == side
        elif p["split"] == "ends / middle":
            mine = (abs(g.rank[pr.idx] - 0.5) > 0.25) == (side == 0)
        else:
            mine = (g.rank[pr.idx] >= 0.5) == (side == 1)
        pic = _pic(pr, pal, p)
        if not mine:
            out[pr.id] = pic * p["floor"]; continue
        if p["motif"] == "flash & decay":
            lvl = np.full(pr.n, 0.25 + 0.75 * m.pulse)
        elif p["motif"] == "chase along the wire":
            head = in_phrase * pr.n
            lvl = 0.2 + 0.8 * np.clip(1 - np.abs(pr.i - head) / (0.15 * pr.n), 0, 1)
        elif p["motif"] == "build up":
            lvl = np.where(pr.y01 <= in_phrase * 1.05, 1.0, 0.1)
        else:
            rr = rng(int(t * 8) + pr.idx)
            lvl = np.where(rr.random(pr.n) < 0.6, 1.0, 0.2)
        out[pr.id] = pic * lvl[:, None]
    return out


@effect("course_wave", "anim", "Wave across", pack=PACK, tags=["geometry"], regions=True, params=[
    Slider("bars", "Bars per crossing", 2, 0.5, 16, 0.5),
    Slider("width_in", "Wave width (in)", 80.0, 20.0, 400.0, 10.0, unit="in"),
    choice("direction", "Direction", "left→right", ["left→right", "right→left", "bounce"]),
    choice("style", "Wave shows", "palette colour", ["palette colour", "painted picture", "white"]),
    Slider("floor", "Behind the wave", 0.1, 0.0, 0.6, 0.05),
    toggle("colour_each", "New colour every crossing", True),
], doc="A wave of light crosses the whole group in real inches over a set number of bars -- the course-wide wave from the brief, built for cars driving along the row. Chain the same clip on every group with staggered starts and it travels the whole course.")
def course_wave(g, m, t, p, pal, st):
    bars = m.bar_index + m.bar_phase
    u = (bars / p["bars"]) % 1.0
    n = int(bars / p["bars"])
    if p["direction"] == "right→left":
        u = 1 - u
    elif p["direction"] == "bounce":
        u = 1 - abs(1 - 2 * u)
    front = g.x0 - p["width_in"] + u * (g.width + 2 * p["width_in"])
    col = pal.color(n if p["colour_each"] else 0)
    out = {}
    for pr in g.props:
        w = np.exp(-((pr.wx - front) / (p["width_in"] / 2)) ** 2)
        if p["style"] == "painted picture":
            pic = drawn(pr, pal, {"colours": "painted"})
            out[pr.id] = pic * (p["floor"] + (1 - p["floor"]) * w)[:, None]
        else:
            c = WHITE if p["style"] == "white" else col
            sh = 0.7 + 0.3 * noise(pr.wx / 22, pr.wz / 22, t * 0.6, pr.idx)
            out[pr.id] = lighten(c[None, :] * (p["floor"] * sh)[:, None], c * w[:, None])
    return out


# ------------------------------------------------------------------- explosion
from .util import fbm as _fbm  # noqa: E402


def _shards(pr, k, seed):
    """Partition the prop's bulbs into k shards: nearest of k seed bulbs (a Voronoi split of the real
    bulb map, so a shard is a connected chunk of the prop). Cached per prop/seed. -> (shard index per
    bulb, seed xy (k,2), KD-tree for membership tests of displaced points)."""
    from scipy.spatial import cKDTree
    key = ("shards", pr.id, k, seed)
    cache = _shards.cache
    if key in cache:
        return cache[key]
    r = rng(seed * 7919 + pr.idx * 131 + k)
    idx = r.choice(pr.n, size=min(k, pr.n), replace=False)
    seeds = np.column_stack([pr.lx[idx], pr.ly[idx]])
    st = cKDTree(seeds)
    which = st.query(np.column_stack([pr.lx, pr.ly]), k=1)[1]
    tree = cKDTree(np.column_stack([pr.lx, pr.ly]))
    cache[key] = (which, seeds, tree)
    return cache[key]


_shards.cache = {}


@effect("explosion", "anim", "Explosion", pack=PACK, tags=["geometry", "music", "regions"], regions=True, params=[
    choice("trigger", "Trigger", "every N bars", ["every N bars", "on hits", "once at clip start"]),
    Slider("bars", "Bars between blasts", 4, 1, 32, 1, kind="int"),
    choice("origin", "Blast origin", "each prop's own centre", ["each prop's own centre", "feature prop (spreads across the group)"]),
    FEATURE, PROP, EVERY,
    Slider("spread_in_s", "Spread across the group (in/s)", 400.0, 100.0, 2000.0, 20.0, unit="in/s"),
    Slider("shards", "Shards per prop", 10, 3, 24, 1, kind="int"),
    Slider("throw", "Throw (share of prop size)", 0.35, 0.15, 1.0, 0.05),
    Slider("ghost", "Afterimage of the prop", 0.3, 0.0, 0.8, 0.05),
    Slider("fly_s", "Seconds in the air", 1.2, 0.4, 4.0, 0.1, unit="s"),
    Slider("gravity", "Gravity", 0.5, 0.0, 1.5, 0.05),
    Slider("fireball", "Fireball", 0.7, 0.0, 1.0, 0.05),
    Slider("hang_s", "Seconds before the pieces fly", 0.12, 0.0, 0.5, 0.02, unit="s"),
    COLOURS,
    toggle("reassemble", "Pieces fly back together before the next blast", True),
], doc="Each prop is blown apart and (optionally) pulls itself back together. A white flash, then a fireball swells out from the blast point in real inches, and the prop breaks into shards -- real chunks of its own bulb map -- that fly outward from the centre, tumble under gravity and fade, leaving smoke. Blast from each prop's own centre, or from the feature prop so the blast wave reaches the far props later. Every N bars from the clip's start, on hits, or once.")
def explosion(g, m, t, p, pal, st):
    from .fire import _heat
    # ---- when did the current blast start, per prop?
    bar_len = m.beat_len * m.beats_per_bar
    if p["trigger"] == "on hits":
        if m.hit > 0.6 and st.get("prev", 0.0) <= 0.6 and t - st.get("t0", -9) > 0.8:
            st["t0"] = t; st["n"] = st.get("n", 0) + 1
        st["prev"] = m.hit
        t0, n, period = st.get("t0", -9.0), st.get("n", 0), 1e9
    elif p["trigger"] == "once at clip start":
        t0, n, period = 0.0, 0, 1e9
    else:
        # anchored to the CLIP, not the song's bar grid: the first blast is at the clip's start, then every N bars
        period = bar_len * int(p["bars"])
        n = int(t // period)
        t0 = n * period
    k_feat = g.feature(p["feature"], m, int(p["every_bars"]), p.get("prop")) if g.P else 0
    src = g.C[k_feat] if g.P else np.zeros(3)
    out = {}
    for pr in g.props:
        delay = 0.0 if p["origin"].startswith("each") else np.hypot(pr.cx - src[0], pr.cz - src[2]) / max(1.0, p["spread_in_s"])
        age = t - t0 - delay
        pic = _pic(pr, pal, p)
        fr = np.zeros((pr.n, 3))
        if age < 0:                                                     # whole, waiting for the wave
            out[pr.id] = pic * (0.85 + 0.15 * _fbm(pr.lx / 8, pr.ly / 8, t * 0.3, pr.idx, 2))[:, None]
            continue
        cx, cy = 0.0, pr.h * 0.5                                        # blast point: the prop's own centre
        # 1. flash
        flash = math.exp(-age / 0.06) if age < 0.25 else 0.0
        # 2. fireball: swells out from the blast point to the prop's size in ~0.4 s, cools from white-hot to smoke
        size = max(pr.w, pr.h)
        R = size * (0.15 + 1.1 * (1 - math.exp(-age / 0.25)))
        d = np.hypot(pr.lx - cx, pr.ly - cy)
        ball = np.clip(1 - d / max(1.0, R), 0, 1) ** 0.35 * (0.8 + 0.4 * _fbm(pr.lx / 5, pr.ly / 5 - age * 12, age * 4, pr.idx + 7, 2))
        heat_v = np.clip(ball * (1.2 - age * 2.4), 0, 1) * p["fireball"] * 0.85
        fr = lighten(fr, _heat(heat_v, "fire", pal))
        smoke = np.clip(np.clip(1 - d / max(1.0, R), 0, 1) * np.clip(age - 0.4, 0, 1) * (1 - age / 2.2), 0, 1) * 0.3 * p["fireball"]
        fr = lighten(fr, np.array([0.45, 0.45, 0.5]) * smoke[:, None])
        # 3. shards: chunks of the real bulb map slide outward from the blast point (as far as the prop can show
        #    them), tumble, sag under gravity and fade -- or ease back home before the next blast
        K = int(p["shards"]); which, seeds, tree = _shards(pr, K, n)
        r = rng(n * 104729 + pr.idx * 17)
        ang_j = (r.random(len(seeds)) - 0.5) * 0.7; spd_j = 0.6 + 0.8 * r.random(len(seeds)); spin = (r.random(len(seeds)) - 0.5) * 1.6
        tfly = max(0.0, age - p["hang_s"])
        reach = p["throw"] * size
        if p["reassemble"] and period < 1e8:
            T = max(0.6, period - p["hang_s"] - 0.15)
            u = min(1.0, tfly / T)
            prog = math.sin(math.pi * u) ** 0.8                              # out, hang at the far point, ease home
            fade = 1 - 0.6 * prog
            sag = p["gravity"] * reach * 0.5 * prog
        else:
            u = min(1.0, tfly / p["fly_s"])
            prog = 1 - (1 - u) ** 2                                          # decelerating throw
            fade = max(0.0, 1 - u) ** 0.7
            sag = p["gravity"] * reach * 0.8 * u * u
        vx = seeds[:, 0] - cx; vy = seeds[:, 1] - cy
        a0 = np.arctan2(vy, vx) + ang_j
        dxk = np.cos(a0) * reach * prog * spd_j; dyk = np.sin(a0) * reach * prog * spd_j - sag
        # every bulb shows whichever shard's image has moved onto it: for shard k, the bulb's source point is
        # pos - d_k rotated back about the shard's seed; lit if that source is a bulb of shard k
        shard_rgb = np.zeros((pr.n, 3))
        nbr = tree.query(np.column_stack([pr.lx, pr.ly]), k=4)[1]
        edge = (which[nbr] != which[:, None]).any(1)                          # bulbs on a shard boundary
        hot = np.array([1.0, 0.45, 0.05]) * ((1 - prog / 0.6) * 0.9 if (tfly > 0 and prog < 0.6) else 0.0)
        for k_ in range(len(seeds)):
            sx = pr.lx - dxk[k_]; sy = pr.ly - dyk[k_]
            c_, s_ = math.cos(spin[k_] * prog), math.sin(spin[k_] * prog)
            rx = sx - seeds[k_, 0]; ry = sy - seeds[k_, 1]
            sx = seeds[k_, 0] + rx * c_ - ry * s_; sy = seeds[k_, 1] + rx * s_ + ry * c_
            dist, j = tree.query(np.column_stack([sx, sy]), k=1)
            on = (dist <= pr.pitch * 1.6) & (which[j] == k_)
            if not on.any():
                continue
            piece = pic[j] * fade
            piece = lighten(piece, hot[None, :] * edge[j][:, None])
            shard_rgb[on] = np.maximum(shard_rgb[on], piece[on])
        fr = lighten(fr, shard_rgb if (tfly > 0 or p["reassemble"]) else pic)
        # a dim afterimage of the whole prop lingers while the pieces are away, so the silhouette never fully vanishes
        if tfly > 0:
            ghost = p["ghost"] * (1 - (prog if p["reassemble"] else u)) * (0.8 + 0.2 * _fbm(pr.lx / 4, pr.ly / 4, t * 2, pr.idx + 3, 2))
            fr = lighten(fr, pic * ghost[:, None])
        fr = lighten(fr, np.broadcast_to(WHITE * flash, (pr.n, 3)))
        out[pr.id] = np.clip(fr, 0, 1)
    return out
