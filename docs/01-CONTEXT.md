# Project context

Read this first. It is the brief a fresh Claude session needs in order to be
useful without re-deriving anything.

## The show

A Christmas light show. Many props, synced to music, driven by SD cards in
standalone controllers. No live network control — every controller plays a
file off its own card, so **synchronisation is achieved by all controllers
starting together and running at the same frame rate**, not by streaming.

That single fact shapes everything: there is no central sequencer at
showtime. The show is compiled ahead of time into one `.rgb` file per
controller, and those files must agree on length and timing to stay in step.

## Hardware inventory

| Item | Count | Notes |
|---|---|---|
| Props | 66 | Each has a `.mod` file with real pixel coordinates |
| GC controllers | ~20 | SD card each; 4-port and 8-port variants exist |
| Ethernet cable | lots | Used for pixel data runs, not IP networking |
| Computers | Mac + PC | Mac is the primary target; PC runs the Chinese tool |

Ports observed per controller: **4**, **8**, and a 24-channel project that is
six 4-port units daisy-chained and addressed as one flat 24-channel list.

## The bench rig (current test setup)

One controller, one prop:

| Port | Content |
|---|---|
| 1–3 | empty → 32 px stubs |
| 4 (ch3) | `47号.mod` — a 4-armed cross, **72 px**, 800×800 units |

The cross's wire traces its outline as one continuous loop: down the
vertical, out the left arm and back, down the bottom, out the right, up to
the top. Frame size is only 504 bytes, so bench files stay tiny.

In real units that cross is **40 x 40 inches with a 2-inch bulb pitch**, and
the bulbs are half-inch, so a bulb fills only a quarter of the gap between
bulbs. It reads as a constellation of discrete points, not a line of light.
Effects with narrow spatial features light almost nothing on it and have to
be widened considerably compared with a dense strip.

A second prop is also on hand: `18号.mod`, a **6-armed** snowflake, 157 px,
24 x 27.5 in on a 1.5-inch pitch. `tools/two_prop_show.py` builds a show for
both together on one controller (18号 on port 3, 47号 on port 4), with the
props placed side by side in one world coordinate space so effects can cross
between them.

Two geometry lessons from writing it, both worth carrying to the other 64
props:

**Detect symmetry, don't assume it.** Sector-evenness scoring fails twice
over: a 6-armed snowflake is perfectly even under 3 sectors, and 47号's arms
are double rows so 8 sectors split them cleanly and score exactly as well as
4. Counting angular *clusters* of the outermost pixels measures arms
directly -- at the outer 15% there is a clean cliff (18号: six ~59 deg gaps
then 2.3 deg; 47号: four ~85 deg gaps then 4.3 deg). Cut at the largest ratio
step. Verified 6 and 4.

**The centre is the mean of the pixels.** Measuring outer pixels per sector
from the mean gives exactly [14,14,14,14,14,14] on 18号 and [10,10,10,10] on
47号. A "densest hub" heuristic landed on an arm instead.

`reference/Bench47.rgb` is an 11-effect test show built for the snowflake
alone.

## Physical scale — and why it drives effect design

Every `.mod`/`.moc` carries `lampRad: 5` — a bulb radius of 5 units, so 10
units across. The bulbs are physically about **half an inch**, which fixes
the coordinate system at **20 units per inch**.

That scale cross-checks three ways: it makes the prop library 14–46 in wide
and 38–51 in tall (3–4 ft, correct for yard props), it makes every pixel
pitch land on a clean value, and it matches `lampRad` exactly.

**Pixel density varies 4x across the library:**

| Pitch | Bulb fills | Props |
|---|---|---|
| 0.5 in | 100% (touching) | spiral tree |
| 1.0 in | 50% | 9号 pair, 11号, 12号 pair |
| 1.1–1.6 in | 31–45% | 2号 pair, 10号, 6号, 7号, 8号 |
| 2.0–2.1 in | 24–25% | 1号, 4号, 47号 |

**This is the single most important constraint on effect design.** A feature
one inch wide is invisible on a 2-inch-pitch prop but spans two bulbs on the
spiral tree. So:

> Effect feature sizes must be expressed in **inches**, not in normalized
> −1..1 coordinates, or they will not port between props.

Concretely, the effect signature should hand an effect real-world
coordinates alongside the normalised ones, and effects should declare
feature sizes in inches. An effect tuned on the dense spiral tree will
vanish on a candy cane; one tuned on a candy cane will look coarse and
blocky on the tree.

