#!/usr/bin/env python3
"""
show47.py -- a music-driven show for prop 47 (72 px, reads as a SNOWFLAKE).

PALETTE: ice. The prop is a snowflake, so the look is frost, not Christmas
red/green/gold. Everything stays in a narrow cool band (hue 0.52-0.68, cyan
through blue to violet). The specific hue matters far less than the
BRIGHTNESS structure, which is what the shape reads on anyway.

Signature look: a sparkle whose CORE IS WHITE AND WHOSE FALLOFF IS BLUE.
Each grain is born desaturated (white hot) and gains saturation as it fades,
cooling into deep blue on the way out. That is one line --
    sat = (1 - v) * bias
-- and it is the difference between "white twinkle" and "frost".

    python show47.py OUTDIR [song.mp3]

With no song it uses a synthetic track so the pipeline can be exercised
end to end.

------------------------------------------------------------------------
DESIGN: what drives what
------------------------------------------------------------------------
The prop has four usable spatial channels and each suits a different
timescale of the music. Matching them up is the whole trick:

  RADIUS (centre -> arm tip, ~10 px deep)
      Bass. Low-frequency energy pushes a ring outward. Bass is slow and
      continuous, and radius is the axis with the most depth, so a bass
      swell reads as the prop physically inflating.

  ANGLE (4 discrete arms)
      Percussive hits. Four arms is a tiny amount of spatial resolution,
      so it should carry DISCRETE events, not continuous values. Each
      onset lights one arm and the choice advances on the beat, so drums
      appear to travel around the cross.

  WIRE ORDER (72-px loop around the outline)
      Melodic motion and section transitions. A chase along the wire
      traces the silhouette, which is the only way to make the shape
      itself legible.

  INDIVIDUAL BULBS (72 large half-inch bulbs)
      Hi-hats and cymbals. The bulbs are big and 2 in apart, so a single
      lit bulb is a distinct point of light. Sparse geometry is bad for
      gradients and excellent for sparkle.

  WHOLE PROP (all 72 at once)
      Harmony and loudness. Chroma sets the hue, RMS sets the level. This
      is the base layer that everything else sits on top of.

Deliberately NOT used: fine spatial gradients. Bulb pitch is 2 in and the
bulbs fill only a quarter of that gap, so anything smaller than ~4 in of
detail simply falls between the bulbs.

------------------------------------------------------------------------
LAYERS
------------------------------------------------------------------------
Six layers composite in order. Every layer is (name, blend, driver):

  0 wash        base     harmonic energy -> level, centroid -> cold hue
  1 bassring    lighten  low band -> radius of an expanding ring
  2 armhits     lighten  percussive onsets -> one arm flashes
  3 sparkle     lighten  high-band onsets -> white-core/blue-falloff grains
 3b shimmer     lighten  time only -> always-on idle glint, never fully dark
  4 melody      lighten  spectral centroid -> a glow travelling the wire
  5 transition  lighten  section boundaries -> a wipe across the prop

Accents composite by LIGHTEN (per-channel max), not by addition. Adding
five layers pushes every channel to 1.0 and the prop turns white, which
destroys the colour distinction that makes the layering readable at all.
Lighten preserves each layer's hue while the brightest still wins.

Layering is what separates this from "brightness follows the music".
Because harmonic and percussive content are separated first, a sustained
pad can hold a colour wash while drums punch through it, instead of both
being driven by one loudness envelope.

------------------------------------------------------------------------
SECTIONS
------------------------------------------------------------------------
Sections are ranked by energy (0 = quietest, 1 = loudest) and the rank
picks a mix. No song-form labels needed, so it works on any track:

  rank < 0.2   wash only, dim, cool                         (intro/outro)
  rank < 0.5   wash + bass ring, restrained                 (verse)
  rank < 0.8   wash + ring + arm hits + some sparkle        (build)
  rank >= 0.8  everything, saturated, arm rotation on downbeats (chorus)

------------------------------------------------------------------------
TWO THINGS THAT MATTER ON THIS HARDWARE
------------------------------------------------------------------------
GAMMA. The 512-byte LUT in the .rgb header is an identity ramp, so the
controller applies no gamma at all: byte value maps ~linearly to
luminance. Perceived brightness goes roughly as luminance^(1/2.2), so a
linear byte ramp looks top-heavy and fades die abruptly. Everything here
is authored in PERCEPTUAL 0..1 and converted with byte = 255 * v**2.2,
which is what makes the slow fades actually look slow.

POWER. 72 half-inch bulbs at full white is real current. Sustained full
white is capped, and the cap is per-frame across the whole prop.
"""

