# Show design

The production show, as specified on 2026-09-07. This is the document an AI
(or a person) should read before touching the timeline, the layout, or any
effect. `CLAUDE.md` says how the hardware works; this says what we are
building on it and how the pieces are named.

Decisions here were made by the show owner. Anything marked *proposed* is a
suggested shape that has not been built or approved yet.

---

## 1. What the show is

- A **driven course**. Cars pass arrangements of props laid out along the
  route. Effects are seen from a moving car at distance, so **readability
  beats detail** — a gesture that spans several props reads; a 2-inch
  gradient does not.
- **68 props (16,349 pixels), ~20 GC-6004 controllers.** The `.mod` library
  is complete in `assets/props/`; the largest prop is 655 px (12号 left/right),
  comfortably under the 1024/port limit. Every prop belongs to exactly one
  **group** (a themed set placed together on the course). Groups map to
  their own controller sets — no controller spans two groups.
- **The music show runs every half hour.** The track (`Xmas Light Showv1.mp3`,
  in the repo as `assets/audio/show16.mp3`) is **14:42 = 881.7 s = 52,903
  frames** at 60 fps — "16 minutes" in conversation. Other songs play between
  runs while slower **ambient patterns** loop.
- **Drift is assumed not to be a problem.** Fallback, if it is: split the
  16-minute file into ~30 scenes of ~32 s and re-trigger each one over DMX,
  so error cannot accumulate past one scene. The architecture below keeps
  that door open (§5).

## 2. Groups

Four groups, assigned from the owner's marked-up contact sheet (2026-09-07)
and stored in `assets/layout.json`:

| Group | Props | Pixels | Members |
|---|---|---|---|
| Santa's Workshop | 15 | 6,718 | the character props (Santas, snowman 9右, bears, reindeer, nutcracker), spiral tree, cupcake, bell 1号, starburst 60号 |
| Snowflakes | 25 | 5,784 | all snowflakes, the trees 10号/11号, wreath 55号, starburst 43号, star 53号 |
| Stars | 18 | 1,702 | the small stars and crosses, candy cane 4号 |
| Yule | 10 | 2,145 | candy canes 2号, bows 8号/6号/7号, bursts 44号/59号, star tree 41号, star 50号, snowman 9左 |

Names in `layout.json` are shape guesses from the sheet — correct them there.
Reassigning a prop is one dropdown in the editor.

A group is the unit of:

- **layout** — its props sit on one virtual grid in inches, with real
  distances between them (§4)
- **wiring** — its own controller(s) and ports
- **multi-prop effects** — ripples, call-and-response, feature-prop emphasis
  compute against the group's geometry, not the whole course
- **palette/theme defaults** — Snowflakes want frost; Yule wants red/green/gold

Course-wide effects (a wave that travels the whole route) still exist; they
just treat groups as points on a longer line.

## 3. Scene budget (files on each SD card)

The GC-6004 holds **62 scene files**. Every controller carries the *same
scene list* so one DMX scene-select means the same thing everywhere.

| Scene | Content | Length | Notes |
|---|---|---|---|
| 1 | Music show | 14:42 = **52,903 frames** at 60 fps | under the 65,535 cap with ~3.5 min to spare |
| 2–16 | 15 ambient patterns | 3–5 min each, seamless loop | speed slower than the show; see §7 |
| 17–46 | *reserved*: split show, 30 × ~32 s | only if drift forces it | |
| 47–62 | spare | test patterns, chain-map, blackout | |

Scene 1 stays scene 1 whether or not it is split, so the runner's schedule
does not change — it just fires more cues.

**File size.** Bytes per controller = pixels × 3 × frames. At the 4096-pixel
per-unit ceiling the show file is 650 MB; at the real average of ~820 px per
controller (16,349 px / 20) it is ~130 MB. Ambient scenes at 4 min are a quarter of that.
Total per card stays under ~1 GB. Fine for the cards; SD read rate at 60 fps
should still be confirmed on the densest controller before the full build.

**Frame count is per-scene, not per-show.** Every controller's file for a
given scene must have the identical frame count. Export asserts this.

## 4. Layout: 2.5D, in inches

