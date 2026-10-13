# Updates from the hardware team

**Revision 2 — 2026-10-07.** The ENTTEC link is working end to end on the bench.
Several things in revision 1 were **wrong** and are corrected below. Read the
"CORRECTIONS" block first — if you built anything against revision 1, it needs changing.

---

## CORRECTIONS to revision 1 (read this first)

### 1. Frame rate is 30.30 fps, fixed. It is NOT 60.

Revision 1 said: *"The 30.30 fps figure was an artefact of the audio box pinning the
controller's speed channel low… Do not hard-code 30.3. Keep `--fps` as a parameter,
default 60."*

**That was wrong.** The audio box had nothing to do with it. 30.30 fps is the GC-6004's
native frame rate and the speed channel at 255 is already flat out. (Owner's note 2026-10-08:
30.3 is the maximum whenever a DMX scene-select signal is going into the box — so no need
for 60 fps rendering at all.)

Measured on the bench 2026-10-07, speed channel = 255, with a card rendered at 60 fps:

- 190 s of content (3:10) played in 377 s (6:17) — hand-timed
- ratio 1.984 ≈ **exactly 2×**
- 11,400 frames ÷ 377 s = **30.24 fps**
- predicted at 30.30 fps: 376.2 s = 6:16.2 — matches to within hand-timing error

Consequences:

- **Render at `--fps 30.3`.** `--fps 60` produces content that plays at half speed.
- **Speed channel = 255 is the ceiling**, not a tuning knob. Set it once and forget it.
- **Frame budget is fine again:** 14:42 at 30.3 fps = 26,724 frames against the 65,535
  uint16 cap. A single file can hold up to **36 minutes**.
- **Show file is ~52 MB**, not ~105 MB.
- The earlier "could the cap be DMX's 44 Hz refresh?" theory is also dead. It is simply
  the controller's fixed output rate.

### 2. The channel map is one lower than documented.

Revision 1 (and `docs/08-CONTROL-PROTOCOL.md` revision 1) used the datasheet's `Add+1` = brightness
wording. **The base address IS the brightness channel.** Confirmed by bisection on the
bench — `set 1=255` lights the props when `DMX Add` = 1.

Correct map, 13 channels from base address `Add`:

| offset | channel when Add=1 | function |
|---|---|---|
| `Add+0` | 1 | **brightness** |
| `Add+1` | 2 | red adjust |
| `Add+2` | 3 | green adjust |
| `Add+3` | 4 | blue adjust |
| `Add+4` | 5 | white adjust |
| `Add+5` | **6** | **SCENE** — value = `(n-1)*4 + 1` |
| `Add+6` | 7 | speed — 255 = native |
| `Add+7` | 8 | strobe — 0 = off |
| `Add+8..11` | 9–12 | mix |
| `Add+12` | 13 | grouping |

Still 13 channels per controller, so addressing is unchanged: 1, 14, 27, 40, …

**The R/G/B/W adjust channels are not optional.** At 0 they mute the output. The runner
must set them to 255 (or the desired trim) or nothing lights, regardless of brightness
and scene. This cost us an hour of "scene select is broken" debugging.

Working command, verified:

```
python3 dmxtool.py set 1=255 2=255 3=255 4=255 6=25 7=255
```

(scene 7, full brightness, all adjusts open, native speed)

### 3. SD cards must be FAT32. exFAT silently fails.

The controller reads **FAT32 only**. An exFAT card mounts fine on a Mac and the controller
either sees nothing or misreads the directory and plays garbage. This masqueraded as a
corrupt card.

Card prep procedure, all 48:

- **FAT32, MBR scheme, 32 KB allocation unit, full (not quick) format**
- Use the SD Association's SD Memory Card Formatter — it aligns to erase blocks;
  the macOS built-in formatter does not
- Write files **largest-first, in one pass**, onto a freshly formatted card
- **Never delete and rewrite in place** — reformat and reload. A fragmented card is what
  made controller B drift; a 52 MB file stalled where the 7 MB clock file never did
- Checksum every `.rgb` on the card against the source after copy
- Label each card with controller ID and content version

8 GB SDHC is the right size — bigger cards default to exFAT and macOS won't offer FAT32
above 32 GB. Capacity need is ~150 MB.

---

## RESOLVED: the controller holds its scene when DMX stops

Tested 2026-10-07 by pulling the adapter mid-show. **The controller keeps playing the
last-selected scene indefinitely.** It does not go dark and it does not reset.

This was the open question gating the field-distribution decision. It resolves in the
cheap direction:

- **Wireless DMX is viable.** Config E goes from reckless to legitimate.
- **Art-Net / UDP is fine.** Packet loss is a non-event.
- **A cable fault mid-show does not kill the show.** Props keep running; you lose the
  ability to *change* scene until the link returns.
- **Config B's main argument weakens.** Isolation is still worth having for ground-
  potential reasons across 300 ft, but "halves the blast radius" mattered more when a
  fault meant darkness.

Three consequences that need designing for:

