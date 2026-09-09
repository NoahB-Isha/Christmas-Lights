#!/usr/bin/env python3
"""
regions.py -- named pixel groups inside a prop (Santa's coat, boots, hat,
face; the bell and its ribbon).

A .mod knows where each bulb is, not what it depicts. Regions add that:

    assets/paint/<mod stem>.json
    {
      "mod": "61号.mod",
      "regions": {
        "hat":   {"color": "#d0232a", "pixels": [0, 1, 2, ...]},
        "face":  {"color": "#f2c9a0", "pixels": [...]},
        "coat":  {"color": "#d0232a", "pixels": [...]},
        ...
      }
    }

Pixels are wire indices. A pixel may belong to one region; unlisted pixels
fall into the implicit region "rest". The colour is the prop's painted
colour there -- the "Drawn" theme uses it directly, and it is a handy hint
for AI when proposing regions.

Authoring: `make paint` -> out/paint.html, click/lasso, name, export. The
tool seeds each prop with AUTO-SUGGESTED regions (see suggest()) -- runs of
the wire between geometric jumps -- which are usually the manufacturer's
own segments (they wire one feature at a time), so most of the work is
naming and merging.
"""

import json, os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PAINT_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "assets", "paint"))


def stem(mod):
    return os.path.splitext(os.path.basename(mod))[0]


def load(mod, paint_dir=PAINT_DIR):
    """-> OrderedDict name -> {"color": hex, "pixels": [int]} or {} if unpainted."""
    path = os.path.join(paint_dir, stem(mod) + ".json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return d.get("regions", {})


def save(mod, regions, paint_dir=PAINT_DIR):
    os.makedirs(paint_dir, exist_ok=True)
    path = os.path.join(paint_dir, stem(mod) + ".json")
    # compact: one region per line so the file stays diffable
    lines = [f'  "{name}": {{"color": "{r.get("color", "#ffffff")}", "pixels": {json.dumps(sorted(set(r.get("pixels", []))))}}}'
             for name, r in regions.items()]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('{\n "mod": ' + json.dumps(os.path.basename(mod), ensure_ascii=False) + ',\n "regions": {\n'
                 + ",\n".join(lines) + "\n }\n}\n")
    return path


def masks(regions, n):
    """-> {name: bool array(n)}, plus "rest" for unassigned pixels."""
    out = {}
    taken = np.zeros(n, bool)
    for name, r in regions.items():
        m = np.zeros(n, bool)
        idx = [i for i in r.get("pixels", []) if 0 <= i < n]
        m[idx] = True
        out[name] = m
        taken |= m
    if (~taken).any():
        out["rest"] = ~taken
    return out


def suggest(xy, jump_factor=2.6, min_run=4):
    """Auto-suggest regions from wire order: cut the wire wherever the step
    between consecutive bulbs is much larger than the median pitch (the wire
    jumped to a new feature), then merge tiny runs into their neighbour.
    xy: (n,2). -> list of index arrays, in wire order."""
    xy = np.asarray(xy, float)
    n = len(xy)
    if n < 2:
        return [np.arange(n)]
    step = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    pitch = np.median(step)
    cuts = [0] + [i + 1 for i in range(len(step)) if step[i] > jump_factor * pitch] + [n]
    runs = [np.arange(a, b) for a, b in zip(cuts[:-1], cuts[1:]) if b > a]
    # merge short runs into the previous run
    merged = []
    for r in runs:
        if merged and len(r) < min_run:
            merged[-1] = np.concatenate([merged[-1], r])
        else:
            merged.append(r)
    return merged


def hex_to_rgb01(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])
