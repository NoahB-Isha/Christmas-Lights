# File formats

Complete reference for every format in this pipeline. All of it is verified
against real files; the `.rgb` codec round-trips five factory files
byte-for-byte.

Pipeline:

```
.mod  (one prop, coordinates)
  |
  +--> .moc / .xml  (rig: which prop on which port)
          |
          +--> .rgb  (compiled frames -> SD card -> controller)
```

- `.mod`, `.moc` — JSON, written by the prop library / rig editor
- `.xml` — Colorloong project (FastLED.exe save file)
- `.rgb` — the binary the controller actually plays

---

# `RGB01001` — SD-card LED show format

Reverse-engineered from `Sc-01-01.rgb` (10,574,579 bytes). Confirmed by
byte-exact round-trip: parse → re-serialize → identical file.

**Endianness: big-endian throughout.** (An earlier draft read `0x0C` as a
little-endian timestamp; a second file disproved that — see below.)

## File layout

```
+---------------------------+
| header            587 B   |   0x000
+---------------------------+
| frame 0          2,028 B  |   0x24B
| frame 1          2,028 B  |
| ...                       |
| frame 5213       2,028 B  |
+---------------------------+
```

No per-frame headers, no delimiters, no trailer, no padding. The body
divides exactly: `(10,574,579 − 587) / 2,028 = 5214.000`.

## Header

| Offset | Size | Value in file | Meaning |
|---|---|---|---|
| `0x00` | 8 | `RGB01001` | magic |
| `0x08` | 4 | `FF FF FF FF` | constant, reserved (all 5 files) |
| `0x0C` | 2 | `02 4A` | **header size − 1** (586 for 4 ch). Tracks channel count |
| `0x0E` | 2 | `14 5E` | **frame count** = 5214. Governs playback length |
| `0x10` | 4 | `00 00 07 EC` | **frame size in BYTES** = 2028 = **676 pixels** |
| `0x14` | 2 | `00 04` | channel count = **4** |
| `0x16` | 1 | `01` | version / flags |
| `0x17` | 13 × N | — | channel records, N = `0x14` |
| `0x4B` | 512 | — | LUT: 256 × uint16 BE, **identity 0…255** |

Header size = `0x17 + 13 × channels + 512`.

### Channel record (13 bytes)

| Offset | Size | Meaning |
|---|---|---|
| `+0` | 2 | channel id, 0-based |
| `+2` | 2 | **byte** count for this channel (÷3 = pixels) |
| `+4` | 9 | `00 00 00 00 04 80 FA 00 50` — constant |

The 9-byte tail is **byte-identical on all four channels**, so it's
per-port config duplicated by the authoring tool. Probable fields: IC
type, colour order, max-pixels-per-port (`0x0480` = 1152), brightness
(`0x50` = 80), refresh (`0xFA` = 250). The exact split is unresolved —
**copy it verbatim.**

### Channel map in this file

| Ch | Bytes (stored) | Pixels | Pixel range | Byte range |
|---|---|---|---|---|
| 0 | 561 | 187 | 0–186 | 0–560 |
| 1 | 210 | 70 | 187–256 | 561–770 |
| 2 | 282 | 94 | 257–350 | 771–1052 |
| 3 | 975 | 325 | 351–675 | 1053–2027 |

The stored counts are BYTES. All four divide evenly by 3. They sum to
2028 bytes = 676 pixels = one frame.

**Frame count: 10,573,992 / 2028 = 5214 exactly.**

Confirmed three ways: every byte count divides by 3; the file's three
strongest spatial discontinuities land exactly on pixel boundaries
187 / 257 / 351 (repeating every 676); and temporal smoothness improves
from 15.47 to 6.36 versus the wrong 2028-pixel reading.

## Frame data

```
frame_size  = value at 0x10 (already bytes) = pixels × 3
frame_count = (filesize − header_size) / frame_size
```

Each frame is every channel concatenated in id order, 3 bytes per pixel.
Channel `c` starts at pixel `sum(counts[:c])`.

## Are the 4 channels independent or synced?

**Both — independently addressed, frame-synchronous.**

- Independent: each channel has its own pixel count and its own pixel
  data. There is no shared/mirrored block.