The same reasoning applies to previews: drawing pixels as arbitrary dots
makes a sparse prop look dense and invites over-fine tuning.
`lightshow/preview.py` now draws bulbs at **true size relative to pitch**
using `lampRad`, so the sparsity is visible on screen.

## Power (estimate — verify against the actual LED spec)

Roughly 16,000 bulbs across 66 props. At 0.2–0.3 W per bulb that is
**3.2–4.8 kW at full white** — enough that it needs planning, and enough
that per-port and per-run current limits matter. The factory files cap
brightness near 127 of 255, which now looks like a power convention rather
than an arbitrary limit, even though the hardware accepts the full range.

Worth building into the tool: a per-port current estimate, and a warning
when an effect drives a large prop to sustained full white.

## Current toolchain and why it needs replacing

`FastLED.exe` (vendor name in the files is **Colorloong**) is the Windows
authoring tool. It imports `.mod` prop models, assigns them to controller
ports, provides a paint canvas, and renders `.rgb` files for the SD cards.

It is genuinely capable, and the goal is not to disparage it. Its real
limits for this project:

- **Windows only.** Primary machine is a Mac.
- **No music timeline.** Nothing to scrub audio against or place cues on a
  beat, which is the core requirement for a synced show.
- **Awkward at scale.** 66 props across ~20 controllers means a lot of
  manual port assignment and a lot of files to place on the right cards.
- **Fixed effect set.** Effects are the ones shipped; there is no way to
  express "make me a custom effect" beyond combining presets.
- **No deployment model.** Nothing tracks which file belongs on which card,
  or which controller sits where in the yard.

## What the new software has to do

In rough priority order:

1. **Visualise props in real space.** Load `.mod`/`.moc`/`.xml` geometry and
   show the props where they physically are, so effects can be designed
   against the actual layout rather than a pixel index.
2. **Sync to music.** Load audio, show a waveform, place cues and effect
   spans against beats, scrub and preview.
3. **Preview effects accurately.** What you see should be the same
   evaluation the exporter performs — same function, same coordinates.
4. **Know the deployment map.** Which controller is where, which ports it
   drives, which file goes on its card, and what that file must be named.
5. **Make AI-authored effects easy.** An effect should be a small pure
   function with a documented signature so it can be requested in plain
   language, dropped in, and previewed immediately.
6. **Stay compatible with the existing tool.** Read Colorloong `.xml`
   projects and `.mod`/`.moc` files; write `.rgb` files the controllers
   already accept. Never require abandoning FastLED mid-project.

## Non-goals

- Live/streaming control (E1.31, Art-Net). The hardware plays from SD.
- Replacing FastLED outright before the show. It stays as the fallback.
- Designing new prop hardware.

## What is already known and proven

The `.rgb` output format is **fully reverse-engineered and verified**: the
codec in `lightshow/formats/rgbfile.py` round-trips five different factory
files byte-for-byte, spanning 4, 8 and 24 channels. See
`02-FILE-FORMATS.md`. Hardware testing confirmed RGB byte order, full 0–255
brightness, and per-pixel addressing on a real controller and prop.

`.mod`, `.moc` and Colorloong `.xml` are all readable, and the three sample
`.xml` projects are the source projects for three of the decoded `.rgb`
files — so the whole pipeline from layout to SD card is understood.

**Frame rate is measured: 60 fps.** `FpsTest.rgb` gave 1800 frames in 30.0 s,
with a 24-blink cross-check at 1.00 blink per second. It is a *device
setting* and is not stored in the file, so every controller must be left on
60 — a unit switched to 25 plays the same file 2.4x slow with nothing to
indicate a problem. Keep it a single constant in code and put it on the
pre-flight checklist.

What remains unknown is **multi-controller drift** (do two units stay
aligned over a full song?) and **chain addressing** (nothing in the file
says which unit is which). Both are blocking; see `06-OPEN-QUESTIONS.md`.

## Working style that has been productive

This format was cracked by a loop of: form a hypothesis, find a test that
would *disprove* it, run it on real hardware, and take the physical result
as authoritative over any amount of reasoning. Several confident
conclusions were wrong and were caught this way — most importantly reading
a byte count as a pixel count, which produced output that looked fine on
uniform test patterns and disintegrated on spatially varied ones.

Two lessons worth carrying into the software:

- **Uniform test patterns prove almost nothing.** A frame where every pixel
  is the same colour renders correctly under any wrong layout. Always test
  with spatially varied content.
- **Verify against real artefacts.** Byte-exact round-trip of a factory
  file is the strongest available check that a format model is right.
