"""util.py -- shared helpers for the effect packs."""

import math
import numpy as np


def smoothstep(e0, e1, x):
    d = np.asarray(e1, float) - np.asarray(e0, float)
    d = np.where(np.abs(d) < 1e-9, 1e-9, d)
    t = np.clip((np.asarray(x, float) - e0) / d, 0, 1)
    return t * t * (3 - 2 * t)


def noise(x, z, t, seed=0.0):
    """Cheap smooth 2D+time noise in 0..1 (sum of incommensurate sines).
    x, z in 'cells' (divide inches by a scale first)."""
    v = (np.sin(x * 1.7 + t * 0.9 + seed) + np.sin(z * 2.3 - t * 0.7 + seed * 1.3)
         + np.sin((x + z) * 1.1 + t * 1.3 + seed * 0.7) + 0.6 * np.sin(x * 3.9 - z * 2.9 + t * 2.1 + seed))
    return (v / 3.6 + 1) / 2


def fbm(x, z, t, seed=0.0, octaves=3):
    """Fractal noise 0..1: several octaves of noise() at doubling frequency, halving weight.
    Gives the ragged, flickery texture that a single smooth noise() lacks (fire, smoke, snow depth)."""
    v = 0.0; w = 1.0; tot = 0.0
    for k in range(octaves):
        v = v + w * noise(x * (2 ** k), z * (2 ** k), t * (1 + 0.6 * k), seed + 3.1 * k)
        tot += w; w *= 0.5
    return v / tot


_trees = {}


def resample(pr, F, dx, dy, pitch_mult=1.6):
    """Look up the colour each bulb would see if the picture were displaced by (dx, dy)
    LOCAL inches (per-bulb arrays or scalars): nearest-bulb sampling with a KD-tree cached per
    prop. A bulb whose source lands off the prop (farther than pitch * pitch_mult from any bulb)
    goes dark. This is how modifiers slide / warp / shake the picture on a fixed bulb map."""
    from scipy.spatial import cKDTree
    tree = _trees.get(pr.id)
    if tree is None or tree.n != pr.n:
        tree = _trees[pr.id] = cKDTree(np.column_stack([pr.lx, pr.ly]))
    q = np.column_stack([pr.lx - np.broadcast_to(dx, pr.n), pr.ly - np.broadcast_to(dy, pr.n)])
    d, i = tree.query(q, k=1)
    out = F[i].copy()
    out[d > pr.pitch * pitch_mult] = 0.0
    return out


def follow(st, key, target, dt, attack, release):
    """One-pole envelope follower with separate attack/release (seconds)."""
    cur = st.get(key)
    target = np.asarray(target, float)
    if cur is None or np.shape(cur) != np.shape(target):
        st[key] = target.copy()
        return st[key]
    tau = np.where(target > cur, attack, release)
    k = 1 - np.exp(-dt / np.maximum(1e-3, tau))
    cur = cur + (target - cur) * k
    st[key] = cur
    return cur


def heat(v, kind="fire"):
    """Heat colour map: v 0..1 -> (n,3). fire: black-red-orange-yellow-white; gas: blue flame; green."""
    v = np.clip(np.asarray(v, float), 0, 1)
    if kind == "gas":
        r = np.clip(v * 1.6 - 0.9, 0, 1); g = np.clip(v * 1.4 - 0.3, 0, 1); b = np.clip(v * 2.2, 0, 1)
    elif kind == "green":
        r = np.clip(v * 2.0 - 1.1, 0, 1); g = np.clip(v * 1.8, 0, 1); b = np.clip(v * 1.2 - 0.5, 0, 1)
    else:
        r = np.clip(v * 2.4, 0, 1); g = np.clip(v * 2.0 - 0.6, 0, 1); b = np.clip(v * 3.0 - 2.1, 0, 1)
    return np.stack([r, g, b], 1)


def gradient(pal, u):
    """Smooth interpolation through the palette's chromatic colours, u in 0..1 (wraps)."""
    u = np.asarray(u, float) % 1.0
    k = pal.k
    pos = u * k
    i0 = np.floor(pos).astype(int) % k
    i1 = (i0 + 1) % k
    f = (pos - np.floor(pos))[:, None]
    return pal.chroma[i0] * (1 - f) + pal.chroma[i1] * f


def per_pixel_rng(pr, slot, salt=0):
    return np.random.default_rng((int(slot) * 7919 + pr.idx * 131 + salt) % (2 ** 32))


