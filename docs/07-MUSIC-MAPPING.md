# Music to light

How the audio is parsed, and how those features become light. Written
against prop 47 (4-armed cross, 72 px) but the reasoning generalises.

## Parsing: five timescales, not one envelope

The commonest failure in a music-reactive show is driving everything from
one loudness envelope. Everything then pulses together and the result reads
as a level meter, not as music. The fix is to extract features at several
timescales and give each one a different job.

```
slow ──────────────────────────────────────────────────────► fast
sections        tempo/beats       band energy        onsets
10–60 s         0.5 s grid        continuous         instant
which look      when things       how much           right now
                may change
```

| Feature | Method | Timescale | What it's for |
|---|---|---|---|
| Sections | novelty over a self-similarity matrix of timbre + chroma | 10–60 s | which *look* is active |
| Tempo, beats | autocorrelation of the onset envelope, then phase-lock | 0.5 s | quantising discrete events |
| Downbeats | best phase of the best beat grouping | 2 s | bar-level changes |
| Band energy | low 20–180 Hz, mid 180–1800, high 1.8–8 k | continuous | smooth modulation |
| Onsets | spectral flux, adaptive threshold, peak-picked | instant | one hit = one event |
| Centroid | spectral centroid in Hz | continuous | timbral brightness → hue |
| Chroma | 12 pitch classes from FFT bins | ~1 s | harmonic colour |
| Harmonic / percussive | median-filter the spectrogram two ways | continuous | **separating sustain from hits** |

**Do not assume 4/4.** Carol of the Bells came back at 166.7 BPM — the
tracker locked to the fast ostinato, not the pulse — so a bar is **6
detected beats (2.16 s)**, which is 3/4 at the real ~83 BPM. Meter is chosen
by scoring each candidate grouping's best phase against the average beat,
with candidates restricted to 2/3/4/6: including 8 lets small-sample bias win
(fewer beats sampled means a luckier subset), and 8 is not a meter anyway,
it is two bars of 4. Even so the downbeat contrast on this track is only
1.086 — weak — so the value is a hint and `beats_per_bar` can be pinned.

The last one earns its place. Median-filtering the spectrogram along time
isolates sustained content; along frequency isolates transients. Once split,
a pad can hold a colour wash while drums punch through it *independently*.
Without it, both are driven by the same envelope and the layering collapses
into one gesture.

Implementation is `lightshow/music.py` — numpy, scipy, and ffmpeg for
decoding. No librosa: the install stays trivial on a Mac, and when a cue
lands wrong you can read the code that put it there.

**Validated** against a synthetic track with known structure: found 120.2
BPM (true 120), 145 beats (true 144), and section boundaries within ~1.5 s
of the real ones. Its one error is splitting a long verse in two, which is
harmless over-segmentation.

## Translating: match the timescale to the spatial channel

Prop 47 has four usable spatial channels, and each has a natural bandwidth.
Pairing a fast feature with a low-resolution channel wastes both.

| Channel | Resolution | Gets | Why |
|---|---|---|---|
| **Radius** centre→tip | ~10 px deep | bass | deepest axis, and bass is slow — a swell reads as the prop inflating |
| **Angle** 4 arms | 4 positions | percussive onsets | too coarse for continuous values; perfect for discrete events |
| **Wire order** 72-px loop | 72 steps | melody, transitions | the only channel that makes the *silhouette* legible |
| **Individual bulbs** | 72 points | hi-hats, cymbals | half-inch bulbs 2 in apart are distinct points — sparkle reads beautifully |
| **Whole prop** | 1 | harmony, loudness | the base everything sits on |

Deliberately unused: **fine spatial gradients.** Bulb pitch is 2 in and a
bulb fills a quarter of that gap, so detail finer than ~4 in falls between
the bulbs and is invisible. This is the constraint that governs everything.

## The layer stack

Six layers, composited in order:

| # | Layer | Blend | Driver |
|---|---|---|---|
| 0 | wash | base | harmonic energy + chroma → hue, RMS → level |
| 1 | bass ring | lighten | low band → radius of an expanding ring |
| 2 | arm hits | lighten | percussive onsets → one arm flashes, advancing on the beat |
| 3 | sparkle | lighten | high-band onsets → random bulbs pop and decay |
| 4 | melody | lighten | centroid → a glow travelling the wire |
| 5 | transition | lighten | section boundaries → a wipe across the prop |

**Accents composite by lighten (per-channel max), not addition.** Summing
five layers drives every channel to 1.0 and the prop turns white, destroying
the colour distinction that makes layering readable. This was measured: with
additive blending mean saturation of lit pixels was visibly washed out; with
lighten it sits at 0.61 and each arm holds its own hue. Additive blending is
the obvious first choice and it is wrong here.

