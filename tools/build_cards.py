#!/usr/bin/env python3
"""
build_cards.py -- render one .rgb per controller from assets/layout.json.

    python tools/build_cards.py                         # 30 s "course wave" ident
    python tools/build_cards.py --seconds 60 --scene 47
    python tools/build_cards.py --effect "radial pulse" # any registry effect
    python tools/build_cards.py --only SF01 SF02        # a subset of cards

Writes out/cards/<CONTROLLER>/<Name>-<NN>.rgb, one folder per SD card, plus
out/cards/manifest.json listing every file, its channel layout, frame count
and md5. Every file has the SAME frame count -- that is what start-time sync
relies on -- and empty ports are written as 32-px stubs.

The default "course wave" is an identification pattern that is deliberately
spatially varied (never test with uniform frames):
  * base colour = the prop's GROUP colour, so a prop on the wrong card or
    wrong group shows up as the wrong hue
  * a bright band sweeps along the course (world x) every few seconds, so
    props light in map order -- a prop out of place lights at the wrong time
  * port 1 of every controller gets one white blink per second, port 2 two,
    etc., in the first 5 s, so a swapped cable is visible without a laptop
"""

import argparse, hashlib, json, math, os, sys
from collections import OrderedDict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from lightshow.layout import Layout, PROPS_DIR                      # noqa: E402
from lightshow.formats.rgbfile import Show                          # noqa: E402
from lightshow.effects import REGISTRY, Ctx, hsv, lighten, to_bytes  # noqa: E402
from lightshow.formats.props import UNITS_PER_INCH                  # noqa: E402

FPS = 60
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def hex_to_rgb01(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def course_wave(t, port_rig, layout, world_x_span, port_index):
    """-> (n, 3) perceptual 0..1 for one port at time t."""
    p = port_rig.placement
    W = port_rig.world
    g = layout.groups[p.group]
    col = hex_to_rgb01(g.get("color", "#ffffff"))
    x0, x1 = world_x_span
    # base: dim group colour, slightly brighter toward the prop's top
    ly = port_rig.local[:, 1]
    base = col[None, :] * (0.12 + 0.10 * ly / max(1e-6, ly.max()))[:, None]
    # sweep along the course: 8 s per pass, 60 in wide band
    period, width = 8.0, 60.0
    head = x0 - width + ((t / period) % 1.0) * (x1 - x0 + 2 * width)
    band = np.exp(-((W[:, 0] - head) / (width / 2)) ** 2)
    sweep = col[None, :] * band[:, None] * 0.9
    # port blinks in the first 5 s: port k blinks k times per second
    blink = np.zeros((len(W), 3))
    if t < 5.0:
        ph = (t % 1.0) * port_index * 2
        on = (ph % 2.0) < 0.6 and ph < port_index * 2
        if on:
            blink[:] = 0.7
    return lighten(base, sweep, blink)


def registry_effect(name, t, port_rig):
    fn = REGISTRY[name]
    loc = port_rig.local * UNITS_PER_INCH
    c = Ctx(loc, port_rig.placement.shape()["pitch_in"])
    c.t = t
    c.p = dict(fn.params)
    return fn(c)


def render(layout, seconds, effect=None, only=None, fps=FPS, scene=1,
           name="Show"):
    rigs = layout.controller_rigs()
    if only:
        rigs = OrderedDict((k, v) for k, v in rigs.items() if k in only)
    xs = np.concatenate([pr.world[:, 0] for r in rigs.values()
                         for pr in r.ports if pr.placement is not None])
    span = (float(xs.min()), float(xs.max()))
    n_frames = int(round(seconds * fps))
    out = OrderedDict()
    for cid, rig in rigs.items():
        show = Show(rig.channels())
        frame_size = show.frame_size
        offsets = np.cumsum([0] + rig.channels()) * 3
        frames = []
        for f in range(n_frames):
            t = f / fps
            buf = np.zeros(frame_size, np.uint8)
            for k, pr in enumerate(rig.ports):
                if pr.placement is None:
                    continue
                if effect:
                    rgb = registry_effect(effect, t, pr)
                else:
                    rgb = course_wave(t, pr, layout, span, k + 1)
                b = to_bytes(rgb).reshape(-1)
                buf[offsets[k]:offsets[k] + len(b)] = b
            frames.append(buf.tobytes())
        show.frames = frames
        out[cid] = show
    return out, n_frames, span


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layout", default=os.path.join(ROOT, "assets", "layout.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "cards"))
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--effect", default=None, help="registry effect name instead of the ident wave")
    ap.add_argument("--scene", type=int, default=1, help="scene number NN in the filename")
    ap.add_argument("--name", default="Ident", help="filename stem before -NN")
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()

    L = Layout.load(a.layout)
    errors = [m for lvl, m in L.validate() if lvl == "error"]
    if errors:
        print("layout has errors -- fix before rendering cards:")
        for m in errors:
            print("  ", m)
        sys.exit(1)

    shows, n_frames, span = render(L, a.seconds, a.effect, a.only, scene=a.scene)
    os.makedirs(a.out, exist_ok=True)
    manifest = OrderedDict(fps=FPS, frames=n_frames, seconds=a.seconds,
                           scene=a.scene, effect=a.effect or "course wave",
                           course_x_in=[round(span[0], 1), round(span[1], 1)],
                           layout=os.path.relpath(a.layout, ROOT), cards=OrderedDict())
    fname = f"{a.name}-{a.scene:02d}.rgb"
    for cid, show in shows.items():
        d = os.path.join(a.out, cid)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, fname)
        show.save(path)
        data = open(path, "rb").read()
        rig = L.controller_rigs()[cid]
        manifest["cards"][cid] = OrderedDict(
            file=os.path.relpath(path, a.out), bytes=len(data),
            md5=hashlib.md5(data).hexdigest(), channels=rig.channels(),
            ports=[(pr.placement.id if pr.placement else None) for pr in rig.ports],
            group=L.controllers.get(cid, {}).get("group"),
            frames=len(show.frames))
        assert len(show.frames) == n_frames
        print(f"{cid}: {fname}  {rig.channels()}  {len(data)/1e6:6.1f} MB  "
              f"ports {[pr.placement.id if pr.placement else '-' for pr in rig.ports]}")
    with open(os.path.join(a.out, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=1)
    print(f"\n{len(shows)} cards, {n_frames} frames each ({a.seconds:.0f} s @ {FPS} fps)"
          f" -> {a.out}/manifest.json")


if __name__ == "__main__":
    main()
