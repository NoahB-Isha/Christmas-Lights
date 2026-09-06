# Open questions

Live document. Anything asserted elsewhere as fact has been verified against
real files or real hardware; anything here has not.

**Frame rate is now measured: 60 fps.** It remains a *device setting* that
is not recorded in the file, so every controller must be left on 60 — a unit
switched to 25 will play the same file 2.4x slow with no error shown. Worth
adding to the pre-flight checklist.

## Blocking

### Multi-controller drift — STILL OPEN on the GC-6004
`Sync master` / `Sync slave` are **GC-6612Pro** features. The GC-6004's
published feature list does not include them, so do not count on hardware
sync until the unit's own menu is checked.

What the 6004 does give us: one DMX scene-select command reaches every unit
simultaneously, which synchronises **starts**. Whether the units stay aligned
across a 3-minute song is unmeasured, and that is the part that matters for a
music show.

**How to close:** check the 6004's LCD menu for a mode setting. If sync modes
exist, wire master/slave. If not, measure drift directly — identical long
file on two cards, start both via DMX, check alignment several minutes in.

### Start trigger over DMX in — PROTOCOL DOCUMENTED, UNTESTED ON GC-6004
**Solved on paper.** The vendor's own GC-6612Pro datasheet gives the complete
13-channel DMX512 trigger map, including scene selection on `Add+6` at four
DMX values per scene, up to 64 scenes. The GC-102C audio box that was wired
to the DMX in port is simply a scene selector driven by drum-beat detection.

Full details in `08-CONTROL-PROTOCOL.md`. Tooling: `tools/dmx_scene.py`.

Remaining work is confirmation, not discovery: the map is documented for the
**GC-6612Pro** and our units are **GC-6004**. Same vendor, same `.rgb`
format, same "GC series" language, so it is very likely shared — but test
before relying on it.

**Open sub-question: is DMX out a passthrough of DMX in, or regenerated /
modified by the unit?** This matters because it decides whether one signal
source can drive a whole chain.

Three ways to find out, cheapest first:

1. **Free, no equipment.** If the audio box still exists: box → unit A DMX in,
   unit A DMX out → unit B DMX in. Change scenes. If B follows A, the control
   information survives the hop (whether passed through or regenerated) and a
   single source can drive a chain. If B ignores it, DMX out is carrying
   something else.
2. **Capture DMX in.** What the audio box sends is the command format itself,
   and it can be correlated against scene changes you can see. This is the
   single most valuable capture. Feed it to `tools/dmx_diff.py`.
3. **Capture in and out simultaneously** (two channels on the logic
   analyser). Identical bytes with a small delay means a buffered repeater;
   anything else means the unit regenerates.

**Brute-force mapping** also works and needs no capture at all: with a DMX
sender, hold all channels at 0, sweep channel 1 through 0–255 watching for a
response, then channel 2, and so on. Undocumented fixtures are mapped this
way routinely. A scene selector is usually a stepped channel with a handful
of discrete values.

### Does the DMX chain carry control or pixel data? — UNKNOWN
The audio-box detail raises a possibility worth taking seriously: the daisy
chain may be a **control** bus (scene select, sync) rather than a pixel-data
bus, with **every unit playing its own card**. In that model the 24-channel
`.rgb` is a project-level artefact and the vendor software splits it into
per-unit files on export — which is exactly what the empty `WriteToSDList`
element in the `.xml` projects would record.

The alternative remains that one master streams frames downstream to slaves.

`tools/bus_probe.py` distinguishes them: if the counting-ramp phase appears
on the wire, it is pixel data; if the wire only ever carries short bursts, it
is control. This is worth settling before the deployment layer is designed,
because the two models need different manifests.

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

## First: identify the dongle you already have

A USB-C dongle with an RJ45 jack is almost always a **USB-to-Ethernet
adapter**, which cannot read DMX no matter what software you run — it is a
network card, and DMX is not network traffic. But a minority of RJ45 dongles
are USB-to-serial (RS-485), and those *can*. One check settles it:

```bash
ls /dev/tty.*                              # before plugging in
# plug it in, then again:
ls /dev/tty.*
networksetup -listallhardwareports         # macOS
```

| What appears | What it is | Can it read DMX |
|---|---|---|
| new `/dev/tty.usbserial*` or `/dev/ttyUSB*` | USB-to-serial | yes, if it is RS-485 — use `tools/dmx_listen.py` |
| new network interface (`en5`, `eth1`) | USB-to-Ethernet | no |
| nothing at all | unpowered or dead | no |

`python tools/dmx_listen.py --list` prints serial adapters with their
vid:pid. FTDI / CH340 / CP210x / PL2303 in the description means serial.

**An Ethernet adapter is still useful for one test.** Plug it into the
controller's port and see whether a link comes up. A link light plus a
network interface that reports connected means the port really is Ethernet
(and Art-Net or sACN is likely, so Wireshark works). No link means it is
RS-485 and you need a serial path. That is a decisive, free identification
test — just do not expect to capture anything with it.

Plugging RS-485 into an Ethernet adapter is very unlikely to damage
anything, since Ethernet inputs are transformer-coupled, but it will not
work.

## Capture options, cheapest first

0. **A USB-to-RS485 adapter you may already own (~$10 if not).** If the
   dongle turns out to be serial, `tools/dmx_listen.py` receives DMX at
   250000 8N2, frames packets on the idle gap between them, and writes CSV
   straight into `tools/dmx_diff.py`. Caveat: a generic UART cannot see the
   DMX break directly, so framing relies on the inter-packet gap. Reliable
   in practice, not bulletproof.
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
