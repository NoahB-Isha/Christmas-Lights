# Roadmap

**2026-09-07:** the production brief is in `09-SHOW-DESIGN.md`; its §10
re-orders the phases below around groups, ambient scenes and a show runner.
The phases here remain the reference for what each step must deliver.

Phases are ordered so that each one produces something usable on its own,
and so the risky unknowns get resolved early rather than late.

Phase 0 is complete — the rate is 60 fps. Re-run it on the actual show
controllers rather than assuming the bench unit is representative, since the
setting is per-device.

---

## Phase 0 — Measure the frame rate — DONE

**Result: 60 fps.** 1800 frames in 30.0 s; the 24-blink cross-check gave
1.00 blink per second. Since the rate is a device setting and not stored in
the file, "every controller is set to 60" belongs on the Phase 5 pre-flight
checklist.

Two blocking unknowns remain before the show can be trusted:
**multi-controller start drift** and **chain addressing** (`ChainMap.rgb`).

*Original instructions, kept for re-testing on the show controllers:*

Copy `reference/FpsTest.rgb` to a card and run it. Two independent
measurements, both spatially uniform so they are immune to any geometry
error:

- solid white for 1800 frames → `fps = 1800 / seconds`
- 24 evenly spaced blinks over 1440 frames → `fps = 1440 / seconds`, and
  `fps = 60 x blinks_per_second`

Expected: 30.0 s / 24.0 s / 1.00 blink per second if the device is on 60.

Also confirm the blinks are **evenly spaced**. Uneven means the device does
not hold a constant rate, which matters far more than the nominal number.

Deliverable: a number written into `06-OPEN-QUESTIONS.md`.

---

## Phase 1 — Import and visualise

*The starting point, and already partly built.*

Load `.mod`, `.moc`, and Colorloong `.xml`; show props in real space; play
effects live against true coordinates.

Already working in `lightshow/`:

- unified `Rig` loader for all four input shapes
- standalone HTML previewer with 9 effects, transport, glow, wire-order
  view, per-port toggles, hover to identify a pixel

Remaining in this phase:

- pan/zoom, and a measurement readout in rig units
- drag props to arrange a **yard layout** (positions are not in the `.mod`
  files; only per-prop shape is)
- save/load a layout file of our own (props + placement + port assignment)
- import a Colorloong `.xml` and reproduce its port assignment exactly

Done when: all 66 props load, are arranged into a yard layout, and the
layout round-trips through our own save format.

---

## Phase 2 — Render and export

*The point at which the tool can actually drive the show.*

- vectorised renderer: evaluate an effect across all pixels at once
- layer stack with blend modes and time spans
- export one `.rgb` per controller, all with identical frame counts
- **32-pixel stub rule** applied for empty ports
- export manifest: file per controller, assumed fps, frame count, checksums
- verification pass: re-read every exported file and confirm geometry

Done when: a hand-authored 30-second show plays correctly on real hardware
across at least two controllers, in sync.

---

## Phase 3 — Music and timeline

- load audio, draw a waveform, scrub with audio playback
- onset/beat detection producing an editable beat grid
- place effect spans on the grid; snap to beats; per-port masks
- preview the whole show at real time against the audio

Done when: a full song is sequenced and previews in sync on screen.

---

## Phase 4 — AI effect authoring

- effects as drop-in files with the documented pure-function signature
- a folder that is watched, so a new effect appears in the picker
- a parameter schema so effects expose sliders without UI code
- a prompt template that hands Claude the signature, the rig, and the
  available audio features
- a gallery of previews so a generated effect can be judged in seconds

Done when: describing an effect in a sentence produces something previewable
without touching the app's code.

---

## Phase 5 — Deployment

- yard map: controller positions, port-to-prop wiring, cable runs
- per-controller staging folders that mirror the SD card layout
- filename convention matching what the controllers expect (`Sc-01-01.rgb`
  and similar — the units almost certainly index fixed names)
- a printable run sheet: which card goes in which controller, where it sits
- a pre-flight check: every file present, same frame count, geometry matches
  the assigned ports

Done when: cards can be written and installed from the manifest without
anyone remembering which file went where.

---

## Later, if it earns its place

- 3D layout, for props at different heights
- physical power/current estimation per port (a full-white 325-pixel prop is
  on the order of 19 A — worth warning about before it browns out a run)
- a scheduler for unattended nightly playback
- direct import of Colorloong effect parameters rather than just geometry

## Risks worth tracking

| Risk | Why it matters | Mitigation |
|---|---|---|
| Frame rate wrong or unstable | Show drifts out of sync with music | Phase 0, and re-test on the actual show controllers |
| Controllers start at different times | Sync is start-time based | Test multi-controller start; measure drift over a full song |
| Empty-port stub rule missed | Silent channel offset corruption | Assert in export; verify by re-reading files |
| Preview/export divergence | Looks right on screen, wrong in yard | One renderer, or a conformance diff test |
| File size / frame cap | uint16 = 65,535 frames max | Check at export; ~18 min at 60 fps |
| 66 props x 20 controllers of manual mapping | Error-prone and tedious | Phase 5 manifest and pre-flight |
