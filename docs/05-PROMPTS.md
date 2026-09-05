# Prompts

Copy-paste prompts for working with Claude on this project. Each is written
to be pasted **with the repo available** (or with `docs/` and `lightshow/`
attached).

## How to get good results here

Things that demonstrably worked while reverse-engineering the format:

- **Ask for the disproving test, not the confirming one.** "What test would
  show this model is wrong?" caught a wrong byte/pixel interpretation that
  three confirming tests had missed.
- **Insist on verification against real artefacts.** Byte-exact round-trip
  of a factory file is worth more than any amount of reasoning.
- **Say when a conclusion is provisional.** Frame rate was assumed at 60 for
  several rounds before being measured, and it happened to be right — but
  everything built on it was a guess until `FpsTest.rgb` ran. Claude should
  propagate that kind of uncertainty rather than harden it into constants.
  Still open the same way: multi-controller drift, and chain addressing.
- **Push back when something smells wrong.** "Wait, I didn't test that yet"
  and "why was that ruled out?" both directly produced corrections. The
  second one cracked the format.

A useful standing instruction to include:

> If you are inferring rather than verifying, say so explicitly. If a claim
> can be checked against a file in this repo, check it before asserting it.

---

## Session opener (use every time)

> I'm building software for a synced Christmas light show: 66 props, ~20
> SD-card LED controllers, Mac primary. Read `docs/01-CONTEXT.md`,
> `docs/02-FILE-FORMATS.md`, and `docs/03-ARCHITECTURE.md` before starting.
>
> The `.rgb` output format is fully reverse-engineered and the codec in
> `lightshow/formats/rgbfile.py` round-trips five factory files byte-for-byte
>  — treat it as correct and don't re-derive it. Frame rate is measured at
> 60 fps; it is a device setting, not in the file, so keep it a single
> constant. Effect feature sizes belong in inches (20 units per inch), not
> normalized coordinates — bulb pitch varies 4x across the prop library.
>
> Today I want to: [TASK]
>
> Tell me if anything in the docs contradicts what you find in the code.

---

## Phase 0 — Frame rate — DONE (60 fps)

Re-run this on the actual show controllers, since the rate is per-device:

> I ran `reference/FpsTest.rgb` on controller **[id]**. Test 1 (1800 frames
> of solid white) took **[X] seconds**. Test 2 (24 blinks over 1440 frames)
> took **[Y] seconds**, and the blinks looked [even / uneven].
>
> Work out the frame rate from both measurements and tell me whether they
> agree with the bench result of 60 fps. If any controller differs, tell me
> what that means for sync rather than averaging it away.

---

## Phase 1 — Layout editor

> Extend `lightshow/preview.py` into a real layout editor. Right now it
> renders a rig read-only.
>
> I need to: drag props to position them in yard space, rotate and flip
> them, assign each to a controller and port, and save/load the whole
> arrangement in a format of our own.
>
> Important: the `.mod` files contain only each prop's own shape, not where
> it sits in the yard — placement is new information we're creating.
>
> Keep it a standalone HTML file with no build step if that's still
> reasonable at this complexity; tell me directly if it isn't and what you'd
> use instead.

> Load all 66 `.mod` files from `[path]` and give me an inventory: pixel
> count, bounding box, wire length, and how many distinct prop shapes there
> actually are (some are mirrored left/right pairs — `左` is left, `右` is
> right). Flag any file whose `dotCount` disagrees with its actual dot
> count, and render a contact sheet of all shapes so I can identify them.

---

## Phase 2 — Renderer and export

> Build the render + export pipeline per `docs/03-ARCHITECTURE.md`.
>
> Requirements, in order of how badly they break the show if wrong:
> 1. Every controller's file gets an **identical frame count** — sync is
>    start-time based, so unequal lengths desynchronise the show.
> 2. Empty ports export as **32-pixel stubs**. See the `.xml` section of
>    `02-FILE-FORMATS.md`; missing this shifts every later channel's byte
>    offset silently.
> 3. Preview and export must use **one renderer**. If you propose splitting
>    them, also give me a conformance test that diffs the two paths.
> 4. Vectorise with numpy — evaluate one effect across all pixels at once,
>    not a Python loop per pixel.
>
> After export, re-read every file with `rgbfile.Show.load` and assert the
> channel geometry matches the rig. Then show me a rendered preview of a few
> frames as PNGs so I can eyeball it before I go to the yard.

---

## Phase 3 — Music timeline

> Add the music timeline. Load an audio file, draw a waveform, detect
> onsets/beats into an editable grid, and let me place effect spans snapped
> to beats with a per-port mask.
>
> Authoring must be in **seconds**, never frames — frame counts are derived
> at render only. (Authoring in frames previously produced a 1.16-second
> "breathing" effect and a twinkle that reseeded every frame, a 60 Hz
> strobe.)
>
> Prefer a light beat-detection dependency over `librosa` if the accuracy is
> comparable; tell me the tradeoff. Beat detection must be manually
> correctable — assume it will be wrong on at least one song.

---

## Phase 4 — AI-authored effects

Set the system up once:

> Build the drop-in effect system from `docs/03-ARCHITECTURE.md`: effects as
> pure functions `effect(u, v, t, i, n, ctx) -> (r, g, b)` in a watched
> folder, with a parameter schema so each exposes sliders without UI code.
> Include 6 reference effects with good docstrings, and write
> `docs/EFFECT-AUTHORING.md` that is complete enough to paste into a fresh
> session as the only context needed to write a new effect.

Then, per effect:

> Write an effect for my light show. Signature and conventions are in
> `docs/EFFECT-AUTHORING.md`.
>
> **Look I want:** [describe it — reference a real thing if you can: "like
> heat shimmer off asphalt", "like a candle guttering"]
>
> **Rig:** [n] props, coordinates spanning [bounds], the biggest prop is
> [n] px.
> **Music:** [tempo, mood, and what should land on the beat]
>
> Give me the function plus 3 parameters worth exposing as sliders. Then
> render a preview strip of 8 frames so I can see it without deploying.

---

## Phase 5 — Deployment

> Build the deployment layer. I have ~20 controllers, a mix of 4-port and
> 8-port, each with its own SD card.
>
> Produce: a yard map of controller positions and port-to-prop wiring, a
> staging folder per controller mirroring its card contents, a printable run
> sheet (which card, which controller, where it sits), and a pre-flight
> check that every file exists, all frame counts match, and each file's
> channel geometry matches its controller's assigned ports.
>
> Note filenames matter — the controllers almost certainly index fixed names
> like `Sc-01-01.rgb`, so we overwrite existing names rather than inventing
> new ones. Confirm the convention against my cards before relying on it.

---

## Debugging a physical problem

This is the prompt shape that actually solved things:

> Something's wrong in the yard. Symptom: **[exactly what you see —
> "strobing", "wrong colours", "only half the prop lights", "it plays then
> stops"]**.
>
> Setup: [controller, port, prop, which file].
>
> Before proposing a fix: list the possible causes, then tell me which
> single test would **eliminate the most** of them at once. Build me that
> test file. Prefer spatially varied test patterns — uniform fills render
> correctly under any wrong layout, which is how a byte/pixel confusion hid
> here for several rounds.

---

## Reviewing your own work

> Review [file/module] against `docs/02-FILE-FORMATS.md`. Specifically:
> where does the code assume something the docs only mark as provisional or
> unknown? Where would a wrong assumption fail *silently* rather than
> loudly? List those, worst first — I'd rather have a short honest list than
> a long reassuring one.
