# Changes — 2026-10-12 · one scene per song

- **Render & cards → One scene per song.** `render.render_songs` cuts the show at the tempo map's song boundaries and
  renders `Sc-NN-01.rgb` per song (first scene number chosen in the UI; the plan table shows scene, DMX value, times and
  frames before you render). Tempo-ramp entries ("… — accelerando") merge into their song; `cut: false/true` on a song
  entry forces it. Each scene starts after a 1.5 s warm-up render so lamps and effects continue as mid-show. Writes
  `out/studio/cards/cues.json` (scene, dmx_value, t0, t1, frames, card files) for the runner. Why: a DMX scene-select at
  each boundary restarts every controller from frame 0 together (free re-sync per song), and the longest card file drops
  from 14:42 to one song — the 40 MB single-file show is suspected in the bench's stuck-port behaviour.
- `render_cards` gained `warm_s` and `manifest` arguments; manifests record `t0`/`t1`.

---

# Changes — 2026-10-12 · prop inspector: controller / port picking

- Props mode → prop inspector: the **controller** dropdown now offers every controller (this group's first, the rest under
  "other groups", each with its port count), so a prop swapped into an existing group can go straight back onto that
  group's controller. The **port** dropdown shows who is on each port; choosing an occupied port moves the other prop off it
  (reported in the status bar). A controller with no free port leaves the port unset and asks you to pick one.

---

# Changes — 2026-10-08 · idle scenes, seamless loops

- **Seamless loops in the renderer**: `render_cards(..., loop_s=4)` renders a pre-roll (every clip pulled `loop_s`
  earlier, local time running negative up to 0 — `_local_shift` in engine.py), hands the pre-roll's lamp and effect state
  to the main render so frame 0 is already warm (no blink on incandescent looks), then crossfades the tail into the
  pre-roll so the last frame flows straight into the first. `Music` now floors negative times (was `int()`), so bar
  counting is right before a clip starts (also helps transitions).
- **`tools/idle_scenes.py`**: the between-shows filler patterns, 12 of them, each a tiny no-audio Studio project rendered
  as its own scene with a 4 s loop crossfade: Starscape · Ice sculpture · Fireside · Fairy lights & ornaments · Nochebuena ·
  Candlelight (painted picture) · Golden bokeh · Snowfall · Northern lights · Lava lamp · Fiesta banners · Heartbeat.
  `python tools/idle_scenes.py` → `out/idle/<NN-name>/<ctrl>/Sc-NN-01.rgb` + manifest + contact sheet PNG + index.md;
  `--layout`, `--seconds`, `--fps`, `--loop`, `--first-scene`, `--only`. Fiesta tweaks: the poinsettia closes again at
  the end of its cycle and the heart fades in, so neither jumps at a cycle boundary.
- Tests: 69 passing (`test_seamless_loop_join`).

---

# Changes — 2026-10-05 · round 6: tempo ramps (the sign walk), Feliz Navidad

- **Tempo ramps.** A song entry in the tempo map may carry `bpm_end`: the beat grid then ramps linearly from `bpm` at
  `from` to `bpm_end` at `to` (`audio.ramp_beats`; the first beat is phased against the onsets over the whole ramp).
  In the audio inspector that is the new **→ BPM** box next to BPM. `Music.bpm` reports the instantaneous tempo.
  Every beat-stepped effect follows the ramp — which is what the sign walk under the Pentatonix accelerando needed.
  The importer now accepts tempo-map changes inside `audio` (songs / BPM / `bpm_end` / first beat) while still
  refusing changes to the audio clips themselves; the digest explains the field.
- **The sign walk (project.json delivered alongside):** God Rest Ye is split into 136 BPM → *accelerando* 856.50–874.79
  ramping **110 → 164 BPM** (fitted to the onset energy of the recording; the a-cappella makes a hand check worth doing:
  zoom in on the beat grid and nudge the start/end BPM if it drifts) → finale 156 BPM. The walk clip now starts on the ramp.
