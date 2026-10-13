"""ibiza.py -- the Ibiza pack: sunset skies, sweeping beams, drop strobes, ocean waves."""

import math
import numpy as np

from ..engine import effect, Slider, choice, toggle
from ...effects import lighten, hsv
from .util import noise, gradient, smoothstep

PACK = "Ibiza"


@effect("ibiza_sunset", "anim", "Sunset sky", pack=PACK, params=[
    Slider("speed", "Sky drift", 1.0, 0.1, 3.0, 0.1),
    Slider("sun", "Sun size (in)", 30.0, 0.0, 120.0, 5.0, unit="in"),
    choice("colours", "Sky colours", "sunset", ["sunset", "palette", "night"]),
    Slider("shimmer", "Heat shimmer", 0.3, 0.0, 1.0, 0.05),
], doc="A slow beach sunset: warm orange at the bottom of the props blending up through pink to violet, the hues drifting over minutes, a sun disc sliding along the row with a shimmering haze.")
def ibiza_sunset(g, m, t, p, pal, st):
    tt = t * p["speed"] * 0.02
    out = {}
    if p["colours"] == "sunset":
        stops = np.array([[1.0, 0.45, 0.05], [1.0, 0.2, 0.35], [0.55, 0.1, 0.8], [0.15, 0.05, 0.5]])
    elif p["colours"] == "night":
        stops = np.array([[0.4, 0.1, 0.5], [0.1, 0.1, 0.6], [0.0, 0.05, 0.3], [0.0, 0.0, 0.12]])
    else:
        stops = pal.chroma[:4] if pal.k >= 4 else np.array([pal.color(i) for i in range(4)])
    sunx = g.x0 + ((tt * 3.0) % 1.0) * g.width
    for pr in g.props:
        u = np.clip(pr.y01 + 0.15 * (noise(pr.wx / 30, pr.wz / 30, t * 0.4, 2.0) - 0.5) * p["shimmer"], 0, 0.999)
        pos = u * (len(stops) - 1); i0 = np.floor(pos).astype(int); f = (pos - i0)[:, None]
        sky = stops[i0] * (1 - f) + stops[np.minimum(i0 + 1, len(stops) - 1)] * f
        sky = sky * (0.75 + 0.25 * math.sin(tt * 40))
        if p["sun"] > 0:
            d = np.hypot(pr.wx - sunx, pr.wz - (g.z0 + g.height * 0.35))
            sun = np.exp(-(d / (p["sun"] / 2)) ** 2)
            sky = lighten(sky, np.array([1.0, 0.9, 0.55]) * sun[:, None])
        out[pr.id] = sky
    return out


@effect("ibiza_beams", "anim", "Moving beams", pack=PACK, params=[
    Slider("beams", "Beams", 3, 1, 6, 1, kind="int"),
    Slider("width_in", "Beam width (in)", 24.0, 6.0, 120.0, 2.0, unit="in"),
    Slider("bars", "Bars per sweep", 2, 0.5, 8, 0.5),
    Slider("floor", "Haze level", 0.08, 0.0, 0.4, 0.02),
    toggle("beat_kick", "Kick on the beat", True),
    toggle("crossing", "Beams cross each other", True),
], doc="Moving-head beams sweep back and forth across the whole row in saturated palette colours, each on its own bar-locked path, kicking brighter on the beat over a faint haze.")
def ibiza_beams(g, m, t, p, pal, st):
    nb = int(p["beams"])
    bars = m.bar_index + m.bar_phase
    kick = 0.7 + 0.3 * m.pulse if p["beat_kick"] else 1.0
    out = {}
    pos = []
    for k in range(nb):
        ph = (bars / p["bars"] + k / nb) % 1.0
        u = 0.5 - 0.5 * math.cos(2 * math.pi * ph)                    # smooth back and forth
        if p["crossing"] and k % 2:
            u = 1 - u
        pos.append(g.x0 - p["width_in"] + u * (g.width + 2 * p["width_in"]))
    for pr in g.props:
        fr = np.broadcast_to(pal.color(0) * p["floor"], (pr.n, 3)).copy()
        for k, bx in enumerate(pos):
            d = (pr.wx - bx) / (p["width_in"] / 2)
            beam = np.exp(-d ** 2) * kick
            fr = lighten(fr, pal.color(k) * beam[:, None])
        out[pr.id] = fr
    return out


