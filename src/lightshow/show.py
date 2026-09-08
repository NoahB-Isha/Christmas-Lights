#!/usr/bin/env python3
"""
show.py -- render show.yaml against a layout, for preview and for cards.

    from lightshow.show import ShowRenderer
    R = ShowRenderer("assets/show/show.yaml", "assets/bench.json")
    frames = R.render(t0=0, t1=83)        # list over time of {prop_id: (n,3) perceptual}
    R.report()                            # per-song brightness figures

THE PIPELINE
    show.yaml     songs -> sections, each with a look, intensity, palette, note
    layout.json   where props are, which controller/port     (lightshow.layout)
    music         per-frame features of the whole track       (lightshow.music)
    songs.json    per-song beat grid, tempo corrected from the reference BPM
                  written in show.yaml's tempo_hint

    frame(t) = crossfade( look_prev(t), look_cur(t) ) over defaults.transition_s

A LOOK is a function  look(t, ctx) -> {prop_id: (n,3) perceptual 0..1}.
`ctx` carries everything a look may want (see Ctx). Looks are registered by
name in LOOKS and referenced by name from show.yaml, so a new look is one
function plus one line in the yaml glossary.

CONVENTIONS (same as effects.py)
    perceptual 0..1 out; to_bytes() applies gamma. Sizes in INCHES. Time in
    SECONDS. Composite with lighten(), not addition.

BRIGHTNESS GUIDELINE (show.yaml defaults.brightness)
    Reported per song by report(): the share of frames whose mean perceptual
    level is >= target_level. Informational -- never clamped.
"""

import json, math, os, re
from collections import OrderedDict

import numpy as np
import yaml

from .layout import Layout
from .effects import hsv, frost, lighten, to_bytes
from . import music

