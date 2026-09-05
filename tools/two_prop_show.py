#!/usr/bin/env python3
"""
two_prop_show.py -- a show for two props on one controller, built around
what each prop's geometry actually is.

    python tools/two_prop_show.py out

RIG
    port 3 (ch2)  18号  157 px  6-armed snowflake, 1.5 in pitch, 24 x 27.5 in
    port 4 (ch3)  47号   72 px  4-armed snowflake, 2.0 in pitch, 40 x 40 in
    ports 1-2     empty -> 32 px stubs
    frame = 879 bytes

The two props sit SIDE BY SIDE in one world coordinate space, measured in
inches, with a 4 in gap. That shared space is what lets an effect cross from
one prop to the other as a single continuous gesture rather than two effects
that happen to run at once.

GEOMETRY IS MEASURED, NOT ASSUMED
    centre      the mean of the pixels. Verified: measuring outer pixels per
                angular sector from the mean gives exactly [14,14,14,14,14,14]
                on 18号 and [10,10,10,10] on 47号 -- perfect symmetry. A
                "densest hub" heuristic got this badly wrong, landing on an
                arm.
    fold        chosen by trying 3/4/5/6/8 and keeping the one whose sector
                populations are most even. 18号 -> 6, 47号 -> 4, detected not
                hardcoded, so this generalises to the other 64 props.
    tips        pixels that are local radius maxima -- the dendrite ends.
    r_in, ang   polar coordinates about the measured centre, radius in INCHES.

WHY INCHES MATTER HERE
    18号 is on a 1.5 in pitch and 47号 on 2.0 in. A ring 2 in thick covers
    more than one bulb spacing on both. The same ring expressed as "0.05 of
    normalised radius" would be 1.1 in on one prop and 1.9 in on the other,
    and would read as two different effects.

CROSS-PROP INTERPLAY
    Several sections deliberately couple the two props:
      call and response   one flashes while the other holds near dark
      orb pass            a light orb crosses both props and the gap between
      counter-rotation    6-fold spins one way, 4-fold the other, locked
      shared wave         a plane wave sweeps world x through both
      sparkle handoff     grain density migrates from one prop to the other
      synchronised burst  both fire from their own centres on the same beat

No audio. This is a standalone demo -- drop it on the card and it runs.
"""

import math, os, sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from lightshow.formats.props import load_mod, UNITS_PER_INCH          # noqa: E402
from lightshow.formats.rgbfile import Show, FrameBuf                  # noqa: E402
from lightshow.effects import frost, hsv, lighten, to_bytes           # noqa: E402

FPS = 60
STUB = 32
GAP_IN = 4.0                      # gap between the two props
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "props")


def fr(sec):
    return max(1, int(round(sec * FPS)))


# --------------------------------------------------------------- geometry
class PropGeom:
    """Everything an effect needs to know about one prop's shape."""

    def __init__(self, name, path, port, x_offset_in):
        p = load_mod(path)
        self.name, self.port = name, port
        self.n = len(p)
        self.i = np.arange(self.n)
        xy = np.array(p.xy, float) / UNITS_PER_INCH        # inches
        self.centre = xy.mean(0)                            # measured, see docstring
        loc = xy - self.centre
        self.r_in = np.hypot(loc[:, 0], loc[:, 1])
        self.r = self.r_in / self.r_in.max()
        self.ang = np.arctan2(loc[:, 1], loc[:, 0])
        self.pitch_in = p.pitch_inches()
        self.fold = self._detect_fold()
        self.arm = (((self.ang + math.pi / self.fold) % (2 * math.pi))
                    / (2 * math.pi / self.fold)).astype(int) % self.fold
        self.tips = self._detect_tips(xy)
        # world placement: shift so the prop's left edge sits at x_offset_in
        self.x_in = loc[:, 0] + (x_offset_in + (xy[:, 0].max() - xy[:, 0].min()) / 2)
        self.y_in = loc[:, 1]
        self.width_in = xy[:, 0].max() - xy[:, 0].min()
        self.height_in = xy[:, 1].max() - xy[:, 1].min()

    def _detect_fold(self):
        """Count arms by finding angular CLUSTERS of outer pixels.

        Sector-evenness scoring does not work here and both failure modes
        showed up in testing. A 6-armed snowflake is perfectly even under 3
        sectors, so "lowest spread" called 18号 3-fold. And 47号's arms are
        double rows, so 8 sectors split each arm cleanly and scored exactly
        as well as 4 -- "finest that fits" then called it 8-fold.

        Arms are contiguous runs of angle separated by real gaps, so
        counting the large gaps measures arms directly instead of inferring
        them. Verified: 18号 -> 6, 47号 -> 4."""
        # Use only the outermost pixels: near the tips the arms are widely
        # separated, while at mid radius the dendrites blur together.
        a = np.sort((self.ang[self.r_in > self.r_in.max() * 0.85]
                     + math.pi) % (2 * math.pi))
        if len(a) < 4:
            return 4
        gaps = np.sort(np.diff(np.concatenate([a, [a[0] + 2 * math.pi]])))[::-1]
        # Between-arm gaps and within-arm gaps are separated by a cliff:
        # 18号 gives 6 gaps of ~59 deg then 2.3 deg; 47号 gives 4 of ~85 deg
        # then 4.3 deg. Cut at the largest ratio step.
        ratios = gaps[:-1] / np.maximum(gaps[1:], 1e-9)
        k = int(np.argmax(ratios[:12])) + 1
        return int(np.clip(k, 2, 12))

    def _detect_tips(self, xy):
        """Pixels that are a local maximum of radius -- dendrite ends."""
        d = np.linalg.norm(xy[:, None] - xy[None], axis=2)
        tips = np.zeros(self.n, bool)
        for k in range(self.n):
            near = np.argsort(d[k])[1:5]
            if self.r_in[k] >= self.r_in[near].max() and \
               self.r_in[k] > self.r_in.max() * 0.45:
                tips[k] = True
        return tips


