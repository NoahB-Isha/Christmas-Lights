# Project overview (start here)

*Written 2026-10-08 as the handoff for a collaborator and their AI agent; kept as the repo's overview. The software it describes is in `src/` and `tools/`.*

Read in this order: this file → `docs/01-CONTEXT.md` → `CLAUDE.md` (the condensed hardware
truth) → `docs/09-SHOW-DESIGN.md` (what the show is) → `docs/12-HARDWARE-UPDATES.md` and
`docs/08-CONTROL-PROTOCOL.md` (DMX, bench-confirmed) → the rest as needed.

---

## 1. What this is, in one paragraph

A **driven course** of Christmas pixel props at the Isha Foundation campus (Tennessee), a
one-way loop ~300 ft long with 6 clusters of props. Each prop is a steel frame of RGB
"bullet" pixels (Colorloong / GIGACOLOR, Chinese vendor). Every prop is wired to a port of a
**GC-6004** 4-port SD-card controller. There is **no live pixel streaming**: each controller
plays a pre-rendered `.rgb` file off its own SD card, and the only runtime control is a
**DMX512 scene-select** command ("play scene N now") sent by a show-runner laptop over an
ENTTEC DMX USB Pro. A **14:42 music show** (nine-song medley, `show16.mp3`) runs every half
hour as scene 1; slower **idle/filler patterns** loop between shows as scenes 2+. The owner
replaced the vendor's Windows-only tool (`FastLED.exe`) with a custom Python pipeline that
knows where props physically are, syncs to the music, and renders one card per controller.

## 2. Hardware — measured facts (do not re-derive)

| Thing | Value |
|---|---|
| Controller | GIGACOLOR **GC-6004**, 4 ports, 1024 px/port, 4096 px/unit, SD card, DMX IN + OUT (RJ45), LCD + 3 buttons, 62 scene files max, DC 5–24 V |
| Playback rate | **30.30 fps**, fixed (measured from video and by hand-timing a 60 fps card playing at exactly half speed). Speed channel 255 = native. **Render everything at 30.3 fps.** |
| Frame cap | 65,535 frames per file (uint16) → 36 min at 30.3 fps. Show = 14:42 = 26,724 frames, ~52 MB per controller at the densest |
| File format | `.rgb`, fully reverse-engineered and verified **byte-for-byte** against factory files (`docs/02-FILE-FORMATS.md`, `assets/factory/`). Header `0x17 + 13×channels + 512` bytes, frame count uint16 at `0x0E`, frame size in BYTES at `0x10`, identity 512-byte LUT → **no hardware gamma, apply gamma 2.2 in software**, no checksum, interleaved RGB |
| Filenames | `Sc-SS-PP.rgb` — **first number is the scene** (confirmed on the unit); keep numbering contiguous |
| Empty port | must be exported as a **32-pixel stub** or every later channel shifts |
| SD cards | **FAT32 only** (exFAT silently fails), MBR, 32 KB allocation unit, full format with the SD Association formatter, write files largest-first in one pass, never rewrite in place (fragmentation made a controller drift). 8 GB industrial SDHC recommended |
| Sync | **Start-time based.** All controllers' files for a scene must have the identical frame count; a DMX scene-select restarts the file from frame 0 on every unit at once → every scene change is a free re-sync |
| DMX hold | Controller **keeps playing the last scene** when DMX stops (tested). Failure mode is "stuck", not "dark"; blackout needs a live link |
| Prop coordinates | `.mod` files: 20 units per inch, `lampRad: 5` = half-inch bulb, **y-down on disk** (flip at load). `dots[i]` = pixel i in wire order |
| Bulb pitch | 0.5–2.1 in across the library — size effect features in **inches**, never normalised |

### DMX channel map (bench-confirmed, revision 2 — the datasheet is one too high)

13 channels from base address `Add`; **the base address itself is brightness.**

| Offset | Ch @ Add=1 | Function |
|---|---|---|
| Add+0 | 1 | brightness |
| Add+1..4 | 2–5 | red / green / blue / white adjust — **must be 255 or output is muted** |
| Add+5 | 6 | **SCENE**, value = (n−1)·4 + 1 (4 DMX values per scene) |
| Add+6 | 7 | speed, 255 = native |
| Add+7 | 8 | strobe, 0 = off |
| Add+8..11 | 9–12 | mix mode / mix RGB |
| Add+12 | 13 | grouping |

Working universe for "scene 7, full": `1=255 2=255 3=255 4=255 6=25 7=255`.

### DMX wiring, ENTTEC DMX USB Pro → GC-6004 DMX IN (RJ45)

XLR 1 (GND) → RJ45 **7** · XLR 2 (Data−) → RJ45 **2** · XLR 3 (Data+) → RJ45 **1** · XLR 4/5 open.
D+/D− on the orange pair, never split. ENTTEC params confirmed: break 181 µs, MaB 43 µs, 40 pkt/s.
**Multimeter every adapter** — the generic XLR→RJ45 adapter shipped with Data+ on pins 4+6 (unconnected
on the controller) and cost a day. Verify XLR 2↔3 reads *open*. If nothing responds, swap 2 and 3.

## 3. Props and layout

- **Library:** 69 `.mod` files (68 props + the `.moc` rig) in `assets/props/`. Each prop has real pixel
  coordinates. Biggest prop 655 px (12号 L/R). Chinese numbering `NN号`, 左/右 = left/right mirror pairs.
- **What is actually owned:** 35 designs / 48 pieces — `docs/13-INVENTORY.md` (vendor order sheet).
  `66#` has no `.mod`. "16#" on the sheet is really 61号 (waving Santa).