FPS = 60
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def parse_t(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if ":" in s:
        m, sec = s.split(":")
        return int(m) * 60 + float(sec)
    return float(s)


# ------------------------------------------------------------------ palette
class Palette:
    def __init__(self, name, spec):
        self.name = name
        self.hues = list(spec.get("hues", []) or [0.58])
        self.sat_max = float(spec.get("sat_max", 1.0))
        self.white_core = bool(spec.get("white_core", False))
        self.accents = spec.get("accents") or {}
        self.accent_density = float(spec.get("accent_density", 0.0))
        self.stripes = spec.get("stripes")

    def hue(self, k, variation=0):
        return self.hues[(k + variation) % len(self.hues)]

    def color(self, v, k=0, variation=0, sat=None):
        """Perceptual brightness array v -> (n,3). white_core palettes go
        white at the top like frost(); others keep saturation."""
        v = np.clip(np.asarray(v, float), 0, 1)
        h = self.hue(k, variation)
        s = self.sat_max if sat is None else min(sat, self.sat_max)
        if self.white_core:
            return hsv(h, np.clip((1 - v) * 1.15, 0, s), v)
        return hsv(h, s, v)

    def accent_colors(self):
        """[(hue or None for white)] for jewel-style accents."""
        out = []
        for name, h in self.accents.items():
            out.append(h)
        return out or [None]


# --------------------------------------------------------------------- ctx
class PropGeom:
    def __init__(self, placement, idx):
        self.pl, self.idx, self.id = placement, idx, placement.id
        self.n = placement.n
        self.i = np.arange(self.n)
        loc = placement.local(); self.lx, self.ly = loc[:, 0], loc[:, 1]
        W = placement.world(); self.wx, self.wy, self.wz = W[:, 0], W[:, 1], W[:, 2]
        self.cx, self.cy, self.cz = placement.centre()
        s = placement.shape(); self.w, self.h, self.pitch = s["w"], s["h"], s["pitch_in"]
        self.r = np.hypot(self.lx, self.ly - self.h / 2)
        self.r01 = self.r / max(1e-6, self.r.max())
        self.ang = np.arctan2(self.ly - self.h / 2, self.lx)
        self.y01 = self.ly / max(1e-6, self.h)            # 0 bottom .. 1 top
        self.group = placement.group


class Ctx:
    """Everything a look can read for one frame."""
    def __init__(self, R, t, sec, song):
        self.R, self.t = R, t
        self.props = R.props
        self.by_id = R.by_id
        self.world = R.world                 # (xmin, xmax) inches
        self.dist = R.dist                   # (P,P) centre distances, inches
        self.sec, self.song = sec, song
        self.t_sec = t - sec["t0"]           # seconds into the section
        self.sec_len = sec["t1"] - sec["t0"]
        self.progress = min(1.0, self.t_sec / max(1e-6, self.sec_len))
        self.t_song = t - song["from"]
        self.palette = R.palette_for(sec, song)
        self.variation = sec["variation"]
        self.intensity = R.intensity_at(t, sec, song)     # 0..1
        f = min(R.n_frames - 1, int(round(t * FPS)))
        A = R.a
        self.rms, self.low, self.mid, self.high = A.rms[f], A.low[f], A.mid[f], A.high[f]
        self.centroid, self.harm, self.perc = A.centroid[f], A.harm[f], A.perc[f]
        self.hit, self.hit_high = A.hit[f], A.hit_high[f]
        self.beat = R.beat_env[f]; self.bar = R.bar_env[f]
        self.beat_phase = R.beat_phase_at(t, song)
        self.bar_phase = R.bar_phase_at(t, song)
        self.bpm = song["bpm"]
        # THE MAIN PULSE. Looks should breathe with this, not twitch at every
        # onset. pulse_beats (per song, show.yaml) says how many detected
        # beats make one felt pulse -- Carol of the Bells is 2 (168 -> 84).
        self.pulse_beats = song.get("pulse_beats", 1)
        self.bar_beats = song.get("bar_beats", 4)
        self.pulse_phase = R.pulse_phase_at(t, song)      # 0..1 within the felt pulse
        # JAGGED, not smooth: 1.0 on the pulse, then an exponential fall.
        self.pulse = math.exp(-4.0 * self.pulse_phase)
        self.phrase_phase = R.phrase_phase_at(t, song)    # 0..1 over 4 bars
        self.energy = R.energy[f]                         # slow loudness, ~1 s window, 0..1 per song
        self.chroma = R.a.chroma_f[f] if hasattr(R.a, "chroma_f") else None
        self.beat_index = R.beat_index_at(t, song)
        # unison: 1 on the phrase downbeat and through the last bar of the
        # phrase, ~0 mid-phrase. Props separate when it is low and snap back
        # together as it rises.
        ph = self.phrase_phase
        self.unison = float(np.clip(1.0 - 4.0 * min(ph, 1.0 - ph) / 0.75, 0, 1)) if ph > 0.75 or ph < 0.08 else 0.0
        self.unison = max(self.unison, float(np.clip((ph - 0.7) / 0.3, 0, 1)))
        self.feature = R.feature_for(sec, song)           # PropGeom
        nxt = R.sections[sec["index"] + 1] if sec["index"] + 1 < len(R.sections) else None
        self.next_look = nxt["look"] if nxt else None
        self.prop_flash = R.prop_flash                    # {prop_id: 0..1} one prop per onset, decaying
        self.rng = np.random.default_rng(int(t * 10) + sec["index"] * 7919 + self.variation * 104729)

    def per_prop(self, fn):
        return {p.id: np.asarray(fn(p), float).reshape(p.n, 3) if np.asarray(fn(p)).ndim == 2 else
                np.broadcast_to(np.asarray(fn(p), float), (p.n, 3)).copy() for p in self.props}

    def grains(self, p, density, life=0.6, seed_extra=0):
        """Sparkle field: `density` grains per prop per second, each born
        bright and decaying over `life` seconds. Deterministic in t."""
        g = np.zeros(p.n)
        births = max(1, int(density * life))
        for k in range(births):
            slot = int((self.t + k * life / births) / life)
            r = np.random.default_rng(slot * 1000003 + k * 7 + p.idx * 131 + seed_extra)
            age = ((self.t + k * life / births) % life) / life
            j = r.integers(0, p.n)
            g[j] = max(g[j], (1 - age) ** 1.4)
        return g

    def shimmer(self, p, level=0.35):
        return self.grains(p, 3, 1.4) * level


# ------------------------------------------------------------------- looks
LOOKS = {}


def look(name):
    def deco(fn):
        LOOKS[name] = fn; return fn
    return deco


def turb(c, p, scale_in=18.0, speed=1.0, seed=0.0):
    """Cheap moving noise 0..1 over world x/z -- the weather behind a storm."""
    x, z = p.wx / scale_in, p.wz / scale_in
    t = c.t * speed + seed
    v = (np.sin(1.0 * x + 0.7 * t) * np.cos(0.8 * z - 0.5 * t)
         + 0.5 * np.sin(2.3 * x - 1.9 * t + 1.3) * np.cos(2.1 * z + 1.1 * t)
         + 0.25 * np.sin(4.7 * x + 3.1 * t + 0.4) * np.cos(4.3 * z - 2.7 * t + 2.0))
    return np.clip(v / 1.75 * 0.5 + 0.5, 0, 1)


def gust(c, p, period=2.6, width_in=70.0, direction=1.0, phase=0.0):
    """A bright front sweeping the whole course once per `period` seconds.
    Sharp leading edge, long tail -- it arrives, it does not ooze."""
    x0, x1 = c.world
    span = x1 - x0 + 2 * width_in
    ph = (c.t / period + phase) % 1.0
    head = (x0 - width_in + ph * span) if direction > 0 else (x1 + width_in - ph * span)
    d = (head - p.wx) * direction                    # >0 behind the front
    return np.where(d < 0, np.exp(-(d / (width_in * 0.08)) ** 2), np.exp(-d / (width_in * 0.6)))


def _rainbow(c, p, speed=0.18):
    x0, x1 = c.world
    ph = (p.wx - x0) / max(1.0, x1 - x0)
    return hsv((ph * 0.8 - c.t * speed) % 1.0, 0.95, np.ones(p.n))


# ---------------------------------------------------------------- the stack
#
# THE MUSIC LAYER STACK is what made the prop-47 show feel connected: each
# music feature owns one spatial channel of every prop, and the layers
# composite by lighten. Looks do not replace it -- they set its MIX and add
# gestures on top. Per prop:
#
#   wash      harmonic energy -> level, palette hue nudged by the chord   whole prop
#   ring      low band -> radius of a ring from the centre                  radius
#   hits      percussive onsets -> one SECTOR of the prop flashes, the       angle
#             sector advancing on each beat (drums walk around the prop)
#   sparkle   high-band onsets -> grains born white, cooling into colour     bulbs
#             (stateful: grains persist and decay across frames)
#   melody    spectral centroid -> a glow travelling the wire               wire order
#   shimmer   time only -> always-on idle glint                             bulbs
#
# SEPARATE AND COME BACK TOGETHER: c.unison (0..1) rises toward the end of
# every 4-bar phrase and peaks on the phrase downbeat. When unison is low,
# props diverge -- each gets its own hue offset, its own sector order and
# its own time offset, so they visibly do their own thing; as unison rises
# those offsets shrink to zero and everything snaps back into one gesture.

def mix_for(c):
    """Intensity 0..1 -> layer gains (the ladder from the prop-47 show)."""
    r = c.intensity
    if r <= 0.25:
        m = dict(wash=0.45, ring=0.30, hits=0.10, sparkle=0.25, melody=0.0, shimmer=0.8, sat=0.85)
    elif r < 0.55:
        m = dict(wash=0.65, ring=0.80, hits=0.50, sparkle=0.60, melody=0.25, shimmer=0.6, sat=0.9)
    elif r < 0.85:
        m = dict(wash=0.80, ring=0.92, hits=0.80, sparkle=0.85, melody=0.55, shimmer=0.45, sat=0.92)
    else:
        m = dict(wash=0.95, ring=1.00, hits=1.00, sparkle=1.00, melody=0.80, shimmer=0.35, sat=0.95)
    return m


def chroma_hue_nudge(c):
    if c.chroma is None:
        return 0.0
    k = int(np.argmax(c.chroma))
    fifths = [0, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10, 5]
    return 0.03 * math.sin(2 * math.pi * fifths.index(k) / 12.0)


def stack(c, p, m, hue_k=0, time_off=0.0, sector_off=0):
    """The six music layers for one prop under mix m -> (n,3)."""
    pal = c.palette
    div = 1.0 - c.unison                          # how far this prop may stray
    h0 = pal.hue(hue_k, c.variation)
    hue = (h0 + chroma_hue_nudge(c) + div * 0.06 * ((p.idx % 3) - 1)) % 1.0
    t = c.t + div * time_off

    # 0 wash -- hits with the felt pulse (attack + fall), never a smooth breath
    lvl = 0.30 + (0.35 * c.rms + 0.65 * c.harm) * m["wash"] * (0.85 + 0.45 * c.pulse)
    rad_fall = 1.0 - 0.2 * p.r01
    sat = m["sat"] * (0.7 + 0.3 * (1 - c.centroid))
    if pal.white_core:
        frame = hsv(hue, np.clip((1 - lvl * rad_fall) * 1.1, 0, sat), lvl * rad_fall)
    else:
        frame = hsv(hue, min(sat, pal.sat_max), lvl * rad_fall)

    # 1 bass ring
    if m["ring"] > 0:
        edge = c.low * 1.05
        band = np.exp(-((p.r01 - edge) / 0.09) ** 2)
        frame = lighten(frame, pal.color(band * c.low * m["ring"], k=hue_k + 1, variation=c.variation, sat=0.6))

    # 2 percussive hits -> one sector, advancing per beat
    if m["hits"] > 0 and c.hit > 0.03:
        n_sec = 4 if p.n < 200 else 6
        sec_i = (c.beat_index + sector_off + (p.idx if div > 0.5 else 0)) % n_sec
        ang = (p.ang + math.pi) / (2 * math.pi) * n_sec
        sel = (ang.astype(int) % n_sec) == sec_i
        v = np.zeros(p.n); v[sel] = c.hit * m["hits"] * (0.5 + 0.5 * p.r01[sel])
        frame = lighten(frame, pal.color(v, k=hue_k + 2, variation=c.variation, sat=0.5))

    # 3 sparkle (stateful grains, see Renderer.spark)
    if m["sparkle"] > 0:
        g = c.R.spark[p.id]
        frame = lighten(frame, pal.color(g * m["sparkle"], k=hue_k, variation=c.variation, sat=0.35))

    # 3b shimmer
    if m["shimmer"] > 0:
        ph = (p.i * 0.618 + t * 0.13) % 1.0
        g = np.exp(-((ph - 0.5) / 0.035) ** 2) * m["shimmer"] * 0.9
        frame = lighten(frame, pal.color(g, k=hue_k + 1, variation=c.variation, sat=0.3))

    # 4 melody glow along the wire
    if m["melody"] > 0:
        pos = ((c.centroid * 0.6 + (t * 0.11) % 1.0) % 1.0) * p.n
        d = np.abs(((p.i - pos + p.n / 2) % p.n) - p.n / 2)
        v = np.exp(-(d / max(4.0, p.n / 10)) ** 2) * c.mid * m["melody"]
        frame = lighten(frame, pal.color(v, k=hue_k + 2, variation=c.variation, sat=0.5))
    return frame


def stack_all(c, m, hue_spread=True):
    out = {}
    for p in c.props:
        out[p.id] = stack(c, p, m, hue_k=(p.idx % 2 if hue_spread else 0),
                          time_off=0.9 * math.sin(p.idx * 2.1), sector_off=p.idx)
    return out


def transition_wipe(c, frames, dur=0.55):
    """Section boundary: a bright wipe bottom->top on every prop (from 47)."""
    if c.t_sec > dur or c.sec["index"] == 0:
        return frames
    pr = c.t_sec / dur
    for p in c.props:
        v = np.exp(-((p.y01 - pr) / 0.16) ** 2) * (1 - pr) * 1.1
        frames[p.id] = lighten(frames[p.id], c.palette.color(v, k=1, variation=c.variation, sat=0.2))
    return frames


# ------------------------------------------------------------- the looks
@look("pulse")
def look_pulse(c):
    return transition_wipe(c, stack_all(c, mix_for(c)))


@look("change-up")
def look_changeup(c):
    m = mix_for(c)
    m["melody"] = min(1.0, m["melody"] + 0.3); m["hits"] = min(1.0, m["hits"] + 0.2)
    return transition_wipe(c, stack_all(c, m, hue_spread=True))


@look("starfield")
def look_starfield(c):
    m = mix_for(c); m.update(wash=0.12, ring=0.0, hits=0.0, melody=0.0, shimmer=0.9, sparkle=1.0)
    out = stack_all(c, m)
    for p in c.props:                                   # whole props fading in and out
        whole = 0.5 + 0.5 * math.sin(2 * math.pi * (c.t / (7 + p.idx % 3) + p.idx * 0.37))
        out[p.id] = lighten(out[p.id], c.palette.color(np.full(p.n, 0.2 * whole ** 3), k=1, variation=c.variation))
    return out


@look("build")
def look_build(c):
    if c.next_look == "drop":
        return look_build_dark(c)
    m = mix_for(c)
    k = c.progress
    m.update(wash=0.4 + 0.3 * k, ring=1.0, hits=0.5 + 0.5 * k, sparkle=0.5 + 0.5 * k, melody=0.6)
    out = stack_all(c, m)
    bar_s = 60.0 / c.bpm * c.bar_beats
    for p in c.props:
        gs = gust(c, p, period=bar_s / (1 + int(2 * k)), width_in=60)
        out[p.id] = lighten(out[p.id], c.palette.color(gs * (0.5 + 0.5 * k), k=1, variation=c.variation, sat=0.35))
        if k > 0.75:                                    # last quarter: stutter with the felt pulse
            out[p.id] = out[p.id] * (0.3 + 0.7 * (c.pulse_phase < 0.5))
    return transition_wipe(c, out)


def look_build_dark(c):
    """The build straight into a drop: DARK, so the drop has something to
    explode out of. Props flash one at a time on the hits, faster and with
    more of them lit as the drop nears; the last half-second is black."""
    pal = c.palette
    k = c.progress
    out = {}
    for p in c.props:
        fl = c.prop_flash[p.id]
        trail = 0.05 * k                                     # a faint growing ember
        v = trail + 0.95 * fl
        if k > 0.82:                                         # final beat: black
            v = 0.0
        col = pal.color(np.full(p.n, v), k=p.idx % 2, variation=c.variation)
        if fl > 0.7:
            col = lighten(col, np.full((p.n, 3), (fl - 0.7) / 0.3))
        out[p.id] = col
    return out


@look("hold-breath")
def look_hold(c):
    """Everything drops to black at once; then each little bell hit lights
    ONE prop -- full, in the palette's brightest colour -- which falls away
    before the next. The props take turns. Contrast is the point."""
    pal = c.palette
    out = {}
    for p in c.props:
        fl = c.prop_flash[p.id]
        v = 0.03 + 0.97 * fl
        col = pal.color(np.full(p.n, v), k=0, variation=c.variation)
        if fl > 0.7:                                        # white flash on the attack
            col = lighten(col, np.full((p.n, 3), (fl - 0.7) / 0.3))
        out[p.id] = col
    return out


@look("drop")
def look_drop(c):
    """White shockwave from every centre, then the full stack at max with
    bar-locked gusts and lightning on loud downbeats."""
    pal = c.palette
    if c.t_sec < 1.2:
        out = {}
        for p in c.props:
            rad = c.t_sec / 0.25
            shock = (p.r01 <= rad).astype(float)
            white = shock * max(0.0, 1 - max(0.0, c.t_sec - 0.25) / 0.95)
            body = pal.color(shock * (0.85 + 0.15 * c.low), k=p.idx, variation=c.variation)
            out[p.id] = lighten(body, np.full((p.n, 3), 1.0) * white[:, None])
        return out
    m = dict(wash=1.0, ring=1.0, hits=1.0, sparkle=1.0, melody=0.8, shimmer=0.3, sat=0.95)
    out = stack_all(c, m)
    bar_s = 60.0 / c.bpm * c.bar_beats
    for p in c.props:
        gs = gust(c, p, period=bar_s, width_in=54, direction=1 if (int(c.t_song / bar_s) % 2 == 0) else -1)
        tex = 0.8 + 0.4 * turb(c, p, 12, 3.0)
        out[p.id] = lighten(out[p.id] * tex[:, None], pal.color(gs, k=1, variation=c.variation, sat=0.35))
        if c.bar > 0.9 and c.energy > 0.6:
            out[p.id] = lighten(out[p.id], np.full((p.n, 3), 0.95 * c.bar))
    return out


@look("wave")
def look_wave(c):
    m = mix_for(c); m["hits"] *= 0.5
    out = stack_all(c, m)
    for p in c.props:
        w1 = gust(c, p, period=4.0, width_in=60 + 60 * c.low)
        w2 = gust(c, p, period=5.5, width_in=50, direction=-1, phase=0.4)
        out[p.id] = lighten(out[p.id], c.palette.color(w1 * 0.9, k=1, variation=c.variation),
                            c.palette.color(w2 * 0.7, k=2, variation=c.variation))
    return transition_wipe(c, out)


@look("conversation")
def look_conversation(c):
    """Two halves of the row trade bars: the active half runs the stack hot,
    the other half holds a dim wash -- then both come together on the phrase."""
    m = mix_for(c)
    order = sorted(c.props, key=lambda q: q.cx)
    left = {q.id for k, q in enumerate(order) if k * 2 < len(order)}
    bar_s = 60.0 / c.bpm * c.bar_beats
    active_left = int(c.t_song / bar_s) % 2 == 0
    out = {}
    for p in c.props:
        on = (p.id in left) == active_left or c.unison > 0.8
        mm = dict(m) if on else dict(m, wash=0.35, ring=0.2, hits=0.0, sparkle=0.2, melody=0.0)
        out[p.id] = stack(c, p, mm, hue_k=0 if on else 1, time_off=0.0, sector_off=p.idx)
    return transition_wipe(c, out)


@look("feature")
def look_feature(c):
    """One prop carries the melody hot; the others answer with the ring only."""
    m = mix_for(c)
    out = {}
    for p in c.props:
        if p is c.feature:
            out[p.id] = stack(c, p, dict(m, melody=1.0, sparkle=1.0, wash=0.7), hue_k=0)
        else:
            out[p.id] = stack(c, p, dict(m, hits=0.3, melody=0.0, sparkle=0.3, wash=0.45), hue_k=1)
    return transition_wipe(c, out)


@look("chase")
def look_chase(c):
    m = mix_for(c); m["melody"] = 1.0
    out = stack_all(c, m)
    for p in c.props:
        tail = max(8, p.n // 5)
        head = c.pulse_phase * (p.n + tail)
        d = head - p.i
        v = np.clip(1 - d / tail, 0, 1) ** 1.2; v[d < 0] = 0
        out[p.id] = lighten(out[p.id], c.palette.color(v, k=1, variation=c.variation, sat=0.4))
    return transition_wipe(c, out)


@look("ornaments")
def look_ornaments(c):
    pal = c.palette
    m = mix_for(c); m.update(hits=0.3, sparkle=0.4)
    out = stack_all(c, m, hue_spread=False)
    for p in c.props:
        r = np.random.default_rng(p.idx * 17 + c.variation)
        acc = pal.accent_colors()
        n_acc = max(3, int(p.n * max(0.05, pal.accent_density or 0.08)))
        idx = r.choice(p.n, n_acc, replace=False)
        fr = out[p.id]
        for k, j in enumerate(idx):
            h = acc[k % len(acc)]
            tw = 0.6 + 0.4 * math.sin(2 * math.pi * (c.t / 1.7 + k * 0.31))
            fr[j] = np.array([1, 1, 1]) * tw if h is None else hsv(h, 0.95, tw)
    return out


@look("shimmer")
def look_shimmer(c):
    m = mix_for(c); m.update(hits=0.0, melody=0.0, ring=0.2, shimmer=1.0, wash=0.4)
    return stack_all(c, m)


@look("fade")
def look_fade(c):
    lvl = 1.0 * (1 - c.progress) + 0.25 * c.progress
    m = mix_for(c); m.update(hits=0.3 * (1 - c.progress), melody=0.0)
    out = stack_all(c, m)
    return {k: v * lvl for k, v in out.items()}


# ----------------------------------------------------------------- renderer
class ShowRenderer:
    def __init__(self, show_yaml, layout_path, songs_json=None, analysis=None, cache=True):
        self.spec = yaml.safe_load(open(show_yaml, encoding="utf-8"))
        self.layout = Layout.load(layout_path)
        self.props = [PropGeom(pl, i) for i, pl in enumerate(self.layout.props)]
        self.by_id = {p.id: p for p in self.props}
        xs = np.concatenate([p.wx for p in self.props])
        self.world = (float(xs.min()), float(xs.max()))
        C = np.array([[p.cx, p.cy, p.cz] for p in self.props])
        self.dist = np.linalg.norm(C[:, None] - C[None, :], axis=2)
        self.palettes = {k: Palette(k, v or {}) for k, v in (self.spec.get("palettes") or {}).items()}
        self.defaults = self.spec.get("defaults", {})
        self.transition = float(self.defaults.get("transition_s", 1.5))
        audio = os.path.join(ROOT, self.spec["audio"])
        self.a = analysis or self._analysis(audio, cache)
        self.n_frames = self.a.n_frames
        self.duration = self.a.duration
        self._songs(songs_json)
        self._sections()

    # ---- music
    def _analysis(self, audio, cache):
        cpath = os.path.join(ROOT, "out", "features.npz")
        if cache and os.path.exists(cpath) and os.path.getmtime(cpath) > os.path.getmtime(audio):
            d = np.load(cpath)
            a = type("A", (), {})()
            for k in d.files:
                setattr(a, k, d[k])
            a.n_frames = int(a.n_frames); a.duration = float(a.duration)
            return a
        A = music.analyse(audio)
        keep = {k: getattr(A, k) for k in ("rms", "low", "mid", "high", "centroid", "harm", "perc",
                                             "hit", "hit_high", "beat_env", "downbeat_env", "chroma_f")}
        keep["n_frames"] = A.n_frames; keep["duration"] = A.duration
        os.makedirs(os.path.dirname(cpath), exist_ok=True)
        np.savez(cpath, **keep)
        return A

    def _songs(self, songs_json):
        sj = None
        p = songs_json or os.path.join(ROOT, self.spec.get("songs_analysis", "out/songs.json"))
        if os.path.exists(p):
            sj = {s["index"] - 1: s for s in json.load(open(p))["songs"]}
        self.songs = []
        for k, s in enumerate(self.spec["songs"]):
            t0, t1 = parse_t(s["from"]), parse_t(s["to"])
            ref = None
            m = re.match(r"\s*([\d.]+)", str(s.get("tempo_hint", "")))
            if m:
                ref = float(m.group(1))
            beats = np.array(sj[k]["beats"]) if sj and k in sj else np.array([])
            det = sj[k]["bpm"] if sj and k in sj else (ref or 120.0)
            bpm = ref or det
            if len(beats) > 1 and ref and abs(ref / det - 2) < 0.15:   # detected half-time: subdivide
                mids = (beats[:-1] + beats[1:]) / 2
                beats = np.sort(np.concatenate([beats, mids]))
            if len(beats) < 2:                                            # synthesize a grid
                beats = np.arange(t0, t1, 60.0 / bpm)
            self.songs.append({"index": k, "name": s["name"], "from": t0, "to": t1, "bpm": bpm,
                               "beats": beats, "spec": s, "palette": s.get("palette"),
                               "theme": s.get("theme"), "pulse_beats": int(s.get("pulse_beats", 1)),
                               "bar_beats": int(s.get("bar_beats", 4))})
        # slow energy: rms smoothed over ~1 s and normalised per song (5th..95th pct)
        from scipy.ndimage import uniform_filter1d
        sm = uniform_filter1d(self.a.rms, int(FPS * 1.0))
        self.energy = np.zeros(self.n_frames)
        for s in self.songs:
            i0, i1 = int(s["from"] * FPS), min(self.n_frames, max(int(s["from"] * FPS) + 1, int(s["to"] * FPS)))
            seg = sm[i0:i1]
            lo, hi = np.percentile(seg, 5), np.percentile(seg, 95)
            self.energy[i0:i1] = np.clip((seg - lo) / max(1e-6, hi - lo), 0, 1)
        # per-frame beat / bar envelopes from the corrected grids
        self.beat_env = np.zeros(self.n_frames); self.bar_env = np.zeros(self.n_frames)
        for s in self.songs:
            for j, b in enumerate(s["beats"]):
                i = int(round(b * FPS))
                if 0 <= i < self.n_frames:
                    self.beat_env[i] = 1.0
                    if j % s["bar_beats"] == 0:
                        self.bar_env[i] = 1.0
        for env, decay in ((self.beat_env, 0.22), (self.bar_env, 0.4)):
            k = math.exp(-1.0 / (decay * FPS))
            for i in range(1, self.n_frames):
                env[i] = max(env[i], env[i - 1] * k)

    def _sections(self):
        self.sections = []
        idx = 0
        for s in self.songs:
            secs = s["spec"].get("sections") or [{"at": s["from"], "look": "pulse"}]
            times = [parse_t(x["at"]) for x in secs]
            variation = 0
            for k, x in enumerate(secs):
                t0 = times[k]
                t1 = times[k + 1] if k + 1 < len(times) else s["to"]
                lk = x.get("look", "pulse")
                if lk not in LOOKS:
                    raise ValueError(f"unknown look '{lk}' at {x.get('at')} -- add it to show.LOOKS")
                if lk == "change-up":
                    variation += 1
                inten = x.get("intensity")
                self.sections.append({"index": idx, "song": s, "t0": t0, "t1": t1, "look": lk,
                                      "intensity": None if inten is None else float(inten) / 10.0,
                                      "palette": x.get("palette"), "note": x.get("note", ""),
                                      "variation": variation, "feature_k": k})
                idx += 1
        self.sections.sort(key=lambda z: z["t0"])

    # ---- lookups
    def section_at(self, t):
        cur = None
        for s in self.sections:
            if s["t0"] <= t:
                cur = s
        return cur or self.sections[0]

    def palette_for(self, sec, song):
        name = sec.get("palette") or song.get("palette")
        if isinstance(name, dict):          # per-group dict: take the first (bench mixes groups)
            name = next(iter(name.values()))
        if name in ("monochrome", "limited", "full", None):
            base = song.get("palette") if isinstance(song.get("palette"), str) else "frost"
            pal = self.palettes.get(base) or Palette(base, {})
            if name == "monochrome":
                pal = Palette(base + "-mono", {"hues": pal.hues[:1], "sat_max": pal.sat_max, "white_core": pal.white_core})
            return pal
        return self.palettes.get(name) or Palette(name, {})

    def intensity_at(self, t, sec, song):
        if sec["intensity"] is not None:
            return sec["intensity"]
        f = min(self.n_frames - 1, int(t * FPS))
        i0, i1 = int(song["from"] * FPS), max(int(song["from"] * FPS) + 1, int(song["to"] * FPS))
        seg = self.a.rms[i0:i1]
        lo, hi = np.percentile(seg, 5), np.percentile(seg, 95)
        return float(np.clip((self.a.rms[f] - lo) / max(1e-6, hi - lo), 0, 1)) * 0.7 + 0.2

    def beat_index_at(self, t, song):
        b = song["beats"]
        return int(np.clip(np.searchsorted(b, t) - 1, 0, max(0, len(b) - 1)))

    def pulse_phase_at(self, t, song):
        b = song["beats"]; pb = song.get("pulse_beats", 1)
        if len(b) < 2:
            return (t * song["bpm"] / 60 / pb) % 1.0
        i = int(np.clip(np.searchsorted(b, t) - 1, 0, len(b) - 2))
        return ((i % pb) + self.beat_phase_at(t, song)) / pb

    def phrase_phase_at(self, t, song):
        b = song["beats"]; bb = song.get("bar_beats", 4) * 4
        if len(b) < 2:
            return (t * song["bpm"] / 60 / bb) % 1.0
        i = int(np.clip(np.searchsorted(b, t) - 1, 0, len(b) - 2))
        return ((i % bb) + self.beat_phase_at(t, song)) / bb

    def beat_phase_at(self, t, song):
        b = song["beats"]
        if len(b) < 2:
            return (t * song["bpm"] / 60) % 1.0
        i = np.searchsorted(b, t) - 1
        i = int(np.clip(i, 0, len(b) - 2))
        return float(np.clip((t - b[i]) / max(1e-6, b[i + 1] - b[i]), 0, 1))

    def bar_phase_at(self, t, song):
        b = song["beats"]
        if len(b) < 5:
            return (t * song["bpm"] / 240) % 1.0
        i = int(np.clip(np.searchsorted(b, t) - 1, 0, len(b) - 2))
        return ((i % 4) + self.beat_phase_at(t, song)) / 4

    def feature_for(self, sec, song):
        # rotate the feature prop per section; prefer the biggest props
        order = sorted(self.props, key=lambda p: -p.n)
        return order[sec["feature_k"] % len(order)]

    # ---- rendering
    def frame(self, t):
        sec = self.section_at(t)
        cur = LOOKS[sec["look"]](Ctx(self, t, sec, sec["song"]))
        # NO CROSSFADES. A new section lands HARD: an over-bright attack on
        # its first frames that falls back to the look's normal level. The
        # music changes on a beat; the lights should hit with it.
        dt = t - sec["t0"]
        if sec["index"] > 0 and dt < 0.6 and sec["look"] not in ("hold-breath", "fade"):
            gain = 1.0 + 0.9 * math.exp(-dt / 0.18)
            cur = {k: v * gain for k, v in cur.items()}
        return {k: np.clip(v, 0, 1) for k, v in cur.items()}

    def _advance_spark(self, t):
        """Stateful sparkle grains: born on high-band onsets (and some strong
        hits), decaying over ~0.3 s. Called once per rendered frame."""
        if not hasattr(self, "spark"):
            self.spark = {p.id: np.zeros(p.n) for p in self.props}
            self._spark_rng = np.random.default_rng(4)
        f = min(self.n_frames - 1, int(round(t * FPS)))
        k = math.exp(-1.0 / (0.30 * FPS))
        hit, hh = self.a.hit[f], self.a.hit_high[f]
        # one-prop-per-onset flashes (the "bell hits" mechanic): on a rising
        # onset the next prop in a shuffled order lights fully and decays
        if not hasattr(self, "prop_flash"):
            self.prop_flash = {p.id: 0.0 for p in self.props}; self._flash_prev = 0.0
            self._flash_order = list(np.random.default_rng(11).permutation(len(self.props))); self._flash_i = 0
        kf = math.exp(-1.0 / (0.45 * FPS))
        for pid in self.prop_flash:
            self.prop_flash[pid] *= kf
        onset = max(hh, hit * 0.8)
        if onset > 0.5 and self._flash_prev < 0.35:
            pid = self.props[self._flash_order[self._flash_i % len(self.props)]].id
            self._flash_i += 1
            self.prop_flash[pid] = 1.0
        self._flash_prev = onset
        for p in self.props:
            g = self.spark[p.id]; g *= k
            if hit > 0.55 and self._spark_rng.random() < 0.35:
                g[self._spark_rng.choice(p.n, size=min(3, p.n), replace=False)] = 0.85
            if hh > 0.25:
                kk = max(2, int((4 + 11 * hh) * p.n / 72))
                g[self._spark_rng.choice(p.n, size=min(kk, p.n), replace=False)] = 1.0

    def render(self, t0=0.0, t1=None, fps=FPS, progress=None):
        t1 = self.duration if t1 is None else min(t1, self.duration)
        n = int(round((t1 - t0) * fps))
        out = []
        self.spark = {p.id: np.zeros(p.n) for p in self.props}
        self._spark_rng = np.random.default_rng(4)
        self.prop_flash = {p.id: 0.0 for p in self.props}; self._flash_prev = 0.0
        self._flash_order = list(np.random.default_rng(11).permutation(len(self.props))); self._flash_i = 0
        for f in range(n):
            self._advance_spark(t0 + f / fps)
            out.append(self.frame(t0 + f / fps))
            if progress and f % 600 == 0:
                progress(f, n)
        return out

    def brightness_report(self, frames, t0=0.0, fps=FPS):
        """-> list of (song name, share of frames >= target, mean level)."""
        bcfg = self.defaults.get("brightness", {})
        target = float(bcfg.get("target_level", 0.6))
        exempt = set(bcfg.get("dark_ok_looks", []))
        rows = []
        for s in self.songs:
            i0 = int(round((s["from"] - t0) * fps)); i1 = int(round((s["to"] - t0) * fps))
            i0, i1 = max(0, i0), min(len(frames), i1)
            if i1 <= i0:
                continue
            lv, lv_all = [], []
            for f in range(i0, i1):
                t = t0 + f / fps
                m = float(np.mean([fr.max(1).mean() for fr in frames[f].values()]))
                lv_all.append(m)
                if self.section_at(t)["look"] not in exempt:
                    lv.append(m)
            rows.append((s["name"], 100 * np.mean(np.array(lv) >= target) if lv else float("nan"),
                         float(np.mean(lv_all)), 100 * np.mean(np.array(lv_all) >= target)))
        return rows

    def write_cards(self, frames, out_dir, scene=1, slug="show", fps=FPS):
        """frames -> one .rgb per controller + manifest. Identical frame counts.
        Files are named Sc-01-NN-<slug>.rgb: NN is the scene number the DMX
        select refers to, the slug is free text the controller ignores."""
        from .formats.rgbfile import Show
        import hashlib
        rigs = self.layout.controller_rigs()
        os.makedirs(out_dir, exist_ok=True)
        man = OrderedDict(fps=fps, frames=len(frames), scene=scene, cards=OrderedDict())
        fname = f"Sc-01-{scene:02d}-{slug}.rgb"
        for cid, rig in rigs.items():
            sh = Show(rig.channels())
            offs = np.cumsum([0] + rig.channels()) * 3
            for fr in frames:
                buf = np.zeros(sh.frame_size, np.uint8)
                for k, pr in enumerate(rig.ports):
                    if pr.placement is None:
                        continue
                    b = to_bytes(fr[pr.placement.id]).reshape(-1)
                    buf[offs[k]:offs[k] + len(b)] = b
                sh.frames.append(buf.tobytes())
            d = os.path.join(out_dir, cid); os.makedirs(d, exist_ok=True)
            path = os.path.join(d, fname); sh.save(path)
            data = open(path, "rb").read()
            man["cards"][cid] = {"file": f"{cid}/{fname}", "bytes": len(data),
                                 "md5": hashlib.md5(data).hexdigest(), "channels": rig.channels(),
                                 "ports": [pr.placement.id if pr.placement else None for pr in rig.ports]}
        json.dump(man, open(os.path.join(out_dir, "manifest.json"), "w"), indent=1)
        return man