- **Fiesta pack** (`fx/fiesta.py`), written for Feliz Navidad, each effect a lyric or an instrument of the track:
  **Guitar strum** (props = strings, pick sweeps across the row on every beat, chord colour per bar, standing-wave ring,
  down/up or rumba patterns), **Fiesta banners** (papel picado: rows of lace-cut pennants stepping their colours along on
  the beat, sagging strings, a breeze), **Nochebuena bloom** (the poinsettia: red bracts open over green leaves around a
  twinkling gold centre, slow turn, beat pulse), **From the bottom of my heart** (a beating heart appears at the very bottom
  of every prop, rises and grows, bursts into a warm wash — cycle in bars, anchored to the clip start so the burst lands on
  the lyric), **Confetti** (piñata burst: a flash at the top and a dense shower of tumbling palette-coloured squares, then a
  lighter rain; bursts once at the clip start or every N bars of clip time).
- **Feliz Navidad sequence** (672.73–763.43) in the delivered project.json, following the song's 8-bar blocks
  (chroma-checked: intro · A · B · B · guitar break · A · B · fade): strum (fiesta reds) → banners on "Feliz Navidad" →
  confetti on "próspero año y felicidad" → poinsettias on "I wanna wish you a Merry Christmas" → the heart on "from the
  bottom of my heart" → Santa's drawn picture + sparkle on the loud second chorus → heart → rumba strum (green/red/gold)
  for the guitar break → pennants → confetti → flowers every bar → the biggest heart as the song fades. Transitions and
  modifiers in the show's own vocabulary (flash in, prop by prop, twinkle burst, spiral, crossfade; twinkle, sparkle).
- Tests: 68 passing. 94 effects.

---

# Changes — 2026-10-05 · round 5: striking slow looks, fire that reads, music displacement

- **Snowfall** rebuilt with depth: three layers (near: big, bright, fast, tumbling; mid; far: small, dim, slow),
  shared wind with gusts. Parallax is what makes it hypnotic from a car.
- **Fire pack** rebuilt so it reads as fire: `flame_field` = per-column flame height with several-Hz flicker,
  fractal noise scrolling upward fast to tear tongues loose, a near-white core at the base, a ragged top, and a
  hotter colour ramp. Flames and Reignite use it. **Embers rising** (was Embers & sparks): a dark pulsing coal
  bed and a few sparks at a time lifting off, wandering sideways, twinkling and fading — the Starfield recipe in
  warm colours.
- **New modifiers** (all displace the picture across the real bulb map via a new `util.resample`):
  **Tape wobble** (slow vertical drift locked to bar / beat, flutter, a kick on the beat),
  **Slice shift** (on hits the picture cuts into horizontal bands that slide sideways and snap back),
  **Wind** (travelling wave ripples the picture like a flag, anchored at the bottom, gusts, shimmer on crests).
- **Ice sculpture** (Ice & Snow): the prop carved from ice — translucent blue-white body, denser toward the base, clear and
  cloudy patches drifting on a 50 s clock, bright veins inside, a white highlight sweeping round as if a light circled it,
  frost glints that cool to blue, and a crack that flashes across every ~10 s. Nothing faster than a slow breath.
- **Explosion** (Choreography): white flash, a fireball swelling out in inches, then the prop breaks into shards — real
  chunks of its own bulb map — that fly out from the blast point (as far as the prop can show them), tumble, sag and
  fade, with hot orange edges and a smoky afterimage; or they ease back together before the next blast. Every N bars,
  on hits, or once; from each prop's own centre or from the feature prop with the wave reaching the far props later.
- `util.fbm` (fractal noise) and `util.resample` (KD-tree pixel displacement) are available to all packs.
- Tests: 66 passing. 89 effects.

---

# Changes — 2026-09-15 · Lightshow Studio, round 4: the effects rework

Your notes on round 3 ("a little lacking", "the ornaments feel flat", "the melt is far too basic",
"the feature prop can't pick a prop") → this round redoes those effects rather than patching them.
In the repo as before; review with `git diff`. Tests: 66 passing. 84 effects (was 77).

## Feature prop: pick a specific prop

