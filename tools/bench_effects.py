#!/usr/bin/env python3
"""
make_bench47.py -- effects test for the bench rig.

RIG
  port 4 (ch3) = 47号.mod, a 4-armed cross, 72 px, 800x800 units,
                 wire traces the outline as one continuous loop
  ports 1-3    = empty -> 32 px stubs (factory convention; omitting them
                 would shift ch3's byte offset)
  frame = (32*3 + 72) * 3 = 504 bytes -- tiny, so the file stays small

Effects are evaluated at each LED's REAL (x, y) from the .mod file, not by
chain index, so radial and angular effects actually radiate from the centre
of the cross and run out along the arms.

10 effects, ~12 s each, with a 1-flash separator before each so you can
follow along against the printed timing map.

FRAME RATE measured at 60 fps (FpsTest.rgb: 1800 frames in 30.0 s, and the
24-blink cross-check gave 1.00 blink/s). It is a device setting and is not
stored in the file, so the controller must stay on 60.
"""

import sys, os, os, math, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from lightshow.formats.rgbfile import Show, FrameBuf
from lightshow.formats.props import load_mod

FPS = 60                      # MEASURED: 1800 frames in 30.0 s
STUB = 32
C = 255
EFFECT_SEC = 12.0

MOD = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "assets", "props", "47号.mod")


def fr(sec):
    return max(1, int(round(sec * FPS)))


def hsv(h, s, v):
    h = h % 1.0
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    r, g, b = [(v, t, p), (q, v, p), (p, v, t),
               (p, q, v), (t, p, v), (v, p, q)][i]
    return r, g, b


# ---------------------------------------------------------------- geometry
prop = load_mod(MOD)
N = len(prop)
x0, y0, x1, y1 = prop.bounds
cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
scale = max(x1 - x0, y1 - y0) / 2 or 1
UV = [((x - cx) / scale, (y - cy) / scale) for x, y in prop.xy]
POLAR = [(math.hypot(u, v), math.atan2(v, u)) for u, v in UV]

CH = [STUB, STUB, STUB, N]
PROP_CH = 3


# ---------------------------------------------------------------- effects
# each: fn(t_seconds) -> list of (r,g,b) floats 0..1, length N

def fx_sparkle(t):
    """Peppered sparkle. Fine grained, many small brief pops, warm white
    with an occasional cool one. State-based so each grain decays instead
    of flickering; new grains are seeded ~18x/second."""
    out = [(0.0, 0.0, 0.0)] * N
    tick = int(t * 18)
    for k in range(tick - 14, tick + 1):          # 14 overlapping generations
        if k < 0:
            continue
        random.seed(k * 6151)
        for _ in range(3):                        # ~3 new grains per tick
            i = random.randrange(N)
            age = (tick - k) / 14.0
            b = (1.0 - age) ** 2.2
            warm = random.random() < 0.78
            h, s = (0.11, 0.35) if warm else (0.55, 0.30)
            r, g, bl = hsv(h, s, b)
            pr, pg, pb = out[i]
            out[i] = (min(1, pr + r), min(1, pg + g), min(1, pb + bl))
    return out


def fx_radial(t):
    """Rings expanding from the centre and running out along the arms."""
    out = []
    for r, a in POLAR:
        k = 0.5 + 0.5 * math.sin(2 * math.pi * (r * 2.2 - t * 0.75))
        out.append(hsv(0.52 + 0.22 * r, 0.9, k ** 1.5))
    return out


def fx_pinwheel(t):
    """Hue by angle: a colour wheel rotating around the cross centre."""
    return [hsv(a / (2 * math.pi) + t * 0.16, 1.0, 1.0) for r, a in POLAR]


def fx_arms(t):
    """Lights one arm at a time, going round. Uses angle quadrants, so it
    finds the arms from the geometry rather than from pixel indices."""
    out = []
    arm = int(t * 0.9) % 4
    lo = -math.pi / 4 + arm * math.pi / 2
    for r, a in POLAR:
        d = (a - lo) % (2 * math.pi)
        on = d < math.pi / 2
        out.append(hsv(0.08 + arm * 0.22, 0.85, 1.0 if on else 0.0))
    return out


def fx_snake(t):
    """Comet along wire order, so it snakes around the cross outline."""
    out = [(0.0, 0.0, 0.0)] * N
    head = (t * 24) % (N + 26)
    for i in range(N):
        d = head - i
        if 0 <= d < 24:
            b = (1 - d / 24) ** 1.3          # sparse prop: keep the tail lit
            out[i] = hsv(0.45 + 0.1 * (i / N), 0.75, b)
    return out


def fx_rain(t):
    """Droplets falling by real y, so they run down the arms."""
    out = []
    drops = []
    for k in range(10):
        random.seed(k * 9187)
        drops.append((random.uniform(-1, 1), random.random()))
    for u, v in UV:
        best = 0.0
        for dx, ph in drops:
            y = 1.3 - ((t * 0.34 + ph) % 1.0) * 2.6
            # widened: this prop has ~9 px per arm, narrow drops miss entirely
            d = math.hypot((u - dx) * 1.15, v - y)
            best = max(best, max(0.0, 1 - d / 0.62))
        out.append(hsv(0.55, 0.45, best ** 1.1))
    return out