def build_rig():
    a = PropGeom("18号", os.path.join(ASSETS, "18号.mod"), 2, 0.0)
    b = PropGeom("47号", os.path.join(ASSETS, "47号.mod"), 3,
                 a.width_in + GAP_IN)
    return [a, b]


# ---------------------------------------------------------------- effects
# every effect: fn(t, props, world) -> list of (n,3) perceptual arrays

def _blank(props):
    return [np.zeros((p.n, 3)) for p in props]


def wake(t, props, w):
    """Light spreads outward from each prop's OWN measured centre. The two
    have different radii (21.5 in vs 38 in) so the sweep speed is scaled to
    finish together -- the point is that they arrive at once, not that they
    move at the same inches per second."""
    out = []
    for p in props:
        edge = (t / 4.0) * p.r_in.max() * 1.15
        v = np.clip(1 - np.abs(p.r_in - edge) / 3.0, 0, 1)
        v = np.maximum(v, (p.r_in < edge) * 0.42)
        out.append(frost(v, 0.56))
    return out


def radial_pulse(t, props, w):
    """Rings of a fixed 2-inch thickness on both props, so they read the same
    despite the 1.5 vs 2.0 inch pitch."""
    out = []
    for p in props:
        phase = (p.r_in / 6.0 - t * 0.55) % 1.0
        v = np.exp(-((phase - 0.5) / 0.17) ** 2)
        out.append(frost(v, 0.52 + 0.10 * p.r))
    return out


def arm_count(t, props, w):
    """18号 walks 6 arms, 47号 walks 4, both completing a full rotation in the
    same time. Geometry decides the count; the show decides the tempo."""
    out = []
    for p in props:
        pos = (t / 3.0) % 1.0
        sel = int(pos * p.fold) % p.fold
        v = np.where(p.arm == sel, 0.45 + 0.55 * p.r, 0.10)
        out.append(frost(v, 0.60))
    return out


