# Handoff — state of the project (2026-09-12)

Read this first in a new session. Then `CLAUDE.md`, `docs/09-SHOW-DESIGN.md`
(design brief + verdicts), `docs/08-CONTROL-PROTOCOL.md` (hardware facts).

## What exists and works

**Pipeline** (all Python, numpy/scipy/ffmpeg; standalone HTML tools, no server)
- `assets/layout.json` (68 props, 4 groups, 19 controllers) / `assets/bench.json` (6-prop bench, controllers A/B)
- `tools/make_layout_editor.py` → 2D/3D layout editor with controller auto-assign
- `tools/make_paint_tool.py` → prop **regions** (`assets/paint/<prop>.json`); Santa (61号) and bell (1号) painted by the owner
- `tools/make_marker_tool.py` → music markers; `tools/song_report.py` → per-song beat grids (`out/songs*.json`)
- `src/lightshow/show.py` → renderer: `show.yaml` sections → looks → frames → `.rgb` cards + HTML player
  (`tools/render_show.py --fps 30.3 --scene 7`, `--player`, `--no-cards`)
- `src/lightshow/lamps.py` → lamp models (`incandescent`, `twinkle`, `led`); neon was built, bench-tested and **dropped**
- `src/lightshow/retro.py` → sign programs (walk/build/alternate/steady/finale, `step_beats`) + per-prop animations by prop kind
- Looks that survived the bench: `starfield` (ambient), `retro` (incandescent sign), `hold-breath` (one prop per onset),
  `outline` (trace-then-fill), `icebuild` (freeze/hold/melt), `parts`/`drawn` (regions), `drop`/lightning (Carol),
  `jewels` (each prop a gemstone). See verdicts below before reusing others.
- `tools/make_cue_track.py` (stereo cue WAV: music L, click train R), `tools/bench_play.py` (two-device playback on a Mac),
  `tools/clock_card.py` / `tools/scene_ladder.py` / `tools/level_sweep.py` (controller/box characterisation),
  `tools/idle_wash.py` (idle scene), `tools/eye_candy.py`

**Hardware facts (measured — do not re-derive)**
- GC-6004: files `Sc-SS-PP.rgb`, **first number = scene**; `P:` readout = file position (clamps to last file); keep numbering contiguous
  (`Sc-01..06` idle copies + `Sc-07` show on the bench). Frame cap 65,535. Reformat the SD card before every big copy (a fragmented
  card made controller B drift).
- GC-102C audio box (Audio Scene mode): DMX master; silence → scene 1; beats → walks scenes 7..max(Scene,7); Scene≤7 ⇒ always 7;
  BPM tracker that ignores sine beeps but fires on drum-like hits / music; Hold Time = min gap between accepted beats; falls back
  1–2 s after audio stops. It pins the controller's speed channel: **playback = 30.30 fps** (constant, both controllers, measured
  from 4K video ±10 ms) → render with `--fps 30.3`. Start latency ≈ 0.56 s → `--music-delay-ms 560`.
- **Cue must be gap-free**: a click train with silence between hits made the box drop to scene 1 and re-trigger (file restarts).
  Untested candidates: `out/boxtest/cue_bed_hits.mp3` (noise bed under hits) and `cue_hits_fast.mp3` (hits every 0.25 s).
- Proper fix (budget request pending): USB-DMX interface driven by the laptop — sets scene/speed/brightness directly, exact timing.
- Two-device playback on a Mac: built-in speakers + a USB audio dongle → `tools/bench_play.py`.

**Bench card sets on the owner's machine** (`~/Downloads/mod files/`): `sd_bench/` (show, 30.3 fps, scene 7 + idle 1–6, cue tracks),
`sd_gravity/` (lamp-model test on "Gravity", lamp_test.yaml), `sd_clock/`, `sd_ladder/`.

## Design verdicts from the real props (Sep 2026)

Works: sparkle fields as ambient/intro (not music-reactive) · incandescent sign on/off (walk at half speed, build, alternate) ·
one prop lit while others dark / one prop per onset · LED freeze-then-melt (no colour flood) · outline trace filling in behind the
head · twinkle that only removes LEDs (no white) · prop regions (Santa/bell) · one unmistakable look per song.

Doesn't: volume-following flicker (the `wash` layer tracking RMS) · muted/desaturated colours (Rudolph) · fast per-beat pulses
(lost at 30 fps and at distance) · neon (any flicker) · solid single-colour fills.

Direction: bright saturated LED-Christmas colours, ≤3 per section + white accent; steps not ramps; events on the beat grid,
choreographed by measures like a dance; props come in and out entirely.

## Songs (assets/show/show.yaml, 14:42 medley)
1 Carol (ice storm — keep sparkle opening + drop, strip flicker) · 2 Rudolph (needs full rework) · 3 Sugar Plum (keep sparkle +
drops, strip flicker) · 4 Jingle Bells (retro sign — approved) · 5–9 drafts only.

## Lightshow Studio (built 2026-09-12, Phase 1) — `docs/11-STUDIO.md`

The linear timeline editor exists: `make studio` (HTML front end + FastAPI backend, `src/lightshow/studio/`).
Prop-group tool (drag/drop groups, grid placement, paint, controllers/SD labels), Premiere-style timeline
(audio lane with tempo map per song, bar-aware section detection, per-group animation/transition/modifier
lanes, snap, trim, undo), live preview streamed from the Python engine, 3 default palettes + generator +
custom, full first effect library (5 transitions, 5 incandescent, lava lamp, starfield, 4 classic LED,
3 modifiers), fps choice 60/30.3 with the measured explanation, card table + render + printable sheet.
Tests: `tests/test_studio.py`. The old yaml/looks pipeline still works untouched.

**Round 2 (2026-09-12, after owner feedback):** transitions blend two LIVE animations (no frozen frame) with
per-transition controls + duration; Static pack; new packs Fire, Ice & Snow, Ibiza, Techno, Music driven
(Carol looks + EQ visualiser on 8 cached bands); +4 slow incandescent, +3 smooth LED, smoothing sliders;
prop silhouettes on the grid and in lists, names in the distance readout, add-props library (used props greyed);
paint follows the prop list and autosaves; ⌘C/⌘V/⌘T; placement PDF (page per group); AI round-trip
(digest + project.json export, validated import with backup). Analysis cache is now `out/studio/<stem>.v2.npz`.

**Next:** owner bench-tests round 2; SD-card format/copy/rename from the tool; audio transitions in the cue
track; 3D preview; range render in the UI; tune section detection against the owner's markers.

## Original brief for the timeline editor (2026-09-12) — kept for reference

Replace the yaml/looks workflow with a **linear video-editor-style tool** (HTML front end + Python backend):
- all effects rendered dynamically for the prop group in play, aware of the array of props (positions, regions)
- colour palette panel: auto-generated palettes + custom colours
- **Transitions**: flash in · twinkle burst · ice up/down · wipe (direction adjustable)
- **Animations**: Incandescent pack (4–5 incandescent-themed effects with sliders) · Lava lamp (colour, bubble count, speed) ·
  Starfield (star count, colour, speed) · Classic LED pack (2–4 stereotypical bright-rich-colour LED effects) · (list was cut off —
  ask the owner for the rest)
- Reuse: `Layout`/`PropGeom` (geometry, regions), `LampBank` (incandescent/twinkle), the music analysis + beat grids, the `.rgb`
  writer (`formats/rgbfile.Show`), the player's bloom renderer, `--fps` compensation, cue-track builder.
