# Control protocol (DMX512 trigger)

Sourced from GIGACOLOR's own datasheets, not from reverse engineering:

- **GC-6612Pro** — 12-port SD controller. Documents the full DMX512 trigger
  channel map, the RJ45 pinout, sync modes, and the `.rgb` filename rule.
- **GC-102C** — the audio box that was previously wired to the DMX in port.
  Documents what it sends and why.

> **Caveat:** the channel map is published for the **GC-6612Pro**. Our units
> are **GC-6004**. The 6004's own product page confirms it "accepts console
> commands to call programs, adjust speed and brightness" — the same three
> functions — but does not publish the channel numbers. Treat the map as
> very likely shared, and **test before relying on it**.

## GC-6004 — confirmed specs from the vendor page

| | |
|---|---|
| Type | 4-port standalone SD offline controller |
| Output | 4 × 3-pin, DMX512 / TTL / SPI, each port can drive a different IC |
| Capacity | **1024 pixels per port, 4096 per unit** |
| Scenes | **Max 62 program files** (the 6612 supports 64) |
| Grey scale | up to 65536 levels, **gamma correction supported** |
| Trigger input | RJ45 (DMX512); the unit has both **DMX IN and DMX OUT** |
| Interface | **LCD display + three buttons** (功能 / ▲ / ▼) |
| Power | DC 5–24 V, 2 W |
| Size | 176 × 93 × 25 mm |
| Software | works with FAST LED — the tool you already use |

The front panel photo labels the RJ45 pins `1:D+ 2:D- 7:GND`, identical to
the 6612. There is also an 音频 (audio) label on the top right.

### Observed on the unit's own panel

- **`DMX Add` menu item exists, settable 1–512.** Confirmed on the hardware,
  not inferred. The GC-6004 therefore implements standard DMX addressing
  across a full universe, and the trigger block is addressed the same way the
  GC-6612Pro documents. This is the strongest evidence yet that the published
  6612 channel map applies.

  Note the block must *fit*: if it is 13 channels wide, the highest workable
  start address is 500. For this project set every controller to **1**.

### Two corrections to earlier notes in this repo

**`0x0480` = 1152 is *not* the per-port pixel limit.** The 6004 is documented
at 1024 pixels per port. That constant in every channel record means
something else and remains unexplained.

**`Sync master` / `Sync slave` is a GC-6612Pro feature.** The 6004's feature
list does not mention it. Multi-controller drift is therefore **still an open
question for our hardware** — what the 6004 does give us is that a single DMX
scene-select command reaches every unit at once, which synchronises *starts*.
Whether they stay aligned over a 3-minute song is unmeasured.

**The 6004 has an LCD and buttons.** If yours appears not to, look again with
the unit powered — the DMX address and mode are set there, and that is the
fastest route to confirming everything on this page.

### What DMX OUT implies about the daisy chain

The 6004 has DMX **IN and OUT** with the same pinout, which is the signature
of a control pass-through, not a pixel bus. Combined with a 4096-pixel
per-unit ceiling, that points at:

> Each unit plays **its own SD card**, and the DMX chain carries only scene
> select / brightness / speed. The 24-channel `.rgb` we decoded is then a
> project-level render that FastLED splits per controller on export — which
> is exactly what the empty `WriteToSDList` element in the `.xml` projects
> would record.

This is the leading hypothesis, not a measurement. `tools/bus_probe.py` and
`tools/chain_map.py` still settle it.

## The DMX in port is a program selector

The GC-102C listens to audio, detects low-frequency drum beats, and emits
DMX512 that tells the controller **which program on the SD card to play**.
Its touch panel buttons map directly to scene numbers — one button plays
scene 2 in a loop, another scene 3, and so on.

So the DMX in port was never a mystery protocol. It is standard DMX512
selecting scenes, which means **selecting a scene is a start trigger**.

## Bench sync through the audio box (decided 2026-09-08)

