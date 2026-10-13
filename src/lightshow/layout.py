#!/usr/bin/env python3
"""
layout.py -- where every prop physically is, and which controller drives it.

The .mod files say what shape a prop is. Nothing in the vendor toolchain says
WHERE it is in the yard or WHICH controller port it hangs off. That is what
`layout.json` holds, and this module is its only reader/writer.

    from lightshow.layout import Layout
    L = Layout.load("assets/layout.json")
    for cid, rig in L.controller_rigs().items():      # one SD card each
        rig.channels()        # -> [n, n, 32, n]  pixel counts, stubs applied
        rig.ports[0].world    # -> (n, 3) inches, world x/y/z for port 1

COORDINATES -- 2.5D, INCHES, Y-UP-ON-THE-MAP
    A prop is a flat panel standing upright. Its placement is:
        x, y     where its horizontal centre sits on the top-down map
        z        height of the prop's BOTTOM edge above the ground (0 = on it)
        rot      yaw in degrees: 0 = the panel runs along +x and faces -y
                 (a car driving along y looks at it face-on); 90 = along +y
        mirror   flip the prop left-right (the 左/右 pairs may need this)
    World coordinates of pixel k, given its local (lx, ly) in inches with
    lx centred and ly measured up from the prop's bottom edge:
        wx = x + lx * cos(rot),  wy = y + lx * sin(rot),  wz = z + ly

    Distances between props for physics effects come straight from these,
    so moving a prop in the editor and re-rendering is all it takes.

CONTROLLER LIMITS (GC-6004, from the vendor page -- see CLAUDE.md)
    4 ports, 1024 px per port, 4096 px per unit. One prop per port. An
    empty port is exported as a 32-px stub or every later channel shifts.

GROUPS
    Every prop is in exactly one group. Auto-assignment never puts props from
    two groups on one controller -- that is a show decision, not a limit.
"""

import json, math, os
from collections import OrderedDict

import numpy as np

from .formats.props import load_mod, UNITS_PER_INCH

HERE = os.path.dirname(os.path.abspath(__file__))
PROPS_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "assets", "props"))

PORTS = 4
MAX_PX_PORT = 1024
MAX_PX_UNIT = 4096
STUB_PX = 32
VERSION = 1


# ----------------------------------------------------------------- shapes
_shape_cache = {}


def prop_shape(mod, props_dir=PROPS_DIR):
    """-> dict with local pixel coords in inches: lx centred, ly from the
    bottom edge. Cached per file."""
    key = (props_dir, mod)
    if key not in _shape_cache:
        p = load_mod(os.path.join(props_dir, mod))          # y-up already
        xy = np.asarray(p.xy, float) / UNITS_PER_INCH
        cx = (xy[:, 0].min() + xy[:, 0].max()) / 2
        lx = xy[:, 0] - cx
        ly = xy[:, 1] - xy[:, 1].min()
        _shape_cache[key] = {
            "n": len(xy), "lx": lx, "ly": ly,
            "w": float(np.ptp(xy[:, 0])), "h": float(np.ptp(xy[:, 1])),
            "pitch_in": p.pitch_inches(),
        }
    return _shape_cache[key]


# ------------------------------------------------------------------ model
class Placement:
    FIELDS = ("id", "mod", "label", "group", "x", "y", "z", "rot", "mirror",
              "controller", "port")

    def __init__(self, id, mod, group, label=None, x=0.0, y=0.0, z=0.0,
                 rot=0.0, mirror=False, controller=None, port=None):
        self.id, self.mod, self.group = id, mod, group
        self.label = label or os.path.splitext(mod)[0]
        self.x, self.y, self.z, self.rot = float(x), float(y), float(z), float(rot)
        self.mirror = bool(mirror)
        self.controller = controller
        self.port = int(port) if port is not None else None     # 1..4

    def to_json(self):
        d = OrderedDict()
        for f in self.FIELDS:
            v = getattr(self, f)
            if f in ("x", "y", "z", "rot"):
                v = round(v, 2)
            d[f] = v
        return d

    def shape(self, props_dir=PROPS_DIR):
        return prop_shape(self.mod, props_dir)

    @property
    def n(self):
        return self.shape()["n"]

    def local(self):
        """(n, 2) local inches: lx (mirror applied), ly from bottom."""
        s = self.shape()
        lx = -s["lx"] if self.mirror else s["lx"]
        return np.column_stack([lx, s["ly"]])

    def world(self):
        """(n, 3) world inches."""
        loc = self.local()
        a = math.radians(self.rot)
        wx = self.x + loc[:, 0] * math.cos(a)
        wy = self.y + loc[:, 0] * math.sin(a)
        wz = self.z + loc[:, 1]
        return np.column_stack([wx, wy, wz])

    def centre(self):
        s = self.shape()
        return np.array([self.x, self.y, self.z + s["h"] / 2])


