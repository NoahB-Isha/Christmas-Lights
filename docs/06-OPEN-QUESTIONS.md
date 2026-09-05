# Open questions

Live document. Anything asserted elsewhere as fact has been verified against
real files or real hardware; anything here has not.

**Frame rate is now measured: 60 fps.** It remains a *device setting* that
is not recorded in the file, so every controller must be left on 60 — a unit
switched to 25 will play the same file 2.4x slow with no error shown. Worth
adding to the pre-flight checklist.

## Blocking

### Multi-controller start drift — UNTESTED
Sync depends entirely on controllers starting together and holding the same
rate. Nobody has measured drift between two units over a full song.

**How to close:** put an identical long file on two cards, start both, and
check whether they are still aligned several minutes in. If they drift, the
show design has to account for it (shorter files, re-sync points, or
accepting per-prop independence).

### Chain addressing — how a controller knows which unit it is — UNKNOWN
Confirmed absent from the file: the 24-channel `.rgb` has flat sequential
channel ids `0..23`, a byte-identical 9-byte tail on all 24 records, and no
grouping, unit id, or per-unit block of any kind. Addressing therefore comes
from outside the file.

Two candidate mechanisms, with very different consequences:

- **Positional** — each unit consumes its channels and passes the rest
  downstream. Chain order *is* the address, nothing is configured on the
  unit, and **re-cabling silently remaps every prop.** Cable order becomes
  show-critical and must be documented and labelled.
- **Configured on the hardware** — DIP switch, rotary, jumper, or stored
  config. Units can be re-cabled freely but must be individually labelled.

**How to close:** run `reference/ChainMap.rgb`, record the channel-to-prop
map, then physically swap two units and run it again. If the map follows the
position it is positional; if it follows the unit it is hardware-configured.
Also pull the SD card from a downstream unit and re-run — if it still lights,
only the master card matters and data passes down the chain; if it goes dark,
every unit needs its own copy.

**Why it matters for the software:** the deployment layer's port-to-prop
mapping is only stable if we know which of these is true. Under positional
addressing the manifest must record cable order as a first-class fact.

### Start trigger over the DMX in/out port — NOT YET INVESTIGATED
The controllers have DMX in/out ports. If a start command can be sent over
them, it replaces the manual "start the music on the 4th blink" step and
removes hand-timing error from the whole show — which also largely dissolves
the multi-controller drift problem above, since all units could be started
from one signal.

Worth capturing when the hardware is to hand: what the ports are physically
(XLR? RJ45?), whether the unit responds to standard DMX, and whether there is
any documented remote/trigger protocol. A logic analyser or a DMX interface
plus a capture of the vendor software talking to the unit would settle it.
This is the highest-value remaining reverse-engineering target.

## Non-blocking

### `0x0480` (=1152) in the channel record tail
The 9-byte tail `00 00 00 00 04 80 FA 00 50` is byte-identical on every
channel of every file, across geometries from 343 to 2907 pixels and 4 to 24
channels. So it is global config, not geometry. 1152 is plausibly a
max-pixels-per-port hardware limit; `0xFA`=250 and `0x50`=80 unexplained.
Copy verbatim.

### `0x16 = 01`
Constant on all five files. Version or flags. Unknown what other values do.

### Non-identity LUT
The 512-byte table is a straight 0..255 identity ramp in every file. Writing
a curve there is a plausible global gamma/dimming hook — untested.

### `WriteToSDList` schema
`Count="0"` in all three sample `.xml` projects, so the element's children
are unknown. This is where FastLED records SD export assignments. Worth
capturing from a project that has actually been exported — it may document
the filename convention the controllers expect.

### `controlType` in `.moc`
Was `4` on a 4-port rig, alongside a separate `portCount: 4`. Cannot tell
whether it duplicates port count or identifies a controller model. An 8-port
`.moc` would distinguish them.

### Filename convention on the cards
Observed: `Sc-01-01.rgb`, `Sc-02-01.rgb`. The units very likely index fixed
names, so custom files should overwrite existing ones. The meaning of the
two number groups (scene? program? slot?) is unconfirmed.

### Practical file size ceiling
No size limit was found — apparent truncation turned out to be a bug in an
early generator writing a wrong frame count. The real limit is that the
frame count field at `0x0E` is a **uint16: 65,535 frames**, about 18 minutes
at 60 fps. A 6.3 MB file has played start to finish; the factory file is
10.5 MB.

## Settled — do not re-litigate

These were expensive to establish. All verified.

