#!/usr/bin/env python3
"""
lamps.py -- LAMP MODELS: make LED pixels behave like the light sources they
are imitating. Applied per frame AFTER the look, stateful per pixel.

    lamp: led            what the LEDs do by themselves (no model)
    lamp: incandescent   C7/C9 filament bulbs (1950s-60s Christmas strings)
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

TWINKLE
  * incandescent, plus a fixed random subset of bulbs that each blink on
    their own irregular 0.8-2.2 s cycle (bimetal strip), unsynchronised.

Section params:  lamp, twinkle_frac (default 0.18), amber (default 1.0 =
full amber shift), tau_on / tau_off.

(A neon model -- instant tubes, cold-start flicker, animated-sign cycling --
was built and tested on the bench 2026-09-11 and DROPPED: it read as
unpleasant flicker on the props. Incandescent + LED looks carry the show.)
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
        self.rng = np.random.default_rng(97)
        # twinkle bulbs: fixed subset, own period and phase
        self.tw_period = {p.id: self.rng.uniform(0.8, 2.2, p.n) for p in props}
        self.tw_phase = {p.id: self.rng.uniform(0, 1, p.n) for p in props}
        self.tw_rank = {p.id: self.rng.permutation(p.n) / p.n for p in props}   # 0..1, pick < frac

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
