# Control protocol (DMX512 trigger)

Sourced from GIGACOLOR's own datasheets, not from reverse engineering:

- **GC-6612Pro** — 12-port SD controller. Documents the full DMX512 trigger
  channel map, the RJ45 pinout, sync modes, and the `.rgb` filename rule.
- **GC-102C** — the audio box that was previously wired to the DMX in port.
  Documents what it sends and why.

> **Caveat worth keeping in front of you:** our controller is the
> **GC-6004**, not the GC-6612Pro. Same vendor, same `.rgb` files, same "GC
> series" language in the GC-102C doc, so the protocol is very likely
> shared — but the channel map below is **documented for the 6612 and
> assumed for the 6004 until tested**. Testing is cheap (see below).

## The DMX in port is a program selector

The GC-102C listens to audio, detects low-frequency drum beats, and emits
DMX512 that tells the controller **which program on the SD card to play**.
Its touch panel buttons map directly to scene numbers — one button plays
scene 2 in a loop, another scene 3, and so on.

So the DMX in port was never a mystery protocol. It is standard DMX512
selecting scenes, which means **selecting a scene is a start trigger**.

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

## Filename convention — confirmed

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
