"""
palettes.py -- colours for the timeline effects.

A palette is a short list of saturated colours (hex) plus the convention that
WHITE is always available as an accent. Effects index into `colors` with
`pal.color(k)` and get an (3,) perceptual 0..1 array.

Three defaults (the owner asked for exactly three), an auto-generator that
builds palettes from a seed hue using colour-harmony rules, and custom
palettes stored in project.json.
"""

import colorsys
import numpy as np

DEFAULTS = {
    "classic": {"name": "Classic Christmas", "colors": ["#ff1a1a", "#12c437", "#ffb01e", "#ffffff"]},
    "frost":   {"name": "Frost",             "colors": ["#3fc6ff", "#ffffff", "#2050ff", "#b8f4ff"]},
    "jewel":   {"name": "Jewels",            "colors": ["#ffb300", "#00b050", "#e0102a", "#2a5cff", "#ffffff"]},
}

SCHEMES = ["analogous", "complementary", "triad", "split", "tetrad", "candy", "mono-warm", "mono-cool"]


def hex_to_rgb01(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def rgb01_to_hex(c):
    c = np.clip(np.asarray(c, float), 0, 1)
    return "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in c)


def hsv_hex(h, s=1.0, v=1.0):
    return rgb01_to_hex(colorsys.hsv_to_rgb(h % 1.0, s, v))


def generate(scheme="triad", seed_hue=None, rng=None):
    """-> {"name", "colors"}. Saturated, bright, LED-friendly. The design
    verdicts say muted colours read as ugly on the props, so saturation stays
    >= 0.85 and value at 1.0; white is appended as the accent."""
    rng = rng or np.random.default_rng()
    h = rng.random() if seed_hue is None else float(seed_hue) % 1.0
    if scheme == "analogous":
        hs = [h - 0.08, h, h + 0.08]
    elif scheme == "complementary":
        hs = [h, h + 0.5, h + 0.04]
    elif scheme == "triad":
        hs = [h, h + 1 / 3, h + 2 / 3]
    elif scheme == "split":
        hs = [h, h + 0.42, h + 0.58]
    elif scheme == "tetrad":
        hs = [h, h + 0.25, h + 0.5, h + 0.75]
    elif scheme == "candy":
        hs = [0.0, 0.95, 0.55]                     # red, pink, ice
    elif scheme == "mono-warm":
        hs = [0.02, 0.08, 0.13]                    # red-orange, orange, gold
    elif scheme == "mono-cool":
        hs = [0.55, 0.62, 0.72]                    # cyan, blue, violet
    else:
        raise ValueError(f"unknown scheme {scheme}")
    sats = [1.0, 1.0, 0.9, 1.0]
    cols = [hsv_hex(x, sats[i % len(sats)], 1.0) for i, x in enumerate(hs)]
    cols.append("#ffffff")
    return {"name": f"{scheme} {int(h * 360)}°", "colors": cols}


class Palette:
    def __init__(self, spec):
        self.name = spec.get("name", "palette")
        self.hex = list(spec.get("colors") or ["#ffffff"])
        self.rgb = np.array([hex_to_rgb01(c) for c in self.hex])       # (K,3)
        # colours that are not white, for effects that want "a colour"
        chroma = [c for c in self.rgb if (c.max() - c.min()) > 0.25]
        self.chroma = np.array(chroma) if chroma else self.rgb
        self.white = np.array([1.0, 1.0, 1.0])

    @property
    def k(self):
        return len(self.chroma)

    def color(self, i):
        """i-th chromatic colour (wraps)."""
        return self.chroma[int(i) % len(self.chroma)]

    def any(self, i):
        """i-th colour including white (wraps)."""
        return self.rgb[int(i) % len(self.rgb)]

    def pick(self, idx):
        """Vectorised: integer array -> (n,3) chromatic colours."""
        idx = np.asarray(idx, int) % len(self.chroma)
        return self.chroma[idx]

    def spec(self):
        return {"name": self.name, "colors": self.hex}


def resolve(ref, custom=None):
    """ref: a default id, a custom palette id, or an inline {"colors": [...]} -> Palette."""
    custom = custom or {}
    if isinstance(ref, dict):
        return Palette(ref)
    if ref in DEFAULTS:
        return Palette(DEFAULTS[ref])
    if ref in custom:
        return Palette(custom[ref])
    return Palette(DEFAULTS["classic"])
