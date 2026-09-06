#!/usr/bin/env python3
"""
drift_test.py -- measure whether two controllers stay in sync over a show.

    python tools/drift_test.py out [minutes]

WHY THIS EXISTS

The GC-6004 has no Sync master / Sync slave mode (confirmed on the unit's
own panel -- those are GC-6612Pro features). So synchronisation comes only
from every controller receiving the same DMX scene-select at the same
instant. That aligns STARTS. Whether they stay aligned across a 3-minute
song is the open question, and it is the one that decides whether a
music-synced show is viable at all.

HOW IT READS

The prop becomes a clock face. One bright pixel steps forward exactly once
per second along the chain, so **pixel position IS elapsed time**. Put this
file on two cards, start both, and stand back:

    dots on the same pixel      -> in sync to better than 1 second
    dots N pixels apart         -> N seconds of drift

No stopwatch, no instruments, no filming required for a coarse read. For a
fine read, film both props in one frame and step through the video.

Two extra channels of information:

  * every 30 s the whole prop flashes white for 0.25 s. Two units flashing
    together is an instant visual check; a camera catches sub-frame offsets.
  * a dim "minute marker" pixel steps once per minute, so you can tell
    revolutions apart on a long run.

WHAT TO CONCLUDE

Expected magnitudes, from component physics rather than measurement:

    clock drift   accumulates.  +/-50 ppm crystal = ~9 ms over 3 minutes
    start jitter  bounded.      one frame (16.7 ms) + DMX packet (22.7 ms)

Perceptual tolerance for light against sound is roughly 50-80 ms. So if
these units use ordinary crystals, drift should be invisible and a fixed
small offset should dominate. If instead you see the dots separate by whole
pixels over a few minutes, the clocks are far worse than expected and the
show has to be built as a CUE LIST -- many short scenes re-triggered over
DMX -- so error cannot accumulate past one scene.

The file is prop-agnostic: it lights by index within every channel, so it
works on any pair of controllers regardless of what is plugged in.
"""

import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from lightshow.formats.rgbfile import Show, FrameBuf

FPS = 60
STUB = 32
# generous default so the file is usable on any port; trim if you like
CHANNELS = [STUB, STUB, 157, 325]

FLASH_EVERY = 30.0        # seconds
FLASH_LEN = 0.25


def build(minutes=5.0, channels=CHANNELS):
    s = Show(channels)
    total = int(minutes * 60 * FPS)
    n_max = max(channels)

    for f in range(total):
        t = f / FPS
        fb = FrameBuf(s, 255)

        flashing = (t % FLASH_EVERY) < FLASH_LEN
        if flashing:
            fb.fill_all(255, 255, 255)
        else:
            sec = int(t)                       # one step per second
            minute = int(t // 60)
            for ch, n in enumerate(channels):
                # second hand: white, unmistakable
                fb.set(ch, sec % n, 255, 255, 255)
                # minute marker: dim amber, lets you tell revolutions apart
                fb.set(ch, (minute * 7) % n, 60, 24, 0)
        s.frames.append(fb.bytes())
    return s


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "out"
    minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    os.makedirs(out, exist_ok=True)
    s = build(minutes)
    n = len(s.frames)
    s.save(os.path.join(out, "DriftTest.rgb"))
    print(f"DriftTest.rgb  {n} frames = {n/FPS/60:.1f} min  "
          f"{(s.header_size + n*s.frame_size)/1e6:.2f} MB")
    print(f"channels {s.channels}")
    print(f"\n  second hand steps 1 pixel per second")
    print(f"  full-prop flash every {FLASH_EVERY:.0f} s for {FLASH_LEN} s")
    print(f"  dim minute marker steps every 60 s")
    print("\nprocedure:")
    print("  1. copy to two cards, both as the SAME scene number")
    print("  2. start both together (DMX scene-select, or power-on in auto)")
    print("  3. let it run the full length, then compare dot positions")
    print("     same pixel      = better than 1 s of drift")
    print("     N pixels apart  = N seconds of drift")
    print("  4. for a fine read, film both props in one shot and step frames")