Every Choreography effect's *Feature prop* choice now has **specific prop**, and a new
*…which prop* selector lists the group's props by name (controller:port shown). Picking one
switches the mode for you; the clip stores the prop id, the digest documents it, and the import
validator clears an id that is not in the clip's group (falls back to the centre prop).
Engine: a new `prop` parameter kind (`prop_pick`), `GroupCtx.index_of()`, `feature(..., prop_id)`.

## Christmas classics, rebuilt

- **Tree & ornaments** (was Ornaments): the tree is three greens (deep shadow, pine, sunlit tips —
  or a blue spruce / lime mix) blended by two scales of noise in inches, lighter toward the tips and
  swaying, never one green. Baubles are shaded glass spheres sized in inches — dark rim, saturated
  colour, a white highlight — that sit *in front of* the needles; each catches the light and flashes
  on its own slow clock (and some on the downbeat). Plus a diagonal tinsel garland, warm mini lights
  fading in and out, and a gold star on the topmost bulbs. All switchable.
- **Wrapped present** (was Ribbon & bow): per prop in its own inches — patterned paper (polka dots,
  stripes or satin), a ribbon crossing through the middle both ways with a fine weave shimmer and a
  bright satin sweep sliding along it every couple of bars, and a bow at the crossing whose loops glint.
- **Romantic melt**: crystalline ice with facets and glints; a *ragged* melt front that keeps its shape
  as it descends; the ice just below the front goes translucent pink before it gives way; the melted
  part is warm red/rose, hottest where freshly melted, slowly convecting; drops form on the front and
  fall under gravity in real inches with a trail, landing in a puddle that grows; then it refreezes
  from the ground up. Melts faster when the song swells (switchable).
- **Wrapped present** also has *random per prop* (each prop gets one of the four preset ribbon / paper combinations) and *random per prop (palette)*
  colour modes, a *mixed (per prop)* paper pattern, and *bars before random presents re-wrap*.
- **Icicles**: icicles of different lengths at a set spacing in inches, brighter at the root, rime
  along the top edge between them; at each tip a drop swells, brightens, lets go and falls.
- **Candy cane**: soft stripe edges, a glossy sugar sheen, and a diagonal-in-inches mode.
- **Shooting star**: white-hot core, a tail that breaks into sparks, a sky with a few real stars.
- **Snow globe**: flakes of different sizes; the snow piles up along the bottom with a bumpy surface;
  a glass highlight at the top.

## New building blocks

- **Fairy lights** (classics) — the plain string of mini lights, warm/cool/multicolour/palette, over a
  dark tree, the painted picture or nothing.
- **Garland** (classics) — tinsel wound around each prop, sparkling and sliding.
- **Toy train** (classics) — a lit train running the group's whole wire, headlight, red engine with a
  flickering firebox, coloured carriages with windows, smoke behind; one lap every N bars.
- **Bokeh** (Classic LED) — out-of-focus coloured discs drifting across the group in inches, bright
  rims like a lens. The Christmas-photo look.
- **Kaleidoscope** (Classic LED) — mirrored wedges and rings around each prop's centre, rotating;
  made for the snowflakes and crosses.
- **Snow on top** (modifier) — caps any animation with ragged, sparkling snow.
- **Melt** (transition) — the old picture melts away top-down (or up) with a warm edge and drops.

## Timeline: multi-select, and why ⌘C / ⌘V / ⌘T "didn't work"

- Two causes found. (1) Shortcuts were ignored whenever anything in the inspector had focus — after moving a
  slider or picking a dropdown, ⌘C went nowhere. Now only a *text* field swallows keys. ⌘C / ⌘V are also
  caught as clipboard events, so they work even where the browser eats the keydown (Safari).
  (2) **⌘T cannot be intercepted by a web page** in Chrome or Safari (it is "new tab"). Split is now also on
  plain **S**, and there are *copy* / *split at playhead* buttons in the clip inspector.
- **Multi-select**: shift-click adds/removes clips; shift-drag on empty timeline draws a selection box;
  ⌘A selects all (of the previewed group if one is chosen); Esc clears. The selection is one block: drag any
  clip to move them all (alt-drag copies the block), ⌘C / ⌘V paste the block at the playhead keeping the
  spacing and groups, S splits every selected clip under the playhead, ⌘D repeats the block after itself,
  Delete removes them all. The inspector lists the selected clips (click one to edit it alone).