| Question | Answer | How it was verified |
|---|---|---|
| `0x10` meaning | Frame size in **bytes**, not pixels | Exact integer frame division on 5 files; the pixel reading gives 42.67 and 88.67 on two of them |
| Channel record counts | **Bytes**; ÷3 = pixels | All divide by 3 on every file; discontinuities land on the resulting pixel boundaries |
| `0x0E` | Frame count (uint16 BE) | Matches computed count on all 5 files |
| `0x0C` | Header size − 1 | 586/587, 638/639, 846/847 across 4-, 8-, 24-channel files |
| Byte order in frames | Interleaved RGB, as stored | Hardware test; planar reading gives spatial roughness 54.7 vs 1.60 |
| Brightness range | Full 0–255 works | Hardware A/B of 127 vs 255 white |
| 32-pixel channels | Unassigned port stub | `LightCount="0"` positions in `es.xml` match the `.rgb` 32-px channel indices exactly |
| Checksum | None anywhere | CRC32/Adler-32/byte-sum over every region fail to match any header field |
| `dots[i]` ordering | Pixel *i* in wire order | Uniform consecutive distances, zero large jumps |
| **Frame rate** | **60 fps** | `FpsTest.rgb`: 1800 frames in 30.0 s = 60.0; 24-blink cross-check gave 1.00 blink/s. Hand timing is ±1.7% on a 30 s interval, so 60 ± 1, and 60 is a menu option |
| Coordinate scale | 20 units per inch | `lampRad: 5` = half-inch bulb; makes props 3–4 ft and every pitch a clean value |

---

# Capturing the DMX / expansion port

Practical notes for the highest-value remaining target. Nothing here is
verified against your hardware yet — identify the port before spending money.

## It is probably not Ethernet

"DMX out" on an RJ45 almost always means **DMX512 over RS-485** — differential
serial on a cat5 cable, borrowing the connector only. A network card cannot
decode it and Wireshark will show nothing.

**Do not plug the controller's DMX out into a computer's Ethernet port.**
RS-485 idle levels and fault conditions are outside what an Ethernet PHY
expects.

Three things it could be:

| Possibility | Tell | How to capture |
|---|---|---|
| DMX512 / RS-485 | an RS-485 transceiver near the jack: MAX485, SP485, ADM485, SN75176 | logic analyser + transceiver, or a DMX interface |
| Real Ethernet (Art-Net / sACN) | magnetics block + a PHY chip, link LEDs that behave like a network port | switch with port mirroring + Wireshark |
| Proprietary pixel bus for daisy-chaining | often also RS-485, sometimes plain TTL or LVDS; no DMX branding on the PCB | logic analyser, decode by hand |

Given the 24-channel file spanning six chained 4-port units, a proprietary
pixel bus is a strong candidate — the "DMX out" may simply be carrying frame
data to the next unit.

**Identify it first:** open the case and read the chip markings by the jack,
and check with a multimeter whether any pins are transformer-coupled. That
one look decides everything downstream.

## Capture options, cheapest first

1. **USB logic analyser (~$10–15) + RS-485 breakout (~$3).** The right tool.
   Convert differential to single-ended, sample at ≥2 MHz, decode in
   PulseView — sigrok has a DMX512 decoder, and failing that decode as UART
   250 kbaud 8N2 and look for the break.
2. **Oscilloscope**, if you have one, purely to characterise first: voltage
   levels, differential or not, bit rate. Answers "what is this" faster than
   anything else.
3. **USB-RS485 dongle (~$10).** Fine for sending, fiddly for receiving —
   DMX's break condition confuses ordinary UARTs.
4. **Enttec DMX USB Pro (~$150).** Reliable receive with good software.
   Overkill unless you end up doing a lot of DMX work.

Pinout is not safe to assume. The ESTA convention for DMX over RJ45 is
pin 1 Data+, pin 2 Data−, pins 7/8 common, but Chinese controllers frequently
use their own. Probe rather than trust.

## Anchoring the capture: `tools/bus_probe.py`

A wall of bits is hard to interpret. `BusProbe.rgb` makes the controller
send bytes that cannot be mistaken for anything else:

| Phase | Pattern | What it gives you |
|---|---|---|
| 1–2 | all `0x00`, then all `0xFF` | value range; anything non-zero in phase 1 is framing |
| 3 | `0xAA`/`0x55` by pixel | visible on a scope before you decode anything; shows bit order |
| 4 | **counting ramp**, byte k = k & 0xFF | **the anchor** — search the capture for `00 01 02 03 04` |
| 5 | channel k = `0xC0 + k` | which channels appear on the wire, in what order |
| 6 | one `0xFF` pixel stepping | a single moving byte, easy to track |

Each phase holds ~6 s so any capture window lands inside one. The tool prints
the exact byte offsets to expect per channel.

## What each outcome would mean

- **Pixel data for every channel, including the master's own** → the master
  streams whole frames downstream and chained units are slaves. Sync within
  a chain becomes automatic and only one card per chain matters. This would
  dissolve most of the drift problem and is the best case.
- **Only the downstream units' channels** → each unit eats its slice and
  forwards the rest. Chain position is the address, and cable order becomes
  show-critical.
- **No pixel data, just short bursts** → it is control/sync, and the start
  command is in there.

Capture at the moment you press play, not just during steady playback — a
start or sync command would appear at the transition and nowhere else.