1. **No re-sync while DMX is down.** Controllers free-run and drift apart until the link
   returns. Per-song scene changes are now doing double duty as drift correction — if
   DMX drops during a song, that song's props slide and stay slid until the next cue.
   Another reason to split the medley into per-song scenes.
2. **You cannot turn the lights off by unplugging.** Curfew blackout requires a live link
   and a running runner. If the laptop dies at 21:00 the field runs the last scene until
   someone pulls mains power. **The runner needs a watchdog**, and the monitored thing is
   the runner, not the cable.
3. **Failure mode is "stuck", not "dark".** A hung runner looks like a working show that
   never changes. Worth an explicit heartbeat so an operator can tell the difference.

**Still untested, and the complement of this:** what does the controller do when
**power-cycled with no DMX present**? Boot into scene 1 and play, or sit dark waiting for
a command? That determines the outcome of a power blip in the field at 20:00 with nobody
watching. If it boots into a scene, make that scene the ambient idle so a blip degrades
gracefully instead of leaving a dark hole in the middle of the course.

---

## Status: the link works

Confirmed working end to end on the bench, one controller:

- ENTTEC **DMX USB Pro**, firmware 1.44, `/dev/cu.usbserial-EN537929`
- break 181 µs, MaB 43 µs, 40 pkt/s — both comfortably in spec (minimums 92 µs / 12 µs).
  An earlier reading of MaB 11 µs was out of spec; ENTTEC's own software appears to have
  rewritten the params. Not a factor now.
- Brightness, R/G/B adjust, scene select and speed all respond correctly

### The adapter was the whole problem

The generic XLR5→RJ45 adapter was wired to a non-standard pinout that put Data+ on RJ45
pins 4 and 6 — pins the controller leaves unconnected. **Every failed test before this
was explained by that**, including the channel scan that came up empty.

As shipped (T568B at the RJ45 end):

| XLR | wire | → RJ45 | should have been |
|---|---|---|---|
| 1 | orange | 2 | 7 |
| 2 | white/orange | 1 | 2 |
| 3 | blue + green | 4 + 6 | 1 |
| 4 | white/brown | 7 | — |
| 5 | brown | 8 | — |

Rewired to:

```
XLR 1 (GND)    ← white/brown  → RJ45 7
XLR 2 (Data −) ← orange       → RJ45 2
XLR 3 (Data +) ← white/orange → RJ45 1
XLR 4, 5         open
```

**Check every adapter with a multimeter before use.** Also verify XLR 2↔3 reads open —
a solder bridge or stray strand there is a dead bus and looks identical to a wiring fault.
If nothing responds, swap XLR 2 and 3 — non-destructive, and it covers the case where the
controller's silkscreen lies about D+/D−. Pin 7 for ground is the reliable part.

Note the ENTTEC Pro is **5-pin**; a 3-pin adapter needs a 5-pin-male → 3-pin-female
turnaround. Pins 4/5 are unused by DMX. OUT is female, IN is male. Plug into the
controller's DMX **IN** jack — IN and OUT have identical pinouts, so it is easy to get wrong.

Verification, with the shell closed:

| check | expect |
|---|---|
| XLR 1 → RJ45 7 | continuity |
| XLR 2 → RJ45 2 | continuity |
| XLR 3 → RJ45 1 | continuity |
| XLR 2 ↔ XLR 3 | open |
| XLR 2 or 3 → shell | open |

---

## The runner exists: `showrunner.py`

Delivered to `~/Downloads/mod files/LightMax/`. Single dependency, pyserial. Same Pro
protocol as `dmxtool.py`.

- Holds the universe on a **background thread at 40 Hz** that never stops. Foreground
  code just changes values. A USB hiccup logs a warning instead of killing the show.
- Fires the scene, then starts audio after **`--lead-ms`** — one calibrated number that
  replaces the old 560 ms box figure. `calibrate` subcommand runs a countdown so you can
  video it and measure the error.
- `--addr 1-40x13` addresses all 40 controllers.
- Subcommands: `play`, `cues` (timed scene changes from JSON), `idle`, `loop`
  (show every N minutes on the wall clock, idle between, curfew blackout), `blackout`,
  `calibrate`.

**Still to measure:** actual start latency. The 0.56 s figure was the audio box's beat
detection and is obsolete.

**Needs adding:** a watchdog / heartbeat, per the hold-on-signal-loss finding above.

---

## What still holds from revision 1

### No more click track