## Group props (`/sort`)

Pool-and-board tool linked from the Groups panel. The pool (left) holds every unassigned prop sorted by theme
(Characters · Sweets & bells · Trees & wreath · Snowflakes large / small · Stars · Bursts & crosses) with
silhouette cards; drag a prop onto the empty board to spawn a group, drag more in, drag back to the pool to
remove; ⇥ drags a whole theme; groups get colour / palette / controller prefix and pixel + controller counts.
*✨ groups from themes* places the pool in one go. *Save to layout* writes `assets/layout.json` (pool leftovers
kept in a hidden "Pool (unassigned)" group; moved props drop their controller for auto-assign).

## Placement grid: map backdrop + arranging props en masse

- **Map backdrop**: pick `site_plan_2026.png` (the PDF you sent, in `assets/site/`; scale 4.67 in/px measured from its scale bar — the nominal
  1 in = 100 ft is not how the PDF was exported) from the grid toolbar; drag it
  under the props with *move map* (M), *calibrate* by clicking two points and typing the real distance, *fit map*,
  opacity slider. Saved in `layout.json` as `map`. *upload…* accepts PNG/JPG/PDF for next year's plan.
- **Multi-select** on the grid: drag a box on empty space, shift-click, ⌘A, or *⬚ select all* on a group card.
  Drag any selected prop to move the lot; arrows / R act on all.
- **Controllers** can be dragged on the grid; they ride along when their whole block of props moves (drag, arrows,
  arrange operations) and can be re-placed at their props' centroid (*⌂ place controllers* on the group card,
  *⌂ re-place controllers* in the Arrange panel).
- **Arrange panel** (2+ selected): move by Δ, face across the row, flip facing, rotate block, mirror, snap;
  straighten onto the best-fit line, distribute evenly, space along the row at N inches, row →, column ↑, reverse
  order, align x/y; place on an arc (radius + span, facing the centre); set z for all; move all to a group.

## Timeline & preview

- The timeline shows **one group's lanes at a time** — group tabs above the tools (the preview follows); *all* for
  every group.
- The preview is a **3D orbit camera**: drag orbit, shift/right-drag pan, wheel dolly, F/double-click fit, presets
  front (1) · top (2) · ¾ (3) · drive-by (4); 5 ft ground grid. **Car view (5)** rides a route you draw on the
  props grid (*🚗 route*) at a set mph / eye height, whole show rendered, head turn by dragging.
- Props grid: silhouettes at **real scale and rotation** (tipped back from the footprint line) so arrangements and
  facing read at a glance; hand tool (hold H / Space or ✋) for panning; controllers draggable and following blocks.

## Under the hood

`fx/util.py`: `glints` (sharp specular flashes, not sine wobble), `baubles`/`bauble` (shaded spheres,
vectorised), `blob`, `wire_offsets`. `classics.tree_body / fairy / tinsel` are reusable scene pieces.
Full-yard cost of the heaviest new effect (Tree & ornaments, 68 props) is ~35 ms/frame in the
preview; everything else is 5–25 ms.

---

# Changes — 2026-09-14 · Lightshow Studio, round 3

26 new effects and a reorganised effects browser. Everything below is in the repo
(`~/Documents/Lightshow/repo`) — no zip this round; review with `git diff`.

## New effects (77 total, was 51)

