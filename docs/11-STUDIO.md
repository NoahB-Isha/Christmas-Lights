# Lightshow Studio — the timeline editor

The linear, video-editor-style tool that replaces the `show.yaml` / looks
workflow. HTML front end, Python backend, one command:

```bash
pip install -r requirements.txt        # adds fastapi, uvicorn, python-multipart, pyyaml
make studio                            # -> http://127.0.0.1:8765   (assets/layout.json)
make studio-bench                      # same tool on the 6-prop bench (assets/bench.json)
python -m lightshow.studio --layout assets/layout.json --port 8765 --no-browser
```

First run analyses `assets/audio/show16.mp3` (~1 min, cached in `out/studio/`)
and creates `assets/studio/<layout>.project.json` seeded with the nine songs
and their reference tempos from `assets/show/show.yaml`, plus the listening
notes from `assets/show/markers.json` as labelled sections.

## Files

| What | Where | Edited by |
|---|---|---|
| prop placement, groups, controllers/ports | `assets/layout.json` | Props & groups mode (same file the old editor used) |
| paint regions | `assets/paint/<prop>.json` | Paint view (same format as `make paint`) |
| audio clips, tempo map, sections, tracks, clips, palettes, SD labels, fps | `assets/studio/layout.project.json` | Timeline & Render modes |
| analysis cache | `out/studio/<audio>.npz` | automatic |
| rendered cards | `out/studio/cards/<controller>/Sc-01-01.rgb` + `manifest.json` | Render & cards |

Everything is JSON text; an AI can edit `project.json` directly (clip times
in seconds, params by slider name) and the UI picks it up on reload.

## Modes

**Props & groups.** Left: groups as cards with a silhouette per prop; drag a prop row onto another group
to move it (its controller is cleared — controllers never span groups). *+ add props* opens the
library of all `.mod` files (already-placed ones are greyed with where they are).
Per group: *Edit on timeline*, *auto-assign* (pack neighbours 4 per
controller), *assign missing*, colour. Centre: top-down grid in inches
(drag to move, snap 6 in, shift = free; wheel zoom; right-drag pan;
arrows nudge 1 in, shift+arrows 12 in; `R` rotates 15°). Double-click a
prop, or *Paint this prop* in the side panel, opens the painter (click /
lasso / shift-flood / wire range / auto-suggest; *Save regions*). The side
panel also lists the group's controllers and SD labels. While painting, clicking another prop in the
group list switches to it; region edits save automatically and the preview picks them up at once.

