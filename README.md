# Christmas Lights — drive-through pixel-prop show

Software for a music-synced Christmas light show on the Isha campus: Colorloong/GIGACOLOR
pixel props driven by **GC-6004** SD-card controllers, selected over DMX from an ENTTEC USB Pro.
It replaces the vendor's Windows-only tool with a Python pipeline that knows where every prop
physically is, syncs to the music, and renders one card file per controller.

**New here? Read in this order:** [`docs/00-OVERVIEW.md`](docs/00-OVERVIEW.md) →
[`CLAUDE.md`](CLAUDE.md) (verified hardware facts + ground rules) →
[`docs/09-SHOW-DESIGN.md`](docs/09-SHOW-DESIGN.md) (what the show is) →
[`docs/08-CONTROL-PROTOCOL.md`](docs/08-CONTROL-PROTOCOL.md) (DMX, bench-confirmed) →
[`docs/11-STUDIO.md`](docs/11-STUDIO.md) (the editor). `CHANGES.md` is the changelog.

## How it works, in one paragraph

Each controller plays a pre-rendered `.rgb` file from its own SD card at a fixed **30.3 fps**; there
is no live pixel streaming. The only runtime control is a **DMX scene-select** ("play scene N now"),
which restarts that file on every controller at the same instant — so synchronisation is start-time
based and every scene change is a free re-sync. The 14:42 music show is rendered as **one scene per
song** (`Sc-01…Sc-09`); slower idle patterns loop between shows. `tools/showplay.py` plays the music
and fires the scene cues from one clock.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # numpy, scipy, fastapi…; ffmpeg must be on PATH (brew install ffmpeg)
make test                                  # the codec is verified byte-exact against real controller files
make studio-bench                          # the timeline editor on the 6-prop bench -> http://127.0.0.1:8765
```

In the studio: **Render & cards → One scene per song** writes `out/studio/cards/<controller>/Sc-NN-01.rgb`
and `cues.json`. Copy each controller's folder onto its card (FAT32, full format, largest file first).

Play the show (ENTTEC plugged in, its own software quit; needs [uv](https://docs.astral.sh/uv/)):

```bash
uv run tools/showplay.py            # music + scene cues, UI opens at http://127.0.0.1:8777
uv run tools/showplay.py --no-dmx   # rehearse without the interface
uv run tools/scenebox.py            # just pick scenes by hand
```

The one number to tune is **lead** (ms): how far before the audio each DMX cue goes out. Adjust it
in the UI; it is saved in `out/showplay.json`.

Idle / filler scenes: `python tools/idle_scenes.py --layout assets/bench.json --first-scene 10`.

## Layout of the repo

```
src/lightshow/
  formats/rgbfile.py     the .rgb controller-file codec (verified byte-exact; do not re-derive)
  formats/props.py       .mod / .moc prop geometry (20 units per inch, y-down on disk)
  layout.py              the yard layout: where props are, which controller/port
  studio/                Lightshow Studio: server.py (FastAPI), engine.py (effect contract),
                         audio.py (tempo map, sections), render.py (cards, loops, per-song scenes),
                         fx/ (effect packs), static/ (the UI)
  show.py, effects.py…   the earlier yaml/looks pipeline (legacy, still works)
tools/
  showplay.py            show runner: audio + DMX cues from one clock, browser UI
  scenebox.py            manual scene picker (TUI)
  idle_scenes.py         the between-shows filler patterns -> cards
  dmx_scene.py, …        hardware diagnostics (chain map, drift test, level sweep…)
assets/
  props/                 all 69 .mod/.moc prop files        paint/     painted pixel regions (Santa, bell)
  layout.json            68-prop yard layout (placeholder)  bench.json the 6-prop test bench
  studio/                the show itself (timeline, tempo map, palettes)  — bench.project.json
  audio/show16.mp3       the 14:42 show track               site/      the course plan (4.674 in/px)
  factory/               two real controller files, the round-trip fixtures
docs/                    00 overview · 01 context · 02 file formats · 03 architecture · 04 roadmap ·
                         05 prompts · 06 open questions · 07 music mapping · 08 control protocol (DMX) ·
                         09 show design · 10 handoff · 11 studio · 12 hardware updates · 13 inventory · 14 site plan
tests/                   pytest; `make test`
out/                     everything generated (cards, analysis cache, logs) — git-ignored
```

## Hardware facts you must not re-derive

- GC-6004: 4 ports, 1024 px/port, plays at **30.30 fps** fixed; 65,535-frame cap per file; 62 scene files.
- DMX, from base address `Add`: `+0` brightness, `+1..+4` R/G/B/W adjust (**must be 255 or output is muted**),
  `+5` scene with value `(n−1)·4+1`, `+6` speed 255. Wiring and the adapter trap: `docs/08`.
- Empty port = 32-px stub or every later channel shifts. Gamma is applied in software (controller LUT is identity).
- SD cards: FAT32 only, full format, write largest-first in one pass, never rewrite in place.
- Controllers hold their last scene when DMX stops; a hung runner looks like a working show that never changes.

## Status (2026-10-13)

Bench: 6 props on 2 controllers, ENTTEC link working, show rendered as 9 per-song scenes, 12 idle scenes.
Field: ~300 ft, 6 clusters, 40 controllers — layout and addressing still to be decided
(`docs/12-HARDWARE-UPDATES.md`, `docs/13-INVENTORY.md`). Open questions in `docs/06` and `docs/12`.