- **Christmas classics** (6): Candy cane (stripes marching along each prop's wire) · Ornaments
  (green tree with glinting ornament clusters) · Ribbon & bow (wrapped-present paper with a
  shining ribbon) · Shooting star (a star crossing the whole group in real inches with a tail) ·
  Snow globe (shaken, swirls, settles over the painted scene) · Icicles (hanging ice with drips).
- **Song themes** (5), one per song that had no look yet: Candy stripes (Rockin' Around) ·
  Tacky (Winter Wonderland — every prop running a different cheap 1990s program at once) ·
  Romantic melt (Snowman — ice melting top-down into reds and pinks) · Pale elements
  (Pentatonix — bass/mid/high each light a different part of the prop) · Plum energy storm
  (Sugar Plum trap remix — 808 shockwaves and hi-hat grains).
- **Choreography** (6) — the multi-prop primitives from the original brief, all using the real
  distances between props: Feature prop · Shockwave · Converge · Scatter · Call & response ·
  Wave across. Each takes a *feature prop* that can sit at the centre/ends, be the largest prop,
  be handed along the row every few bars, or jump at random per phrase.
- **Transitions** +4: Prop by prop · Curtain · Spiral out · Blackout cut.
- **Modifiers** +5: Strobe gate · Colour shift (hue rotate, fixed or driven) ·
  Brightness envelope (breathe / duck / swell / follow / fade) · Mirror · Sparkle overlay.

## Effects browser

Search box (`/` to focus), filter chips for kind and for tags (♪ music, slow, painted, bulbs,
multi-prop), collapsible packs with counts, and per-effect favourites (★) that collect into a
Favourites section at the top. Filters, folded packs and stars are remembered between sessions;
a search unfolds everything and highlights the match. Tags show inline on each row.

## Tests: 64 passing

---

# Changes — 2026-09-12 · Lightshow Studio, round 2

Drop over your checkout as before. New Python deps: `matplotlib` (placement PDF).
The audio analysis cache moved to `out/studio/show16.v2.npz` (adds 8 EQ bands); the zip
includes it so the first start is instant. Your paint files and layout are untouched.

## Your feedback → what changed

- **Regions** — added a test that Santa's painted regions come out in their painted colours; the
  amber shift now barely touches saturated colours (a red bell stays red when dimmed). Every
  region-aware clip's inspector says how many props in the group are painted.
- **Static views** — *Static* pack → **Static picture** clip (painted / palette / one colour / white,
  slow breathe, lamp model as a slider).
- **New packs** — Fire (4), Ice & Snow (5), Ibiza (4), Techno (4), Music driven (6 incl. the Carol
  looks: onset sparkle, hold-your-breath, the drop, outline trace, energy fill, **EQ visualiser**).
  Incandescent +4 slower looks (Warm breathe, Slow wave, Twinkle bulbs, Region wander).
  Classic LED +3 smooth looks (Gradient flow, Colour breathe, Meteors); Colour blocks / chase / fill
  got blend / soft-edge / smooth sliders (defaults smooth). 51 effects total.
- **Transitions** — the outgoing and incoming animations both keep running through the whole
  transition (the old version froze the last frame — that was the visible stop). Every transition has
  a timing curve and extra controls; the inspector has a duration field and *centre on cut*. New: Shatter.
- **Painting** — click another prop in the group list while painting to switch; edits autosave and the
  preview updates immediately.
- **Grid** — silhouette icons on the map and in the lists; distance readout uses the prop's name;
  *+ add props* per group opens the library (already-placed props greyed with where they are).
- **Timeline** — ⌘C / ⌘V copy & paste at the playhead, ⌘T split at the playhead. **Effect previews**: hover an effect in the browser to see it animate on a 4-prop rig (click to pin); transitions preview as Colour blocks → Rainbow, modifiers over Gradient flow.
- **Render page** — *Placement PDF*: page 1 whole course, then one page per group (top-down in inches,
  silhouettes, names, controller:port, neighbour distances, table). Plus the AI round-trip (below).

## AI final pass

Render & cards → **AI final pass**: download `show_digest.md` + `project.json`, hand both to Claude with
your notes ("make the Snowflakes calmer in song 3", "tighten every transition to 1 bar", …), then
**Import project.json…** the file it returns. The import validates everything (unknown effects /
params dropped, values clamped, overlaps trimmed) and shows the fix-up report; the previous project is
backed up next to it. You keep full control: nothing in the tool is generated, the AI only edits the
same JSON you edit.

## Tests: 62 passing (`make test`)

Workflow from here: I edit the files directly in `~/Documents/Lightshow/repo` (you review with `git diff` and commit); no more zips.
