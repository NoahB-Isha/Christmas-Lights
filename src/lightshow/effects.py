"""
effects.py -- the effect registry.

AN EFFECT IS A PURE FUNCTION of one context object:

    @effect("my effect")
    def my_effect(c):
        return frost(c.rms * (1 - c.r))          # -> (n, 3) floats 0..1

No lifecycle, no framework, no state. That is deliberate: it is the property
that makes an effect writable from a one-sentence description, droppable
into a folder, and previewable immediately.

THE CONTEXT (`c`) -- all arrays are length n, one entry per pixel:

    c.t          float, seconds since the show started
    c.n          int, pixels on this port
    c.i          int array 0..n-1, position along the WIRE
    c.u, c.v     position, normalised so the longest axis spans -1..1, y up
    c.x_in,      position in INCHES from the prop centre
    c.y_in
    c.r          radius, normalised 0..1 (1 = furthest pixel)
    c.r_in       radius in inches
    c.ang        angle in radians, -pi..pi
    c.arm        int array, which quadrant/arm each pixel is in
    c.pitch_in   float, median bulb spacing in inches
    c.p          dict of tunable parameters

    Music (all 0..1 unless noted, sampled at c.t; zero if no track loaded):
    c.rms c.low c.mid c.high c.centroid c.harm c.perc
    c.hit        percussive onset, decaying
    c.hit_high   high-band onset, decaying
    c.beat       beat impulse, decaying
    c.downbeat   bar impulse, decaying
    c.beat_phase 0..1 within the current beat
    c.bpm        float

SIZE THINGS IN INCHES, NOT IN u/v. Bulb pitch across the prop library runs
from 0.5 in to 2.1 in -- a 4x spread. A feature sized in normalised
coordinates is invisible on a sparse prop and coarse on a dense one. Use
c.x_in / c.r_in / c.pitch_in and a feature will port between props.

Return PERCEPTUAL brightness 0..1. The renderer applies gamma 2.2 on the way
to bytes, because the controller's LUT is an identity ramp and applies none.
"""

import math
import numpy as np

REGISTRY = {}


def effect(name, **defaults):
    def deco(fn):
        fn.effect_name = name
        fn.params = defaults
        REGISTRY[name] = fn
        return fn
    return deco


# ---------------------------------------------------------------- colour
def hsv(h, s, v):
    """Vectorised HSV->RGB. Any of h/s/v may be scalar or array."""
    shape = np.broadcast(np.asarray(h, float), np.asarray(s, float),
                         np.asarray(v, float)).shape
    h = np.broadcast_to(np.asarray(h, float) % 1.0, shape)
    s = np.broadcast_to(np.clip(np.asarray(s, float), 0, 1), shape)
    v = np.broadcast_to(np.clip(np.asarray(v, float), 0, 1), shape)
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    out = np.zeros(shape + (3,))
    for k, trio in enumerate([(v, t, p), (q, v, p), (p, v, t),
                              (p, q, v), (t, p, v), (v, p, q)]):
        m = i == k
        for ch in range(3):
            out[..., ch][m] = trio[ch][m]
    return out


ICE_COOL, ICE_BASE, ICE_WARM = 0.52, 0.60, 0.68


def frost(v, hue=0.585, bias=1.15, gain=0.95):
    """White core, blue falloff. Saturation RISES as brightness falls, so a
    grain is born white-hot and cools into blue as it decays. That inversion
    is the difference between a white twinkle and frost."""
    v = np.clip(np.asarray(v, float), 0, 1)
    return hsv(hue, np.clip((1 - v) * bias, 0, gain), v)


def lighten(*layers):
    """Per-channel max. Compositing several layers by ADDITION drives every
    channel to 1.0 and the prop turns white, destroying the colour
    distinction that makes layering readable at all. Measured: additive gave
    a washed-out result, lighten holds mean saturation ~0.6."""
    out = layers[0]
    for L in layers[1:]:
        out = np.maximum(out, L)
    return out


# ---------------------------------------------------------------- context
class Ctx:
    def __init__(self, prop_xy, pitch_in, units_per_inch=20.0):
        xy = np.asarray(prop_xy, float)
        self.n = len(xy)
        self.i = np.arange(self.n)
        cx, cy = xy[:, 0].mean(), xy[:, 1].mean()
        bx = max(xy[:, 0].max() - xy[:, 0].min(), xy[:, 1].max() - xy[:, 1].min())
        span = (bx / 2) or 1.0
        self.u = (xy[:, 0] - (xy[:, 0].min() + xy[:, 0].max()) / 2) / span
        self.v = (xy[:, 1] - (xy[:, 1].min() + xy[:, 1].max()) / 2) / span
        self.x_in = self.u * span / units_per_inch
        self.y_in = self.v * span / units_per_inch
        self.r = np.hypot(self.u, self.v)
        self.r /= max(1e-9, self.r.max())
        self.r_in = np.hypot(self.x_in, self.y_in)
        self.ang = np.arctan2(self.v, self.u)
        self.arm = ((self.ang + math.pi / 4) % (2 * math.pi)
                    / (math.pi / 2)).astype(int) % 4
        self.pitch_in = pitch_in
        self.t = 0.0
        self.p = {}
        self.bpm = 120.0
        for k in ("rms", "low", "mid", "high", "centroid", "harm", "perc",
                  "hit", "hit_high", "beat", "downbeat", "beat_phase"):
            setattr(self, k, 0.0)

    def set_music(self, a, frame):
        """Pull every feature for one frame off a music.Analysis."""
        f = min(frame, a.n_frames - 1)
        for k in ("rms", "low", "mid", "high", "centroid", "harm", "perc"):
            setattr(self, k, float(getattr(a, k)[f]))
        self.hit = float(a.hit[f]); self.hit_high = float(a.hit_high[f])
        self.beat = float(a.beat_env[f]); self.downbeat = float(a.downbeat_env[f])
        self.beat_phase = a.beat_phase(self.t)
        self.bpm = a.bpm