Until the yard runner exists, the **laptop is the runner**. One stereo file:
music on one channel to the speakers, **cue beeps** on the other channel into
the GC-102C. The box hears a "drum hit", emits a DMX scene-select, and every
controller on the chain starts the scene at the same instant — locked to the
music because both channels come off one clock.

`tools/make_cue_track.py` builds the file. The beep is kick-shaped (80 Hz,
150 ms decay, click transient) at full scale; the cue channel carries nothing
else, so the detector only ever sees our cues.

**Characterise the box first** (`--test`, a beep every 10 s, no music) and
record here what a beep actually does:

| Question | How to see it | Result |
|---|---|---|
| Does one beep **advance** to the next scene, **restart** the current one, or pick at **random**? | count scenes on the LCD across 6 beeps | *unknown* |
| Shortest gap between beeps it honours? | `--every 2`, then 1, 0.5 | *unknown* |
| Does it need a burst (`--repeat 3`) or one hit? | try both | *unknown* |
| Level needed at the box input? | lower `--beep-gain-db` until it stops | *unknown* |
| Beep → lights-on latency (box + DMX + controller)? | phone video at 60 fps, count frames between the beep and the first lit frame | *unknown* → becomes `--music-delay-ms` |
| Does the box also react to the music channel bleeding in? | play music only, cue channel silent | *unknown* |

If a beep *advances* rather than selects, scene order on the card is the
show order, and a "reset to scene 1" needs its own procedure (power cycle, or
N beeps to wrap around). Note it here once known.

## Channel map

Thirteen channels from a user-set base address (`Add`):

| Channel | Function |
|---|---|
| `Add+1` | Total brightness |
| `Add+2` | Red adjust |
| `Add+3` | Green adjust |
| `Add+4` | Blue adjust |
| `Add+5` | White adjust (RGBW fixtures only) |
| `Add+6` | **Scene selection** — 4 DMX values per scene, up to 64 scenes |
| `Add+7` | Play speed (0 = slowest) |
| `Add+8` | Strobe (0 = off) |
| `Add+9` | Mix/background mode |
| `Add+10..12` | Mix red / green / blue |
| `Add+13` | Grouping — per-port open/close patterns |

**Scene selection is quantised to 4 DMX values per scene:**

```
scene 1 -> values 0-3        scene n -> values (n-1)*4 .. (n-1)*4+3
scene 2 -> values 4-7        so a safe value is (n-1)*4 + 1
scene 3 -> values 8-11
```

Base address is set on the controller itself (its display shows a DMX
address). Give every controller the **same** base address and one DMX
command drives them all together — or different addresses to control them
independently.

## Pinout — it is RS-485, not Ethernet

The DMX RJ45 is wired:

| Pin | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| | D+ | D− | NC | NC | NC | NC | GND | NC |

This confirms the earlier reasoning: a USB-to-Ethernet dongle can never read
it. You need RS-485 on pins 1, 2 and 7.

Note the touch panel runs over a network cable at standard **T568B**, so
cabling is ordinary Cat5e — only the signalling differs.

**Output ports** are 3-pin: `GND`, `DA/D+`, `D−`, and the datasheet states
they are compatible with both RS-485 and SPI (TTL). So a single-wire IC like
UCS2903/WS2811 uses D+ as its data line.

## Sync master / slave — this solves the drift problem

The controller has four modes:

| Mode | Behaviour |
|---|---|
| `auto` | plays every scene file on the SD in serial-number order, looping |
| `Dmx trigger` | obeys DMX512 commands |
| `Sync master` | issues synchronisation instructions to other controllers |
| `Sync slave` | follows a master controller's sync instructions |

**There is a built-in hardware synchronisation mechanism.** Multi-controller
drift was logged as a blocking unknown on the assumption that sync could only
come from starting units simultaneously by hand. It does not — one unit runs
as master and the rest follow.

