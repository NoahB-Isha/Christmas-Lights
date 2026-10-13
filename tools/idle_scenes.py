"""
idle_scenes.py -- the between-shows filler patterns, rendered straight to .rgb cards.

Each pattern is a tiny Studio project with no audio (the engine feeds a 120 BPM click, so
nothing here is beat-driven), rendered as one scene per pattern with a seamless loop: the
last LOOP_S seconds crossfade into the first. Slow looks only -- these hold the yard for
half an hour at a time, so nothing flashes and nothing repeats on a short period.

    python tools/idle_scenes.py                       # bench layout, scenes 1..N into out/idle/
    python tools/idle_scenes.py --layout assets/layout.json --out out/idle_yard --first-scene 2
    python tools/idle_scenes.py --only starscape,fireside --seconds 60   # quick look

Writes out/idle/<NN-name>/<controller>/Sc-NN-01.rgb + manifest.json, a contact sheet PNG per
pattern (what it looks like at six moments) and an index.md listing the scenes.
"""

import argparse, json, os, sys, time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from lightshow import layout as LAY                       # noqa: E402
from lightshow.studio.project import Project              # noqa: E402
from lightshow.studio.render import render_cards          # noqa: E402
from lightshow.studio.engine import Renderer              # noqa: E402

SECONDS = 120.0
FPS = 30.3
LOOP_S = 4.0

# ------------------------------------------------------------------ the patterns
# (name, description, palettes, clips) -- clips are (kind, effect, t0, t1, palette, params)
# t1 = None means "to the end". Anim clips on the one track must not overlap; a crossfade
# transition spans the join. Everything slow: nothing cycles faster than ~10 s.
WARM_GOLD = {"name": "idle golds", "colors": ["#ffb01e", "#ff7a00", "#fff0b8", "#ffffff"]}
ICE_PAL = {"name": "idle ice", "colors": ["#3fc6ff", "#2050ff", "#b8f4ff", "#ffffff"]}
FIESTA = {"name": "idle fiesta", "colors": ["#fa0000", "#ff961f", "#ff007b", "#ffffff"]}

PATTERNS = [
    ("starscape", "Starscape -- slow frost starfield, each bulb on its own clock, with a shooting star crossing the row every so often",
     {}, [
         ("anim", "starfield", 0, None, "frost", {"stars": 12, "speed": 0.6, "glow": 0.22, "breathe": True}),
         ("mod", "mod_sparkle", 0, None, "frost", {"density": 0.6, "life_s": 0.5, "color": "frost", "level": 0.8}),
     ]),
    ("ice-sculpture", "Ice sculpture -- the props carved from ice: clear and cloudy patches drifting, veins, a highlight circling, a crack now and then; snow on top",
     {}, [
         ("anim", "ice_sculpture", 0, None, "frost", {"sheen_s": 18.0, "sparkle": 0.35, "cracks": 0.3}),
         ("mod", "mod_snowcap", 0, None, "frost", {"depth": 0.14, "sparkle": 0.4}),
     ]),
    ("fireside", "Fireside -- a dark bed of pulsing coals with sparks lifting off and fading; every two minutes the fire is never the same",
     {}, [
         ("anim", "fire_embers", 0, None, "classic", {"bed": 0.55, "bed_height": 0.4, "sparks": 10, "rise": 10.0, "wander": 0.8, "bright": 0.3}),
     ]),
    ("fairy-lights", "Fairy lights & ornaments -- warm mini lights fading in and out over a dark tree, melting into the decorated tree and back",
     {}, [
         ("anim", "fairy_lights", 0, 62, "classic", {"density": 0.8, "colours": "warm white", "fade": 1.3, "behind": "dark tree", "behind_level": 0.35}),
         ("trans", "crossfade", 56, 68, "classic", {"curve": "ease in-out"}),
         ("anim", "ornaments", 62, None, "classic", {"density": 10, "glint": 0.5, "fairy": 0.5, "move_bars": 0}),
         ("trans", "crossfade", 114, 120, "classic", {"curve": "ease in-out"}),
     ]),
    ("nochebuena", "Nochebuena -- poinsettias opening slowly on every prop (16 s per bloom), turning, gold seed-lights twinkling",
     {}, [
         ("anim", "poinsettia", 0, None, "classic", {"bars": 8, "spin": 2.5, "music": False, "leaves": 0.8}),
     ]),
    ("candlelight", "Candlelight -- the painted picture (Santa, the bell, the snowflakes in their colours) under a slow candle flicker",
     {}, [
         ("anim", "fire_candle", 0, None, "classic", {"level": 0.9, "flicker": 0.2, "rate": 0.7, "colours": "painted"}),
         ("mod", "mod_sparkle", 0, None, "classic", {"density": 0.5, "life_s": 0.6, "color": "gold", "level": 0.7, "only_lit": True}),
     ]),
    ("golden-bokeh", "Golden bokeh -- big out-of-focus discs of gold and amber drifting across the whole row",
     {"pal_idle_gold": WARM_GOLD}, [
         ("anim", "bokeh", 0, None, "pal_idle_gold", {"count": 22, "size_in": 20.0, "drift_in_s": 2.0, "ring": 0.45, "floor": 0.12}),
     ]),
    ("snowfall", "Snowfall -- three layers of flakes with parallax, a gentle wind, a hint of night sky",
     {}, [
         ("anim", "snowfall", 0, None, "frost", {"flakes": 26, "speed": 9.0, "size_in": 4.5, "depth": 1.0, "wind": 0.35, "gusts": 0.4, "sky": 0.22, "color": "frost"}),
     ]),
    ("aurora", "Northern lights -- green and violet curtains drifting across the row",
     {}, [
         ("anim", "aurora", 0, None, "classic", {"speed": 0.5, "curtain_in": 48.0, "colours": "green / violet", "level": 1.0}),
         ("mod", "mod_sparkle", 0, None, "frost", {"density": 0.4, "life_s": 0.5, "color": "white", "level": 0.6}),
     ]),
    ("lava-lamp", "Lava lamp -- slow orange bubbles rising through blue goop",
     {}, [
         ("anim", "lavalamp", 0, None, "classic", {"bubbles": 6, "speed": 0.45, "size_in": 24.0, "bubble": "orange", "goop": "blue", "goop_level": 0.35}),
     ]),
    ("fiesta-banners", "Fiesta banners -- rows of papel picado pennants in fiesta colours, fluttering, colours drifting along one flag every few seconds",
     {"pal_idle_fiesta": FIESTA}, [
         ("anim", "papel_picado", 0, None, "pal_idle_fiesta", {"step": "every bar", "flutter": 0.5, "shape": "scallop", "lace": 0.4}),
     ]),
    ("heartbeat", "Heartbeat -- a slow heart rising from the bottom of every prop every half minute and letting go in a warm glow",
     {"pal_idle_fiesta": FIESTA}, [
         ("anim", "corazon", 0, None, "pal_idle_fiesta", {"bars": 15, "rise": 0.7, "pulse": 0.06, "burst": 0.8, "glow": 0.3}),
     ]),
]


