#!/usr/bin/env python3
"""
rig.py -- one geometry model for every input format.

Loads .mod (single prop), .moc (controller rig) and Colorloong .xml
(full project) into the same Rig object, so downstream code never cares
which tool produced the layout.

Coordinate convention: y-UP, floats. Both .xml and .mod/.moc are y-down on
disk and get flipped by their loaders. Units are whatever the source used (.mod/.moc use a
10-unit grid; .xml uses ~1 unit per pixel spacing).
"""

import os, glob, json
from .formats.props import (load_mod, load_moc, UNITS_PER_INCH,
                            BULB_DIAMETER_UNITS)
from .formats.colorloong import load_xml, STUB_PIXELS


class RigPort:
    def __init__(self, index, pixels, name=None, light_model=None):
        self.index = index
        self.pixels = [(float(x), float(y)) for x, y in pixels]
        self.name = name or f"port{index}"
        self.light_model = light_model

    def __len__(self):
        return len(self.pixels)

    @property
    def is_empty(self):
        return not self.pixels

    @property
    def export_pixels(self):
        return STUB_PIXELS if self.is_empty else len(self.pixels)

    @property
    def bounds(self):
        if not self.pixels:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [p[0] for p in self.pixels]; ys = [p[1] for p in self.pixels]
        return min(xs), min(ys), max(xs), max(ys)


class Rig:
    def __init__(self, name, ports, source=""):
        self.name = name
        self.ports = ports
        self.source = source

    @property
    def bounds(self):
        pts = [p for pt in self.ports for p in pt.pixels]
        if not pts:
            return (0.0, 0.0, 1.0, 1.0)
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def total_pixels(self):
        return sum(len(p) for p in self.ports)

    def rgb_channels(self):
        """Pixel counts for rgbfile.Show(). Empty ports become 32 px stubs,
        matching the factory exporter -- otherwise channel offsets shift."""
        return [p.export_pixels for p in self.ports]

    def to_json(self):
        x0, y0, x1, y1 = self.bounds
        return {"name": self.name, "source": self.source,
                "bounds": [x0, y0, x1, y1],
                "unitsPerInch": UNITS_PER_INCH,
                "bulbDiameterUnits": BULB_DIAMETER_UNITS,
                "ports": [{"index": p.index, "name": p.name,
                           "empty": p.is_empty,
                           "lightModel": p.light_model,
                           "pixels": [[round(x, 2), round(y, 2)]
                                      for x, y in p.pixels]}
                          for p in self.ports]}


def from_mod(path):
    p = load_mod(path)
    nm = os.path.splitext(os.path.basename(path))[0]
    return Rig(nm, [RigPort(0, p.xy, nm)], source=path)


def from_mods(paths, gap=120.0):
    """Lay several .mod props side by side, one per port, so a folder of
    props can be previewed as a rig before a real .moc exists."""
    ports, cursor = [], 0.0
    for i, path in enumerate(paths):
        p = load_mod(path)
        x0, y0, x1, y1 = p.bounds
        off = cursor - x0
        ports.append(RigPort(i, [(x + off, y) for x, y in p.xy],
                             os.path.splitext(os.path.basename(path))[0]))
        cursor += (x1 - x0) + gap
    return Rig("props", ports, source="+".join(map(os.path.basename, paths)))


def from_moc(path):
    props, meta = load_moc(path)
    ports = [RigPort(i, pr.xy, f"port{i}") for i, pr in enumerate(props)]
    return Rig(os.path.splitext(os.path.basename(path))[0], ports, source=path)


def from_xml(path):
    proj = load_xml(path)
    ports = [RigPort(p.index, p.pixels, p.name, p.light_model)
             for p in proj.ports]
    return Rig(os.path.splitext(os.path.basename(path))[0], ports, source=path)


def load(path, **kw):
    """Dispatch on extension. A directory of .mod files loads as a rig."""
    if os.path.isdir(path):
        mods = sorted(glob.glob(os.path.join(path, "*.mod")))
        if not mods:
            raise ValueError(f"no .mod files in {path}")
        return from_mods(mods, **kw)
    ext = os.path.splitext(path)[1].lower()
    return {".mod": from_mod, ".moc": from_moc, ".xml": from_xml}[ext](path)
