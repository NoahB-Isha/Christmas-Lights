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
        self.feature = R.feature_for(sec, song)           # PropGeom
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


def _wave_x(c, p, speed_in_s=60.0, width_in=40.0, phase=0.0):
    x0, x1 = c.world
    span = max(1.0, x1 - x0)
    head = x0 - width_in + ((c.t * speed_in_s + phase) % (span + 2 * width_in))
    return np.exp(-((p.wx - head) / (width_in / 2)) ** 2)


@look("starfield")
def look_starfield(c):
    pal = c.palette
    def f(p):
        base = pal.color(np.full(p.n, 0.10 + 0.05 * c.rms), k=0, variation=c.variation)
        g = c.grains(p, 4 + 12 * c.hit_high + 6 * c.intensity, 0.9)
        whole = 0.5 + 0.5 * math.sin(2 * math.pi * (c.t / (7 + p.idx % 3) + p.idx * 0.37))
        wash = pal.color(np.full(p.n, 0.18 * whole ** 3), k=1, variation=c.variation)
        return lighten(base, wash, pal.color(g, k=0, variation=c.variation, sat=0.4))
    return c.per_prop(f)


@look("pulse")
def look_pulse(c):
    pal = c.palette
    lvl = 0.55 + 0.30 * c.intensity
    def f(p):
        breath = lvl + 0.25 * c.beat * (0.5 + 0.5 * c.intensity)
        col = pal.color(np.full(p.n, min(1.0, breath)), k=p.idx, variation=c.variation)
        return lighten(col, pal.color(c.shimmer(p), k=p.idx + 1, variation=c.variation, sat=0.3))
    return c.per_prop(f)


@look("change-up")
def look_changeup(c):
    return look_pulse(c)


@look("build")
def look_build(c):
    pal = c.palette
    lvl = 0.45 + 0.5 * c.progress
    def f(p):
        col = pal.color(np.full(p.n, lvl * (0.85 + 0.15 * c.beat)), k=p.idx, variation=c.variation)
        g = c.grains(p, 2 + 30 * c.progress ** 2, 0.5)
        return lighten(col, pal.color(g, k=p.idx + 2, variation=c.variation, sat=0.2))
    return c.per_prop(f)


@look("hold-breath")
def look_hold(c):
    pal = c.palette
    def f(p):
        if p is c.feature:
            return pal.color(np.full(p.n, 0.75 + 0.2 * c.rms), k=0, variation=c.variation)
        return pal.color(np.full(p.n, 0.14), k=1, variation=c.variation)
    return c.per_prop(f)


@look("drop")
def look_drop(c):
    pal = c.palette
    def f(p):
        base = pal.color(np.full(p.n, 0.6 + 0.3 * c.low), k=p.idx, variation=c.variation)
        wave = _wave_x(c, p, speed_in_s=120 + 80 * c.intensity, width_in=48) * (0.6 + 0.4 * c.bar)
        wv = pal.color(wave, k=p.idx + 1, variation=c.variation, sat=0.5)
        g = c.grains(p, 20 * c.hit + 6, 0.35)
        ring = np.exp(-((p.r01 - (c.beat_phase)) / 0.12) ** 2) * c.beat
        return lighten(base, wv, pal.color(g, k=p.idx + 2, variation=c.variation, sat=0.2),
                       pal.color(ring, k=p.idx + 3, variation=c.variation, sat=0.6))
    return c.per_prop(f)


@look("wave")
def look_wave(c):
    pal = c.palette
    def f(p):
        base = pal.color(np.full(p.n, 0.45 + 0.15 * c.intensity), k=p.idx, variation=c.variation)
        w1 = _wave_x(c, p, speed_in_s=40, width_in=60 + 60 * c.low)
        w2 = _wave_x(c, p, speed_in_s=-28, width_in=50, phase=137)
        return lighten(base, pal.color(w1 * 0.95, k=1, variation=c.variation),
                       pal.color(w2 * 0.8, k=2, variation=c.variation))
    return c.per_prop(f)


@look("conversation")
def look_conversation(c):
    pal = c.palette
    # split props into two halves by x; the active half swaps every bar
    order = sorted(c.props, key=lambda q: q.cx)
    half = {q.id: (k * 2 < len(order)) for k, q in enumerate(order)}
    active_left = (int(c.t_song / max(0.5, 60.0 / c.bpm * 4)) % 2) == 0
    def f(p):
        on = half[p.id] == active_left
        lvl = (0.75 + 0.2 * c.rms) if on else 0.35
        col = pal.color(np.full(p.n, lvl), k=(0 if on else 1), variation=c.variation)
        if on:
            col = lighten(col, pal.color(c.grains(p, 8 * c.hit_high + 3, 0.4), k=2, variation=c.variation, sat=0.3))
        return col
    return c.per_prop(f)