import sys, os, math, colorsys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lightshow.formats.rgbfile import Show, FrameBuf
from lightshow.formats.props import load_mod, UNITS_PER_INCH
from lightshow import music

FPS = 60
GAMMA = 2.2
POWER_CAP = 0.62          # max mean perceptual level per frame
STUB = 32
MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "props", "47号.mod")


# ------------------------------------------------------------------ geometry
prop = load_mod(MOD)
N = len(prop)
x0, y0, x1, y1 = prop.bounds
cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
XY_IN = np.array([[(x - cx) / UNITS_PER_INCH, (y - cy) / UNITS_PER_INCH]
                  for x, y in prop.xy])          # inches from centre
R_IN = np.hypot(XY_IN[:, 0], XY_IN[:, 1])
ANG = np.arctan2(XY_IN[:, 1], XY_IN[:, 0])
R_MAX = R_IN.max()
ARM = ((ANG + math.pi / 4) % (2 * math.pi) / (math.pi / 2)).astype(int) % 4
IDX = np.arange(N)

CH = [STUB, STUB, STUB, N]
PROP_CH = 3


def hsv_arr(h, s, v):
    """vectorised hsv -> rgb, arrays or scalars, all 0..1"""
    h = np.asarray(h, float) % 1.0
    s = np.clip(np.asarray(s, float), 0, 1)
    v = np.clip(np.asarray(v, float), 0, 1)
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    out = np.zeros(np.broadcast(h, s, v).shape + (3,))
    for k, (r, g, b) in enumerate([(v, t, p), (q, v, p), (p, v, t),
                                   (p, q, v), (t, p, v), (v, p, q)]):
        m = i == k
        out[m, 0] = np.broadcast_to(r, m.shape)[m]
        out[m, 1] = np.broadcast_to(g, m.shape)[m]
        out[m, 2] = np.broadcast_to(b, m.shape)[m]
    return out


# ---------------------------------------------------------------- palette
ICE_COOL = 0.52        # cyan
ICE_BASE = 0.60        # deep blue
ICE_WARM = 0.68        # violet -- the "warm" end of an all-cold palette


def frost(v, hue=0.585, bias=1.15, gain=0.95):
    """White core, blue falloff. Bright grains read near-white; as they decay
    they gain saturation and cool into blue."""
    v = np.clip(np.asarray(v, float), 0, 1)
    sat = np.clip((1 - v) * bias, 0, gain)
    return hsv_arr(np.full(v.shape, hue), sat, v)


def lighten(base, add):
    """Per-channel max, not sum. Additive compositing of several layers
    drives every channel toward 1.0 and the prop goes white, losing exactly
    the colour distinction that makes layers legible. Lighten keeps each
    layer's hue identity while still letting the brightest one win."""
    return np.maximum(base, add)


def chroma_hue(chroma_vec):
    """Dominant pitch class -> hue, so the palette follows the harmony
    instead of drifting arbitrarily. Circle of fifths spreads related keys
    to nearby hues, which keeps chord changes from lurching in colour."""
    k = int(np.argmax(chroma_vec))
    fifths = [0, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10, 5]
    return fifths.index(k) / 12.0


