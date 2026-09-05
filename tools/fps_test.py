#!/usr/bin/env python3
"""
make_fpstest.py -- measure the real playback frame rate with a stopwatch.

DESIGN NOTES

1. Every frame is SPATIALLY UNIFORM (one colour across all pixels). We
   know from hardware testing that uniform frames render correctly under
   any byte layout, so this test does not depend on the geometry model,
   the port mapping, or the prop's real length. It measures rate only.

2. Two independent measurements:
     TEST 1  one long 1800-frame interval  -> fps = 1800 / seconds
     TEST 2  24 blinks over 1440 frames    -> fps = 1440 / seconds
   Test 2 also reveals dropped frames: the blinks are evenly spaced, so
   uneven blinking means the device is not keeping a constant rate.

3. Sustained segments run at ~40% brightness, not full white. 325 LEDs at
   255,255,255 can pull ~19 A; a sag would corrupt the very timing we are
   trying to measure. Short cue flashes use full brightness. The factory
   files also cap near 127, which is probably the same reasoning.

4. Long intervals so human reaction time (~0.2 s) is negligible: worst
   case 1800 frames at 60 fps = 30 s, giving well under 1% error.

EXPECTED DURATIONS

  TEST 1 (1800 frames)        TEST 2 (1440 frames, 24 blinks)
    25 fps -> 72.0 s            25 fps -> 57.6 s  (0.42 blinks/s)
    30 fps -> 60.0 s            30 fps -> 48.0 s  (0.50 blinks/s)
    45 fps -> 40.0 s            45 fps -> 32.0 s  (0.75 blinks/s)
    50 fps -> 36.0 s            50 fps -> 28.8 s  (0.83 blinks/s)
    60 fps -> 30.0 s            60 fps -> 24.0 s  (1.00 blink/s)
   100 fps -> 18.0 s           100 fps -> 14.4 s  (1.67 blinks/s)

  At 60 fps the blinks land at exactly one per second, which is the
  easiest possible thing to confirm against a phone clock.
"""

import sys, os, os
from rgbfile import Show, FrameBuf

CH = [32, 32, 32, 325]        # stub/stub/stub/prop -- irrelevant here, all fills
DIM = 100                     # sustained brightness (~40%)
FULL = 255                    # brief cues only

T1_FRAMES = 1800
T2_BLINKS = 24
T2_HALF = 30                  # 30 on + 30 off = 60-frame period
T2_FRAMES = T2_BLINKS * T2_HALF * 2


def build():
    s = Show(CH)
    log = []

    def mark(n, name):
        log.append((len(s.frames), n, name))

    def fill(col, n):
        fb = FrameBuf(s, 255)
        fb.fill_all(*col)
        f = fb.bytes()
        for _ in range(n):
            s.frames.append(f)

    D = (0, 0, 0)
    WHITE = (DIM, DIM, DIM)
    GREEN = (0, FULL, 0)
    BLUE = (0, 0, FULL)
    RED = (FULL, 0, 0)

    # lead-in so you can get the stopwatch ready
    mark(180, "dark lead-in"); fill(D, 180)

    # ---- TEST 1: one long interval ----
    mark(180, "CUE: 3 green flashes = test 1 about to start")
    for _ in range(3):
        fill(GREEN, 30); fill(D, 30)
    mark(60, "dark, hold"); fill(D, 60)

    mark(T1_FRAMES, f"TEST 1: white ON for {T1_FRAMES} frames "
                    f"<== START timer on white, STOP when it ends")
    fill(WHITE, T1_FRAMES)

    mark(120, "RED = test 1 over"); fill(RED, 120)
    mark(120, "dark"); fill(D, 120)

    # ---- TEST 2: blink counter ----
    mark(180, "CUE: 3 blue flashes = test 2 about to start")
    for _ in range(3):
        fill(BLUE, 30); fill(D, 30)
    mark(60, "dark, hold"); fill(D, 60)

    mark(T2_FRAMES, f"TEST 2: {T2_BLINKS} blinks over {T2_FRAMES} frames "
                    f"<== time all {T2_BLINKS}, and count blinks per second")
    for _ in range(T2_BLINKS):
        fill(WHITE, T2_HALF)
        fill(D, T2_HALF)

    mark(120, "RED = test 2 over"); fill(RED, 120)
    mark(180, "dark tail"); fill(D, 180)
    return s, log


if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "out"), exist_ok=True)
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    s, log = build()
    s.save(f"{out}/FpsTest.rgb")
    n = len(s.frames)
    print(s.info())
    print(f"\nFpsTest.rgb {n} frames  "
          f"{(s.header_size + n * s.frame_size)/1e6:.2f} MB")
    print("\n--- sequence ---")
    for st, cnt, name in log:
        print(f"  frame {st:5d} +{cnt:5d}  {name}")
    print("\n--- total file duration at each candidate rate ---")
    for f in (25, 30, 45, 50, 60, 100):
        print(f"   {f:3d} fps -> {n/f:6.1f} s total")
    print("\n--- solve for fps from your measurements ---")
    print(f"   fps = {T1_FRAMES} / (test 1 seconds)")
    print(f"   fps = {T2_FRAMES} / (test 2 seconds)")
    print(f"   fps = 60 x (blinks per second)")
