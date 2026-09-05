#!/usr/bin/env python3
"""
showcase.py -- a longer, full-colour show whose purpose is to demonstrate
what this hardware can actually do.

    python tools/showcase.py out

Same rig as two_prop_show: 18号 (6-armed, 157 px, 1.5 in) on port 3 and
47号 (4-armed, 72 px, 2.0 in) on port 4, side by side with a 4 in gap.

------------------------------------------------------------------
COLOUR: gradients, not hue
------------------------------------------------------------------
The obvious way to get "more colours" is to sweep hue, and it looks cheap
almost immediately -- a full-saturation rainbow reads as a test pattern.
Everything here instead computes a SCALAR FIELD (0..1) and maps it through a
hand-picked gradient. That is why a photograph of a sunset looks designed and
a hue sweep does not: real palettes move in brightness and saturation at the
same time as hue, and they do not visit every hue.

Each palette is a short list of stops interpolated into a 256-entry LUT, so
swapping the look of an effect is one word.

------------------------------------------------------------------
TECHNIQUES, one per section
------------------------------------------------------------------
Grouped by what they demonstrate, not by how they look:

  FIELDS          value noise, flow advection, wave interference, ripples
  SIMULATION      reaction-diffusion, particle gravity, fire, lightning
  STRUCTURE       kaleidoscope folding, voronoi cells, log spirals, vortices
  COLOUR TRICKS   palette cycling, gradient morph, chromatic separation
  CROSS-PROP      everything spatial runs in shared world inches, so fronts,
                  particles and fields carry across the gap

Reaction-diffusion, fire and lightning all run on the prop's actual NEIGHBOUR
GRAPH -- built from real bulb positions, not from chain index -- so diffusion
spreads the way the prop is physically shaped. That is the part that would be
impossible without the .mod geometry.
"""

import math, os, sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lightshow.formats.rgbfile import Show, FrameBuf          # noqa: E402
from lightshow.effects import to_bytes                        # noqa: E402
from two_prop_show import PropGeom, GAP_IN, ASSETS            # noqa: E402

FPS = 60
STUB = 32


def fr(sec):
    return max(1, int(round(sec * FPS)))


# ------------------------------------------------------------------ palettes
PALETTES = {
    "aurora":   ["#04121F", "#0B6E4F", "#1FD6A0", "#8CE8DC", "#B98CE0"],
    "ember":    ["#160801", "#7A1E05", "#D4541A", "#F2A33C", "#FFE9B0"],
    "spectral": ["#241653", "#2E6FB7", "#3FBFA8", "#E8D46B", "#E8685A"],
    "oceanic":  ["#01101B", "#04425E", "#1D8FA8", "#7FD1C8", "#EAF7F2"],
    "dusk":     ["#0E0420", "#4A1259", "#A02B7E", "#E2698E", "#FBC79A"],
    "frost":    ["#050C1A", "#123A6B", "#2D82C4", "#93D6F0", "#FFFFFF"],
    "moss":     ["#04120C", "#124A33", "#3E9C6D", "#A6DFA0", "#EAF7DC"],
    "copper":   ["#120A08", "#4A2418", "#9C5A2E", "#D69C5E", "#F6E2BE"],
}


