#!/usr/bin/env python3
"""
make_chainmap.py -- find out which physical controller is which in a chain.

WHY THIS EXISTS

The .rgb file contains NO unit id, no chain position, no grouping. Verified
on the 24-channel file: channel ids are a flat sequential 0..23, the 9-byte
record tail is byte-identical on all 24, and there is no per-unit block. So
whatever tells a controller "you are unit 3, take channels 8-11" comes from
outside the file -- either its physical position in the chain, or a
switch/jumper on the unit.

This file determines it empirically.

HOW IT WORKS

Channels are walked one at a time, in index order, grouped by ports-per-unit.
Before each group, EVERY channel flashes together as a "new unit" marker.
Then the group's channels light one by one.

So you see, on the props:

    [all flash 2x]  -> unit 1 starting
    prop A on       -> unit 1, port 1  (channel 0)
    prop B on       -> unit 1, port 2  (channel 1)
    ...
    [all flash 2x]  -> unit 2 starting
    ...

Write down what lights in what order and you have the complete channel ->
physical prop map, which is exactly what the deployment manifest needs.

THE ACTUAL EXPERIMENT

Run it once and record the map. Then physically swap two units in the chain
and run it again:

  * map follows the POSITION  -> addressing is positional. The chain order
    IS the address, nothing is configured on the unit, and re-cabling
    silently remaps every prop. Cable order becomes show-critical.
  * map follows the UNIT      -> addressing is set on the hardware (DIP
    switch, rotary, jumper, or a stored config). Units can be re-cabled
    freely but must be labelled.

Also worth testing: pull the SD card from a downstream unit and re-run. If
it still lights, only the master card matters and data passes down the
chain. If it goes dark, every unit needs its own copy.

NOTE: frame rate is measured at 60 fps, so the timings below are real
seconds. It is a device setting -- if the unit is switched to 25 or 45 the
whole file simply runs slower.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from lightshow.formats.rgbfile import Show, FrameBuf

FPS = 60                     # MEASURED 2026-09: 1800 frames in 30.0 s
PORTS_PER_UNIT = 4           # 4-port units daisy-chained; use 8 for 8-port

# real 24-channel geometry, from es.xml (empty ports already 32 px stubs)
CH = [176, 193, 176, 179, 179, 32, 193, 187, 32, 32, 179, 32,
      32, 32, 176, 32, 32, 98, 325, 32, 247, 32, 247, 32]

C = 255
WHITE = (C, C, C)
CYAN = (0, C, C)
RED = (C, 0, 0)
# a distinct colour per port slot within a unit, so port order is readable
# even if two props are hard to tell apart
SLOT = [(C, 0, 0), (0, C, 0), (0, 0, C), (C, C, 0),
        (C, 0, C), (0, C, C), (C, 128, 0), (128, 0, C)]


def fr(sec):
    return max(1, int(round(sec * FPS)))


def build():
    s = Show(CH)
    log = []

    def mark(n, txt):
        log.append((len(s.frames), n, txt))

    def hold(fb, n):
        b = fb.bytes()
        for _ in range(n):
            s.frames.append(b)

    def dark(sec):
        hold(FrameBuf(s, C), fr(sec))

    def all_flash(times, col, on=0.13, off=0.13):
        for _ in range(times):
            fb = FrameBuf(s, C); fb.fill_all(*col); hold(fb, fr(on))
            dark(off)

    # opening: unmistakable start
    mark(fr(1.0), "dark"); dark(1.0)
    mark(fr(1.2), "START: all channels white"); 
    fb = FrameBuf(s, C); fb.fill_all(*WHITE); hold(fb, fr(1.2))
    dark(1.0)

    nunits = (len(CH) + PORTS_PER_UNIT - 1) // PORTS_PER_UNIT
    for u in range(nunits):
        mark(fr(0.8), f"--- UNIT {u+1} marker: all flash 2x cyan ---")
        all_flash(2, CYAN)
        dark(0.5)
        for slot in range(PORTS_PER_UNIT):
            ch = u * PORTS_PER_UNIT + slot
            if ch >= len(CH):
                break
            stub = " (empty/stub)" if CH[ch] == 32 else ""
            mark(fr(1.6), f"unit {u+1} port {slot+1} = channel {ch} "
                          f"[{CH[ch]} px]{stub}")
            fb = FrameBuf(s, C)
            fb.fill(ch, *SLOT[slot % len(SLOT)])
            hold(fb, fr(1.6))
            dark(0.55)
        dark(0.6)

    mark(fr(1.5), "END: all red"); 
    fb = FrameBuf(s, C); fb.fill_all(*RED); hold(fb, fr(1.5))
    dark(1.0)
    return s, log


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    s, log = build()
    s.save(f"{out}/ChainMap.rgb")
    n = len(s.frames)
    print(s.info())
    print(f"\nChainMap.rgb  {n} frames = {n/FPS:.0f} s at {FPS} fps  "
          f"{(s.header_size + n*s.frame_size)/1e6:.2f} MB")
    print(f"\n{len(CH)} channels, {PORTS_PER_UNIT} ports/unit -> "
          f"{(len(CH)+PORTS_PER_UNIT-1)//PORTS_PER_UNIT} units\n")
    print("--- what to write down ---")
    for st, cnt, txt in log:
        if txt.startswith("unit") or txt.startswith("---"):
            print(f"  t={st/FPS:6.1f}s  {txt}")
    print("\nSlot colours: port1=red port2=green port3=blue port4=yellow")