# ---------------------------------------------------------------- effects
@effect("radial pulse", speed=0.75, rings=2.2)
def radial_pulse(c):
    k = 0.5 + 0.5 * np.sin(2 * np.pi * (c.r * c.p.get("rings", 2.2)
                                        - c.t * c.p.get("speed", 0.75)))
    return frost(k ** 1.5, ICE_COOL, bias=0.95)


@effect("pinwheel", speed=0.16)
def pinwheel(c):
    return hsv(c.ang / (2 * np.pi) + c.t * c.p.get("speed", 0.16), 1.0, 1.0)


@effect("wire snake", px_per_sec=24, tail=24)
def wire_snake(c):
    tail = c.p.get("tail", 24)
    head = (c.t * c.p.get("px_per_sec", 24)) % (c.n + tail)
    d = head - c.i
    # clip BEFORE the fractional power: np.where evaluates both branches, so
    # a negative base would produce NaN even though it is masked out
    v = np.clip(1 - d / tail, 0, 1) ** 1.3
    v[d < 0] = 0.0
    return frost(v, ICE_COOL)


@effect("rain", speed=0.34, drops=10, radius_in=12.0)
def rain(c):
    best = np.zeros(c.n)
    rad = c.p.get("radius_in", 12.0)          # INCHES -- see module docstring
    for k in range(int(c.p.get("drops", 10))):
        rng = np.random.default_rng(k * 9187)
        dx = rng.uniform(-1, 1) * (c.x_in.max() or 1)
        ph = rng.random()
        span_in = (c.y_in.max() - c.y_in.min()) or 1
        y = c.y_in.max() + 0.15 * span_in - ((c.t * c.p.get("speed", .34) + ph)
                                             % 1.0) * span_in * 1.3
        d = np.hypot((c.x_in - dx) * 1.15, c.y_in - y)
        best = np.maximum(best, np.clip(1 - d / rad, 0, 1))
    return frost(best ** 1.1, 0.55)


@effect("radar sweep", speed=0.55)
def radar(c):
    beam = (c.t * c.p.get("speed", 0.55) % 1.0) * 2 * np.pi
    d = (beam - c.ang) % (2 * np.pi)
    b = np.clip(1 - d / 2.2, 0, 1) ** 1.4
    edge = np.clip(1 - d / 0.35, 0, 1)
    return frost(np.minimum(1, b + edge * 0.9), ICE_BASE, bias=0.9)


@effect("breathe", period=4.0)
def breathe(c):
    k = (math.sin(2 * math.pi * c.t / c.p.get("period", 4.0)) * .5 + .5) ** 2
    return frost(np.full(c.n, k), ICE_BASE, bias=1.0)


@effect("embers", rate=12)
def embers(c):
    tick = int(c.t * c.p.get("rate", 12))
    rng = np.random.default_rng(tick * 733)
    nz = rng.random(c.n)
    span = (c.y_in.max() - c.y_in.min()) or 1
    heat = np.clip((0.75 - 0.42 * (c.y_in / span * 2)) * (0.55 + 0.55 * nz), 0, 1)
    return hsv(0.02 + 0.09 * heat, 0.95 - 0.35 * heat, heat)


@effect("peppered sparkle", rate=18, life=14, per_tick=3, warm=False)
def peppered_sparkle(c):
    """Fine grains that pop and decay. State-free: it sums a fixed number of
    overlapping generations, each seeded from its own tick index, so the
    same t always gives the same frame and the effect stays a pure function.
    Reseeding every frame instead would be a 60 Hz strobe."""
    out = np.zeros(c.n)
    rate = c.p.get("rate", 18); life = int(c.p.get("life", 14))
    tick = int(c.t * rate)
    for k in range(max(0, tick - life), tick + 1):
        rng = np.random.default_rng(k * 6151)
        idx = rng.integers(0, c.n, int(c.p.get("per_tick", 3)))
        out[idx] = np.maximum(out[idx], (1 - (tick - k) / life) ** 2.2)
    hue = 0.11 if c.p.get("warm") else 0.585
    return frost(out, hue, bias=0.35 if c.p.get("warm") else 1.15)


@effect("bass ring", width_in=3.0)
def bass_ring(c):
    edge = c.low * c.r_in.max() * 1.05
    band = np.exp(-((c.r_in - edge) / c.p.get("width_in", 3.0)) ** 2)
    return frost(band * c.low, ICE_COOL, bias=0.95)


@effect("arm hits")
def arm_hits(c):
    if c.hit < 0.02:
        return np.zeros((c.n, 3))
    arm = int(c.t * c.bpm / 60) % 4
    v = np.where(c.arm == arm, c.hit * (0.45 + 0.55 * c.r), 0.0)
    return frost(v, ICE_BASE, bias=1.3)


@effect("idle shimmer", density=0.05, speed=0.13)
def idle_shimmer(c):
    ph = (c.i * 0.618 + c.t * c.p.get("speed", 0.13)) % 1.0
    return frost(np.exp(-((ph - 0.5) / c.p.get("density", 0.05)) ** 2), 0.565)


def render(name, ctx, **params):
    ctx.p = dict(REGISTRY[name].params, **params)
    return np.clip(REGISTRY[name](ctx), 0, 1)


def to_bytes(rgb, gamma=2.2):
    """Perceptual 0..1 -> byte. The controller's LUT is identity, so it
    applies no gamma; without this, fades look top-heavy and die at the
    bottom end."""
    return (np.clip(rgb, 0, 1) ** gamma * 255).astype(np.uint8)