**Hues are spread deliberately** — ring at +0.10 from the wash, melody +0.28,
arms +0.45, sparkle a fixed warm 0.11. Layers that share a hue are
indistinguishable no matter how they blend.

## Sections drive the mix, without knowing song form

Each section gets an `intensity` and the mix follows:

| Intensity | Mix |
|---|---|
| ≤ 0.25 | wash + faint ring, dim, cool — reads as intro/outro |
| < 0.55 | + arm hits, sparkle, melody, restrained |
| < 0.85 | fuller, brighter, more sparkle |
| ≥ 0.85 | everything, saturated, arm selection rotates on downbeats |

`intensity` blends **ordinal rank with absolute loudness**. Rank alone is a
trap: in a 6-section song the near-silent intro ranks 2nd-quietest = 0.2,
which scored it the same as a real verse and made the intro far too busy.
Blending in normalised energy dropped it to 0.16 and the intro went quiet.

No labels like "chorus" are needed, so this works on any track.

## Palette: ice, not Christmas

Prop 47 reads as a **snowflake**, so the look is frost. Red/green/gold would
fight the shape. Everything stays inside a narrow cold band — hue 0.52–0.68,
cyan through blue to violet — and the specific hue matters far less than the
brightness structure, which is what the silhouette actually reads on.
Measured on the finished show: **99.2% of lit pixels fall inside the cold
band**, mean saturation 0.64.

The signature element is a sparkle whose **core is white and whose falloff is
blue**. Each grain is born desaturated (white hot) and *gains* saturation as
it decays, cooling into deep blue on the way out:

```python
def frost(v, hue=0.585, bias=1.15):
    sat = clip((1 - v) * bias, 0, 0.95)     # brighter = whiter
    return hsv(hue, sat, v)
```

That inversion — saturation rising as brightness falls — is the whole
difference between "white twinkle" and "frost". Every accent layer uses it,
with a different hue and bias per layer.

Two additions the real track forced:

**Sparkle needed a second trigger.** Carol of the Bells has only 191
high-band onsets in 186 s — nowhere near enough to carry the look. Grains
are now also seeded probabilistically from strong percussive hits, which
gets the glint rate up to a near-white grain in 6.3% of frames.

**An always-on shimmer layer.** A snowflake should glint even in the
quietest bars, so a slow low-density twinkle runs underneath everything,
driven by time rather than by onsets. Without it the two breakdown sections
(intensity 0.06 and 0.00) went completely dark and the prop looked switched
off rather than resting.

## Two hardware facts that change the output

**Gamma.** The 512-byte LUT in the `.rgb` header is an identity ramp, so the
controller applies *no* gamma — byte value maps roughly linearly to
luminance. Perceived brightness goes as luminance^(1/2.2), so a linear byte
ramp looks top-heavy and fades collapse at the low end. Everything is
authored in perceptual 0..1 and written as `byte = 255 * v**2.2`. This is
the single change that makes slow fades look slow.

**Power.** 72 half-inch bulbs at full white is real current, and the factory
files cap near 127/255, which now looks like a power convention. The mix
caps mean per-frame level at 0.62 across the prop.

## Sync: the unavoidable manual step

The `.rgb` carries no audio and the controller has no trigger input, so
alignment is manual. The show file opens with **four beats of dim white at
the detected tempo, the fourth brighter** — start the music on that beat.

Expect ±100–200 ms by hand. Perceptual tolerance for light-to-sound is
roughly 50–80 ms, so this is worth iterating on: watch it, then nudge an
offset constant and re-render. Once ~20 controllers are involved, this
becomes the drift question in `06-OPEN-QUESTIONS.md` and may need a hardware
trigger or a very disciplined start procedure.

## Running it

```bash
cd reference
python show47.py OUTDIR                # synthetic track, exercises the pipeline
python show47.py OUTDIR /path/song.mp3 # a real song
```

Prints the tempo, the sections it found, and the mix chosen for each, so you
can sanity-check the analysis before looking at the lights.

## What to tune first, in order

1. **Section boundaries.** If they are wrong, everything downstream is wrong.
   Check the printed list against the song before anything else.
2. **Sync offset.** Cheap to fix, and the most visible error.
3. **Layer levels per section.** Taste, not correctness.
4. **Hue mapping.** Chroma → hue via the circle of fifths keeps related keys
   adjacent, but any fixed palette per section also works and is often more
   deliberate for a Christmas show, where red/green/gold may matter more than
   harmonic accuracy.