- Synced: there is exactly one frame counter for the whole file. All
  channels advance together and cannot have different lengths or rates.
  Brightness-envelope correlation between channels is 0.94–0.97 — the
  same choreographed show, not identical data.

You get full per-pixel control of all 2028 pixels, but one timeline.

## Notable findings

**Values never exceed 127.** Every byte in 10.5 MB falls in `0…127`, and
only 16 distinct values appear: `0, 8, 17, 25, 34, 42, 51, 59, 68, 76,
85, 93, 102, 110, 119, 127` — exactly `round(i × 127/15)` for i = 0…15.
So the source artwork was 4-bit-per-channel, scaled into a 7-bit range.
Whether the hardware accepts `128…255` is untested; `Diag.rgb` tests it.

**No checksum anywhere.** Nothing validates file integrity, so
hand-authored files load without needing a checksum fixed up.

**`0x0E` is the frame count, and it is authoritative.** The unit plays
exactly this many frames, not however many the file size implies. Writing
a value smaller than the real frame count truncates playback; writing a
larger one reads past EOF. It is a uint16, so **65535 frames is the hard
ceiling** (~132 MB at 2028 B/frame). There is no file-size limit as such.

Confirmed across five files spanning three channel counts:

| File | Size | Ch | `0x10` frame | Pixels | `0x0E` frames | Body ÷ frame | `0x0C` | Header |
|---|---|---|---|---|---|---|---|---|
| A | 10,574,579 | 4 | 2028 B | 676 | 5214 | 5214.0 | 586 | 587 |
| B | 132,299 | 4 | 1029 B | 343 | 128 | 128.0 | 586 | 587 |
| C | 561,581 | 4 | 2109 B | 703 | 266 | 266.0 | 586 | 587 |
| D | 1,301,631 | **8** | 4224 B | 1408 | 308 | 308.0 | **638** | **639** |
| E | 2,843,893 | **24** | 8721 B | 2907 | 326 | 326.0 | **846** | **847** |

Every one divides exactly; in all five the channel byte counts sum to
`0x10` and each divides by 3. The old pixel-count model fails on B and C
(`42.67`, `88.67` frames) — disproved by counter-example.

**`0x0C` is header size − 1.** Files D and E settled this: 638/639 and
846/847, matching 586/587 on the 4-channel files. So it is a derived
pointer to the last header byte, not a magic constant, and an authoring
tool must recompute it when the channel count changes.

**Header size is dynamic:** `0x17 + 13 × channels + 512`.

**Channel count scales freely.** File D is a single 8-port unit. File E
is 24 channels — six 4-port units daisy-chained — and the chain is
addressed as one flat channel list with no grouping, nesting, or
per-unit structure of any kind. Whatever the topology, it is just N
channels in one frame. `0x14` is a uint16, so up to 65535 channels.

Constant across all five files despite geometries from 343 to 2907
pixels: `FF FF FF FF` at `0x08`, `01` at `0x16`, the identity LUT, and
the 9-byte record tail on every channel. The tail never varying with
channel length or channel count confirms it is global config, not
geometry — so `0x0480` = 1152 is most plausibly a hardware
max-pixels-per-port limit stamped in unchanged.

**A 32-pixel channel means "no prop on this port."** Confirmed on
hardware and in the data: in file E all eleven 32 px channels are
byte-identical to one another, spatially uniform within every frame, and
merely follow a global fade (`0,0,0` → `18,13,13` → `36,26,26` → …).
It is the authoring tool's stub for an unconfigured port, not content.
This also explains file B's `ch1 == ch2 == ch3` — three empty ports, with
only its 247 px port 1 populated.

Real prop sizes therefore come from this vocabulary: **70, 94, 98, 157,
176, 179, 187, 193, 247, 325**. When authoring, declare unused ports as
32 px stubs to match the factory convention and keep the frame small.

Populated channels always hold independent data (file E's per-channel
means range from 4.86 to 49.0).

Bit depth is an authoring choice too. Files B and C use 3-bit levels
(8 steps); file E uses nearly the full 0-128 range. Several files contain
a stray **128**, so 0-127 was only ever a convention — consistent with
full 0-255 working on hardware.