Decision: **2.5D.** Each prop has `x, y` (top-down, inches), `z` (height of
the prop's centre above ground), `rot` (yaw, degrees), and its `.mod` shape.
That is enough to render a 3D viewport and to compute real distances for
physics effects. Full 3D tilt is not needed.

**Built:** `assets/layout.json`, read and written only by `lightshow/layout.py`.
`z` is the height of the prop's *bottom edge* (0 = standing on the ground).

```json
{
  "units": "in",
  "groups": {
    "snowflakes": {"label": "Snowflakes", "palette": "frost", "controllers": ["C01", "C02"]},
    "workshop":   {"label": "Santa's Workshop", "palette": "classic", "controllers": ["C03"]}
  },
  "props": [
    {"id": "sf-47", "mod": "47号.mod", "group": "snowflakes",
     "x": 0, "y": 0, "z": 60, "rot": 0,
     "controller": "C01", "port": 4}
  ],
  "controllers": {
    "C01": {"model": "GC-6004", "dmx_addr": 1, "x": 12, "y": -30}
  }
}
```

Two views over the same file (**built**, `make editor` → `out/layout_editor.html`):

- **Top-down editor** — drag props on a grid, snap to 6 in, distance
  readouts between selected props, group colouring, port/pixel-count
  warnings (1024/port, 4096/unit). This is the one used during setup when
  positions change.
- **3D viewport** — same data, orbit camera, props as glowing point clouds
  at their `z`, plays the rendered show. For judging how it reads from the
  road, not for editing.

**Distance-based effects recompute automatically.** Effects never hard-code
positions; they read `layout.json` at render time. Move a prop, re-render
the group, done. A `make group GROUP=snowflakes` target renders only that
group's controllers.

## 5. Show file: how the 16 minutes are described

*Proposed*: `show.yaml`, human- and AI-editable, seconds-based, rendered by
one renderer for both preview and export (see `03-ARCHITECTURE.md`).

```yaml
audio: assets/audio/show16.mp3
fps: 60                         # assumed device setting, see CLAUDE.md
groups: layout.json

# Baseline is COMPUTED from music.py analysis: sections -> intensity,
# beats, onsets, bands. Everything below is an override on top of it.

markers:                        # user-placed, seconds
  - at: 0:00      type: pattern  effect: "opening frost"       groups: all
  - at: 1:12.5    type: change_up                              # vary within the current pattern
  - at: 2:40      type: pattern  effect: "workshop conveyor"   groups: [workshop]
  - at: 5:25      type: intensity  value: 4                    # 0..10
  - at: 5:25      type: palette    value: limited              # monochrome | limited | full
  - at: 8:19      type: pattern  effect: "call and response"   groups: [stars, snowflakes]

spans:                          # explicit layers with a time range
  - from: 5:25  to: 8:19  effect: sparkle   params: {rate: 0.4}
  - from: 5:25  to: 8:19  effect: colour_waves  params: {follow: call_response}
```

Semantics:

- **`pattern`** — switch the active look for the named groups. Transitions
  are crossfades of `transition_s` (default 1.5 s) unless the effect declares
  its own wipe.
- **`change_up`** — keep the pattern, re-roll its variation seed and
  advance its palette rotation. Cheap way to keep a long section alive.
- **`intensity`** — 0–10, overrides the computed section intensity until the
  next marker. Maps onto the mix ladder in `07-MUSIC-MAPPING.md`.
- **`palette`** — `monochrome` (one hue, brightness only), `limited` (the
  group's theme palette, 3–4 hues), `full` (anything).
- **`spans`** — explicit layers, composited by `lighten()` over the pattern.

Natural-language edits land here. "5:25–8:19 is rough, slow the sparkle,
transition to colour waves that follow the call-and-response" becomes: an
edited `sparkle.rate`, a new `colour_waves` span, and a `pattern` marker at
8:19. Each change is a diff a human can read, so the AI-assisted workflow is
"edit `show.yaml`, re-render 5:20–8:25, look at it".

**Time ranges are first-class.** The renderer accepts `--from --to` so a
three-minute fix does not cost a sixteen-minute render, and the HTML player
seeks to the edited range.

**Splitting for drift** (if ever needed) is an export option, not an
authoring change: `export --split 32s` cuts the rendered frame stream into
scenes 17–46 and writes the cue times for the runner.

## 6. Effect taxonomy

Effects stay **pure functions of a context** (`effects.py`). What is new is
the *context* grows from one prop to a group, and effects declare their
scope so the renderer knows what to hand them.

| Scope | Sees | Typical use |
|---|---|---|
| **global** | one prop, no geometry (`c.i`, `c.n`, `c.t`, music) | wash, twinkle, candy-cane stripes along the wire |
| **global geometry-aware** | one prop with `c.x_in/y_in/r_in/ang/arm/tips` | radial bursts, arm chases, outline draw, bottom-to-top freeze |
| **individual** | one *named* prop or set | Santa's red jacket; the "Drawn" pattern |
| **multi-prop** (always geometry-aware) | the whole group: per-prop centres in world inches, pairwise distances, prop bounding radii, `c.feature` (the emphasised prop) | ripple, shockwave, feature-prop blackout, scattered intensity, light conversation |

*Proposed* group context additions:

```
g.props        list of per-prop contexts (each is today's `c`)
g.centres_in   (P, 3) world-space centres, inches
g.dist_in      (P, P) pairwise centre distances
g.radius_in    (P,)   bounding radius of each prop
g.feature      index of the feature prop, or None
g.world_x_in   per-pixel world x (for waves that cross the gap between props)
```

A shockwave is then `exp(-((g.dist_in[feature] - speed*t) / width)**2)` per
prop — one line, and it is correct for any layout because the distances come
from `layout.json`.

**Multi-prop primitives to build first** (they compose into most of what was
asked for):

- `emphasise(feature)` — feature at full, others dim to a floor
- `ripple(source, speed_in_s, width_in)` — pulse radiating outward
- `converge(target, ...)` — the same pulse run inward, intensifying at the
  target
- `scatter(density, hold_s)` — random props step up/down in brightness
- `converse(a, b, phrase_s)` — alternating call/response between two props
  or two sub-groups, phrase-locked to bars
- `assign(prop, feature="low"|"perc"|"melody"|"chroma")` — one prop
  becomes the visible instrument for one music feature

**Readability rule.** Every effect declares a `min_feature_in` and the
renderer warns if it is smaller than 2× the group's coarsest bulb pitch.
That is the constraint that keeps "wow" effects visible from a car.

## 7. Ambient patterns (scenes 2–16)

Slower, looping, no music dependency. Each is a `show.yaml` with no `audio`
and a `loop: true` flag; the renderer makes the last 2 s crossfade into the
first so the loop point is invisible.

| # | Name | Notes from the brief | Scope needed |
|---|---|---|---|
| 1 | Lava Lamp | undulating orange bubbles, blue goop, yellow | global |
| 2 | Northern Lights | curtains of green/violet drifting | global geometry-aware (uses world `y` for the curtain) |
| 3 | Starscape | pixel twinkle, whole props fade in/out, shooting stars crossing props, mostly monochrome with a little colour | multi-prop (shooting star travels `world_x`) |
| 4 | Blizzard Ice | cool white/blue, turbulent swirl; **freeze**: bright outline draw then softens to blue bottom→top; **shatter** to dark | geometry-aware (outline = tips + wire order; bottom→top = `y_in`) |
| 5 | Fireside | flames wicking; a prop dies down and is **reignited** | geometry-aware (flame rises along `y_in`), multi-prop for reignite handoff |
| 6 | Christmas Tree | classic green with gold/red/blue "ornament" pixel clusters; green needs hardware tuning | global, with a per-group ornament seed |
| 7 | Golden Sparkle | shades of gold washing over props, occasional sparkle | global |
| 8 | Drawn | prop-true colours — Santa: red jacket, flesh face, blue eyes | **individual**, hand-painted per `.mod` via a paint tool (see below) |
| 9 | Candy Cane | red/white diagonal stripes | global geometry-aware (stripe angle in world space) |
| 10–15 | AI's choice | six patterns to be designed | any |

**"Drawn" needs a paint tool.** A `.mod` knows pixel positions, not what the
pixel depicts. *Proposed*: a `paint` mode in the preview — click/lasso
pixels, assign a colour region name — saved as `assets/paint/<prop>.json`.
An AI can propose a first pass from the silhouette (the face is the top
blob, the belt is the horizontal line) but a human confirms. The same file
gives every other effect a `c.region` array, which is useful beyond Drawn
("only the star on top of the tree twinkles").

**Green.** Christmas Tree and Northern Lights both depend on a green that
reads as green on these LEDs, not lime. Do one hardware session with a
green ramp test file and record the RGB that looks right in
`06-OPEN-QUESTIONS.md`; palettes reference it by name (`palette.green`).

## 8. Show runner

Decision: **build one.** A small always-on box (Raspberry Pi or a spare Mac)
with a USB–RS485 adapter on the DMX chain and audio out to the PA.

Responsibilities (*proposed*):

- **Schedule.** At `:00` and `:30`: fire scene 1 and start `show16.mp3` in
  the same call; on show end, pick the next ambient scene and start the
  between-shows playlist. Ambient scenes rotate; the playlist is independent
  of them.
- **One clock.** The runner sends the DMX scene-select and starts audio
  playback from one function so the offset between them is a single tunable
  constant (`audio_offset_ms`), measured once with a phone video.
- **DMX keep-alive.** DMX receivers expect a continuous stream; the runner
  refreshes the universe at ~30 Hz holding the current scene value, using
  `tools/dmx_scene.py`'s packet builder.
- **Split-show mode.** If scenes 17–46 are in use, it fires each cue at the
  time the exporter wrote into `cues.json`.
- **Manual overrides.** A tiny local web page: start show now, pick an
  ambient scene, blackout, brightness. Useful during setup nights.
- **Logging.** When each cue fired and what audio position it saw, so a
  drift complaint can be checked against the log.

Pre-flight checklist (per controller, every season): fps set to 60, DMX
address 1, the same scene list on the card, chain continuity, scene 1 frame
count identical across all cards.

## 9. Making it AI-editable

The rules that let an AI make a good change without breaking the show:

1. **Everything is text.** `layout.json`, `show.yaml`, effect `.py` files,
   `paint/*.json`. No binary state outside `out/`.
2. **Seconds and inches.** Never frames, never normalised coordinates for
   feature sizes (`CLAUDE.md` rules 4 and 5).
3. **Range renders.** `make show FROM=5:20 TO=8:25 GROUP=stars` renders a
   preview of only what changed.
4. **Effects self-describe.** `@effect(name, scope=..., params={...},
   min_feature_in=...)`, plus a one-paragraph docstring saying what it looks
   like. The picker, the docs, and the AI prompt are all generated from the
   registry.
5. **Golden frames per pattern.** A PNG contact sheet per scene in `docs/`
   so a change can be eyeballed in a diff.
6. **The timeline UI edits the same `show.yaml`** the AI edits. There is no
   second representation to fall out of sync.

## 9a. Brightness policy and per-song themes

**Lights stay on.** Owner's rule (2026-09-07): avoid total blackouts. As a
general minimum, props are at **≥ 60 % brightness at least 75 % of the time**
— 75 % of the *time* within a song, not of area. It is a soft guideline:
more time at full is welcome, a look that only works dark (starfield, the
hold-breath before a drop, a fade) is exempt, and a particular effect may
stretch it. Encoded in `show.yaml → defaults.brightness`; the renderer prints
a per-song figure for information only — it never clamps or enforces.

**One theme per song**, in mix order (`show.yaml → songs[].theme`):

| # | Song | Theme |
|---|---|---|
| 1 | Carol of the Bells — Lindsey Stirling | Ice Storm |
| 2 | Run Rudolph Run — Chuck Berry | Classic Christmas |
| 3 | Sugar Plum Fairy (Trap Remix) — Trap Music Now | Plum Energy Storm |
| 4 | Jingle Bells — Michael Bublé ft. The Puppini Sisters | Jewels — predominantly gold, scattered emeralds, rubies, diamonds |
| 5 | Rockin' Around the Christmas Tree — Brenda Lee | Modern Christmas, candy stripes |
| 6 | Winter Wonderland — Brooks & Dunn | Tacky |
| 7 | Snowman — Sia | Romantic — reds, pinks; icy blues melted away top to bottom |
| 8 | Feliz Navidad — José Feliciano | AI's choice |
| 9 | God Rest Ye Merry Gentlemen — Pentatonix | Pale palette; brightness follows the musical elements |

Song reference data (tempo, key, energy, mood) is in `assets/show/songlist.md`.

## 9b. Music markers

`make markers` builds `out/markers.html`: waveform, playback, the analyser's
section candidates as clickable ticks, and `S`/`D` to drop **song change** /
**section** markers while listening. Each marker optionally carries an
intensity (0–10) and a palette. Export writes `markers.json`; it is committed
at `assets/show/markers.json` and is the user-input half of `show.yaml`
(§5). Song markers reset the pattern; section markers "change it up".

## 9c. How the show is developed and tested

- **Test bench, now → mid-November:** 6 props, 2 GC-6004 controllers, 1 audio
  box (GC-102C, the DMX scene selector). Every pattern is proven here on a
  technical level first — sync, stubs, brightness, readability.
- **Assembly, mid-November:** a team builds the prop groups in the yard.
  Groups may change at that point; expect to re-run auto-assign, define
  feature props, and rework a few looks against the real `layout.json`.
- **Hardware headroom:** one or two more controllers/props can be added a few
  weeks out if a test needs them.

Design consequence: every pattern renders against *whatever layout it is
given*. The bench is just a second layout file (`assets/bench.json`, 6 props
on 2 controllers) — the same `show.yaml` renders to the bench for testing and
to the full yard for the show. Nothing may be hard-coded to a prop count.

## 10. Order of work

Adjusted from `04-ROADMAP.md` to fit this brief:

1. **Layout** — DONE 2026-09-07: `layout.json`, all 68 props, editor with
   groups, distances, 3D view, controller auto-assign, per-card render
   (`build_cards.py`). Remaining: drag the placeholder positions into the
   real course, confirm handedness.
2. **Group renderer + multi-prop context** — `g.*` above, the six primitives,
   per-group export with identical frame counts, `--from/--to` range renders.
3. **Ambient patterns** — the nine named looks first (they are music-free, so
   they exercise the full pipeline without the audio dependency), then the
   six AI patterns. First real full-card content for all controllers.
4. **Music show** — analyse `show16.mp3`, `show.yaml` markers, timeline UI,
   first full render. Iterate by time range.
5. **Show runner** — schedule, DMX + audio from one clock, override page.
6. **Paint tool + Drawn**, **green calibration** — can slot in whenever a
   hardware session is available.

## 11. First look at the track

`music.py` on `show16.mp3` (after fixing a 2.5% time-base bug in the section
detector that this track exposed — boundaries were landing 22 s late by the
end):

- 132.5 BPM detected with a 6-beat bar — as with Carol of the Bells, the
  tracker locked to a fast subdivision; treat bars as a hint, not truth. A
  medley changes tempo between songs, so **per-song tempo** is needed:
  re-run the tracker inside each song's boundaries.
- 57 sections in 14:42 — over-segmented for a medley. What the show needs is
  **two levels**: song boundaries (the "change pattern altogether" moments,
  probably 6–8 of them) and sections within each song. Candidate song
  breaks from the quiet/long sections: ~0:26, ~1:12, ~3:02, ~4:40, ~6:42,
  ~8:06, ~10:30, ~12:42. Confirm by ear and pin them as `pattern` markers.
- Quiet passages (intensity < 0.12): 0:00–0:26, 1:12–1:31, 3:02–3:25,
  4:39–4:48, 6:42–7:20, 8:06–8:18. These are where the always-on shimmer
  layer earns its place.
- Loudest: 5:51–6:30 (0.88) and 10:30–10:52 (0.98) — natural spots for
  "everything" sections and course-wide waves.
- Analysis cached at `out/show16_analysis.json`.

## 12. Open items from this brief

- The remaining group names and which props go in each. The contact sheet
  (`make props`) shows: ~20 snowflakes, ~14 stars (4/5/6/8-point), 2 candy
  canes, 3 bells, 2 bows, a spiral tree, and the character props (Santas,
  snowmen, reindeer, gift piles — 9号/12号/13号/14号/15号/61–65号).
- **Resolved:** the `.mod` files are y-down on disk; `props.py` now flips
  them and every prop renders upright. **Still open:** handedness — the
  owner's 180° rotation of the sheet put snowman 9左's broom on the left,
  a vertical flip puts it on the right. Check one asymmetric prop in the
  vendor tool; if it is mirrored, set `mirror: true` on the 左/右 pairs.
- The spiral tree `.mod` is a 62 × 1.5 in strip — the strip that wraps the
  cone, not the cone. It needs its own geometry (helix) before geometry-aware
  effects make sense on it.
- Course geometry: approximate spacing between groups along the route, and
  which way cars travel (sets the direction of course-wide waves).
- Whether ambient scenes should react to the between-show songs at all
  (current answer: no — pure time-based loops).
- PA / audio path from the runner, and where the runner physically sits on
  the DMX chain.