# -------------------------------------------------------------------- layers
def build(a, mix_fn):
    """a: music.Analysis. Returns (n_frames, N, 3) perceptual 0..1."""
    nf = a.n_frames
    out = np.zeros((nf, N, 3), np.float32)

    # sparkle state, decayed across frames so grains fade instead of blink
    spark = np.zeros(N)
    spark_k = math.exp(-1.0 / (0.30 * FPS))
    rng = np.random.default_rng(4)

    # arm selection advances on each beat
    beat_i = np.zeros(nf, int)
    bi = 0
    bts = list(a.beats) + [1e9]
    for f in range(nf):
        while f / FPS >= bts[bi + 1] if bi + 1 < len(bts) else False:
            bi += 1
        beat_i[f] = bi

    sec_bounds = [s["start"] for s in a.sections] + [a.duration]

    for f in range(nf):
        t = f / FPS
        sec = a.section_at(t)
        m = mix_fn(sec)
        frame = np.zeros((N, 3), np.float32)

        # ---- layer 0: wash. harmony -> hue, RMS+harmonic -> level ----
        # hue never leaves the cold band; centroid slides cyan->violet and
        # chroma only nudges it, so the palette always reads as ice
        cold = ICE_COOL + (ICE_WARM - ICE_COOL) * a.centroid[f]
        hue = cold + 0.02 * math.sin(2 * math.pi * chroma_hue(a.chroma_f[f]))
        hue += m["hue_shift"]
        lvl = (0.30 * a.rms[f] + 0.70 * a.harm[f]) * m["wash"]
        sat = m["sat"] * (0.62 + 0.30 * (1 - a.centroid[f]))
        # slight radial falloff so the centre reads as the core of the prop
        rad_fall = 1.0 - 0.25 * (R_IN / R_MAX)
        frame += hsv_arr(np.full(N, hue), np.full(N, sat), lvl * rad_fall)

        # ---- layer 1: bass ring, radius driven by low band ----
        if m["ring"] > 0:
            edge = a.low[f] * R_MAX * 1.05
            width = 3.0                                  # inches
            band = np.exp(-((R_IN - edge) / width) ** 2)
            v = band * a.low[f] * m["ring"]
            frame = lighten(frame, frost(v, ICE_COOL, bias=0.95))

        # ---- layer 2: arm hits, percussive onsets pick one arm ----
        if m["arms"] > 0 and a.hit[f] > 0.02:
            arm = (beat_i[f] * (3 if m["rotate"] else 1)) % 4
            sel = (ARM == arm)
            v = np.zeros(N)
            v[sel] = a.hit[f] * m["arms"] * (0.45 + 0.55 * (R_IN[sel] / R_MAX))
            frame = lighten(frame, frost(v, ICE_BASE, bias=1.30))

        # ---- layer 3: sparkle from high-band onsets ----
        spark *= spark_k
        if m["sparkle"] > 0 and a.hit[f] > 0.55 and rng.random() < 0.35:
            spark[rng.choice(N, size=min(3, N), replace=False)] = 0.85
        if m["sparkle"] > 0 and a.hit_high[f] > 0.25:
            k = max(2, int(4 + 11 * a.hit_high[f] * m["sparkle"]))
            spark[rng.choice(N, size=min(k, N), replace=False)] = 1.0
        if m["sparkle"] > 0:
            v = spark * m["sparkle"]
            # the signature grains: white core, blue falloff
            frame = lighten(frame, frost(v, 0.585, bias=1.15))

        # ---- layer 3b: idle shimmer. A snowflake should glint even in the
        # quietest bars, so a slow low-density twinkle runs underneath
        # everything, driven by time rather than by onsets. ----
        if m["shimmer"] > 0:
            ph = (IDX * 0.618 + t * 0.13) % 1.0
            g = np.exp(-((ph - 0.5) / 0.035) ** 2) * m["shimmer"]
            frame = lighten(frame, frost(g, 0.565, bias=1.0))

        # ---- layer 4: melody glow travelling the wire ----
        if m["melody"] > 0:
            pos = (a.centroid[f] * 0.6 + (t * 0.11) % 1.0) % 1.0 * N
            d = np.abs(((IDX - pos + N / 2) % N) - N / 2)
            v = np.exp(-(d / 7.0) ** 2) * a.mid[f] * m["melody"]
            frame = lighten(frame, frost(v, ICE_WARM, bias=1.00))

        # ---- layer 5: section transition wipe ----
        for b in sec_bounds:
            dt = t - b
            if 0 <= dt < 0.55:
                p = dt / 0.55
                sweep = (XY_IN[:, 1] / R_MAX + 1) / 2          # bottom -> top
                v = np.exp(-((sweep - p) / 0.16) ** 2) * (1 - p) * 1.1
                frame = lighten(frame, frost(v, ICE_COOL, bias=0.70))

        # ---- power cap, applied to the composite ----
        frame = np.clip(frame, 0, 1)
        meanv = frame.mean()
        if meanv > POWER_CAP:
            frame *= POWER_CAP / meanv
        out[f] = frame
    return out