**Identity LUT.** The 512-byte table is a straight 0…255 ramp, so it's an
unused gamma/brightness curve. Writing a non-linear curve here is a
plausible global dimming/gamma hook — untested.

## Colour order caveat

The byte triplets are almost certainly emitted to the LED IC in stored
order, but whether that's physically R,G,B depends on the strip's chip
(WS2811/WS2812 are commonly GRB). Frame 0 is `7F 00 00` on all channels.
If `Diag.rgb`'s "PURE R" phase lights green, swap bytes 0 and 1.

## Writing your own

1. Keep the header byte-identical unless changing geometry.
2. If you change pixel counts, update **both** the per-channel records
   and the total at `0x10`. They must sum.
3. Frame count is implicit in file size — just append frames.
4. Match the SD card's filename convention (`Sc-01-01.rgb`); overwrite an
   existing file rather than inventing a new name, since the unit's menu
   almost certainly indexes fixed names.
5. Back up the original card first.

## Frame rate

**Not stored in the file at all.** It is a device setting, with options
including 25 / 45 / 60 fps. **Measured at 60 fps** with `FpsTest.rgb`:
1800 frames took 30.0 s, and a 24-blink cross-check gave 1.00 blink per
second.

Note that the device setting silently rescales every file. Nothing in the
format records the rate a file was authored for, so a 60 fps file played
at the 25 setting simply runs 2.4x slow with no indication of a mismatch.

| File | Frames | Duration at 60 fps |
|---|---|---|
| A | 5214 | 86.9 s (full show) |
| B | 128 | 2.1 s (loop) |
| C | 266 | 4.4 s (loop) |
| D | 308 | 5.1 s (loop) |
| E | 326 | 5.4 s (loop) |

The short files are clearly loop segments, not truncated shows — that
conclusion holds at any rate, since they are 16-40x shorter than file A.

## Open questions


- Meaning of the 9-byte record tail. It is byte-identical across both
  files and all channels even though their geometries differ completely,
  so it is global config, not per-channel geometry. `0x0480` = 1152 still
  unexplained.
- Whether non-identity LUTs work. Full 0-255 brightness is confirmed.
- What `0x16 = 01` selects.

---

# Companion files: `.mod` and `.moc`

Both are **plain JSON** (UTF-8), used by the authoring software. They hold
the geometry the `.rgb` file does not.

## `.mod` — one prop model

```json
{ "dotCount": 98,
  "dots": [ {"x": -70, "y": 410}, ... ],
  "lampRad": 5,
  "version": "1.0" }
```

## `.moc` — a controller rig

```json
{ "controlType": 4,
  "portCount": 4,
  "ports": [ {"portNum": 0, "dotCount": 360, "dots": [...] }, ... ],
  "lampRad": 5,
  "version": "1.0" }
```

## What these establish

**`dots[i]` is pixel `i` in wire order.** Consecutive-dot distances are
uniform with zero large jumps (median step 10–41 units by prop), so list
order matches the LED chain. Coordinates snap to a 10-unit grid; y
increases upward.

**A `.moc` port's `dotCount` is exactly the `.rgb` channel size.** So
`.moc` defines the rig and `.rgb` is a render for it:
`rgb_channel_bytes[i] == moc.ports[i].dotCount * 3`. Prop `dotCount`s
match channel sizes seen in real `.rgb` files — 247, 179, 98, 176 and 193
all appear directly.

**`.moc` coordinates are one shared absolute space.** Ports are laid out
side by side (port 0 x −350..−240, port 1 −230..−120, …), not each
centred on itself. Effects should therefore be evaluated in global rig
coordinates; centring per port renders the effect once per prop instead
of once across the rig.

**This is the missing half of the toolchain.** The `.rgb` file carries no
geometry beyond pixel counts, so alone it only supports 1D index chases.
With `.mod`/`.moc` you can evaluate a spatial function at each LED's true
(x, y) and get rising fills, radial pulses, pinwheels and rain.

Observed props are Christmas decorations — candy canes, bows, bells, and
detailed figures. The spiral tree is an unrolled spiral: 500 dots at
exactly 10-unit pitch in a 1240 x 30 bounding box.

`controlType` was 4 on a 4-port rig, so it likely equals port count or a
controller model id; an 8-port `.moc` would distinguish these.

---

# Colorloong `.xml` — FastLED project file