**Map backdrop.** The grid toolbar has a *map* picker: any image in `assets/site/` (the 2026 site plan is there as
`site_plan_2026.png`, rendered from the PDF at 150 dpi; scale **4.67 in per pixel**, measured from the sheet's own
graphic scale bar — the PDF is not plotted at its nominal 1 in = 100 ft, so always trust the bar / *calibrate*). *upload…*
takes a PNG/JPG or a PDF (rendered with poppler's `pdftoppm`). *move map* (or **M**) lets you drag the image under the
props; *calibrate* = click two points on the map (the scale bar's ends, say) and type the real distance in feet;
*fit map* zooms to it; the slider sets opacity. The map's file, scale, offset and opacity are saved in `layout.json`
(`map`). The grid fades when a map is shown.

**Selecting many.** Drag on empty grid = selection box (shift adds to it); shift-click toggles a prop; ⌘A selects
all (or the "only selected group" set); *⬚ select all* on a group card selects and zooms to that group; Esc clears.
Dragging any selected prop moves them all; arrows nudge (shift 12 in); R rotates each in place. With two or more
selected the inspector becomes the **Arrange** panel: move by Δx/Δy · face across the row / flip facing · rotate
the block ±15°/90° · mirror order · snap to 6 in · **straighten** (best-fit line) · **distribute evenly** between the
end props · **space along row** at N inches · row → / column ↑ · reverse order · align x / y · **place on arc**
(radius, span; props face the arc centre) · set z for all · move all to another group.

**Group props** (`/sort`, linked from the Groups panel). Left: the **pool** — every prop not yet in a
group, sorted into themes (Characters · Sweets & bells · Trees & wreath · Snowflakes large / small · Stars ·
Bursts & crosses), each a silhouette card with size and pixel count; filter box; fold a theme; ⇥ drags a whole
theme at once; shift-click / ⌘A picks several. Right: the **board** — drag a prop onto empty board space to
spawn a group (named and coloured after the prop's theme, cursor lands in the name so you can rename), drag more
props into any group, drag a prop back to the pool to remove it, ✕ dissolves a group. Per group: colour,
palette, controller prefix, and totals (props · pixels · controllers needed at ≤4 props / ≤4096 px).
*✨ groups from themes* places everything still in the pool into one group per theme; *↩ all to pool* empties
the groups. *Save to layout* writes `assets/layout.json` — props still in the pool are kept in a hidden
"Pool (unassigned)" group; a prop that changes group loses its controller/port (re-run auto-assign).

**Timeline.** Premiere-style: ruler, audio lane with waveform, sections
lane, then three lanes for **one group at a time** — animations (wide), transitions (thin),
modifiers. The group tabs above the tools pick which (the preview follows; *all* shows every group's lanes). Hover an effect in the left browser to see it animate on a small fixed rig (click to pin the preview), then drag it onto a lane.

*The effects browser* has a search box (`/` focuses it), filter chips for
Animations / Transitions / Modifiers and for the tags `♪ music`, `slow`,
`painted`, `bulbs`, `multi-prop`, plus `★ favourites`. Packs fold with a
click on their heading and every effect can be starred; the filters, folded
packs and favourites are remembered in the browser between sessions. A
search temporarily unfolds everything and highlights the match. Clips: drag
to move, drag the edges to trim, alt-drag to duplicate, ⌘D duplicate
after, Delete removes, ⌘Z / ⇧⌘Z undo/redo; snap to beats (zoomed in) or
bars. Animations never overlap on a lane (placing one trims or splits the
neighbour); transitions and modifiers may overlap anything. Space plays;
click the ruler to seek; ← → step a beat (shift: a bar). The preview above
streams frames from the backend over a WebSocket: what you see is what the
cards get. The viewer is a 3D orbit camera: drag = orbit, shift/right-drag = pan, wheel = dolly,
F / double-click = fit; presets front (1) · top-down (2) · ¾ (3) · drive-by (4) in the `view` menu;
a 5 ft ground grid gives the scale. **Car view (5)**: draw the cars' route on the props grid
(*🚗 route*: click points along the road in driving order, Enter to finish; drag / double-click points to edit;
saved in `layout.json` as `route`), then the camera rides it at the set mph and eye height — the whole show is
rendered, drag looks around, wheel or the slider moves the car, F looks ahead. Position = start + speed × show time,
so scrubbing the timeline drives the car; the ride loops at the end of the route. On the props grid the silhouettes are drawn at real size and
turned with the prop (lying back from the footprint line), so an arrangement reads as a plan.

*Audio*: clips play sequentially (no stacking; *+ audio* appends). Selecting
the audio shows the **tempo map**: one row per song with BPM, beats/bar and
first-beat nudge, and a **→ BPM** box for a passage that speeds up or slows
down: split the song where the change starts and ends, type the end tempo in
the → box of the middle row, and the beat grid ramps linearly across it
(`bpm_end` in the song entry; `audio.ramp_beats`). Every beat-stepped effect
(Sign walk, Build, Alternate, Marquee…) follows the ramp, and `Music.bpm`
reports the instantaneous tempo. A typed BPM always wins over the detector.
*Split song at playhead* adds a row. *Detect sections* builds sections from the beat grid:
per-bar timbre novelty + energy step, peaks ≥ 4 bars apart, snapped to
4-bar phrases, always on bar lines. Sections can be renamed (double-click),
split at the playhead, merged (Delete), and *filled* with an animation per
group from the section inspector.

*Palettes*: three defaults (Classic Christmas, Frost, Jewels), *generate*
(harmony schemes from a random seed hue — analogous, complementary, triad,
split, tetrad, candy, mono-warm, mono-cool; always saturated, white
appended) and *custom* (editable swatches, stored in the project).

**Render & cards.** Frame-rate choice with the measured explanation
(60 = controller native / DMX start; 30.3 = GC-102C audio-box start), the
card table (controller → ports → props, px, file size, SD label, last
render) and *Render all cards* (`POST /api/render`). *Print prop / card
sheet* opens a printable page listing every card with its ports and every
prop with group, controller, port and position.

*One scene per song* (`POST /api/render_songs`, plan at `GET
/api/render_songs/plan`): the show is cut at the tempo map's song boundaries
and rendered as `Sc-NN-01.rgb` per song from the chosen first scene number.
A tempo-map entry that only exists for a tempo change (its name shares the
song's base name, e.g. "God Rest Ye — accelerando", or has `cut: false`)
stays inside its song's scene. Each scene is rendered from that song's start
after a 1.5 s warm-up of the timeline state (filament warmth, effect
envelopes continue as if mid-show). `out/studio/cards/cues.json` lists
scene number, DMX value `(n−1)·4+1`, timeline `t0/t1`, frame count and card
files for the show runner, which selects the next scene at every boundary:
every controller restarts that file from frame 0 together, so inter-controller
drift is reset once per song and no card file is longer than one song.

## Effects (src/lightshow/studio/fx)

All effects are group-aware: they get a `GroupCtx` (props sorted left→right
in world inches, centres, pairwise distances, group extents) and size
everything in inches, so the same clip renders correctly on the bench and
in the yard. Music arrives as a `Music` object (levels, beat/bar/phrase
phase from the tempo map, hits, energy, 8 EQ bands, dt). Without audio the
engine feeds a synthetic 120 BPM click so every effect still previews.

| Pack | Effects | Notes |
|---|---|---|
| Transitions | Flash in · Twinkle burst · Ice up/down · Wipe · Crossfade · Shatter · Prop by prop · Curtain · Spiral out · Blackout cut · **Melt** | both animations keep RUNNING through the window (no frozen last frame); each has a timing curve + its own controls; duration / "centre on cut" in the inspector |
| Static | Static picture | painted picture (or palette / one colour / white) that just stays on; optional slow breathe; lamp model as a slider |
| Incandescent | Sign walk · Build · Alternate · Marquee chase · Drawn picture · **Warm breathe · Slow wave · Twinkle bulbs · Region wander** | props drawn from paint regions in their painted colours; LampBank filament + amber (saturated dyed glass barely shifts) |
| Classic LED | Rainbow wave · Colour blocks (blend slider) · Colour chase (soft edges) · Beat fill (smooth by default) · Gradient flow · Colour breathe · Meteors · **Bokeh · Kaleidoscope** | all smooth; Bokeh = out-of-focus discs drifting across the group in inches; Kaleidoscope = mirrored wedges around each prop's centre |
| Music driven | Onset sparkle · Hold your breath · The drop · Outline trace · Energy fill · **EQ visualiser** | the first Carol show's looks as clips; EQ = one band per prop (bass left → air right, or all props on one band), attack/release, peak-hold dot, DAW colours |
| Ice & Snow | Snowfall (3 layers of depth, gusts) · Freeze & shatter · Crystal growth · Northern lights · Frost breath · **Ice sculpture** | Ice sculpture = translucent blue-white body with slow clear/cloudy patches, veins, a circling highlight, frost glints and rare crack flashes |
| Fire | **Flames** · **Embers rising** · Reignite · Candle flicker | rebuilt round 5: white-hot core, tongues that tear loose and race up, ragged flickering top (`flame_field`); Embers rising = dark coal bed + sparse slow sparks |
| Ibiza | Sunset sky · Moving beams · Wash & strobe · Ocean waves | |
| Techno | Scanner · Grid flicker · Lasers · Hard pulse | |
| Christmas classics | Candy cane · **Tree & ornaments** · **Wrapped present** · **Fairy lights** · **Garland** · **Toy train** · Shooting star · Snow globe · Icicles | rebuilt in round 4: the tree mixes three greens at two scales with shaded glass baubles that catch the light, tinsel, mini lights and a star; the present is per prop in local inches (paper pattern, ribbon, satin sweep, bow); Fairy lights and Garland are building blocks; the train runs along the group's whole wire |
| Song themes | Candy stripes · Tacky · **Romantic melt** · Pale elements · Plum energy storm | one signature look per undesigned song (docs/09 §9a); the melt is now crystalline ice with a ragged front, pink seep above it, convecting warm colour, drops that fall under gravity into a puddle, and a refreeze from the ground up |
| Fiesta | **Guitar strum · Fiesta banners · Nochebuena bloom · From the bottom of my heart · Confetti** | written for Feliz Navidad: the props are six guitar strings the pick sweeps on every beat (chord colour per bar, standing-wave ring); papel picado pennants that step colours on the beat and flutter; the poinsettia blooming red bracts over green leaves with a twinkling gold centre; a beating heart that rises from the bottom of every prop and bursts into glow; a piñata burst of tumbling palette-coloured paper. Bursts are anchored to the clip start |
| Choreography | Feature prop · Shockwave · Converge · Scatter · Call & response · Wave across · **Explosion** | the multi-prop primitives from docs/09 §6; every one uses the real distances and a feature prop that can be handed along the row — or **a specific prop picked by name** in the inspector (`feature = specific prop`, `prop = <id>`). Explosion splits each prop into shards of its real bulb map (Voronoi over the bulbs) that fly out from the blast point, tumble and fade behind a fireball — or ease back together before the next blast; blast from each prop's centre or from the feature prop with the wave reaching far props later |
| Lava lamp · Starfield | | |
| Modifiers | Twinkle (removes bulbs) · Ripple · Glitch · Strobe gate · Colour shift · Brightness envelope · Mirror · Sparkle overlay · Snow on top · **Tape wobble · Slice shift · Wind** | stack on top of whatever is playing; the last three DISPLACE the picture (`util.resample`: nearest-bulb lookup through a per-prop KD-tree, so pixels slide across the real bulb map) |

Adding an effect: one function with `@effect(name, kind, label, pack=..., params=[Slider(...)])`
in `fx/`; the browser, inspector sliders, digest and docs come from the registry.
Contract in `engine.py`'s docstring; helpers (noise, heat map, palette
gradient, envelope follower, `glints` specular flashes, `baubles` shaded spheres,
`blob`, `wire_offsets`) in `fx/util.py`; `classics.tree_body / fairy / tinsel` are
reusable scene pieces. Parameter kinds: float / int / choice / bool / **prop** —
a `prop_pick(...)` param stores one of the group's prop ids and the inspector
offers the group's props by name (import validation clears ids from other groups).

## Placement sheets

*Render & cards → Placement PDF*: page 1 is the whole course; then one page
per group — top-down map in inches (long rows are wrapped into strips), each
prop's silhouette, name, controller:port, the distance to its neighbour,
controllers with cable runs, and the prop table. `GET /api/print/placement.pdf`
(needs matplotlib).

## AI final pass (file round-trip)

*Render & cards → AI final pass*: download `show_digest.md` (every group,
prop, song, section and clip in plain words, plus the full effect catalogue
with slider ranges and the design rules from the bench) and `project.json`.
Give both to Claude with your notes; it returns an edited `project.json`.
*Import project.json…* validates it — unknown effects/params dropped,
values clamped, overlaps trimmed, unknown palettes → classic — shows the
fix-up report, keeps a timestamped backup of the previous project, and the
timeline reloads. `audio`, `layout`, `fps` and `cards` are never taken from
an import.

## Shortcuts

Space play/pause · Home to start · ← → step beats (shift: bars) · ⌘Z / ⇧⌘Z undo/redo ·
**shift-click** adds a clip to the selection, **shift-drag** on empty timeline draws a selection box, ⌘A selects
every clip (of the previewed group, if one is chosen), Esc clears ·
⌘C / ⌘V copy & paste the selection at the playhead (a block keeps its spacing; a single-group block lands on the
previewed group) · **S** (or ⌘T — Chrome and Safari reserve ⌘T for "new tab", so S is the one that always works)
splits every selected clip at the playhead · ⌘D repeats the selection after itself · alt-drag duplicates ·
dragging any selected clip moves the whole selection · Delete removes the selection ·
props grid: arrows nudge 1 in (shift 12 in), R rotate 15°.

Shortcuts work while a slider, checkbox or dropdown in the inspector has focus; only a text field swallows them.
The single-clip inspector also has *copy* and *split at playhead* buttons.

## Backend API (server.py)

`GET /sort` (grouping board) · `GET /api/site` · `GET /api/site/{name}` · `POST /api/site/upload` · `GET /api/state` · `PUT /api/project` · `PUT /api/layout` ·
`POST /api/layout/auto_assign` · `GET|PUT /api/paint/{stem}` ·
`GET /api/audio/{id}/analysis` · `GET /api/audio/{id}/file` ·
`POST /api/audio/import` · `POST /api/audio/upload` ·
`GET /api/palettes/generate` · `POST /api/render` · `GET /api/print/placement.pdf` ·
`GET /api/export/digest.md` · `GET /api/export/project.json` · `POST /api/import/project` · `WS /ws/preview`.

## Not yet

- Formatting / copying / renaming the physical SD cards from the tool (the
  render writes `out/studio/cards/`; the card table tracks labels and last
  render).
- Audio transitions (crossfade / fade) are stored but the preview cuts;
  the cue-track builder should consume them.
- 3D orbit preview; course-wide effects across groups; range render in the UI.