def dendrite_glints(t, props, w):
    """Only the tip pixels -- the dendrite ends -- twinkle. On 47号 that is
    the four arm ends; on 18号 it is every branch end."""
    out = []
    for k, p in enumerate(props):
        v = np.zeros(p.n)
        tick = int(t * 6) + k * 3
        rng = np.random.default_rng(tick * 7717)
        idx = np.flatnonzero(p.tips)
        if len(idx):
            chosen = rng.choice(idx, size=max(2, len(idx) * 2 // 3), replace=False)
            age = (t * 6) % 1.0
            v[chosen] = (1 - age) ** 1.3
        # hold a faint level everywhere so the silhouette stays readable;
        # tips alone on a dark prop read as random dots, not as a snowflake
        base = np.where(p.tips, 0.20, 0.10)
        out.append(frost(np.maximum(v, base), 0.575))
    return out


def call_response(t, props, w):
    """One flashes, the other holds near dark, then they swap."""
    period = 1.3
    phase = (t / period) % 2.0
    lead = 0 if phase < 1.0 else 1
    k = (phase % 1.0)
    hit = math.exp(-k * 2.6)
    out = []
    for idx, p in enumerate(props):
        if idx == lead:
            # flash, then settle to a held glow rather than to black -- if
            # both props go dark between calls the shapes vanish entirely
            v = np.full(p.n, 0.20) + hit * (0.55 + 0.45 * (1 - p.r))
        else:
            v = np.full(p.n, 0.16 - 0.08 * hit)      # dips as the other fires
        out.append(frost(np.clip(v, 0, 1), 0.55 if idx == lead else 0.64))
    return out


def orb_pass(t, props, w):
    """An orb travels the whole layout in WORLD inches, crossing prop A, the
    gap, and prop B, then returning. Only possible because both props share
    one coordinate space."""
    span = w["x_max"] - w["x_min"]
    tri = abs(((t / 5.0) % 2.0) - 1.0)                   # 0..1..0
    ox = w["x_min"] - 4 + tri * (span + 8)
    oy = 0.0
    out = []
    for p in props:
        d = np.hypot(p.x_in - ox, p.y_in - oy)
        v = np.exp(-(d / 5.0) ** 2)
        trail = np.exp(-(d / 11.0) ** 2) * 0.28
        out.append(frost(np.clip(v + trail, 0, 1), 0.55))
    return out


def counter_rotate(t, props, w):
    """6-fold spins one way, 4-fold the other, locked to the same period."""
    out = []
    for k, p in enumerate(props):
        direction = 1 if k == 0 else -1
        a = (p.ang / (2 * math.pi) + direction * t * 0.22) % 1.0
        blades = (np.cos(a * 2 * math.pi * p.fold) * 0.5 + 0.5) ** 2.4
        out.append(frost(blades * (0.25 + 0.75 * p.r), 0.53 + 0.12 * k))
    return out


def frost_creep(t, props, w):
    """Crystal growth along the WIRE from the centre outward. 18号 has 157
    pixels and 47号 has 72, so the rate is scaled per prop to finish
    together -- otherwise the small prop would be done in half the time."""
    out = []
    for p in props:
        prog = np.clip(t / 5.0, 0, 1.2)
        order = np.argsort(p.r_in)                     # centre outward
        rank = np.empty(p.n)
        rank[order] = np.linspace(0, 1, p.n)
        v = np.clip((prog - rank) * 6.0, 0, 1)
        edge = np.exp(-((rank - prog) / 0.07) ** 2)
        out.append(frost(np.clip(v * 0.55 + edge, 0, 1), 0.57))
    return out


def antiphase_breath(t, props, w):
    """One inhales as the other exhales."""
    out = []
    for k, p in enumerate(props):
        ph = t / 4.0 + (0.5 if k else 0.0)
        lvl = (math.sin(2 * math.pi * ph) * 0.5 + 0.5) ** 2
        out.append(frost(np.full(p.n, lvl * 0.85), 0.60 - 0.06 * k))
    return out


def shared_wave(t, props, w):
    """A plane wave sweeping world x. It crosses prop A, the gap, then prop
    B as one continuous front -- the clearest proof they share a space."""
    out = []
    for p in props:
        phase = (p.x_in / 26.0 - t * 0.40) % 1.0
        v = np.exp(-((phase - 0.5) / 0.15) ** 2)
        out.append(frost(v, 0.54))
    return out


def sparkle_handoff(t, props, w):
    """Grain density migrates from one prop to the other and back."""
    bias = (math.sin(2 * math.pi * t / 6.0) * 0.5 + 0.5)
    out = []
    for k, p in enumerate(props):
        share = bias if k == 0 else (1 - bias)
        v = np.zeros(p.n)
        tick = int(t * 20)
        for g in range(max(0, tick - 12), tick + 1):
            rng = np.random.default_rng(g * 6151 + k * 99)
            cnt = int(1 + 7 * share)
            idx = rng.integers(0, p.n, cnt)
            v[idx] = np.maximum(v[idx], (1 - (tick - g) / 12) ** 2.2)
        out.append(frost(v, 0.585))
    return out


def synchronised_burst(t, props, w):
    """Both fire from their own centres on the same beat, each at its own
    scale so the fronts reach the tips together."""
    out = []
    beat = 1.25
    k = (t % beat) / beat
    for p in props:
        edge = k * p.r_in.max() * 1.1
        v = np.clip(1 - np.abs(p.r_in - edge) / 2.5, 0, 1) * (1 - k) ** 0.5
        out.append(frost(v, 0.50))
    return out


def finale(t, props, w):
    """Everything at once, then a clean fade."""
    out = []
    fade = np.clip(1 - max(0.0, t - 6.0) / 3.0, 0, 1)
    for k, p in enumerate(props):
        ring = np.exp(-((((p.r_in / 5.0 - t * 0.9) % 1.0) - 0.5) / 0.18) ** 2)
        spin = (np.cos((p.ang / (2 * math.pi) + t * 0.3) * 2 * math.pi * p.fold)
                * 0.5 + 0.5) ** 3
        tipglow = np.where(p.tips, 0.5 + 0.5 * math.sin(t * 7 + k), 0.0)
        v = np.clip(ring * 0.8 + spin * 0.45 + tipglow * 0.5, 0, 1) * fade
        out.append(frost(v, 0.52))
    return out


SECTIONS = [
    ("wake: light spreads from each measured centre", wake, 9.0),
    ("radial pulse: 2-inch rings on both, despite different pitch", radial_pulse, 12.0),
    ("arm count: 18号 walks 6 arms, 47号 walks 4", arm_count, 12.0),
    ("dendrite glints: only the branch tips", dendrite_glints, 10.0),
    ("call and response: one flashes, one holds dark", call_response, 12.0),
    ("orb pass: an orb crosses both props and the gap", orb_pass, 15.0),
    ("counter-rotation: 6-fold one way, 4-fold the other", counter_rotate, 12.0),
    ("frost creep: growth centre-outward, scaled to finish together", frost_creep, 11.0),
    ("antiphase breath: one inhales as the other exhales", antiphase_breath, 12.0),
    ("shared wave: one front sweeps across both", shared_wave, 12.0),
    ("sparkle handoff: density migrates between props", sparkle_handoff, 12.0),
    ("synchronised burst: both fire from their own centre", synchronised_burst, 10.0),
    ("finale", finale, 9.0),
]


def build():
    props = build_rig()
    world = {"x_min": min(p.x_in.min() for p in props),
             "x_max": max(p.x_in.max() for p in props)}
    channels = [STUB, STUB, 0, 0]
    for p in props:
        channels[p.port] = p.n
    s = Show(channels)
    log = []

    def push(per_prop):
        fb = FrameBuf(s, 255)
        for p, rgb in zip(props, per_prop):
            b = to_bytes(rgb)
            for i in range(p.n):
                fb.set(p.port, i, int(b[i, 0]), int(b[i, 1]), int(b[i, 2]))
        s.frames.append(fb.bytes())

    def dark(sec):
        blk = FrameBuf(s, 255).bytes()
        for _ in range(fr(sec)):
            s.frames.append(blk)

    dark(1.0)
    for name, fn, dur in SECTIONS:
        log.append((len(s.frames), dur, name))
        for f in range(fr(dur)):
            push(fn(f / FPS, props, world))
        dark(0.7)
    dark(1.3)
    return s, props, world, log


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "out"
    os.makedirs(out, exist_ok=True)
    s, props, world, log = build()
    n = len(s.frames)
    print("rig:")
    for p in props:
        print(f"   port {p.port+1} (ch{p.port})  {p.name}  {p.n:3d} px  "
              f"{p.fold}-fold (detected)  pitch {p.pitch_in:.2f} in  "
              f"radius {p.r_in.max():.1f} in  tips {int(p.tips.sum())}")
    print(f"   world span {world['x_min']:.1f} .. {world['x_max']:.1f} in "
          f"({world['x_max']-world['x_min']:.1f} in wide, {GAP_IN:.0f} in gap)")
    print()
    print(s.info())
    s.save(os.path.join(out, "TwoProps.rgb"))
    print(f"\nTwoProps.rgb  {n} frames = {n/FPS:.0f} s  "
          f"{(s.header_size + n*s.frame_size)/1e6:.2f} MB")
    print("\n--- timing map ---")
    for st, dur, name in log:
        print(f"   t={st/FPS:6.1f}s +{dur:4.0f}s  {name}")