@look("feature")
def look_feature(c):
    pal = c.palette
    fe = c.feature
    def f(p):
        if p is fe:
            glow = 0.7 + 0.3 * c.rms
            trav = np.exp(-(((p.i / p.n) - ((c.t_sec * 0.6) % 1.0)) / 0.08) ** 2)
            col = pal.color(np.full(p.n, glow), k=0, variation=c.variation)
            return lighten(col, pal.color(trav, k=1, variation=c.variation, sat=0.3),
                           pal.color(c.grains(p, 6 + 20 * c.hit_high, 0.3), k=2, variation=c.variation, sat=0.2))
        d = c.dist[p.idx, fe.idx]
        ripple = np.exp(-((d - c.beat_phase * 240) / 30.0) ** 2) * c.beat * 0.5
        base = pal.color(np.full(p.n, 0.45), k=p.idx + 1, variation=c.variation)
        return lighten(base, pal.color(np.full(p.n, ripple), k=1, variation=c.variation))
    return c.per_prop(f)


@look("chase")
def look_chase(c):
    pal = c.palette
    def f(p):
        tail = max(8, p.n // 5)
        head = ((c.t_song * c.bpm / 60.0) % 4) / 4 * (p.n + tail)
        d = head - p.i
        v = np.clip(1 - d / tail, 0, 1) ** 1.2; v[d < 0] = 0
        ring = np.exp(-((p.r01 - c.beat_phase) / 0.1) ** 2) * 0.7
        base = pal.color(np.full(p.n, 0.55), k=p.idx, variation=c.variation)
        return lighten(base, pal.color(v, k=p.idx + 1, variation=c.variation, sat=0.4),
                       pal.color(ring, k=p.idx + 2, variation=c.variation))
    return c.per_prop(f)


@look("ornaments")
def look_ornaments(c):
    pal = c.palette
    def f(p):
        base = pal.color(np.full(p.n, 0.6 + 0.1 * c.rms), k=0, variation=c.variation)
        r = np.random.default_rng(p.idx * 17 + c.variation)
        acc = pal.accent_colors()
        n_acc = max(3, int(p.n * max(0.05, pal.accent_density or 0.08)))
        idx = r.choice(p.n, n_acc, replace=False)
        out = base.copy()
        for k, j in enumerate(idx):
            h = acc[k % len(acc)]
            tw = 0.6 + 0.4 * math.sin(2 * math.pi * (c.t / 1.7 + k * 0.31))
            out[j] = np.array([1, 1, 1]) * tw if h is None else hsv(h, 0.95, tw)
        return out
    return c.per_prop(f)


@look("shimmer")
def look_shimmer(c):
    pal = c.palette
    def f(p):
        base = pal.color(np.full(p.n, 0.45), k=0, variation=c.variation)
        return lighten(base, pal.color(c.shimmer(p, 0.8), k=1, variation=c.variation, sat=0.3))
    return c.per_prop(f)


@look("fade")
def look_fade(c):
    pal = c.palette
    lvl = 0.7 * (1 - c.progress) + 0.18 * c.progress
    def f(p):
        return lighten(pal.color(np.full(p.n, lvl), k=p.idx, variation=c.variation),
                       pal.color(c.shimmer(p, 0.5 * lvl), k=1, variation=c.variation, sat=0.3))
    return c.per_prop(f)


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
                                             "hit", "hit_high", "beat_env", "downbeat_env")}
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
                               "theme": s.get("theme")})
        # per-frame beat / bar envelopes from the corrected grids
        self.beat_env = np.zeros(self.n_frames); self.bar_env = np.zeros(self.n_frames)
        for s in self.songs:
            for j, b in enumerate(s["beats"]):
                i = int(round(b * FPS))
                if 0 <= i < self.n_frames:
                    self.beat_env[i] = 1.0
                    if j % 4 == 0:
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
        dt = t - sec["t0"]
        if dt < self.transition and sec["index"] > 0:
            prev = self.sections[sec["index"] - 1]
            pv = LOOKS[prev["look"]](Ctx(self, t, prev, prev["song"]))
            a = dt / self.transition
            cur = {k: pv[k] * (1 - a) + cur[k] * a for k in cur}
        return {k: np.clip(v, 0, 1) for k, v in cur.items()}

    def render(self, t0=0.0, t1=None, fps=FPS, progress=None):
        t1 = self.duration if t1 is None else min(t1, self.duration)
        n = int(round((t1 - t0) * fps))
        out = []
        for f in range(n):
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