def fx_plasma(t):
    """Sin-field plasma in real space."""
    out = []
    for u, v in UV:
        f = (math.sin(u * 3.0 + t * 1.6)
             + math.sin(v * 2.6 - t * 1.2)
             + math.sin((u + v) * 2.1 + t * 0.9))
        out.append(hsv(0.72 + f * 0.10, 0.9, 0.5 + 0.5 * math.sin(f * 1.25)))
    return out


def fx_radar(t):
    """A bar sweeps around the centre and leaves a fading trail."""
    out = []
    beam = (t * 0.55 % 1.0) * 2 * math.pi
    for r, a in POLAR:
        d = (beam - a) % (2 * math.pi)
        b = max(0.0, 1 - d / 2.2) ** 1.4
        edge = max(0.0, 1 - d / 0.35)          # hot leading edge
        b = min(1.0, b + edge * 0.9)
        out.append(hsv(0.33 - 0.05 * edge, 0.8 - 0.4 * edge, b))
    return out


def fx_breathe(t):
    """Whole prop breathes, hue drifting. 4 s period."""
    k = (math.sin(2 * math.pi * t / 4.0) * 0.5 + 0.5) ** 2
    r, g, b = hsv(t * 0.06, 0.85, 1.0)
    return [(r * k, g * k, b * k)] * N


def fx_twincomet(t):
    """Two pulses launch from the centre and race out opposite arms."""
    out = []
    ph = (t * 0.6) % 1.0
    edge = ph * 1.35
    tilt = t * 0.35
    for r, a in POLAR:
        along = math.cos(a - tilt)
        d = abs(r - edge)
        # widened band and a gentler axis falloff -- the old 0.28/^1.5 combo
        # lit only 2-3 pixels of this sparse prop
        b = max(0.0, 1 - d / 0.50) ** 1.2 * (0.35 + 0.65 * abs(along))
        h = 0.02 if along > 0 else 0.60
        out.append(hsv(h, 0.8, min(1.0, b)))
    return out


def fx_ember(t):
    """Warm flicker weighted so the lower arm glows hottest."""
    out = []
    tick = int(t * 12)
    for idx, (u, v) in enumerate(UV):
        random.seed(tick * 733 + idx * 17)
        n = random.random()
        heat = max(0.0, 0.75 - 0.42 * v) * (0.55 + 0.55 * n)
        heat = min(1.0, heat)
        out.append(hsv(0.02 + 0.09 * heat, 0.95 - 0.35 * heat, heat))
    return out


EFFECTS = [
    ("Peppered sparkle", fx_sparkle),
    ("Radial pulse", fx_radial),
    ("Pinwheel", fx_pinwheel),
    ("Arm by arm", fx_arms),
    ("Wire snake", fx_snake),
    ("Rain down the arms", fx_rain),
    ("Plasma", fx_plasma),
    ("Radar sweep", fx_radar),
    ("Breathe", fx_breathe),
    ("Twin comets", fx_twincomet),
    ("Embers", fx_ember),
]


# ---------------------------------------------------------------- assemble
def build():
    s = Show(CH)
    log = []

    def push(cols):
        fb = FrameBuf(s, C)
        for i, (r, g, b) in enumerate(cols):
            fb.set(PROP_CH, i, r * C, g * C, b * C)
        s.frames.append(fb.bytes())

    def flat(col, sec):
        fb = FrameBuf(s, C)
        fb.fill(PROP_CH, *[c * C for c in col])
        blk = fb.bytes()
        for _ in range(fr(sec)):
            s.frames.append(blk)

    def dark(sec):
        flat((0, 0, 0), sec)

    dark(1.0)
    log.append((len(s.frames), "START: all white 1.0 s"))
    flat((1, 1, 1), 1.0)
    dark(1.0)

    for n, (name, fn) in enumerate(EFFECTS):
        # one white blip as separator
        flat((1, 1, 1), 0.14)
        dark(0.5)
        log.append((len(s.frames), f"{n+1:2d}. {name}"))
        for f in range(fr(EFFECT_SEC)):
            push(fn(f / FPS))
        dark(0.55)

    log.append((len(s.frames), "END: 4x red/blue"))
    for _ in range(4):
        flat((1, 0, 0), 0.22)
        flat((0, 0, 1), 0.22)
    dark(1.0)
    return s, log


if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "out"), exist_ok=True)
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    s, log = build()
    s.save(os.path.join(out, "Bench47.rgb"))
    n = len(s.frames)
    print(f"prop: {os.path.basename(MOD)}  {N} px, bbox {x1-x0:.0f}x{y1-y0:.0f}")
    print(s.info())
    print(f"\nBench47.rgb  {n} frames = {n/FPS:.0f} s at {FPS} fps  "
          f"{(s.header_size + n*s.frame_size)/1e6:.2f} MB")
    print("\n--- timing map (t at 60 fps; each effect preceded by 1 white blip) ---")
    for st, name in log:
        print(f"  t={st/FPS:6.1f}s   {name}")
