#!/usr/bin/env python3
"""
bus_probe.py -- build an .rgb whose BYTES are unmistakable in a bus capture.

    python tools/bus_probe.py out [CHANNELS...]

WHY

When you put a logic analyser on the controller's DMX/expansion port you get
a wall of bits. The hard part is not capturing it, it is knowing which bytes
are pixel data, where a frame starts, and what order channels appear in.

The fix is to make the controller send data you cannot mistake for anything
else. Each phase below writes a byte pattern that is trivially findable in a
capture, and holds it long enough (default 6 s) that any capture window
lands inside one.

PHASES

  1  all 0x00            floor. Anything non-zero is framing or overhead.
  2  all 0xFF            ceiling. Bracket the value range.
  3  0xAA / 0x55 alternating by pixel
                         10101010 / 01010101 -- obvious on a scope even
                         before you decode anything, and it makes bit order
                         (MSB/LSB first) visible by eye.
  4  counting ramp       pixel k gets byte value k & 0xFF, so the stream
                         reads 00 01 02 03 ... This is the one that matters:
                         it reveals frame start, byte order, and whether the
                         controller passes values through untouched.
  5  channel signature   channel k filled with byte 0xC0 + k. Tells you the
                         order channels appear in on the wire and whether
                         downstream units get only their own slice or the
                         whole frame.
  6  single hot pixel    one pixel 0xFF, everything else 0x00, stepping
                         slowly. A moving single byte is easy to track.

HOW TO USE IT

  1. Play this file on the controller.
  2. Capture the port with a logic analyser (see docs/06-OPEN-QUESTIONS.md).
  3. Search the capture for `00 01 02 03 04` -- phase 4. That anchors
     everything: you now know where a frame begins and how wide it is.
  4. Compare phase 5 against the channel list printed below.

WHAT THE ANSWER MEANS

  * You find pixel data for ALL channels -> the master streams the whole
    frame downstream and the daisy-chained units are slaves. Sync within a
    chain is then automatic and only ONE card matters per chain -- which
    would dissolve most of the drift problem.
  * You find only the DOWNSTREAM units' channels -> each unit consumes its
    own slice and forwards the rest. Position in the chain is the address.
  * You find no pixel data at all, only short bursts -> it is control or
    sync, and the start command is in there.

NOTE ON VALUES: these bytes are written raw, with no gamma applied, because
here the byte value IS the signal. If what you capture does not match what
was written, the controller is scaling or reordering, which is itself worth
knowing.
"""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from lightshow.formats.rgbfile import Show, FrameBuf

FPS = 60
HOLD = 6.0            # seconds per phase -- long enough to catch in a capture


def fr(sec):
    return max(1, int(round(sec * FPS)))


def build(channels):
    s = Show(channels)
    total_px = sum(channels)
    log = []

    def mark(name):
        log.append((len(s.frames), name))

    def raw_frame(values):
        """values: bytes-like of length frame_size, written verbatim"""
        assert len(values) == s.frame_size
        return bytes(values)

    def hold(frame, sec=HOLD):
        for _ in range(fr(sec)):
            s.frames.append(frame)

    def flat(byte):
        return raw_frame(bytes([byte]) * s.frame_size)

    # 1 / 2  floor and ceiling
    mark("phase 1: all 0x00")
    hold(flat(0x00), 3.0)
    mark("phase 2: all 0xFF")
    hold(flat(0xFF))
    mark("gap")
    hold(flat(0x00), 1.5)

    # 3  alternating bit patterns, per pixel
    mark("phase 3: 0xAA / 0x55 alternating by pixel")
    buf = bytearray()
    for i in range(total_px):
        buf += bytes([0xAA if i % 2 == 0 else 0x55] * 3)
    hold(raw_frame(buf))
    mark("gap")
    hold(flat(0x00), 1.5)

    # 4  counting ramp -- the anchor
    mark("phase 4: counting ramp, byte k = k & 0xFF  <== SEARCH FOR THIS")
    hold(raw_frame(bytes([k & 0xFF for k in range(s.frame_size)])))
    mark("gap")
    hold(flat(0x00), 1.5)

    # 5  per-channel signature
    mark("phase 5: channel k = byte 0xC0 + k")
    buf = bytearray()
    for k, n in enumerate(channels):
        buf += bytes([(0xC0 + k) & 0xFF] * (n * 3))
    hold(raw_frame(buf))
    mark("gap")
    hold(flat(0x00), 1.5)

    # 6  one hot pixel, stepping
    mark("phase 6: single 0xFF pixel stepping through every channel")
    step = max(1, total_px // 48)
    for p in range(0, total_px, step):
        fb = FrameBuf(s, 255)
        o = p * 3
        fb.buf[o] = fb.buf[o + 1] = fb.buf[o + 2] = 0xFF
        blk = fb.bytes()
        for _ in range(fr(0.5)):
            s.frames.append(blk)

    mark("end")
    hold(flat(0x00), 2.0)
    return s, log


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "out"
    os.makedirs(out, exist_ok=True)
    chans = [int(a) for a in sys.argv[2:]] or [32, 32, 32, 72]
    s, log = build(chans)
    s.save(os.path.join(out, "BusProbe.rgb"))
    n = len(s.frames)
    print(s.info())
    print(f"\nBusProbe.rgb  {n} frames = {n/FPS:.0f} s  "
          f"{(s.header_size + n*s.frame_size)/1e6:.2f} MB")
    print("\n--- byte offsets to expect in ONE frame ---")
    off = 0
    for k, px in enumerate(chans):
        print(f"   ch{k}: bytes[{off}:{off+px*3}]  ({px} px)  "
              f"phase-5 signature 0x{(0xC0+k)&0xFF:02X}")
        off += px * 3
    print(f"   frame total {s.frame_size} bytes")
    print("\n--- timing map ---")
    for st, name in log:
        if name != "gap":
            print(f"   t={st/FPS:6.1f}s  {name}")
