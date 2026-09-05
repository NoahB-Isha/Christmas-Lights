# Architecture

A proposal, not a decree. The parts that are load-bearing are marked.

## The shape of the problem

The show compiles to one `.rgb` file per controller. Everything upstream is
about producing those files correctly and being able to see what they will
look like before driving to the yard.

```
 66 .mod props ──┐
                 ├─> Layout (props placed in yard space)
 controller map ─┘        │
                          ├─> Timeline (effects x time, against audio)
 audio track ─────────────┘        │
                                   ├─> Render (evaluate effects per pixel)
                                   │
                                   ├─> Preview (screen)
                                   └─> Export (one .rgb per controller
                                                + SD placement manifest)
```

The single most important design consequence: **preview and export must
share one renderer.** If the screen preview and the file exporter are two
implementations, they will drift, and you will only find out in the yard.
Render once to an RGB buffer; the screen and the `.rgb` writer are two sinks
for the same buffer.

## Layered design

**1. Formats layer** — pure I/O, no opinions. Already built and verified:
`rgbfile.py`, `props.py`, `colorloong.py`. Treat as stable; it round-trips
real files byte-for-byte.

**2. Geometry layer** — `rig.py`. One `Rig` = ordered ports, each an ordered
list of `(x, y)` pixels in a shared coordinate space. Every input format
normalises into this. Downstream code never asks where the layout came from.

*Load-bearing:* `Rig.rgb_channels()` must apply the 32-pixel stub rule for
empty ports. Get this wrong and channel offsets shift silently.

**3. Effect layer** — an effect is a pure function:

```python
def effect(u, v, t, i, n, ctx) -> (r, g, b)   # floats 0..1
```

- `u, v` — pixel position in rig space, normalised so the longest axis spans
  −1..1, y up
- `x_in, y_in` — the same position in **inches** (20 units per inch). Use
  these for anything with a physical feature size. Bulb pitch varies 4x
  across the prop library (0.5 in to 2.1 in), so a feature sized in
  normalised coordinates will be invisible on some props and coarse on
  others. Sizes belong in inches.
- `t` — time in **seconds** (never frames; see the frame-rate note)
- `i, n` — index within its port and port length, for wire-order effects
- `ctx` — audio features at `t` (beat phase, band energies), plus params

Pure functions are the reason AI-authored effects work well here: no
lifecycle, no state, no framework knowledge required. Describe the look,
get a function, drop it in a folder, preview it.

Composition: layers with blend modes and time spans, evaluated in order.
This mirrors Colorloong's `LayerList`, which keeps import/export sane.

**4. Timeline layer** — audio + cue list. Beat grid from onset detection,
manually correctable. Effect instances are placed as spans with a start, a
duration, and a port mask. Two properties matter: scrub must be cheap, and
the same cue list must render identically every time.

**5. Render + export layer** — walk frames, evaluate the layer stack per
pixel, write to a buffer. Sinks: screen, or `rgbfile.Show` per controller.

*Load-bearing:* every controller's file must have the **same frame count**.
Sync comes from equal-length files started together. A show is
`ceil(duration x fps)` frames, and every file gets exactly that many.

**6. Deployment layer** — the yard map. Which controller sits where, which
props hang off which of its ports, which file goes on its card, what the
card's directory must look like. Output is a manifest plus a staging folder
per controller so copying to cards is mechanical.

## Frame rate

Not stored in the `.rgb` file. It is a device setting. Therefore:

- Keep it **one constant** in the codebase, and derive every speed from it.
- Express all authoring in **seconds**, convert to frames only at render.
- Put the assumed rate in the export manifest, so a future reader knows
  what the files were built for.
- Record the measured value in `06-OPEN-QUESTIONS.md` once known.

Authoring in frames is how the first demo ended up with a 1.16-second
"breathing" pulse and a twinkle that reseeded every frame — a 60 Hz strobe.
Seconds-based authoring makes those errors impossible to write.

## Technology

The requirement is Mac-first, cross-platform, and easy for an AI to extend.

**Recommended: Python core + web UI.**

- Python already holds a verified codec, and it is the easiest language to
  hand an AI-written effect function.
- A web UI runs identically on Mac and PC with no native toolchain. Canvas
  2D handles thousands of glowing points comfortably; WebGL only if profiling
  says so.
- `lightshow/preview.py` already emits a **standalone HTML file with no
  server, no build step, no install** — that pattern is worth keeping as
  long as it holds, because it makes sharing a preview trivial.

For the interactive app, a small local server (FastAPI or plain
`http.server`) plus a browser front end avoids Electron/Tauri packaging
entirely. Effects live as Python files; the browser previews, the server
renders and exports.

Alternative worth considering: effects in JS so preview needs no round-trip,
with Python only for export. Faster scrubbing, but it splits the renderer in
two — the exact failure mode called out above. If you go that way, generate
both from one source or accept a conformance test that renders the same
frames through both paths and diffs them.

**Dependencies to keep minimal:** numpy (render buffers), an audio decoder,
and an onset/beat library (`librosa` is the obvious pick, and heavy —
`aubio` is lighter). Everything else is standard library.

## Performance sanity check

Worst case observed: 24 channels x 2907 px. For 66 props at ~200 px average
across 20 controllers, budget ~15,000 pixels total. A 4-minute show at 60 fps
is 14,400 frames.

`15,000 px x 14,400 frames = 216 M pixel evaluations` per full render. Pure
Python at ~1 µs per pixel is ~4 minutes — acceptable for a final export, too
slow for scrubbing. Vectorise per-effect over numpy arrays of coordinates
(evaluate one effect across all pixels at once) and this drops by 10–50x.

Export size per controller: 2907 px x 3 x 14,400 = 125 MB. Note the frame
count field is a **uint16, hard-capped at 65,535 frames** — 18 minutes at
60 fps. Fine for a song, worth knowing for a full show.

## Testing

- **Round-trip:** parse and re-serialise every factory `.rgb`; assert
  byte-identical. This is the strongest available check and already passes.
- **Conformance:** if preview and export are separate code paths, render N
  frames through both and diff.
- **Spatially varied fixtures:** never test with uniform frames. A
  full-frame fill renders correctly under any wrong layout and will hide
  exactly the bugs that matter.
- **Golden frames:** small PNG renders of known effects, compared per commit.