@effect("ibiza_strobe", "anim", "Wash & strobe", pack=PACK, params=[
    Slider("wash", "Wash level", 0.5, 0.1, 1.0, 0.05),
    Slider("bass", "Bass drives the wash", 0.6, 0.0, 1.0, 0.05),
    choice("strobe_on", "Strobe on", "hits", ["hits", "every beat", "every bar", "off"]),
    Slider("strobe_len", "Strobe length (s)", 0.08, 0.03, 0.3, 0.01, unit="s"),
    Slider("hue_bars", "Bars per colour", 2, 1, 8, 1, kind="int"),
    toggle("white_strobe", "White strobe (else palette)", True),
], doc="A saturated colour wash that breathes with the bass and changes colour every couple of bars, with hard strobes fired by the drum hits (or the beat). The club look for the drops.")
def ibiza_strobe(g, m, t, p, pal, st):
    col = pal.color(m.bar_index // max(1, int(p["hue_bars"])))
    lvl = p["wash"] * (1 - p["bass"] + p["bass"] * (0.4 + 0.6 * m.low))
    # strobe timing
    fire = False
    if p["strobe_on"] == "hits":
        if m.hit > 0.55 and st.get("prev", 0.0) <= 0.55:
            st["t_s"] = t
        st["prev"] = m.hit
        fire = t - st.get("t_s", -9) < p["strobe_len"]
    elif p["strobe_on"] == "every beat":
        fire = m.beat_phase * m.beat_len < p["strobe_len"]
    elif p["strobe_on"] == "every bar":
        fire = m.bar_phase * m.beat_len * m.beats_per_bar < p["strobe_len"]
    out = {}
    for pr in g.props:
        # never a flat fill: a slow drifting shimmer keeps the wash alive (and readable at distance)
        sh = 0.75 + 0.35 * noise(pr.wx / 24, pr.wz / 24, t * 0.8, pr.idx)
        fr = col[None, :] * (lvl * sh)[:, None]
        if fire:
            sc = np.ones(3) if p["white_strobe"] else pal.color(m.beat_index)
            fr = lighten(fr, np.broadcast_to(sc, (pr.n, 3)))
        out[pr.id] = fr
    return out


@effect("ibiza_waves", "anim", "Ocean waves", pack=PACK, params=[
    Slider("bars", "Bars per wave", 2, 0.5, 8, 0.5),
    Slider("wave_in", "Wavelength (in)", 120.0, 30.0, 400.0, 10.0, unit="in"),
    Slider("foam", "Foam", 0.6, 0.0, 1.0, 0.05),
    choice("colours", "Water colours", "teal", ["teal", "palette", "deep blue"]),
    choice("direction", "Direction", "left→right", ["left→right", "right→left"]),
], doc="Smooth waves roll across the row in real inches -- deep water at the bottom of the props, a bright teal crest with white foam that travels with the music.")
def ibiza_waves(g, m, t, p, pal, st):
    bars = m.bar_index + m.bar_phase
    phase = (bars / p["bars"]) * (1 if p["direction"] == "left→right" else -1)
    if p["colours"] == "teal":
        deep, crest = np.array([0.0, 0.15, 0.45]), np.array([0.0, 0.9, 0.8])
    elif p["colours"] == "deep blue":
        deep, crest = np.array([0.0, 0.05, 0.35]), np.array([0.2, 0.5, 1.0])
    else:
        deep, crest = pal.color(1) * 0.35, pal.color(0)
    out = {}
    for pr in g.props:
        w = 0.5 + 0.5 * np.sin(2 * math.pi * (pr.wx / p["wave_in"] - phase))
        h = 0.35 + 0.45 * w                                   # water height 0..1 along each prop
        under = smoothstep(h + 0.06, h - 0.06, pr.y01)       # 1 below the surface
        crestband = np.exp(-((pr.y01 - h) / 0.06) ** 2)
        col = deep[None, :] * (1 - pr.y01 / np.maximum(h, 1e-3))[:, None] * 0.6 + crest[None, :] * (0.4 + 0.6 * (pr.y01 / np.maximum(h, 1e-3)))[:, None]
        fr = col * under[:, None]
        foam = crestband * w ** 2 * p["foam"]
        out[pr.id] = lighten(fr, np.ones(3) * foam[:, None])
    return out
