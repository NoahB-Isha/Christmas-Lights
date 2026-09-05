# CLAUDE.md

Read this before doing anything. It is the condensed result of a long
reverse-engineering session and it will save you from re-deriving things
that cost real hardware time to establish.

## What this is

Software for a music-synced Christmas light show: 66 props, ~20 SD-card LED
controllers, Mac primary. It replaces a Windows-only vendor tool
(`FastLED.exe`, vendor name **Colorloong**) with something that understands
where props physically are, syncs to music, and can be extended with
AI-written effects.

**Sync is start-time based.** The controllers play from their own SD cards
with no network. Every controller's file must have the *same frame count*,
and they must be started together. There is no live sequencing at showtime.

## Ground rules

1. **Do not re-derive the `.rgb` format.** It is fully solved. The codec
   round-trips real factory files **byte-for-byte** across 4, 8 and 24
   channels, and `tests/` asserts it. If you think it is wrong, run the
   tests first.
2. **Verify against real artefacts.** Byte-exact round-trip beats any amount
   of reasoning. `assets/factory/` holds two real controller files.
3. **Never test with uniform frames.** A frame where every pixel is the same
   colour renders correctly under *any* wrong layout. A byte-vs-pixel
   confusion hid behind uniform test patterns for several rounds of hardware
   testing. Always use spatially varied content.
4. **Size effect features in inches, not normalised coordinates.** Bulb
   pitch across the prop library runs 0.5 in to 2.1 in — a 4x spread. A
   feature sized in u/v is invisible on a sparse prop and coarse on a dense
   one.
5. **Author in seconds, not frames.** Converting at render time only.
   Frame-based authoring previously produced a 1.16 s "breathing" pulse and
   a twinkle that reseeded every frame — a 60 Hz strobe.
6. **Say when you are inferring rather than verifying.** Several confident
   conclusions here were wrong and were caught by physical testing.

## Layout

```
src/lightshow/
  formats/rgbfile.py    .rgb codec (verified byte-exact)
  formats/props.py      .mod / .moc + physical scale
  formats/colorloong.py FastLED .xml projects
  rig.py                one geometry model for all input formats
  music.py              audio analysis (numpy + scipy + ffmpeg, no librosa)
  effects.py            effect registry, pure functions
  preview.py            standalone HTML geometry viewer
tools/                  generators and hardware diagnostics
assets/props            .mod prop models, .moc rig
assets/projects         Colorloong .xml projects
assets/factory          real controller files -- the round-trip fixtures
docs/                   full documentation, start at 01-CONTEXT.md
out/                    generated, gitignored
```

## Facts, verified

| Thing | Value |
|---|---|
| Frame rate | **60 fps**, measured. A *device setting*, not in the file |
| `0x10` | frame size in **bytes**, not pixels |
| Channel record counts | **bytes**; ÷3 = pixels |
| `0x0E` | frame count, uint16 — hard cap 65,535 frames (~18 min) |
| `0x0C` | header size − 1 |
| Header size | `0x17 + 13 × channels + 512` |
| Byte order | interleaved RGB as stored, no swap |
| Brightness | full 0–255 works; factory caps ~127 as a power convention |
| Checksum | none anywhere |
| LUT | 512-byte identity ramp → **no hardware gamma**, do it in software |
| Coordinate scale | 20 units per inch (`lampRad: 5` = half-inch bulb) |
| Empty port | exports as a **32-pixel stub** — omitting it shifts all later channels |
| `dots[i]` | pixel *i* in wire order |

## Unknowns — do not assume these

**Blocking:**

- **Multi-controller start drift.** Nobody has measured whether two units
  stay aligned over a full song. Sync depends entirely on it.
- **Chain addressing.** Nothing in the file says which unit is which in a
  daisy chain. Run `tools/chain_map.py`, swap two units, run again. If the
  map follows position, cable order is show-critical.

**High value:**

- **DMX in/out start trigger.** If a start command can be sent, it removes
  hand-timing error *and* largely dissolves the drift problem. Highest-value
  remaining reverse-engineering target.

Details and the rest in `docs/06-OPEN-QUESTIONS.md`.

## Common tasks

```bash
pip install -e ".[dev]"        # or: pip install -r requirements.txt
make test                      # 43 tests, ~0.4 s
make props                     # contact sheet of every prop
make show SONG=path/to.mp3     # build the music-driven show
make player SONG=path/to.mp3   # audio-synced HTML preview
python -m lightshow.preview assets/props/47号.mod out/prop.html
```

Audio needs `ffmpeg` on PATH (`brew install ffmpeg`).

## Writing an effect

Effects are pure functions of one context object, registered by decorator.
Read the docstring at the top of `src/lightshow/effects.py` — it documents
every field and is written to be sufficient on its own.

```python
@effect("drifting frost", speed=0.3)
def drifting_frost(c):
    band = np.exp(-((c.y_in - c.t * c.p["speed"] * 12) / 6.0) ** 2)
    return frost(band * c.rms)
```

Two conventions that are not obvious:

- Return **perceptual** 0..1. `to_bytes()` applies gamma 2.2, because the
  controller applies none.
- Composite layers with `lighten()` (per-channel max), not addition. Adding
  several coloured layers drives every channel to 1.0 and the prop turns
  white, destroying the colour distinction that makes layering readable.
  `tests/` asserts this.

## The current bench rig

One controller, one prop: `47号.mod` on **port 4 (ch3)**, 72 px, a
4-armed cross that reads as a **snowflake**, 40 × 40 in on a 2-inch pitch.
Ports 1–3 are empty → 32 px stubs. Frame is 504 bytes.

Palette is **ice**, not Christmas red/green/gold — the shape wants frost.
The signature element is a sparkle whose core is white and whose falloff is
blue: saturation *rises* as brightness falls, so grains are born white-hot
and cool into blue. That inversion is one line in `frost()`.

## Where to pick up

`docs/04-ROADMAP.md` has the phases. Phase 0 (frame rate) is done. The
present state: a single prop plays a full music-synced show that looks good
on hardware. The next real step is Phase 1 — a layout editor, since prop
placement in the yard is information that does not exist in any file yet.