def mix_for(sec):
    """Section intensity -> layer mix. No song-form labels, so any track
    works. `intensity` blends ordinal rank with absolute loudness; rank
    alone lets a near-silent intro score as high as a real verse."""
    r = sec.get("intensity", 0.5) if sec else 0.5
    if r <= 0.25:
        return dict(wash=0.34, ring=0.26, arms=0.0, sparkle=0.0, melody=0.0,
                    shimmer=0.75, sat=0.85, hue_shift=0.0, rotate=False)
    if r < 0.55:
        return dict(wash=0.38, ring=0.80, arms=0.40, sparkle=0.60, melody=0.0,
                    shimmer=0.60, sat=0.85, hue_shift=0.0, rotate=False)
    if r < 0.85:
        return dict(wash=0.42, ring=0.92, arms=0.78, sparkle=0.85, melody=0.50,
                    shimmer=0.45, sat=0.90, hue_shift=0.0, rotate=False)
    return dict(wash=0.44, ring=1.00, arms=1.00, sparkle=1.00, melody=0.75,
                shimmer=0.35, sat=0.95, hue_shift=0.0, rotate=True)


# --------------------------------------------------------------------- write
def countdown(s, bpm):
    """4 beats of dim white so the music can be started in time. The .rgb
    carries no audio, so alignment is manual -- hit play on the 4th blink."""
    spb = 60.0 / max(60.0, bpm)
    for i in range(4):
        fb = FrameBuf(s, 255)
        v = int(255 * (0.35 ** GAMMA) * (1 if i < 3 else 2.4))
        fb.fill(PROP_CH, min(255, v), min(255, v), min(255, v))
        blk = fb.bytes()
        for _ in range(max(1, int(spb * 0.16 * FPS))):
            s.frames.append(blk)
        dark = FrameBuf(s, 255).bytes()
        for _ in range(max(1, int(spb * 0.84 * FPS))):
            s.frames.append(dark)


def write(buf, path, bpm, lead=True):
    s = Show(CH)
    if lead:
        countdown(s, bpm)
    lead_frames = len(s.frames)
    for f in range(buf.shape[0]):
        fb = FrameBuf(s, 255)
        b = np.clip(buf[f], 0, 1) ** GAMMA * 255.0      # perceptual -> byte
        b = b.astype(np.uint8)
        for i in range(N):
            fb.set(PROP_CH, i, int(b[i, 0]), int(b[i, 1]), int(b[i, 2]))
        s.frames.append(fb.bytes())
    s.save(path)
    return s, lead_frames


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    song = sys.argv[2] if len(sys.argv) > 2 else None
    # Carol of the Bells is in 3/4; the tracker locks to the fast ostinato
    # (166.7 BPM), so a bar is 6 detected beats. Auto-detection agrees, but
    # pin it -- the downbeat contrast on this track is only 1.086, i.e. weak.
    a = music.analyse(song, fps=FPS, beats_per_bar=6 if song else None)
    print(a.summary())
    print()
    for i, sec in enumerate(a.sections):
        m = mix_for(sec)
        act = [k for k in ("wash", "ring", "arms", "sparkle", "melody") if m[k] > 0]
        print(f"  section {i+1} intensity {sec.get('intensity',0):.2f} -> "
              f"{'+'.join(act)}{'  (rotating)' if m['rotate'] else ''}")
    buf = build(a, mix_for)
    s, lead = write(buf, os.path.join(out, "Show47Music.rgb"), a.bpm)
    n = len(s.frames)
    print(f"\nShow47Music.rgb  {n} frames = {n/FPS:.1f} s  "
          f"{(s.header_size + n*s.frame_size)/1e6:.2f} MB")
    print(f"lead-in {lead} frames ({lead/FPS:.1f} s) -- start the music on the "
          f"4th, brighter blink")
    np.save(os.path.join(out, "_show47_buf.npy"), buf)
