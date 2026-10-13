"""
modifiers.py -- layers that change whatever is already playing.

fn(g, m, t, p, pal, F, st) -> frame.  F is the frame so far.
"""

import math
import numpy as np

from .util import rng, hue_rotate, noise, resample, smoothstep
from ..engine import effect, Slider, choice, toggle
from ...effects import lighten

PACK = "Modifiers"


@effect("mod_twinkle", "mod", "Twinkle", pack=PACK, params=[
    Slider("amount", "Share of bulbs off", 0.25, 0.05, 0.8, 0.05),
    Slider("rate", "Changes per second", 6.0, 1.0, 20.0, 0.5),
    toggle("beat", "Denser on the beat", False),
], doc="Randomly REMOVES bulbs for a moment (never adds white) so the picture twinkles without changing its colours -- the twinkle that worked on the bench.")
def mod_twinkle(g, m, t, p, pal, F, st):
    slot = int(t * p["rate"])
    amt = p["amount"] * (1 + 0.6 * m.beat_env if p["beat"] else 1.0)
    out = {}
    for pr in g.props:
        r = rng(slot * 7919 + pr.idx * 131)
        off = r.random(pr.n) < amt
        out[pr.id] = F[pr.id] * (~off)[:, None]
    return out


@effect("mod_ripple", "mod", "Ripple", pack=PACK, params=[
    choice("source", "Ripple from", "centre prop", ["centre prop", "left end", "right end", "random prop"]),
    choice("trigger", "Trigger", "every bar", ["every beat", "every bar", "on hits"]),
    Slider("speed_in_s", "Speed (in/s)", 240.0, 60.0, 800.0, 10.0, unit="in/s"),
    Slider("width_in", "Ring width (in)", 30.0, 8.0, 120.0, 2.0, unit="in"),
    Slider("depth", "Depth (dims the rest)", 0.6, 0.0, 1.0, 0.05),
    Slider("boost", "Boost on the ring", 0.4, 0.0, 1.0, 0.05),
], doc="A brightness ring radiates outward across the group from a source prop using the real distances between props; the picture underneath is dimmed away from the ring and brightened on it.")
def mod_ripple(g, m, t, p, pal, F, st):
    if not g.P:
        return F
    # when did the last ripple start?
    if p["trigger"] == "every beat":
        age = m.beat_phase * m.beat_len
    elif p["trigger"] == "every bar":
        age = m.bar_phase * m.beat_len * m.beats_per_bar
    else:
        if m.hit > 0.6 and st.get("prev_hit", 0.0) <= 0.6:
            st["t_hit"] = t
        st["prev_hit"] = m.hit
        age = t - st.get("t_hit", -10.0)
    if p["source"] == "centre prop":
        src = g.C[g.P // 2]
    elif p["source"] == "left end":
        src = g.C[0]
    elif p["source"] == "right end":
        src = g.C[-1]
    else:
        src = g.C[rng(m.bar_index).integers(0, g.P)]
    rad = age * p["speed_in_s"]
    out = {}
    for pr in g.props:
        d = np.hypot(pr.wx - src[0], pr.wz - src[2])
        ring = np.exp(-((d - rad) / (p["width_in"] / 2)) ** 2)
        gain = (1 - p["depth"]) + p["depth"] * ring + p["boost"] * ring
        out[pr.id] = np.clip(F[pr.id] * gain[:, None], 0, 1)
    return out


@effect("mod_glitch", "mod", "Glitch", pack=PACK, params=[
    Slider("amount", "Amount", 0.5, 0.0, 1.0, 0.05),
    Slider("rate", "Glitches per second", 4.0, 0.5, 20.0, 0.5),
    choice("trigger", "Trigger", "random", ["random", "on hits", "on the beat"]),
    toggle("invert", "Colour inversion bursts", True),
    toggle("blackout", "Block dropouts", True),
    toggle("shift", "Wire-order slips", True),
], doc="Digital corruption: blocks of a prop drop out, the wire order slips a few bulbs, colours invert for a frame. Driven by the music if you want it to hit with the drums.")
def mod_glitch(g, m, t, p, pal, F, st):
    slot = int(t * p["rate"])
    gate = 1.0
    if p["trigger"] == "on hits":
        gate = 1.0 if m.hit > 0.5 else 0.0
    elif p["trigger"] == "on the beat":
        gate = 1.0 if m.beat_phase < 0.25 else 0.0
    amt = p["amount"] * gate
    if amt <= 0:
        return F
    out = {}
    for pr in g.props:
        r = rng(slot * 104729 + pr.idx * 7)
        fr = F[pr.id].copy()
        if r.random() > amt:
            out[pr.id] = fr; continue
        if p["shift"] and r.random() < 0.6:
            fr = np.roll(fr, int(r.integers(-8, 9)), axis=0)
        if p["blackout"] and r.random() < 0.6:
            a = int(r.integers(0, pr.n)); b = min(pr.n, a + int(r.integers(2, max(3, pr.n // 3))))
            fr[a:b] = 0
        if p["invert"] and r.random() < 0.35:
            lit = fr.max(1) > 0.05
            fr[lit] = 1 - fr[lit]
        out[pr.id] = fr
    return out


@effect("mod_strobe", "mod", "Strobe gate", pack=PACK, tags=["music"], params=[
    choice("trigger", "Fire on", "every beat", ["every beat", "8ths", "16ths", "every bar", "on hits", "free running"]),
    Slider("on_s", "Flash length (s)", 0.06, 0.01, 0.4, 0.01, unit="s"),
    Slider("hz", "Free-run rate (Hz)", 8.0, 1.0, 20.0, 0.5),
    Slider("floor", "Level between flashes", 0.0, 0.0, 0.8, 0.05),
    Slider("bursts", "Flashes per trigger", 1, 1, 6, 1, kind="int"),
    toggle("white", "Flash white (else keep the colours)", False),
], doc="Chops whatever is playing into hard flashes on the beat grid -- one hit, a burst of several, or free-running. Between flashes the picture drops to the floor level, so set the floor above zero if you want the look to stay visible.")
def mod_strobe(g, m, t, p, pal, F, st):
    on = p["on_s"]
    if p["trigger"] == "free running":
        ph = (t * p["hz"]) % 1.0
        fire = ph < on * p["hz"]
    elif p["trigger"] == "on hits":
        if m.hit > 0.55 and st.get("prev", 0.0) <= 0.55:
            st["t0"] = t
        st["prev"] = m.hit
        age = t - st.get("t0", -9)
        fire = any(k * on * 2 <= age < k * on * 2 + on for k in range(int(p["bursts"])))
    else:
        sub = {"every beat": 1, "8ths": 2, "16ths": 4, "every bar": 1 / max(1, m.beats_per_bar)}[p["trigger"]]
        pos = ((m.beat_index + m.beat_phase) * sub) % 1.0
        age = pos * m.beat_len / sub
        fire = any(k * on * 2 <= age < k * on * 2 + on for k in range(int(p["bursts"])))
    if fire:
        if not p["white"]:
            return F
        return {pid: np.maximum(F[pid], np.broadcast_to(np.ones(3) * F[pid].max(), F[pid].shape)) for pid in F}
    return {pid: F[pid] * p["floor"] for pid in F}


@effect("mod_hue", "mod", "Colour shift", pack=PACK, tags=[], params=[
    Slider("shift", "Hue shift", 0.0, -0.5, 0.5, 0.01),
    choice("drive", "Animate the shift with", "off", ["off", "slow drift", "per bar step", "beat pulse", "energy"]),
    Slider("range", "Animated range", 0.25, 0.0, 1.0, 0.01),
    Slider("period_s", "Drift period (s)", 12.0, 2.0, 60.0, 0.5, unit="s"),
    Slider("saturation", "Saturation", 1.0, 0.0, 2.0, 0.05),
], doc="Rotates the hue of everything underneath -- a fixed shift to recolour a look you like, or animated: a slow drift, a step every bar, a kick on the beat, or driven by the music's energy. Saturation below 1 washes it toward white, above 1 deepens it.")
def mod_hue(g, m, t, p, pal, F, st):
    d = p["shift"]
    if p["drive"] == "slow drift":
        d += p["range"] * math.sin(2 * math.pi * t / p["period_s"])
    elif p["drive"] == "per bar step":
        d += p["range"] * ((m.bar_index % 4) / 4.0)
    elif p["drive"] == "beat pulse":
        d += p["range"] * m.pulse
    elif p["drive"] == "energy":
        d += p["range"] * m.energy
    if abs(d) < 1e-4 and abs(p["saturation"] - 1) < 1e-3:
        return F
    return {pid: hue_rotate(F[pid], d, p["saturation"]) for pid in F}


@effect("mod_envelope", "mod", "Brightness envelope", pack=PACK, tags=["music"], params=[
    choice("shape", "Shape", "breathe", ["breathe", "duck on the beat", "swell into the bar", "follow the music", "fade in", "fade out"]),
    Slider("depth", "Depth", 0.5, 0.0, 1.0, 0.05),
    Slider("period_s", "Breathe period (s)", 6.0, 1.0, 40.0, 0.5, unit="s"),
    Slider("floor", "Never below", 0.1, 0.0, 0.9, 0.05),
    Slider("clip_s", "Fade length (s)", 4.0, 0.5, 60.0, 0.5, unit="s"),
], doc="Shapes the brightness of whatever is playing without touching its colours: a slow breathe, a duck on every beat (so the beat reads as a dip, not a flash), a swell into each bar, a follow of the music's loudness, or a plain fade in / out over the clip.")
def mod_envelope(g, m, t, p, pal, F, st):
    if p["shape"] == "breathe":
        w = 0.5 + 0.5 * math.sin(2 * math.pi * t / p["period_s"])
    elif p["shape"] == "duck on the beat":
        w = 1 - m.pulse
    elif p["shape"] == "swell into the bar":
        w = m.bar_phase
    elif p["shape"] == "follow the music":
        w = m.energy
    elif p["shape"] == "fade in":
        w = min(1.0, t / max(0.1, p["clip_s"]))
    else:
        w = max(0.0, 1 - t / max(0.1, p["clip_s"]))
    lvl = 1 - p["depth"] * (1 - w)
    lvl = max(p["floor"], lvl)
    return {pid: F[pid] * lvl for pid in F}


@effect("mod_mirror", "mod", "Mirror", pack=PACK, tags=[], params=[
    choice("axis", "Mirror", "each prop left↔right", ["each prop left↔right", "each prop top↕bottom", "the row left↔right", "wire order"]),
    Slider("blend", "Blend with the original", 1.0, 0.0, 1.0, 0.05),
    choice("drive", "Flip", "always", ["always", "every bar", "every 2 bars", "every 4 bars"]),
], doc="Reflects the picture -- each prop mirrored left to right, flipped top to bottom, or the whole row reversed so the left end plays what the right end was doing. Blend below 1 keeps both halves layered, which doubles up a chase into a symmetric pattern.")
def mod_mirror(g, m, t, p, pal, F, st):
    if p["drive"] != "always":
        every = {"every bar": 1, "every 2 bars": 2, "every 4 bars": 4}[p["drive"]]
        if (m.bar_index // every) % 2 == 0:
            return F
    out = {}
    if p["axis"] == "the row left↔right":
        ids = [pr.id for pr in g.props]
        for k, pr in enumerate(g.props):
            other = g.props[len(g.props) - 1 - k]
            src = F[other.id]
            if src.shape[0] != pr.n:                                  # different pixel counts: resample by position
                idx = np.clip((np.arange(pr.n) * src.shape[0] // max(1, pr.n)), 0, src.shape[0] - 1)
                src = src[idx]
            out[pr.id] = F[pr.id] * (1 - p["blend"]) + src * p["blend"] if p["blend"] < 1 else np.maximum(src, F[pr.id] * 0)
        return out
    for pr in g.props:
        fr = F[pr.id]
        if p["axis"] == "wire order":
            mirrored = fr[::-1]
        elif p["axis"] == "each prop top↕bottom":
            order = np.argsort(pr.ly)
            rev = order[::-1]
            mirrored = fr.copy(); mirrored[order] = fr[rev]
        else:
            order = np.argsort(pr.lx)
            rev = order[::-1]
            mirrored = fr.copy(); mirrored[order] = fr[rev]
        out[pr.id] = np.maximum(fr * (1 - p["blend"]), mirrored) if p["blend"] < 1 else mirrored
    return out


@effect("mod_sparkle", "mod", "Sparkle overlay", pack=PACK, tags=["music"], params=[
    Slider("density", "Sparkles per prop per second", 6.0, 0.5, 40.0, 0.5),
    Slider("life_s", "Sparkle life (s)", 0.3, 0.05, 1.5, 0.05, unit="s"),
    choice("color", "Colour", "white", ["white", "frost", "gold", "palette", "brighter version of what's underneath"]),
    choice("drive", "More sparkles on", "off", ["off", "hits", "the beat", "loud passages"]),
    Slider("level", "Sparkle brightness", 1.0, 0.2, 1.0, 0.05),
    toggle("only_lit", "Only on bulbs that are already lit", False),
], doc="Scatters bright grains on top of whatever is playing -- the frost sparkle as a layer you can add to any look. Unlike Twinkle (which removes bulbs) this one adds them, so use it sparingly on bright looks.")
def mod_sparkle(g, m, t, p, pal, F, st):
    from ...effects import frost
    boost = {"hits": 1 + 2.5 * m.hit, "the beat": 1 + 1.5 * m.beat_env, "loud passages": 0.4 + 1.6 * m.energy}.get(p["drive"], 1.0)
    dens = p["density"] * boost
    life = p["life_s"]
    out = {}
    for pr in g.props:
        gr = st.get(pr.id)
        if gr is None or len(gr) != pr.n:
            gr = np.zeros(pr.n)
        gr = gr * math.exp(-m.dt / life * 3)
        n_new = dens * m.dt * pr.n / 72.0
        k = int(n_new) + (1 if rng(int(t * 1e5) + pr.idx).random() < (n_new % 1.0) else 0)
        if k > 0:
            r = rng(int(t * 1e4) + pr.idx * 7)
            gr[r.integers(0, pr.n, min(k, pr.n))] = 1.0
        st[pr.id] = gr
        v = gr * p["level"]
        if p["only_lit"]:
            v = v * (F[pr.id].max(1) > 0.05)
        if p["color"] == "frost":
            sp = frost(v)
        elif p["color"] == "gold":
            sp = np.array([1.0, 0.75, 0.25]) * v[:, None]
        elif p["color"] == "palette":
            sp = pal.pick(rng(pr.idx).integers(0, pal.k, pr.n)) * v[:, None]
        elif p["color"] == "brighter version of what's underneath":
            base = F[pr.id]
            mx = np.maximum(base.max(1, keepdims=True), 1e-3)
            sp = (base / mx) * v[:, None]
        else:
            sp = np.ones(3) * v[:, None]
        out[pr.id] = lighten(F[pr.id], sp)
    return out


@effect("mod_snowcap", "mod", "Snow on top", pack=PACK, tags=[], params=[
    Slider("depth", "How far down (share of prop)", 0.18, 0.05, 0.6, 0.01),
    Slider("ragged", "Ragged edge", 0.5, 0.0, 1.0, 0.05),
    Slider("sparkle", "Sparkle", 0.5, 0.0, 1.0, 0.05),
    Slider("level", "Snow brightness", 0.9, 0.3, 1.0, 0.05),
    choice("tint", "Snow", "frost", ["frost", "white", "warm"]),
], doc="Puts a cap of snow on top of whatever is playing: the upper part of every prop goes white with a ragged lower edge and a soft sparkle, the rest untouched. Works on any animation -- a fire with snow on it, a rainbow with snow on it. A building block.")
def mod_snowcap(g, m, t, p, pal, F, st):
    from .util import noise, smoothstep, glints
    from ...effects import frost
    tint = {"white": np.ones(3), "warm": np.array([1.0, 0.92, 0.8])}.get(p["tint"])
    out = {}
    for pr in g.props:
        edge = 1 - p["depth"] + (noise(pr.lx / 3.0, 0, 0, pr.idx + 1) - 0.5) * 0.3 * p["ragged"]
        w = smoothstep(edge - 0.04, edge + 0.04, pr.y01)
        shade = 0.8 + 0.2 * noise(pr.lx / 2.5, pr.ly / 2.5, t * 0.2, pr.idx)
        v = w * p["level"] * shade
        v = np.maximum(v, w * p["sparkle"] * glints(pr, t, 0.5, pr.idx + 8, 14.0))
        snow = frost(v) if p["tint"] == "frost" else tint * v[:, None]
        out[pr.id] = F[pr.id] * (1 - w * 0.9)[:, None] + snow * w[:, None]
    return {k: np.clip(v, 0, 1) for k, v in out.items()}


@effect("mod_wobble", "mod", "Tape wobble", pack=PACK, tags=["music"], params=[
    Slider("depth_in", "Wobble depth (in)", 4.0, 0.5, 18.0, 0.5, unit="in"),
    choice("sync", "Wobble clock", "one bar", ["one bar", "two bars", "one beat", "free (0.4 Hz)"]),
    Slider("flutter", "Flutter (fast jitter)", 0.2, 0.0, 1.0, 0.05),
    Slider("beat_kick", "Kick on the beat (in)", 2.0, 0.0, 12.0, 0.5, unit="in"),
    toggle("sideways", "Drift sideways too", False),
], doc="A warped record: the whole picture drifts up and down a few inches in a slow sine locked to the bar (or beat), with a touch of fast flutter, and a small downward kick on each beat that springs back. Subtle, musical, and it makes any static picture breathe.")
def mod_wobble(g, m, t, p, pal, F, st):
    ph = {"one bar": m.bar_phase, "two bars": ((m.bar_index % 2) + m.bar_phase) / 2, "one beat": m.beat_phase}.get(p["sync"], (t * 0.4) % 1.0)
    dy = p["depth_in"] * math.sin(ph * 2 * math.pi) + p["flutter"] * 1.5 * math.sin(t * 23.0) * math.sin(t * 7.3)
    dy -= p["beat_kick"] * m.pulse
    dx = p["depth_in"] * 0.5 * math.sin(ph * 2 * math.pi + 1.2) if p["sideways"] else 0.0
    return {pr.id: resample(pr, F[pr.id], dx, dy) for pr in g.props}


@effect("mod_slices", "mod", "Slice shift", pack=PACK, tags=["music"], params=[
    Slider("band_in", "Band height (in)", 6.0, 2.0, 24.0, 1.0, unit="in"),
    Slider("shift_in", "Max shift (in)", 10.0, 2.0, 40.0, 1.0, unit="in"),
    choice("trigger", "Trigger", "on hits", ["on hits", "every beat", "every bar", "always"]),
    Slider("threshold", "Hit threshold", 0.5, 0.1, 0.9, 0.05),
    Slider("decay_s", "Snap back (s)", 0.25, 0.05, 1.0, 0.05, unit="s"),
    Slider("share", "Share of bands that move", 0.5, 0.1, 1.0, 0.05),
], doc="On each hit the picture is cut into horizontal bands and some of them slide sideways by a few inches, then snap back -- harder hits throw more bands further. Geometric cousin of Glitch; great on drums.")
def mod_slices(g, m, t, p, pal, F, st):
    # a new slice pattern on each trigger; its strength decays
    if p["trigger"] == "on hits":
        fire = m.hit > p["threshold"] and st.get("prev", 0.0) <= p["threshold"]; st["prev"] = m.hit; amt = m.hit
    elif p["trigger"] == "every beat":
        fire = m.beat_phase * m.beat_len < m.dt * 1.5; amt = 0.8
    elif p["trigger"] == "every bar":
        fire = m.on_bar or (m.bar_phase * m.beat_len * m.beats_per_bar < m.dt * 1.5); amt = 1.0
    else:
        fire = True; amt = 0.7
    if fire:
        st["t0"] = t; st["n"] = st.get("n", 0) + 1; st["amt"] = amt
    age = t - st.get("t0", -9)
    k = st.get("amt", 0.0) * math.exp(-age / max(0.02, p["decay_s"]) * 3)
    if k < 0.02:
        return F
    out = {}
    for pr in g.props:
        r = rng(st.get("n", 0) * 7919 + pr.idx * 31)
        band = np.floor(pr.ly / p["band_in"]).astype(int)
        nb = int(band.max()) + 1 if pr.n else 1
        moving = r.random(nb) < p["share"]
        amount = (r.random(nb) * 2 - 1) * p["shift_in"] * k * moving
        out[pr.id] = resample(pr, F[pr.id], amount[band], 0.0)
    return out


@effect("mod_wind", "mod", "Wind", pack=PACK, tags=["slow"], params=[
    Slider("strength", "Strength", 0.5, 0.0, 1.0, 0.05),
    Slider("wave_in", "Wavelength (in)", 24.0, 8.0, 80.0, 2.0, unit="in"),
    Slider("speed", "Wave speed (in/s)", 30.0, 5.0, 120.0, 5.0, unit="in/s"),
    choice("direction", "Blows", "left → right", ["left → right", "right → left"]),
    Slider("gusts", "Gusts", 0.6, 0.0, 1.0, 0.05),
    Slider("shimmer", "Shimmer", 0.35, 0.0, 1.0, 0.05),
    toggle("anchor", "Anchored at the bottom", True),
], doc="The picture ripples like a flag in a breeze: a travelling wave displaces the pixels sideways (more toward the top if anchored at the bottom), with gusts that come and go and a faint shimmer where the fabric catches the light. Slow and alive; drop it on a static picture or any calm animation.")
def mod_wind(g, m, t, p, pal, F, st):
    dirn = 1.0 if p["direction"] == "left → right" else -1.0
    gust = 0.6 + 0.4 * (noise(t * 0.15, 0, 0, 5) * 2 - 1) * p["gusts"] + 0.25 * p["gusts"] * math.sin(t * 0.9)
    amp = p["strength"] * 6.0 * gust                                   # inches at full strength
    out = {}
    for pr in g.props:
        phase = (pr.ly - dirn * t * p["speed"]) / p["wave_in"] * 2 * math.pi + pr.lx / (p["wave_in"] * 2.5)
        env = (0.25 + 0.75 * pr.y01) if p["anchor"] else np.ones(pr.n)
        ripple = np.sin(phase) + 0.35 * np.sin(phase * 2.1 + 0.7)
        dx = dirn * amp * env * ripple
        fr = resample(pr, F[pr.id], dx, 0.0)
        if p["shimmer"] > 0:                                             # light catches the crests
            crest = np.clip(np.cos(phase), 0, 1) ** 3
            fr = np.clip(fr * (1 + p["shimmer"] * 0.5 * crest * env)[:, None], 0, 1)
        out[pr.id] = fr
    return out