def rng(seed):
    """default_rng that tolerates negative / huge seeds (local times can be negative
    while a transition runs an animation before its clip starts)."""
    return np.random.default_rng(int(seed) % (2 ** 32))


def glints(pr, t, rate=0.4, seed=0, sharp=14.0, spread=0.8):
    """Per-bulb specular glints in 0..1: every bulb flashes once per ~1/rate s at
    its own phase and speed -- sharp attack, quick decay (the way a bauble catches
    a light), not a sine wobble."""
    r = rng(pr.idx * 97 + seed)
    ph = r.random(pr.n); sp = 1 - spread / 2 + spread * r.random(pr.n)
    u = (t * rate * sp + ph) % 1.0
    return np.exp(-u * sharp)


def blob(pr, cx, cy, radius):
    """Soft disc in the prop's LOCAL inches around (cx, cy): 1 at the centre, 0 at `radius`."""
    d = np.hypot(pr.lx - cx, pr.ly - cy)
    return np.clip(1 - d / max(1e-3, radius), 0, 1)


def baubles(pr, cx, cy, radius, cols, glint=0.0, light=(-0.35, 0.35)):
    """Shaded glass spheres in LOCAL inches, all at once: saturated colour, darker
    rim, a white highlight offset toward `light`, an optional per-ball glint 0..1.
    cx, cy, cols (k,3), glint are per ball. -> (rgb (n,3), coverage (n,) 0..1);
    where balls overlap the nearer (smaller d01) one wins."""
    cx = np.atleast_1d(np.asarray(cx, float)); cy = np.atleast_1d(np.asarray(cy, float))
    cols = np.atleast_2d(np.asarray(cols, float)); glint = np.broadcast_to(np.asarray(glint, float), cx.shape)
    d01 = np.hypot(pr.lx[:, None] - cx[None, :], pr.ly[:, None] - cy[None, :]) / max(1e-3, radius)     # (n,k)
    k = np.argmin(d01, axis=1)                                                                          # nearest ball per bulb
    d = d01[np.arange(pr.n), k]
    cover = smoothstep(1.0, 0.8, d)
    sphere = np.sqrt(np.clip(1 - d ** 2, 0, 1))
    shade = 0.35 + 0.65 * sphere
    hx, hy = cx[k] + light[0] * radius, cy[k] + light[1] * radius
    hi = np.exp(-(np.hypot(pr.lx - hx, pr.ly - hy) / (0.33 * radius)) ** 2)
    rgb = cols[k] * shade[:, None]
    rgb = np.maximum(rgb, (0.85 * hi * sphere)[:, None])
    rgb = np.maximum(rgb, (glint[k] * sphere)[:, None])
    return rgb * cover[:, None], cover


def bauble(pr, cx, cy, radius, col, light=(-0.35, 0.35), glint=0.0):
    """One shaded sphere (see baubles)."""
    return baubles(pr, [cx], [cy], radius, [col], [glint], light)


def wire_offsets(g):
    """Start index of every prop along the group's concatenated wire (props left->right) and the total length."""
    off, total = {}, 0
    for p in g.props:
        off[p.id] = total; total += p.n
    return off, total


def hue_rotate(rgb, delta, sat=1.0):
    """Rotate hue by `delta` turns (0..1) and optionally scale saturation,
    keeping value. Vectorised over an (n,3) frame; cheap enough per frame."""
    rgb = np.clip(np.asarray(rgb, float), 0, 1)
    mx = rgb.max(1); mn = rgb.min(1); d = mx - mn
    v = mx
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0.0) * sat
    s = np.clip(s, 0, 1)
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    h = np.zeros_like(mx)
    nz = d > 1e-6
    h = np.where(nz & (mx == r), ((g - b) / np.maximum(d, 1e-6)) % 6, h)
    h = np.where(nz & (mx == g), (b - r) / np.maximum(d, 1e-6) + 2, h)
    h = np.where(nz & (mx == b), (r - g) / np.maximum(d, 1e-6) + 4, h)
    h = (h / 6.0 + delta) % 1.0
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    pp = v * (1 - s); q = v * (1 - s * f); tt = v * (1 - s * (1 - f))
    out = np.zeros_like(rgb)
    for k, trio in enumerate([(v, tt, pp), (q, v, pp), (pp, v, tt), (pp, q, v), (tt, pp, v), (v, pp, q)]):
        msk = i == k
        for ch in range(3):
            out[:, ch][msk] = trio[ch][msk]
    return out