- **Layouts** (`assets/`): `layout.json` = all 68 library props in 4 themed groups
  (Santa's Workshop / Snowflakes / Stars / Yule) with 19 controllers — placeholder positions, to be
  rebuilt from the real inventory and the final grouping. `bench.json` = the 6-prop test bench
  (controller A ports 1–4: bell 1号, candy cane 4号, snowflake 27号, cross snowflake 47号;
  controller B ports 1–2: snowflake 19号, waving Santa 61号). Layout is 2.5D in inches:
  `x, y` on the ground plan, `z` = height of the bottom edge, `rot` yaw, `mirror`; each prop has a
  `group`, `controller`, `port`. Schema in `docs/09-SHOW-DESIGN.md` §4.
- **Paint regions** (`assets/paint/`): named pixel groups per prop with painted colours — Santa 61号
  (hat, face, jacket, trims, boots…) and bell 1号 (ribbon, bell). Lets effects draw "the real Santa".
- **Site plan** (`assets/site/site_plan_2026.png`, `docs/14-SITE-PLAN.md`): last year's course, orientation only.
  True scale **4.674 in/px** (from the drawing's scale bar; the nominal 1"=100' is not what the
  render came out at). Cars enter SE, exit NW. Christian area / manger / tunnel / pavilion have their
  own non-DMX lights.

## 4. The show

- **Track:** `Xmas Light Showv1.mp3` (= `show16.mp3` in the repo, not included here, 25 MB).
  14:42. Songs and per-song tempo map in the studio's digest export (Render & cards → show_digest.md) and `assets/show/songlist.md`:
  Carol of the Bells (84 BPM 3/4) · Run Rudolph Run (152) · Sugar Plum Fairy trap remix (64.6) ·
  Jingle Bells — Bublé (123) · Rockin' Around the Christmas Tree — Brenda Lee (142) ·
  Winter Wonderland — Brooks & Dunn (130) · Snowman — Sia (105) · Feliz Navidad (149) ·
  God Rest Ye Merry Gentlemen — Pentatonix (136, accelerando 110→164 at the end).
- **What the show looks like:** the studio's digest export (Render & cards → show_digest.md) is a complete, human-readable description of
  the sequenced show as of 2026-10-05 (every clip, effect, palette and parameter, plus the
  effect catalogue) — the best single document for understanding the creative content.
- **Design verdicts from the real props** (bench-tested, `docs/09-SHOW-DESIGN.md`, `docs/10-HANDOFF.md`):
  bright saturated LED-Christmas colours, ≤3 per section + white accent (muted colours look ugly);
  steps and clear events on the beat grid read from a moving car; fast per-beat flicker and
  volume-following flicker do not; props come in and out entirely; one unmistakable look per song;
  sparkle fields work as intros/ambient; incandescent "sign" programs (walk at half speed, build,
  alternate) and the painted picture were approved; avoid total blackouts (props ≥60 % bright
  ≥75 % of the time, soft rule).
- **Scene budget per card:** 1 = music show · 2–16 = idle loops · 17–46 reserved for a split show
  (per-song scenes, re-triggered over DMX, if drift ever matters — every scene change re-syncs for
  free) · 47–62 spare. **Every controller carries the same scene list.**
- **Idle/filler scenes:** 12 rendered for the bench on 2026-10-08 (2 min each, seamless loop with a
  4 s crossfade into a pre-roll of the start): Starscape · Ice sculpture · Fireside · Fairy lights &
  ornaments · Nochebuena (poinsettia) · Candlelight (painted picture) · Golden bokeh · Snowfall ·
  Northern lights · Lava lamp · Fiesta banners · Heartbeat.

## 5. Show runner (field operation)

- `showrunner.py` (owner's, pyserial, ENTTEC Pro protocol): holds the DMX universe on a 40 Hz
  background thread; fires the scene then starts audio after a calibrated `--lead-ms`;
  `play / cues / idle / loop (show every N min, idle between, curfew blackout) / blackout / calibrate`.
  Needs a watchdog (a hung runner looks like a working show that never changes).
- **Addressing:** 13 ch × 40 controllers = 520 > one universe → share addresses within a cluster
  (6 clusters → 6 addresses), or Art-Net with several universes.
- **Field distribution** (`docs/12-HARDWARE-UPDATES.md`): ~300 ft, 6 clusters, 40 units. Recommended
  Config B (two isolated DMX branches over outdoor Cat5e, 120 Ω terminators, opto splitter);
  wireless DMX (Config E) is now competitive because controllers hold their scene on signal loss;
  the same Cat5 can carry Art-Net later. Old system: FM-broadcast music + per-prop GC-102C audio
  boxes doing beat detection — retired; the audio box only ever emitted scene-selects.
- **Pre-flight per controller:** DMX address set, same scene list on the card, identical frame
  count per scene across all cards, chain continuity, FAT32 card freshly written.

## 6. Open questions (priority order)

1. Power-cycle with no DMX present — boots into a scene, or sits dark? (decides what a field power
   blip looks like; if it boots into a scene, make that scene the idle)
2. Start latency on direct DMX (video scene command vs first light)
3. Two controllers on different addresses → independent scene control confirmed?
4. Daisy chain via DMX OUT → pass-through confirmed? (+ terminator)
5. Scene channel range across all 62 scenes (`scene = value//4 + 1`)
6. Does the LCD's local speed setting multiply with the DMX speed channel?
7. Handedness of 左/右 pairs (`mirror` flag) — compare one asymmetric prop with the vendor tool
8. Prop 66# drawing from the vendor; final grouping/placement of the 48 owned pieces
9. Real-world drift over a full song (top risk if the show is kept as one 14:42 file)

## 7. Where things are

See the repo layout in `README.md`. The music file is `assets/audio/show16.mp3`; rendered cards and the
analysis cache live in `out/` (git-ignored, regenerable).