The save format of `FastLED.exe`. XML, CRLF line endings, attribute-only
elements, root `<Colorloong>`.

```
<Colorloong>
  <PointRadius Radius="1"/>
  <DxfMark Mark="1"/>
  <PointShapeList Count="N">        whole canvas point cloud
    <PointShape Model TotalNum VerticalNum HorizontalNum
                Left Top Right Bottom/>
  <BufferCardList Count="P">        one BufferCard == one OUTPUT PORT
    <BufferCard LightModel="通用IC" LightCount="247">
      <Rect SortModel Left Top Right Bottom
            ShapeRadian ShapeMode ShapeAngleCount/>   one per pixel, WIRE ORDER
  <SceneList Count="1">
    <LayerList Count="L">
      <Layer LayName Ma LayerNum>
        <ShapeList/>
        <EffectList Count="1"><Effect .../></EffectList>
  <LightModels>                     library of 13 IC types
    <Light PinCount="3" Name="通用IC" IC="7" WhiteFlg WhiteScale
           AdjustRedScale ...>  4x <PinControl/>
  <WriteToSDList Count="0"/>        SD-card export assignments
```

## Verified facts

**`BufferCard` = one output port.** Its `LightCount` is exactly the `.rgb`
channel pixel count for that port. The three sample projects reproduce the
decoded `.rgb` channel lists exactly:

| Project | Ports | LightCounts | Total | Matches |
|---|---|---|---|---|
| `example3.xml` | 4 | 247/179/179/98 | 703 px | file C |
| `example.xml` | 8 | 176/179/193/193/193/157/70/247 | 1408 px | file D |
| `es.xml` | 24 | 11 of them `0` | 2555 px | file E (as 2907) |

**An empty port exports as a 32-pixel stub.** This is the mechanism behind
the 32 px channels in the `.rgb` files. In `es.xml`, `LightCount="0"` appears
at ports `[5,8,9,11,12,13,15,16,19,21,23]`, and file E's `.rgb` has 32 px
channels at *exactly* those indices. Substituting 0 → 32 reproduces the
channel list, and `2555 + 11x32 = 2907` is the exact frame pixel total.

> Any exporter **must** reproduce this. Emitting nothing for an empty port
> shifts every later channel's byte offset and silently corrupts the show.

**`Rect` centre is the pixel position.** Each `Rect` is a 2x2 box whose
centre equals the matching `PointShape`. The `BufferCard`s exactly partition
the `PointShapeList` — verified as sets: the union of 703 card-rect centres
equals the 703 `PointShape`s.

**Canvas coordinates are y-DOWN** (screen convention) and integer, unlike
`.mod`/`.moc` which are y-UP. `lightshow` flips y at load so everything
internal is y-up.

**IC library.** 13 `Light` models, each with 4 `PinControl` children.
Observed names include `通用IC` ("generic IC", `IC="7"`, the one used by every
sample project), `DMX512常规` (DMX standard), `DMX512高速` (DMX high-speed),
`UCS_2903`, `512-RGBW`, `TTL-RGBW`. Each carries per-channel scaling
(`AdjustRedScale`, `AdjustGreenScale`, `AdjustBlueScale`, `AdjustWhiteScale`,
`WhiteScale`), which is where a colour-correction feature would hook in.

**Effects are parametric, not baked.** An `<Effect>` carries `Mode` (e.g.
`4000`), `Angle` (radians), `Speed`, `Alpha`, `SingleFillWidth`,
`DiffuseOut`, `Transition`, flash frame counts, a `<Clolorlist>` (sic) of
`<Color Value="...">` integers (`0`, `255`, `65280`, `16711680` = black, red,
green, blue as packed BGR/RGB ints), and a full `LOGFONT` block for text
effects. `Left/Top/Right/Bottom` on the Effect is its extent on the
timeline/canvas, not a pixel region.

`WriteToSDList` was `Count="0"` in all three samples, so its schema is
unknown — this is where the tool records SD export assignments and is worth
capturing from a project that has actually been exported.

## Reading it

```python
from lightshow.formats.colorloong import load_xml
proj = load_xml("es.xml")
print(proj.summary())
print(proj.rgb_channels())   # 32-px stubs already substituted
```
