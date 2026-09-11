#!/usr/bin/env python3
"""
lamps.py -- LAMP MODELS: make LED pixels behave like the light sources they
are imitating. Applied per frame AFTER the look, stateful per pixel.

    lamp: led            what the LEDs do by themselves (no model)
    lamp: incandescent   C7/C9 filament bulbs (1950s-60s Christmas strings)
    lamp: neon           gas-discharge tubes (Times Square signs)
    lamp: twinkle        incandescent + a fraction of bimetal "twinkle" bulbs

Physics we mimic (see docs/09):

INCANDESCENT
  * thermal inertia: the filament heats in tens of ms and cools over
    100-300 ms -> soft attack (tau ~60 ms), longer afterglow (tau ~180 ms).
    A blinking C9 never snaps; it breathes at the edges.
  * amber shift: a dimming filament goes ORANGE, not grey. We slide the
    colour toward amber as the level falls -- strongly for whites/pastels,
    barely for saturated dyed-glass colours (a red bulb stays red).
  * dyed-glass palette: red, green, blue, orange, gold, white -- saturated.

NEON
  * instant on / instant off: no lag at all.
  * cold-start stutter: for ~300 ms after a tube ignites it drops out for
    a frame or two, at random, then holds solid.
  * a tube is UNIFORM along its length: every pixel of a segment (a prop
    region, or the whole prop) shows the segment's colour at the segment's
    level -- a line of light, not points.

TWINKLE
  * incandescent, plus a fixed random subset of bulbs that each blink on
    their own irregular 0.8-2.2 s cycle (bimetal strip), unsynchronised.

Section params:  lamp, twinkle_frac (default 0.18), tube_uniform (default
true for neon), amber (default 1.0 = full amber shift), tau_on / tau_off.
"""

import math

import numpy as np

AMBER = np.array([1.0, 0.42, 0.06])


def _lin(v):
    return np.clip(v, 0, 1) ** 2.2


def _per(v):
    return np.clip(v, 0, 1) ** (1 / 2.2)


class LampBank:
    def __init__(self, props, fps):
        self.props = props
        self.fps = fps
        self.dt = 1.0 / fps
        self.L = {p.id: np.zeros(p.n) for p in props}              # lagged linear level per pixel
        self.dir = {p.id: np.ones((p.n, 3)) for p in props}        # last chroma direction
        self.tubes = {p.id: self._tubes(p) for p in props}
        self.on_since = {p.id: np.full(len(self.tubes[p.id]), -1e9) for p in props}
        self.off_since = {p.id: np.full(len(self.tubes[p.id]), -1e9) for p in props}   # a warm tube re-ignites without stutter
        self.rng = np.random.default_rng(97)
        # twinkle bulbs: fixed subset, own period and phase
        self.tw_period = {p.id: self.rng.uniform(0.8, 2.2, p.n) for p in props}
        self.tw_phase = {p.id: self.rng.uniform(0, 1, p.n) for p in props}
        self.tw_rank = {p.id: self.rng.permutation(p.n) / p.n for p in props}   # 0..1, pick < frac

    @staticmethod
    def _tubes(p):
        """segments that behave as one neon tube: regions if painted, else the whole prop"""
        if p.region_names:
            return [p.regions[k] for k in p.regions]              # includes 'rest'
        return [np.ones(p.n, bool)]

    # ---------------------------------------------------------------- apply
    def apply(self, frames, t, params):
        model = (params or {}).get("lamp", "led")
        if model == "led":
            # still track state so a later switch to incandescent starts sane
            for p in self.props:
                fr = frames[p.id]; lvl = _lin(fr.max(1))
                self.L[p.id] = lvl
                nz = lvl > 1e-4
                self.dir[p.id][nz] = fr[nz] / fr[nz].max(1, keepdims=True)
            return frames
        out = {}
        for p in self.props:
            fr = frames[p.id]
            if model in ("incandescent", "twinkle"):
                out[p.id] = self._incandescent(p, fr, t, params, twinkle=(model == "twinkle"))
            elif model == "neon":
                out[p.id] = self._neon(p, fr, t, params)
            else:
                out[p.id] = fr
        return out

    # ---------------------------------------------------------- filament
    def _incandescent(self, p, fr, t, params, twinkle=False):
        tau_on = float(params.get("tau_on", 0.06)); tau_off = float(params.get("tau_off", 0.18))
        amber = float(params.get("amber", 1.0))
        target = _lin(fr.max(1))                                     # linear light the look asks for
        if twinkle:
            frac = float(params.get("twinkle_frac", 0.18))
            tw = self.tw_rank[p.id] < frac
            ph = ((t / self.tw_period[p.id]) + self.tw_phase[p.id]) % 1.0
            target = np.where(tw & (ph > 0.5), 0.0, target)          # bimetal opens: bulb off half the cycle
        L = self.L[p.id]
        rising = target > L
        k_on = 1 - math.exp(-self.dt / tau_on); k_off = 1 - math.exp(-self.dt / tau_off)
        L = L + (target - L) * np.where(rising, k_on, k_off)
        self.L[p.id] = L
        d = self.dir[p.id]
        nz = fr.max(1) > 1e-4
        d[nz] = fr[nz] / fr[nz].max(1, keepdims=True)                 # remember colour while lit
        # amber shift: how "white" is this pixel's colour? (1 - saturation)
        mx = d.max(1); mn = d.min(1); sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
        whiteness = 1 - sat
        dim = np.clip(1 - L / 0.45, 0, 1)                              # below ~45 % linear the filament is visibly orange
        w = (amber * dim * (0.25 + 0.75 * whiteness))[:, None]
        chroma = d * (1 - w) + AMBER[None, :] * w
        per = _per(L)
        return chroma * per[:, None]

    # -------------------------------------------------------------- neon
    def _neon(self, p, fr, t, params):
        uniform = bool(params.get("tube_uniform", True))
        out = fr.copy()
        lvl = fr.max(1)
        for k, m in enumerate(self.tubes[p.id]):
            seg = lvl[m]
            if seg.size == 0:
                continue
            on = seg.max() > 0.08
            if on and self.on_since[p.id][k] < -1e8:
                cold = (t - self.off_since[p.id][k]) > 1.5              # off for > 1.5 s -> cold start
                self.on_since[p.id][k] = t if cold else t - 1.0         # warm: pretend it ignited long ago
            if not on:
                if self.on_since[p.id][k] > -1e8:
                    self.off_since[p.id][k] = t
                self.on_since[p.id][k] = -1e9
                continue
            if uniform:
                j = int(np.argmax(seg)); col = fr[m][j]
                out[m] = col                                          # the whole tube at the brightest pixel's colour
            age = t - self.on_since[p.id][k]
            if age < 0.30:                                            # cold start: random dropouts, denser at first
                r = np.random.default_rng(int(t * self.fps) * 7919 + k * 131 + p.idx)
                if r.random() < 0.55 * (1 - age / 0.30):
                    out[m] *= 0.15
        return out