def build_project(layout_path, groups, name, palettes, clips, seconds, fps):
    rel = os.path.relpath(layout_path, ROOT)
    P = Project.default(None, rel, groups)
    d = P.d
    d["name"] = f"idle {name}"; d["fps"] = fps; d["audio"] = []; d["sections"] = []
    d["palettes"].update(palettes)
    for tr in d["tracks"]:
        tr["clips"] = []
        for k, (kind, fx, t0, t1, pal, params) in enumerate(clips):
            tr["clips"].append({"id": f"c_idle{k:04d}", "kind": kind, "effect": fx, "t0": float(t0),
                                "t1": float(seconds if t1 is None else t1), "params": dict(params), "palette": pal})
    return P


def contact_sheet(P, layout, path, seconds, fps, n=6):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    R = Renderer(P, layout, fps)
    props = sorted(layout.props, key=lambda p: p.x) if hasattr(layout, "props") else []
    gs = list(R.groups.values())
    x0 = min(g.x0 for g in gs); x1 = max(g.x1 for g in gs); z0 = min(g.z0 for g in gs); z1 = max(g.z1 for g in gs)
    sc = 2.2; W = int((x1 - x0) * sc) + 40; H = int((z1 - z0) * sc) + 28
    img = Image.new("RGB", (W, H * n), (8, 8, 12)); d = ImageDraw.Draw(img)
    for row in range(n):
        t = seconds * row / n
        for tt in np.arange(max(0, t - 0.6), t, 1 / fps):
            R.frame(tt)
        fr = R.frame(t)
        for g in gs:
            for pr in g.props:
                v = np.clip(fr[pr.id], 0, 1)
                for k in range(pr.n):
                    x = (pr.wx[k] - x0) * sc + 20; y = row * H + H - 12 - (pr.wz[k] - z0) * sc
                    d.ellipse([x - 1.5, y - 1.5, x + 1.5, y + 1.5], fill=tuple(int(255 * q) for q in v[k]))
        d.text((4, row * H + 3), f"{P.d['name']}  t={t:.0f}s", fill=(150, 150, 150))
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", default=os.path.join(ROOT, "assets", "bench.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "idle"))
    ap.add_argument("--seconds", type=float, default=SECONDS)
    ap.add_argument("--fps", type=float, default=FPS)
    ap.add_argument("--loop", type=float, default=LOOP_S, help="seamless-loop crossfade length (s)")
    ap.add_argument("--first-scene", type=int, default=1, help="scene number of the first pattern")
    ap.add_argument("--only", default="", help="comma-separated pattern names")
    ap.add_argument("--sheets-only", action="store_true", help="just the contact sheets, no cards")
    a = ap.parse_args()
    layout = LAY.Layout.load(a.layout)
    only = {s.strip() for s in a.only.split(",") if s.strip()}
    os.makedirs(a.out, exist_ok=True)
    index = ["# Idle scenes", "", f"layout `{os.path.relpath(a.layout, ROOT)}`, {a.seconds:.0f} s each at {a.fps} fps, seamless loop ({a.loop:.0f} s crossfade)", ""]
    scene = a.first_scene
    for name, desc, pals, clips in PATTERNS:
        if only and name not in only:
            continue
        P = build_project(a.layout, layout.groups, name, pals, clips, a.seconds, a.fps)
        folder = os.path.join(a.out, f"{scene:02d}-{name}")
        os.makedirs(folder, exist_ok=True)
        t = time.time()
        contact_sheet(P, layout, os.path.join(folder, f"{name}.png"), a.seconds, a.fps)
        if not a.sheets_only:
            P.path = os.path.join(folder, "project.json")
            man = render_cards(P, layout, folder, scene=scene, loop_s=a.loop)
            print(f"Sc-{scene:02d} {name:16s} {man['frames']} frames  {time.time() - t:5.1f} s   {', '.join(c['file'] for c in man['cards'].values())}")
        index.append(f"- **Sc-{scene:02d}** `{name}` — {desc}")
        scene += 1
    open(os.path.join(a.out, "index.md"), "w").write("\n".join(index) + "\n")
    print("wrote", os.path.relpath(a.out, ROOT))


if __name__ == "__main__":
    main()
