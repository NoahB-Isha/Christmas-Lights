#!/usr/bin/env python3
"""
render_show.py -- render show.yaml to per-controller cards (and a preview).

    python tools/render_show.py --layout assets/bench.json --from 0 --to 1:23 --slug carol_ice_storm
    python tools/render_show.py --layout assets/layout.json                  # the whole show
    python tools/render_show.py --layout assets/bench.json --song 1          # one song by number

Output: out/show_<layout>/<CTRL>/Sc-<scene>-01.rgb + manifest.json, and a
brightness report per song. --player also writes an audio-synced HTML preview.

FILENAMES: Sc-<scene>-01.rgb (Sc-01-01.rgb, Sc-02-01.rgb ...). Confirmed on the
GC-6004: the FIRST number is the scene; Sc-01-NN-<desc> names all read as scene 1.
Scene 1 is the music show.
"""

import argparse, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from lightshow.show import ShowRenderer, parse_t, FPS   # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", default=os.path.join(ROOT, "assets", "show", "show.yaml"))
    ap.add_argument("--layout", default=os.path.join(ROOT, "assets", "bench.json"))
    ap.add_argument("--from", dest="t0", default=None)
    ap.add_argument("--to", dest="t1", default=None)
    ap.add_argument("--song", type=int, default=None, help="render just song N (1-based)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--scene", type=int, default=1)
    ap.add_argument("--slug", default="show")
    ap.add_argument("--player", action="store_true", help="also write an HTML preview")
    ap.add_argument("--no-cards", action="store_true", help="skip writing .rgb cards (fast preview iteration)")
    a = ap.parse_args()

    R = ShowRenderer(a.show, a.layout)
    if a.song:
        s = R.songs[a.song - 1]; t0, t1 = s["from"], s["to"]
    else:
        t0 = parse_t(a.t0) if a.t0 else 0.0
        t1 = parse_t(a.t1) if a.t1 else R.duration
    lname = os.path.splitext(os.path.basename(a.layout))[0]
    out = a.out or os.path.join(ROOT, "out", f"show_{lname}")

    print(f"{len(R.props)} props, {len(R.songs)} songs, {len(R.sections)} sections; "
          f"rendering {t0:.1f}-{t1:.1f} s ({(t1-t0)*FPS:.0f} frames)")
    tic = time.time()
    frames = R.render(t0, t1, progress=lambda f, n: print(f"  {f}/{n}", end="\r"))
    print(f"  rendered in {time.time()-tic:.1f} s          ")
    if not a.no_cards:
        man = R.write_cards(frames, out, scene=a.scene, slug=a.slug, fps=FPS)
        for cid, c in man["cards"].items():
            print(f"  {cid}: {c['file']}  {c['channels']}  {c['bytes']/1e6:.1f} MB")
    os.makedirs(out, exist_ok=True)
    print("\nbrightness (share of time >= 60%, non-exempt looks | mean level | all looks):")
    for name, share, mean, share_all in R.brightness_report(frames, t0):
        print(f"  {share:5.0f}%   {mean:.2f}   {share_all:5.0f}%   {name}")
    if a.player:
        from make_show_player import build_player
        html = os.path.join(out, "player.html")
        build_player(R, frames, t0, html)
        print(f"\npreview: {html}")


if __name__ == "__main__":
    main()
