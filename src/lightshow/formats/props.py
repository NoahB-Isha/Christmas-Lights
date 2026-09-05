#!/usr/bin/env python3
"""
props.py -- read the Chinese LED software's prop/rig files.

FORMATS (both plain JSON, UTF-8)

  .mod  a single prop model
        { "dotCount": int,
          "dots": [ {"x": int, "y": int}, ... ],   # len == dotCount
          "lampRad": 5,
          "version": "1.0" }

  .moc  a controller rig: which prop geometry sits on which port
        { "controlType": 4,
          "portCount": 4,
          "ports": [ {"portNum": 0, "dotCount": int, "dots": [...] }, ... ],
          "lampRad": 5,
          "version": "1.0" }

KEY FACTS ESTABLISHED

* dots[i] is pixel i in WIRE ORDER. Consecutive-dot distances are uniform
  with zero large jumps (median step 10-41 units depending on prop), so
  the list order matches the LED chain order. This is what lets a 2D
  effect be sampled per pixel.
* Coordinates snap to a 10-unit grid, y increases upward.
* A .moc's per-port dotCount is exactly what the .rgb header stores as a
  channel byte count / 3. So .moc defines the rig and .rgb is the render
  for it:  rgb_channel_bytes[i] == moc.ports[i].dotCount * 3
* Prop dotCounts match the channel sizes seen in real .rgb files
  (247, 179, 98, 176, 193 all appear directly).

This is the missing half of the toolchain: the .rgb file carries no
geometry beyond pixel counts, so without the .moc/.mod you can only
author in 1D pixel index. With them you can author in real 2D space.
"""

import json, math, glob, os

# ---- physical scale -------------------------------------------------------
# Every .mod/.moc carries lampRad = 5, i.e. a bulb RADIUS of 5 units, so a
# bulb is 10 units across. The bulbs are physically ~0.5 in, which fixes the
# coordinate scale at 20 units per inch. Cross-check: that makes the prop
# library 14-46 in wide and 38-51 in tall (3-4 ft), correct for yard props,
# and it makes every pixel pitch land on a clean value (0.5, 1.0, 2.0 in).
UNITS_PER_INCH = 20.0
BULB_DIAMETER_UNITS = 10.0        # = 0.5 in


def units_to_inches(u):
    return u / UNITS_PER_INCH


class Prop:
    """One prop or one port's geometry."""

    def __init__(self, name, dots, lamp_rad=5):
        self.name = name
        self.xy = [(d["x"], d["y"]) for d in dots]
        self.lamp_rad = lamp_rad

    def __len__(self):
        return len(self.xy)

    @property
    def bounds(self):
        xs = [p[0] for p in self.xy]; ys = [p[1] for p in self.xy]
        return min(xs), min(ys), max(xs), max(ys)

    def normalized(self):
        """-> [(u,v)] with u,v in 0..1, v=0 at the bottom. Aspect preserved."""
        x0, y0, x1, y1 = self.bounds
        w = (x1 - x0) or 1
        h = (y1 - y0) or 1
        s = max(w, h)
        return [(((x - x0) - (w - s) / 2) / s, ((y - y0) - (h - s) / 2) / s)
                for x, y in self.xy]

    def centered(self):
        """-> [(u,v)] centred on 0, longest axis spanning -1..1."""
        x0, y0, x1, y1 = self.bounds
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        s = max(x1 - x0, y1 - y0) / 2 or 1
        return [((x - cx) / s, (y - cy) / s) for x, y in self.xy]

    def pitch(self):
        """Median distance between consecutive bulbs, in rig units."""
        if len(self.xy) < 2:
            return 0.0
        d = sorted(math.dist(self.xy[i], self.xy[i + 1])
                   for i in range(len(self.xy) - 1))
        return d[len(d) // 2]

    def pitch_inches(self):
        return units_to_inches(self.pitch())

    def fill_ratio(self):
        """Bulb diameter / pitch. 1.0 means bulbs touch; 0.25 means big gaps.
        Ranges 0.24-1.00 across the observed library -- a 4x spread, which is
        why effect feature sizes must be specified in inches, not in
        normalized coordinates."""
        p = self.pitch()
        return (BULB_DIAMETER_UNITS / p) if p else 0.0

    def size_inches(self):
        x0, y0, x1, y1 = self.bounds
        return units_to_inches(x1 - x0), units_to_inches(y1 - y0)

    def wire_length(self):
        return sum(math.dist(self.xy[i], self.xy[i + 1])
                   for i in range(len(self.xy) - 1))


def load_mod(path):
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    p = Prop(os.path.basename(path), d["dots"], d.get("lampRad", 5))
    if d.get("dotCount") != len(p):
        print(f"  WARNING {path}: dotCount={d.get('dotCount')} but "
              f"{len(p)} dots present")
    return p


def load_moc(path):
    """-> (list of Prop in port order, meta dict)"""
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    ports = sorted(d["ports"], key=lambda p: p["portNum"])
    props = [Prop(f"port{p['portNum']}", p["dots"], d.get("lampRad", 5))
             for p in ports]
    meta = {"controlType": d.get("controlType"),
            "portCount": d.get("portCount"),
            "version": d.get("version")}
    if meta["portCount"] != len(props):
        print(f"  WARNING {path}: portCount={meta['portCount']} but "
              f"{len(props)} ports present")
    return props, meta


def rgb_channels(props):
    """pixel counts to pass straight to rgbfile.Show()."""
    return [len(p) for p in props]


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    for f in sorted(glob.glob(os.path.join(d, "*.mod"))):
        p = load_mod(f)
        x0, y0, x1, y1 = p.bounds
        print(f"{os.path.basename(f):24s} n={len(p):4d}  "
              f"bbox {x1-x0:4d} x {y1-y0:4d}  wire={p.wire_length():7.0f}")
    for f in sorted(glob.glob(os.path.join(d, "*.moc"))):
        props, meta = load_moc(f)
        print(f"\n{os.path.basename(f)}  controlType={meta['controlType']} "
              f"portCount={meta['portCount']}")
        for i, p in enumerate(props):
            x0, y0, x1, y1 = p.bounds
            print(f"   port{i}: n={len(p):4d}  bbox {x1-x0:4d} x {y1-y0:4d}")
        print(f"   -> rgb channels {rgb_channels(props)}  "
              f"total {sum(rgb_channels(props))} px  "
              f"frame {sum(rgb_channels(props))*3} B")