This needs testing on the GC-6004 specifically, and the wiring path for the
sync signal needs confirming (most likely the same DMX in/out chain), but it
changes the deployment architecture from "hope they stay aligned" to "wire
them as master and slaves".

## Filename convention — confirmed ON THE BENCH (2026-09-10)

```
Sc-SS-PP.rgb   e.g. Sc-01-01.rgb, Sc-02-01.rgb
   |  |
   |  +-- part (keep 01)
   +----- SCENE number: what the SCE button and the DMX scene select refer to
```

Tested: with `Sc-01-01-show.rgb` + `Sc-01-02-eye_candy.rgb` the controller's
SCE setting did nothing (both files read as scene 1). Renamed to `Sc-01-01.rgb`
and `Sc-02-01.rgb`, SCE switched between them. Whether a description suffix
is tolerated is untested -- keep the bare form. The datasheet's "NAME-XX" text
below is therefore misleading for the 6004: the FIRST numeric group is the
scene. Descriptions live in manifest.json, not the filename.

Datasheet text (for reference):

```
XXXXXXXX-XX.rgb
   |       |
   |       +-- scene serial number, 01..64. Auto mode plays in this order.
   +---------- name, up to 8 characters, default "SC"
```

Up to **64 scene files** per card. The datasheet recommends formatting the SD
card before copying, and editing filenames on a PC rather than in place.

That matches the cards: `Sc-01-01.rgb`, `Sc-02-01.rgb`.

## The 512-byte LUT is a gamma curve

The datasheet lists "up to 65536 gray level control, built-in user-defined
gamma correction curve". That is what the 256-entry uint16 table in the
`.rgb` header is — a user-definable gamma curve, not a vestigial field.

Our factory files all carry an identity ramp, which is consistent with the
measurement that the hardware applies no gamma, and why the toolkit applies
`v ** 2.2` in software. Writing a real curve into that table is a viable
alternative and is now a known-good option rather than a guess.

## Other specs worth knowing

- Frame rate is a device setting, and load-dependent: the datasheet warns
  that at maximum pixels per port you must drop to about 20 Hz. Our
  measured 60 fps is consistent with a light load.
- IC type is selectable: UCS2903, DMX512 250K, DMX512 500K, plus custom
  modes. The `.xml` projects use "通用IC" (generic IC).
- GC-6612Pro tops out at 1360 pixels/port and 16K total. The GC-6004's
  limits are unknown; the constant `0x0480` = 1152 in every channel record
  may be its per-port maximum.

## How to drive it

Cheapest path is an **ESP32 or Arduino plus a MAX485** (about $8 total):

1. Set every controller to the same DMX base address and `Dmx trigger` mode.
2. Send a DMX universe with `Add+1` at 255 (full brightness) and `Add+6` at
   `(scene-1)*4 + 1`.
3. Every controller jumps to that scene at once — a synchronised start with
   no hand timing.

`tools/dmx_scene.py` computes the values and can send them if you have a
USB-RS485 adapter.

**Test order on the GC-6004**, cheapest first:

1. Check the controller's display/menu for a DMX address and a mode setting.
   If `Sync master`/`Sync slave` appear, the architecture question is
   answered on the spot.
2. Send scene-select on `Add+6` and watch for a program change.
3. If nothing responds, sweep the base address — the map may be shared but
   offset, or the 6004 may implement a subset.

## Bench playback on a Mac (speakers + box)

A Mac cannot drive its built-in speakers and the headphone jack at once (the jack takes over the same output device), so the GC-102C needs its own output: a USB-C → 3.5 mm adapter. `tools/bench_play.py` plays `cue_show.mp3` to two devices at once — music (L) to the speakers, beep (R) to the USB adapter → RCA → box. No aggregate device or BlackHole needed; the two streams start within a few ms, and after the beep the controller runs on its own clock. `--offset-ms` shifts music vs. beep at playback (no re-render); `--list` shows devices.