def _hex(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def lut(name, n=256):
    stops = [_hex(c) for c in PALETTES[name]]
    pos = np.linspace(0, 1, len(stops))
    x = np.linspace(0, 1, n)
    out = np.zeros((n, 3))
    for c in range(3):
        out[:, c] = np.interp(x, pos, [s[c] for s in stops])
    return out


LUTS = {k: lut(k) for k in PALETTES}


def ramp(field, name, gain=1.0, floor=0.0):
    """Scalar field 0..1 -> RGB through a gradient, with the field also
    driving brightness so dark parts of the palette stay dark."""
    f = np.clip(np.asarray(field, float), 0, 1)
    idx = (f * 255).astype(int)
    rgb = LUTS[name][idx]
    return np.clip(rgb * (floor + (1 - floor) * f[:, None] ** 0.75) * gain, 0, 1)


def mix_lut(field, a, b, k):
    """Crossfade between two palettes -- the same field, different look."""
    f = np.clip(np.asarray(field, float), 0, 1)
    i = (f * 255).astype(int)
    rgb = LUTS[a][i] * (1 - k) + LUTS[b][i] * k
    return np.clip(rgb * (0.15 + 0.85 * f[:, None] ** 0.75), 0, 1)


# --------------------------------------------------------------- noise field
_RNG = np.random.default_rng(7)
_GRID = _RNG.random((64, 64, 4))            # 4 octaves of value noise


def _smooth(t):
    return t * t * (3 - 2 * t)


def noise2(x, y, z=0.0, octave=0):
    """Value noise on a 64x64 torus, bilinear + smoothstep. x, y in grid
    units; z shifts between two slices so it animates smoothly."""
    g = _GRID[:, :, octave % 4]
    xi, yi = np.floor(x).astype(int), np.floor(y).astype(int)
    xf, yf = _smooth(x - xi), _smooth(y - yi)
    x0, x1 = xi % 64, (xi + 1) % 64
    y0, y1 = yi % 64, (yi + 1) % 64
    n = (g[x0, y0] * (1 - xf) * (1 - yf) + g[x1, y0] * xf * (1 - yf) +
         g[x0, y1] * (1 - xf) * yf + g[x1, y1] * xf * yf)
    zf = _smooth(z % 1.0)
    g2 = _GRID[:, :, (octave + 1) % 4]
    m = (g2[x0, y0] * (1 - xf) * (1 - yf) + g2[x1, y0] * xf * (1 - yf) +
         g2[x0, y1] * (1 - xf) * yf + g2[x1, y1] * xf * yf)
    return n * (1 - zf) + m * zf


def fbm(x, y, z, octaves=3):
    v, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
    for o in range(octaves):
        v = v + amp * noise2(x * freq, y * freq, z * freq, o)
        norm += amp
        amp *= 0.5
        freq *= 2.0
    return v / norm


# ------------------------------------------------------------------ the rig
def build_rig():
    a = PropGeom("18号", os.path.join(ASSETS, "18号.mod"), 2, 0.0)
    b = PropGeom("47号", os.path.join(ASSETS, "47号.mod"), 3, a.width_in + GAP_IN)
    for p in (a, b):
        _attach_graph(p)
    return [a, b]


def _attach_graph(p):
    """Neighbour graph from real bulb positions. Diffusion, fire and lightning
    all travel along this, so they spread the way the prop is physically
    shaped rather than along the wire."""
    xy = np.stack([p.x_in, p.y_in], 1)
    d = np.linalg.norm(xy[:, None] - xy[None], axis=2)
    np.fill_diagonal(d, 1e9)
    k = 4
    idx = np.argsort(d, axis=1)[:, :k]
    w = np.exp(-(np.take_along_axis(d, idx, 1) / (p.pitch_in * 1.6)) ** 2)
    p.nb_idx = idx
    p.nb_w = w / np.maximum(1e-9, w.sum(1, keepdims=True))


def diffuse(p, v, amount):
    """One diffusion step over the neighbour graph."""
    return v * (1 - amount) + amount * (v[p.nb_idx] * p.nb_w).sum(1)


# ------------------------------------------------------------------ effects
# fn(t, props, world, st) -> list of (n,3); st is a per-section scratch dict

def aurora(t, props, w, st):
    out = []
    for p in props:
        f = fbm(p.x_in * 0.09, p.y_in * 0.05 - t * 0.42, t * 0.30, 3)
        curtain = np.clip((f - 0.34) * 2.6, 0, 1)
        curtain *= np.clip(0.35 + 0.65 * (p.y_in - p.y_in.min()) /
                           max(1e-6, float(np.ptp(p.y_in))), 0, 1)
        out.append(ramp(curtain, "aurora", floor=0.05))
    return out


def interference(t, props, w, st):
    """Two point sources; where the wavefronts meet you get fringes. The
    sources sit in world space so the pattern is continuous across both."""
    ax = w["x_min"] + 6 + 8 * math.sin(t * 0.35)
    bx = w["x_max"] - 6 + 8 * math.sin(t * 0.29 + 2)
    out = []
    for p in props:
        d1 = np.hypot(p.x_in - ax, p.y_in - 4 * math.sin(t * 0.4))
        d2 = np.hypot(p.x_in - bx, p.y_in + 4 * math.sin(t * 0.31))
        f = (np.sin(d1 * 0.75 - t * 3.0) + np.sin(d2 * 0.75 - t * 3.0)) * 0.25 + 0.5
        out.append(ramp(f ** 1.4, "oceanic", floor=0.04))
    return out


def reaction_diffusion(t, props, w, st):
    """Gray-Scott on the neighbour graph. Two chemicals, one feeding on the
    other; the classic parameters give drifting spots and worms. Running it
    on real bulb positions means the pattern follows the prop's shape."""
    if "u" not in st:
        st["u"], st["v"] = [], []
        for p in props:
            u = np.ones(p.n)
            v = np.zeros(p.n)
            seed = np.random.default_rng(3).choice(p.n, size=max(6, p.n // 6),
                                                   replace=False)
            v[seed] = 0.5; u[seed] = 0.5
            st["u"].append(u); st["v"].append(v)
    # Parameters matter enormously here and were swept on the real graph:
    # F=0.036/K=0.062 collapses to zero within ~600 iterations. F=0.055,
    # K=0.062 holds the most spatial variance (std 0.157) of the sets tried.
    # Even the stable sets converge to a frozen steady state, so a light
    # perturbation is injected to keep the pattern alive and moving.
    F, K, Du, Dv = 0.055, 0.062, 0.60, 0.30
    out = []
    for i, p in enumerate(props):
        u, v = st["u"][i], st["v"][i]
        for _ in range(8):
            lu = diffuse(p, u, 1.0) - u
            lv = diffuse(p, v, 1.0) - v
            uvv = u * v * v
            u = np.clip(u + Du * lu - uvv + F * (1 - u), 0, 1.5)
            v = np.clip(v + Dv * lv + uvv - (F + K) * v, 0, 1.2)
        if int(t * 60) % 90 == i * 45:                 # keep it from freezing
            rng = np.random.default_rng(int(t * 13) + i)
            spot = rng.integers(0, p.n)
            near = p.nb_idx[spot]
            v[near] = 0.55; u[near] = 0.35
        st["u"][i], st["v"][i] = u, v
        out.append(ramp(np.clip(v * 2.6, 0, 1), "moss", floor=0.04))
    return out


def particles(t, props, w, st):
    """Gravity, bounce, drag. Particles live in world inches so they fall
    across both props and the gap between them."""
    if "p" not in st:
        rng = np.random.default_rng(11)
        m = 40
        st["p"] = {"x": rng.uniform(w["x_min"], w["x_max"], m),
                   "y": rng.uniform(2, 16, m),
                   "vx": rng.normal(0, 5, m), "vy": np.zeros(m),
                   "c": rng.random(m)}
        st["last"] = t
    P = st["p"]
    dt = min(0.05, max(0.0, t - st["last"])); st["last"] = t
    P["vy"] -= 26.0 * dt
    P["x"] += P["vx"] * dt
    P["y"] += P["vy"] * dt
    floor = -13.0
    hit = P["y"] < floor
    P["y"][hit] = floor
    P["vy"][hit] *= -0.72
    P["vx"][hit] *= 0.88
    off = (P["x"] < w["x_min"] - 3) | (P["x"] > w["x_max"] + 3)
    P["vx"][off] *= -1
    if "trail" not in st:
        st["trail"] = [np.zeros(p.n) for p in props]
    out = []
    for pi, p in enumerate(props):
        f = np.zeros(p.n)
        col = np.zeros(p.n)
        for k in range(len(P["x"])):
            d2 = (p.x_in - P["x"][k]) ** 2 + (p.y_in - P["y"][k]) ** 2
            g = np.exp(-d2 / 30.0)      # widened twice: a narrow blob falls
                                        # between bulbs on a 2 in pitch prop
            col = np.where(g > f, P["c"][k], col)
            f = np.maximum(f, g)
        st["trail"][pi] = np.maximum(st["trail"][pi] * 0.90, f)
        f = np.maximum(f, st["trail"][pi] * 0.65)
        rgb = LUTS["spectral"][(np.clip(col, 0, 1) * 255).astype(int)]
        out.append(np.clip(rgb * f[:, None] ** 0.8, 0, 1))
    return out


def flow(t, props, w, st):
    """Advect a scalar through a noise-driven vector field: the look of
    smoke or slow water."""
    out = []
    for p in props:
        ang = fbm(p.x_in * 0.055, p.y_in * 0.055, t * 0.04, 2) * 2 * math.pi * 2
        sx = p.x_in + np.cos(ang) * 5.0
        sy = p.y_in + np.sin(ang) * 5.0
        f = fbm(sx * 0.10, sy * 0.10, t * 0.10, 3)
        out.append(ramp(np.clip((f - 0.30) * 2.2, 0, 1), "dusk", floor=0.05))
    return out


def kaleidoscope(t, props, w, st):
    """Generate the pattern in ONE sector and fold it onto the others, using
    each prop's detected symmetry -- 6 on 18号, 4 on 47号. The fold is what
    makes it read as a snowflake rather than as noise on a snowflake."""
    out = []
    for p in props:
        sector = 2 * math.pi / p.fold
        a = np.mod(p.ang, sector)
        a = np.minimum(a, sector - a)                 # mirror within sector
        f = fbm(np.cos(a) * p.r_in * 0.16 + 3 + t * 0.20,
                np.sin(a) * p.r_in * 0.16 + 3, t * 0.34, 3)
        f = np.clip((f - 0.28) * 2.4, 0, 1) * (0.35 + 0.65 * (1 - p.r) ** 0.6)
        out.append(ramp(f, "frost", floor=0.04))
    return out


def voronoi(t, props, w, st):
    """Moving seeds; each bulb takes the colour of its nearest seed, with the
    cell edges darkened so the structure is visible."""
    m = 7
    k = np.arange(m)
    sx = w["x_min"] + (w["x_max"] - w["x_min"]) * (0.5 + 0.45 * np.sin(t * 0.23 + k * 1.7))
    sy = 14 * np.sin(t * 0.31 + k * 2.3)
    hue = (k / m + t * 0.02) % 1.0
    out = []
    for p in props:
        d = np.stack([np.hypot(p.x_in - sx[i], p.y_in - sy[i]) for i in range(m)], 1)
        near = np.argsort(d, axis=1)
        d0 = np.take_along_axis(d, near[:, :1], 1)[:, 0]
        d1 = np.take_along_axis(d, near[:, 1:2], 1)[:, 0]
        edge = np.clip((d1 - d0) / 3.0, 0, 1)         # 0 on a cell border
        col = hue[near[:, 0]]
        rgb = LUTS["spectral"][(col * 255).astype(int)]
        out.append(np.clip(rgb * (0.12 + 0.88 * edge)[:, None], 0, 1))
    return out


def lightning(t, props, w, st):
    """A discharge propagates outward along the neighbour graph from a random
    bulb, then the whole prop glows and decays."""
    if "q" not in st:
        st["q"] = [np.zeros(p.n) for p in props]
        st["next"] = t
    if t >= st["next"]:
        i = np.random.default_rng(int(t * 97)).integers(0, len(props))
        p = props[i]
        st["q"][i][np.random.default_rng(int(t * 131)).integers(0, p.n)] = 1.0
        st["next"] = t + np.random.default_rng(int(t * 53)).uniform(0.18, 0.5)
    out = []
    for i, p in enumerate(props):
        q = st["q"][i]
        # decay was outrunning the spread, so a strike died before it
        # travelled: hold the charge longer and let diffusion carry further
        # 3 hops per frame so a strike crosses the prop, but the per-hop
        # decay compounds -- 0.985^3 with a further 0.94 gave 0.89/frame and
        # the strike died faster than before. Keep the net near 0.95.
        for _ in range(3):
            q = np.maximum(q * 0.997, diffuse(p, q, 0.95) * 0.999)
        q *= 0.965
        st["q"][i] = q
        out.append(ramp(np.clip(q * 3.2, 0, 1), "frost", floor=0.03))
    return out


def fire(t, props, w, st):
    """Heat injected at the bottom, diffused through the graph, buoyant --
    each bulb pulls a little heat from the bulbs below it."""
    if "h" not in st:
        st["h"] = [np.zeros(p.n) for p in props]
    out = []
    for i, p in enumerate(props):
        h = st["h"][i]
        low = p.y_in < (p.y_in.min() + p.height_in * 0.22)
        rng = np.random.default_rng(int(t * 60) + i * 17)
        h = np.where(low, np.maximum(h, rng.random(p.n) * 0.95), h)
        h = diffuse(p, h, 0.55) * 0.975
        below = p.nb_idx[np.arange(p.n)]
        lift = (p.y_in[below] < p.y_in[:, None])
        wl = np.where(lift, p.nb_w, 0)
        tot = wl.sum(1, keepdims=True)
        # A bulb with no neighbour below it has tot == 0. Dividing anyway
        # produced a zero buoyancy term and killed its heat, so the flame
        # never climbed past the bottom row. Fall back to the bulb's own heat.
        up = np.where(tot[:, 0] > 1e-9,
                      (h[below] * (wl / np.maximum(1e-9, tot))).sum(1), h)
        h = np.clip(0.45 * h + 0.55 * up, 0, 1)
        st["h"][i] = h
        out.append(ramp(np.clip(h * 1.5, 0, 1) ** 0.9, "ember", floor=0.0))
    return out


def spiral(t, props, w, st):
    """Logarithmic spiral arms rotating -- the arm count comes from the
    prop's own symmetry."""
    out = []
    for p in props:
        theta = p.ang + np.log1p(p.r_in) * 1.5 - t * 0.5
        f = (np.cos(theta * p.fold / 2) * 0.5 + 0.5) ** 2.2
        f *= 0.25 + 0.75 * (1 - p.r) ** 0.4
        out.append(ramp(f, "dusk", floor=0.03))
    return out


def vortex(t, props, w, st):
    """Counter-rotating vortices, one per prop, with the twist increasing
    toward the rim."""
    out = []
    for i, p in enumerate(props):
        d = 1 if i == 0 else -1
        swirl = p.ang + d * (t * 0.7 - p.r * 3.2)
        f = (np.sin(swirl * p.fold / 2) * 0.5 + 0.5) ** 1.8
        f = f * (0.2 + 0.8 * p.r ** 0.7)
        out.append(ramp(f, "oceanic" if i == 0 else "copper", floor=0.03))
    return out


def palette_cycle(t, props, w, st):
    """A static scalar field with the LUT index scrolling underneath it --
    a demoscene trick that costs nothing and reads as motion where there is
    none. Nothing on the prop moves; only the colour assignment does."""
    out = []
    for p in props:
        base = (p.r_in * 0.10 + np.sin(p.ang * p.fold) * 0.06) % 1.0
        f = (base + t * 0.16) % 1.0
        rgb = LUTS["spectral"][(f * 255).astype(int)]
        out.append(np.clip(rgb * (0.30 + 0.70 * (1 - p.r) ** 0.5)[:, None], 0, 1))
    return out


def gradient_morph(t, props, w, st):
    """One field, the palette crossfading through four looks -- the clearest
    demonstration that colour and structure are separable."""
    names = ["oceanic", "moss", "dusk", "ember"]
    span = 4.5
    i = int(t / span) % len(names)
    k = (t / span) % 1.0
    k = _smooth(np.clip((k - 0.65) / 0.35, 0, 1))
    a, b = names[i], names[(i + 1) % len(names)]
    out = []
    for p in props:
        f = (np.sin(p.r_in * 0.55 - t * 1.1) * 0.5 + 0.5) ** 1.5
        out.append(mix_lut(f, a, b, float(k)))
    return out


def chromatic(t, props, w, st):
    """The same pulse rendered three times at slightly different radii, one
    per colour channel. Chromatic aberration: the fringes are the point."""
    out = []
    for p in props:
        rgb = np.zeros((p.n, 3))
        for c, off in enumerate((0.0, 1.1, 2.2)):
            phase = (p.r_in + off) * 0.30 - t * 1.4
            rgb[:, c] = (np.sin(phase) * 0.5 + 0.5) ** 3.0
        out.append(np.clip(rgb * (0.25 + 0.75 * (1 - p.r) ** 0.4)[:, None], 0, 1))
    return out


def ripples(t, props, w, st):
    """Impacts drop into the world and their rings interfere."""
    if "d" not in st:
        st["d"] = []
        st["next"] = t
    if t >= st["next"]:
        rng = np.random.default_rng(int(t * 211))
        st["d"].append((t, rng.uniform(w["x_min"], w["x_max"]),
                        rng.uniform(-12, 12)))
        st["next"] = t + 0.75
        st["d"] = st["d"][-7:]
    out = []
    for p in props:
        f = np.zeros(p.n)
        for (t0, cx, cy) in st["d"]:
            age = t - t0
            d = np.hypot(p.x_in - cx, p.y_in - cy)
            ring = np.sin(d * 0.85 - age * 7.0) * np.exp(-(d - age * 9) ** 2 / 60)
            f += ring * math.exp(-age * 0.55)
        out.append(ramp(np.clip(f * 0.6 + 0.5, 0, 1), "frost", floor=0.02))
    return out


def sunrise(t, props, w, st):
    """A horizon line rising through the whole layout, palette mapped to
    height above it. Slow, and the only section that is meant to be still."""
    out = []
    horizon = -20 + (t / 13.0) * 46
    for p in props:
        above = np.clip((p.y_in - horizon) / 12.0 + 0.5, 0, 1)
        glow = np.exp(-((p.y_in - horizon) / 5.0) ** 2)
        f = np.clip(above * 0.55 + glow * 0.9, 0, 1)
        out.append(ramp(f, "ember", floor=0.02))
    return out


def finale(t, props, w, st):
    """Everything at once: an advected noise bed, interference on top,
    particles over that, and a rising palette cycle underneath."""
    a = flow(t, props, w, st)
    b = interference(t * 1.3, props, w, st)
    c = ripples(t, props, w, st)
    fade = float(np.clip(1 - max(0.0, t - 14.0) / 4.0, 0, 1))
    out = []
    for i, p in enumerate(props):
        m = np.maximum(np.maximum(a[i] * 0.85, b[i] * 0.75), c[i])
        out.append(np.clip(m * fade, 0, 1))
    return out


SECTIONS = [
    ("aurora curtains — animated noise field", aurora, 20.0),
    ("wave interference — two moving sources", interference, 18.0),
    ("reaction–diffusion — Gray-Scott on the bulb graph", reaction_diffusion, 22.0),
    ("flow field — noise advection", flow, 18.0),
    ("kaleidoscope — one sector folded by detected symmetry", kaleidoscope, 18.0),
    ("particles — gravity and bounce in world space", particles, 20.0),
    ("voronoi cells — nearest moving seed", voronoi, 16.0),
    ("lightning — discharge along the neighbour graph", lightning, 16.0),
    ("fire — buoyant heat diffusion", fire, 18.0),
    ("logarithmic spirals", spiral, 15.0),
    ("counter-rotating vortices", vortex, 15.0),
    ("palette cycling — nothing moves but the colours", palette_cycle, 15.0),
    ("gradient morph — one field, four palettes", gradient_morph, 18.0),
    ("chromatic aberration — RGB at different radii", chromatic, 14.0),
    ("ripples — impacts interfering", ripples, 16.0),
    ("sunrise — a horizon crossing the layout", sunrise, 14.0),
    ("finale — layered composite", finale, 18.0),
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
        st = {}
        n = fr(dur)
        for f in range(n):
            tt = f / FPS
            rgb = fn(tt, props, world, st)
            # short cross-fades so sections do not slam into each other
            k = min(1.0, tt / 0.9, max(0.0, (n - f) / FPS) / 0.9)
            push([r * k for r in rgb])
        dark(0.45)
    dark(1.5)
    return s, props, world, log


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "out"
    os.makedirs(out, exist_ok=True)
    s, props, world, log = build()
    n = len(s.frames)
    for p in props:
        print(f"   port {p.port+1}  {p.name}  {p.n:3d} px  {p.fold}-fold  "
              f"pitch {p.pitch_in:.2f} in")
    print(f"   world {world['x_max']-world['x_min']:.0f} in wide\n")
    s.save(os.path.join(out, "Showcase.rgb"))
    print(f"Showcase.rgb  {n} frames = {n/FPS:.0f} s ({n/FPS/60:.1f} min)  "
          f"{(s.header_size + n*s.frame_size)/1e6:.2f} MB")
    print(f"palettes: {', '.join(PALETTES)}\n")
    print("--- timing map ---")
    for st_, dur, name in log:
        print(f"   t={st_/FPS:6.1f}s +{dur:4.0f}s  {name}")