The cue-track machinery (`make_cue_track.py --train`, `--music-delay-ms`, the "box hears
drum hits" scheme) is retired. Audio is plain stereo music. Keep the code as a fallback;
do not build the new tool around it.

### Scene select is exact and arbitrary

Jump to any of the 62 scenes at any instant, on the beat, no beat detector in the loop.
Confirmed working.

### Per-controller / per-group addressing

13 channels × 40 controllers = 520 channels — **this now exceeds one 512-channel
universe.** Options:

- **Share addresses within a group** (6 clusters → 6 addresses → 78 channels). Simplest,
  and probably right: props in a cluster generally want the same scene anyway.
- Two universes, if per-controller independence turns out to matter.

Add a `dmx_address` field per controller in the layout JSON alongside `controller` / `port`,
with group-shared addressing as the default.

This does not change how content reaches the props: each controller plays its own SD
card, DMX only chooses *which file*. "Scene 7 on group A, scene 3 on group B" means each
card must carry that group's content in those slots.

### Re-sync is free

Every scene-select change restarts that file from frame 0. Splitting the show into
per-song scenes and re-selecting at each boundary zeroes inter-controller drift for
free. **Worth doing even if drift looks acceptable** — it's the cheapest insurance
available and costs one DMX value per song.

### DMX output behind a driver interface

Three backends: `enttec-usb`, `artnet`, `null/simulate`. Same 512-byte universe, same
40 Hz push — only the sink changes. The field transport may end up as Art-Net rather than
USB (see Field distribution). `showrunner.py`'s `DmxEngine` class is a working reference
for the `enttec-usb` backend.

---

## Field distribution

**Site:** ~300 ft, **6 clusters**, 40 GC-6004 units.

**The old system, for the record:** an FM transmitter broadcast the music; each prop
location had a cheap FM receiver feeding its own GC-102C over a red/black audio lead, and
the box did local beat detection. The *music* was the sync signal. The FM transmitter
stays if that is how cars hear the audio; the receivers at the props go idle. They cannot
be retrofitted to emit DMX — they output audio, and only the box turns audio into DMX.

**The reframe:** this is not a lighting-data problem. Each controller plays its own SD
card; DMX only carries "play scene N now" — a few bytes, a few times an hour, re-asserted
40×/s. Loss-tolerant, and now proven loss-*survivable*: the controllers hold their scene
if the link drops. 300 ft and 40 devices are inside DMX512 limits (~1000 ft, 32 unit
loads — 40 devices may need a splitter for unit-load reasons, which Config B provides
anyway).

Ballpark costs (US, Sep 2026; cable is cheap, weatherproofing and labour are the real cost):

| Config | What | Est. |
|---|---|---|
| A | Single daisy chain + one isolator at the head | ~$450 |
| B | 2 isolated branches from a central point | **~$510** |
| C | 6 isolated home runs | ~$745 |
| D | Same Cat5 run as **Ethernet** + Art-Net→DMX node per cluster | ~$960 commercial / ~$560 DIY |
| E | Wireless DMX, TX + 6 RX, no cable | ~$540 |

Line items: outdoor direct-burial solid-copper Cat5e 1000 ft $120–200 · RJ45 plugs $15–25 ·
weatherproofing (IP67 couplers or gland boxes) $120–300 · 120 Ω terminators DIY ~$2 ·
opto-isolated splitter $70–180 · XLR→RJ45 adapter per branch $15–20 · Art-Net node $70–150
commercial or ~$25–35 DIY (ESP32 + RS485) · PoE switch $80–150 if not on hand.

**Recommendation: still Config B for this season**, but the case is now about ground
isolation across 300 ft rather than fault blast radius. Pull **two** runs per cluster
while the trench is open; spare cable is far cheaper than spare labour.

**Config E (wireless) is now genuinely competitive** given the hold-on-loss behaviour —
same price as B, no trenching, and a dropout costs you a missed scene change rather than
a dark cluster. Worth pricing properly before committing to a trench.

**The cable choice is not locked in.** The same Cat5 can carry DMX now and Ethernet +
Art-Net later — only the boxes on the ends change. Config B now does not foreclose
Config D next season.

**Art-Net nodes (Config D), for the record:** a node takes network in and emits DMX out.
Commercial 1-universe units (Pknight, LTech, DMXking) $70–150, PoE variants available;
or DIY ESP32 + RS485 for ~$25–35. Advantages: star topology allowed (DMX forbids it), PoE
powers the node over the same cable, standard switches and VLANs, and every node is
pingable/monitorable. Cost is one more layer to fail and DIY build time. With 40 controllers
at 13 channels each, Art-Net also solves the 512-channel ceiling cleanly.

---

## Open questions, in priority order

1. **Power-cycle with no DMX present** — does the controller boot into a scene and play,
   or sit dark? Determines the outcome of a field power blip. See the RESOLVED section.
2. **Start latency** on direct DMX. Video the scene command vs first light.
3. **Two controllers on different addresses** → confirm independent scene control.
4. **Daisy chain two units** via DMX OUT → confirm pass-through; add the 120 Ω terminator.
5. **Scene channel range** — confirm `scene = value//4 + 1` holds across all 62 scenes,
   not just the low end.
6. Does the controller's LCD have a local speed setting that multiplies with the DMX
   channel? Not yet checked.

## Still to buy

48 × **8 GB industrial SDHC** (Kingston SDIT/8GB, pSLC, −40/85 °C, ~$23) — the shipped
4 GB cards skip files · opto-isolated DMX splitter · 120 Ω terminators ·
outdoor/direct-burial Cat5e (crimp T568B: pins 1+2 are the orange pair, so D+/D− ride one
twisted pair — do not split them) · one XLR→RJ45 adapter per branch, **each verified with
a multimeter** · possibly wireless DMX transmitter/receiver pairs.