class PortRig:
    def __init__(self, port, placement):
        self.port = port                       # 1..4
        self.placement = placement             # None = empty port

    @property
    def n(self):
        return 0 if self.placement is None else self.placement.n

    @property
    def export_px(self):
        return STUB_PX if self.placement is None else self.n

    @property
    def world(self):
        return None if self.placement is None else self.placement.world()

    @property
    def local(self):
        return None if self.placement is None else self.placement.local()


class ControllerRig:
    """Everything the renderer needs to write one SD card."""

    def __init__(self, cid, meta, ports):
        self.id, self.meta, self.ports = cid, meta, ports   # ports: 4 PortRig

    def channels(self):
        return [p.export_px for p in self.ports]

    def props(self):
        return [p.placement for p in self.ports if p.placement is not None]

    def total_px(self):
        return sum(p.n for p in self.ports)


class Layout:
    def __init__(self, groups=None, props=None, controllers=None, meta=None):
        self.groups = OrderedDict(groups or {})
        self.props = list(props or [])
        self.controllers = OrderedDict(controllers or {})
        self.meta = meta or {}

    # ------------------------------------------------------------- io
    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        props = [Placement(**{k: v for k, v in p.items() if k in Placement.FIELDS})
                 for p in d.get("props", [])]
        L = cls(d.get("groups", {}), props, d.get("controllers", {}),
                {k: v for k, v in d.items()
                 if k not in ("groups", "props", "controllers")})
        L.path = path
        return L

    def to_json(self):
        d = OrderedDict()
        d["version"] = VERSION
        d["units"] = "in"
        d["notes"] = self.meta.get("notes", "")
        if self.meta.get("map"):                       # site-plan backdrop for the grid: file, in/px, placement, opacity
            d["map"] = self.meta["map"]
        if self.meta.get("route"):                     # the cars' path through the show: {points: [[x, y], ...] inches, speed_mph, eye_in}
            d["route"] = self.meta["route"]
        d["groups"] = self.groups
        d["controllers"] = self.controllers
        d["props"] = [p.to_json() for p in self.props]
        return d

    def save(self, path=None):
        path = path or self.path
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_json(), fh, ensure_ascii=False, indent=1)
        return path

    # -------------------------------------------------------- queries
    def prop(self, pid):
        for p in self.props:
            if p.id == pid:
                return p
        raise KeyError(pid)

    def in_group(self, gid):
        return [p for p in self.props if p.group == gid]

    def total_px(self):
        return sum(p.n for p in self.props)

    def group_of_controller(self, cid):
        gs = {p.group for p in self.props if p.controller == cid}
        return gs

    def controller_rigs(self):
        """-> OrderedDict cid -> ControllerRig. Only controllers that have at
        least one prop, plus any declared in `controllers` (empty cards)."""
        cids = list(self.controllers.keys())
        for p in self.props:
            if p.controller and p.controller not in cids:
                cids.append(p.controller)
        out = OrderedDict()
        for cid in cids:
            ports = [PortRig(k, None) for k in range(1, PORTS + 1)]
            for p in self.props:
                if p.controller == cid and p.port:
                    ports[p.port - 1] = PortRig(p.port, p)
            out[cid] = ControllerRig(cid, self.controllers.get(cid, {}), ports)
        return out

    def group_world(self, gid):
        """Per-prop centres (P,3) and pairwise distances (P,P) for one group --
        the inputs a multi-prop effect needs."""
        ps = self.in_group(gid)
        C = np.array([p.centre() for p in ps]) if ps else np.zeros((0, 3))
        D = np.linalg.norm(C[:, None, :] - C[None, :, :], axis=2) if len(ps) else C
        return ps, C, D

    # ------------------------------------------------------ validation
    def validate(self):
        """-> list of (level, message). level is 'error' or 'warn'.
        Errors mean the export would be wrong on hardware."""
        issues = []
        seen = {}
        for p in self.props:
            if p.group not in self.groups:
                issues.append(("error", f"{p.id}: group '{p.group}' not defined"))
            if p.n > MAX_PX_PORT:
                issues.append(("error", f"{p.id}: {p.n} px exceeds {MAX_PX_PORT}/port"))
            if (p.controller is None) != (p.port is None):
                issues.append(("error", f"{p.id}: controller and port must be set together"))
            if p.controller is None:
                issues.append(("warn", f"{p.id}: not assigned to a controller"))
                continue
            if not (1 <= (p.port or 0) <= PORTS):
                issues.append(("error", f"{p.id}: port {p.port} not in 1..{PORTS}"))
            key = (p.controller, p.port)
            if key in seen:
                issues.append(("error", f"{p.controller} port {p.port}: both "
                                        f"{seen[key]} and {p.id}"))
            seen[key] = p.id
        for cid, rig in self.controller_rigs().items():
            # sum over props, not ports: a double-booked port would hide a prop
            px = sum(p.n for p in self.props if p.controller == cid)
            if px > MAX_PX_UNIT:
                issues.append(("error", f"{cid}: {px} px exceeds {MAX_PX_UNIT}/unit"))
            gs = self.group_of_controller(cid)
            if len(gs) > 1:
                issues.append(("warn", f"{cid}: spans groups {sorted(gs)}"))
            if rig.total_px() == 0:
                issues.append(("warn", f"{cid}: declared but drives nothing"))
        return issues

    # --------------------------------------------------- auto-assign
    def auto_assign(self, group=None, keep=False, along="x"):
        """Assign controllers/ports per group. Props are walked in map order
        (along x by default) and packed 4 to a controller so a controller's
        props are neighbours -- cable runs stay short and a group never
        shares a controller. With keep=True props that already have a valid
        assignment are left alone and only the rest are packed.

        Controller ids are <GROUP PREFIX><NN>, e.g. SF01, SF02 for
        snowflakes. Returns the list of controller ids touched."""
        groups = [group] if group else list(self.groups.keys())
        touched = []
        for gid in groups:
            g = self.groups.get(gid, {})
            prefix = g.get("prefix") or gid[:2].upper()
            ps = self.in_group(gid)
            ps.sort(key=lambda p: (getattr(p, along), p.y if along == "x" else p.x))
            if keep:
                todo = [p for p in ps if not (p.controller and p.port)]
                used = {(p.controller, p.port) for p in ps if p.controller}
                existing = sorted({p.controller for p in ps if p.controller})
            else:
                todo, used, existing = ps, set(), []
                for p in ps:
                    p.controller = p.port = None
                # drop this group's old controllers
                for cid in [c for c in self.controllers
                            if self.controllers[c].get("group") == gid]:
                    del self.controllers[cid]
            n = 0
            for cid in existing:
                try:
                    n = max(n, int(cid[len(prefix):]))
                except ValueError:
                    pass
            cur, cur_px, port = None, 0, PORTS + 1
            for p in todo:
                if p.n > MAX_PX_PORT:
                    continue                            # validate() reports it
                if cur is None or port > PORTS or cur_px + p.n > MAX_PX_UNIT:
                    n += 1
                    cur, cur_px, port = f"{prefix}{n:02d}", 0, 1
                    self.controllers[cur] = {"model": "GC-6004", "dmx_addr": 1,
                                             "group": gid}
                    touched.append(cur)
                while (cur, port) in used:
                    port += 1
                    if port > PORTS:
                        break
                if port > PORTS:
                    n += 1
                    cur, cur_px, port = f"{prefix}{n:02d}", 0, 1
                    self.controllers[cur] = {"model": "GC-6004", "dmx_addr": 1,
                                             "group": gid}
                    touched.append(cur)
                p.controller, p.port = cur, port
                used.add((cur, port))
                cur_px += p.n
                port += 1
            # controller map position: centroid of its props
            for cid in {p.controller for p in ps if p.controller}:
                mine = [p for p in ps if p.controller == cid]
                self.controllers.setdefault(cid, {"model": "GC-6004", "dmx_addr": 1,
                                                  "group": gid})
                self.controllers[cid]["x"] = round(sum(p.x for p in mine) / len(mine), 1)
                self.controllers[cid]["y"] = round(sum(p.y for p in mine) / len(mine) - 36, 1)
        return touched

    # ------------------------------------------------------ summary
    def summary(self):
        L = [f"{len(self.props)} props, {self.total_px()} px, "
             f"{len(self.groups)} groups, {len(self.controller_rigs())} controllers"]
        for gid, g in self.groups.items():
            ps = self.in_group(gid)
            cids = sorted({p.controller for p in ps if p.controller})
            L.append(f"  {g.get('label', gid):18s} {len(ps):3d} props "
                     f"{sum(p.n for p in ps):6d} px  controllers: {', '.join(cids) or '-'}")
        for lvl, msg in self.validate():
            L.append(f"  {lvl.upper():5s} {msg}")
        return "\n".join(L)


# ------------------------------------------------------------ for the UI
def shapes_json(layout, props_dir=PROPS_DIR):
    """Local shapes for every prop the layout uses -- what the HTML editor
    embeds so it needs no server."""
    out = {}
    for p in layout.props:
        if p.mod in out:
            continue
        s = prop_shape(p.mod, props_dir)
        out[p.mod] = {"n": s["n"], "w": round(s["w"], 2), "h": round(s["h"], 2),
                      "pitch_in": round(s["pitch_in"], 3),
                      "lx": [round(float(v), 2) for v in s["lx"]],
                      "ly": [round(float(v), 2) for v in s["ly"]]}
    return out


if __name__ == "__main__":
    import sys
    L = Layout.load(sys.argv[1] if len(sys.argv) > 1 else
                    os.path.join(PROPS_DIR, "..", "layout.json"))
    print(L.summary())
