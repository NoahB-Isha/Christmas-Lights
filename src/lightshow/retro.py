#!/usr/bin/env python3
"""
retro.py -- the "1960s Times Square" look family: classic wholesome
incandescent Christmas, props drawn as what they ARE, flashing in and out
like a marquee sign.

Two independent things happen every frame:

1. THE SIGN PROGRAM decides which props are ON at all (whole prop, hard
   on/off with an incandescent tail). Programs run on 8th-note "ticks"
   over a 4-bar phrase, on props bucketed left->right:

     walk       one prop at a time steps along the row, one per beat;
                last bar everyone is on
     build      props come on cumulatively, one per beat, hold all-on,
                then three flashes and OUT (the classic sign cycle)
     alternate  odd / even props swap every beat; last bar all on
     steady     everything on (the per-prop animation carries it)
     finale     everything on; the song's last two bars stutter on 8ths

2. EACH PROP HAS ITS OWN ANIMATION while it is on, keyed to what the prop
   depicts (regions from assets/paint, else its label):

     santa      painted regions -- red suit, flesh face/hands, grey boots --
                all the WHITE TRIM blinks together on the beat, hands flash
                on the sleigh-bell hits (waving), suit throbs on the pulse
     bell       red bell body with gold glitter (density = treble), gold
                ribbon blinking on the off-beat, and a RING: a bright band
                swings across the bell on every pulse, alternating direction
     cane       red/white stripes that MARCH one step per beat (a quarter
                stripe), white stripes popping on the pulse
     snowflake  icy tendrils: on each pulse light grows from the centre out
                to the tips, the tips glitter white; ice-blue and white
     star       yellow with white flashes on the hits and a marquee chaser
                (every 3rd bulb) running around the wire on the 16ths
     other      warm-white incandescent wash with a chaser (unknown props)

Cross-prop moments on top: a warm pop on every bar downbeat, and a
warm-white sweep along the row on the phrase turn.

Section params:  program: walk|build|alternate|steady|finale (default: by
phrase -- build, alternate, build, steady), pop: 0..1 (bar pop level).
"""

import math

import numpy as np

from .effects import hsv, lighten
from .show import look, gust

# incandescent colours (perceptual)
WARM = np.array([1.00, 0.80, 0.55])       # tungsten white
RED = np.array([1.00, 0.10, 0.06])
GREEN = np.array([0.15, 0.85, 0.25])
GOLD = np.array([1.00, 0.62, 0.12])
YELLOW = np.array([1.00, 0.78, 0.15])
ICE = np.array([0.55, 0.80, 1.00])
WHITE = np.array([0.92, 0.94, 1.00])
FLESH = np.array([0.95, 0.72, 0.50])
GREY = np.array([0.42, 0.38, 0.36])

TRIM = ("arm cuffs", "leg cuffs", "jacket bottom trim", "center jacket trim", "hat pompom", "hat and collar trim", "trim", "cuffs", "collar")


def prop_kind(p):
    names = set(p.region_names)
    if "jacket body" in names or "coat" in names:
        return "santa"
    if "sparkly bell" in names or "bell" in names:
        return "bell"
    lab = ((p.pl.label or "") + " " + p.pl.mod).lower()
    for key, kind in (("cane", "cane"), ("santa", "santa"), ("bell", "bell"), ("cross", "star"),
                      ("star", "star"), ("snow", "snowflake"), ("flake", "snowflake")):
        if key in lab:
            return kind
    return "other"


# ------------------------------------------------------------ sign programs
def _buckets(c):
    order = sorted(c.props, key=lambda q: q.cx)
    nb = min(len(order), 8)
    return {q.id: k * nb // len(order) for k, q in enumerate(order)}, nb


def _program_state(prog, tick, nb, k, last_bars=False):
    """Is bucket k on at phrase tick (0..31, 8 ticks per bar)?"""
    bar, tb, beat = tick // 8, tick % 8, tick // 2
    if prog == "walk":
        return bar == 3 or (beat % nb) == k
    if prog == "build":
        step = max(1, 16 // nb)                  # ticks per bucket on the way up
        if bar < 2:
            return k <= tick // step
        if bar == 2:
            return True
        return tb < 6 and tb % 2 == 0            # three flashes, then out
    if prog == "alternate":
        if bar == 3:
            return tick < 30
        return (beat % 2) == (k % 2)
    if prog == "finale":
        return (tick % 2 == 0) if last_bars else True
    return True                                  # steady


def sign_levels(c):
    """{prop_id: 0..1} whole-prop on-level with an incandescent tail."""
    prog = c.params.get("program")
    phrase_i = int(c.beat_index // (c.bar_beats * 4))
    if not prog:
        prog = ["build", "alternate", "build", "steady"][phrase_i % 4]
    buckets, nb = _buckets(c)
    sb = max(1, int(c.params.get("step_beats", 1)))            # beats per program step (2 = half speed)
    sbeat = c.beat_index // sb
    sphase = ((c.beat_index % sb) + c.beat_phase) / sb
    bi = sbeat % (c.bar_beats * 4)
    half = sphase >= 0.5
    tick = bi * 2 + (1 if half else 0)
    beat_s = 60.0 / c.bpm * sb
    t_tick = (sphase - (0.5 if half else 0.0)) * beat_s
    last_bars = (c.song["to"] - c.t) < 2 * beat_s * c.bar_beats
    out = {}
    for p in c.props:
        k = buckets[p.id]
        on = _program_state(prog, tick, nb, k, last_bars)
        was = _program_state(prog, (tick - 1) % 32, nb, k, last_bars)
        if c.params.get("lamp", "led") != "led":                   # a lamp model shapes the edges: hand it hard on/off
            lvl = 1.0 if on else 0.0
        elif on:
            lvl = 1.0 if was else min(1.0, 0.35 + t_tick / 0.05)   # filament warms in ~50 ms
        else:
            lvl = math.exp(-t_tick / 0.11) * 0.9 if was else 0.0   # and cools out
        out[p.id] = lvl
    return out


# ------------------------------------------------------- per-prop animation
def _region_fill(p, colours, default):
    fr = np.tile(default, (p.n, 1)).astype(float)
    for name, m in p.regions.items():
        col = colours(name)
        if col is not None:
            fr[m] = col
    return fr


def anim_santa(c, p):
    blink = 1.0 if (c.beat_index % 2 == 0) else 0.4              # the white trim blinks on the beat
    suit = 0.88 + 0.12 * c.pulse
    wave = min(1.0, 0.25 + 1.4 * c.hit_high + 0.6 * c.hit)         # hands flash on the bells

    def colours(name):
        n = name.lower()
        if any(t in n for t in TRIM):
            return WHITE * blink
        if "hand" in n:
            return lighten(FLESH * 0.8, WHITE * wave * 0.9)
        if "face" in n:
            return FLESH * 0.9
        if "boot" in n:
            return GREY
        if "hat" in n or "jacket" in n or "pant" in n or "coat" in n or "suit" in n:
            return RED * suit
        return None
    return _region_fill(p, colours, RED * suit)


def anim_bell(c, p):
    body_m = p.regions.get("sparkly bell", p.regions.get("bell", p.regions.get("rest")))
    ring_dir = 1 if (c.beat_index % 2 == 0) else -1
    x01 = (p.lx - p.lx.min()) / max(1e-6, np.ptp(p.lx))
    pos = 0.5 + ring_dir * (c.pulse_phase - 0.5)                  # swings across on the pulse
    band = np.exp(-((x01 - pos) / 0.14) ** 2) * (0.9 * c.pulse + 0.2)
    body = RED[None, :] * (0.7 + 0.3 * c.pulse)
    glitter = c.grains(p, 6 + 30 * c.high, 0.45, seed_extra=3)
    fr = lighten(body * np.ones((p.n, 1)), GOLD[None, :] * glitter[:, None], WHITE[None, :] * band[:, None] * 0.7)
    ribbon = GOLD * (1.0 if (c.beat_index % 2 == 1) else 0.5)     # off-beat against Santa's trim
    for name, m in p.regions.items():
        if "ribbon" in name.lower() or "bow" in name.lower():
            fr[m] = ribbon
    return fr


def anim_cane(c, p):
    pitch = max(4.0, p.h / 5.0)                                    # ~5 fat stripes up the cane (2" bulb pitch: keep them coarse)
    s = (p.ly + 0.35 * p.lx) / pitch + c.beat_index * 0.25         # slight diagonal; marches a quarter stripe per beat
    white = (s % 1.0) < 0.5
    pop = 0.7 + 0.3 * c.pulse
    fr = np.where(white[:, None], WHITE[None, :] * pop, RED[None, :] * 0.95)
    return fr


def anim_snowflake(c, p):
    """Icy: steady ice-blue body, the tendrils grow centre -> tips once per
    BAR (not per pulse -- at fast walks that was too busy), tips glitter
    slowly. Under a lamp model: just the steady ice with slow tip glitter."""
    if c.params.get("lamp", "led") != "led" or c.params.get("calm"):
        base = ICE[None, :] * 0.85 * np.ones((p.n, 1))
        tips = c.grains(p, 2, 1.8, seed_extra=7) * (p.r01 > 0.75)
        return lighten(base, WHITE[None, :] * tips[:, None] * 0.8)
    grow = np.clip((c.bar_phase * 1.25 - p.r01) / 0.18, 0, 1)      # front travels centre -> tips over a bar
    front = np.exp(-((p.r01 - c.bar_phase * 1.25) / 0.10) ** 2)
    base = ICE[None, :] * (0.45 + 0.5 * grow[:, None])
    fr = lighten(base, WHITE[None, :] * front[:, None] * 0.9)
    tips = c.grains(p, 3, 1.2, seed_extra=7) * (p.r01 > 0.7)
    return lighten(fr, WHITE[None, :] * tips[:, None])


def anim_star(c, p):
    sixteenth = int(c.beat_phase * 4) + c.beat_index * 4
    chaser = ((p.i - sixteenth) % 3) == 0
    flash = min(1.0, max(0.0, (c.hit - 0.55) / 0.45) + 0.5 * max(0.0, c.hit_high - 0.5))  # only the real hits go white
    fr = YELLOW[None, :] * (0.8 + 0.2 * c.pulse) * np.ones((p.n, 1))
    fr = lighten(fr, WHITE[None, :] * chaser[:, None] * 0.55)
    return fr + (WHITE[None, :] - fr) * flash                       # blend TO white (lighten would leave it pink)


def anim_other(c, p):
    sixteenth = int(c.beat_phase * 4) + c.beat_index * 4
    chaser = ((p.i - sixteenth) % 4) == 0
    fr = WARM[None, :] * (0.55 + 0.25 * c.pulse) * np.ones((p.n, 1))
    return lighten(fr, WARM[None, :] * chaser[:, None])


ANIM = {"santa": anim_santa, "bell": anim_bell, "cane": anim_cane,
        "snowflake": anim_snowflake, "star": anim_star, "other": anim_other}


@look("retro")
def look_retro(c):
    levels = sign_levels(c)
    pop_lvl = float(c.params.get("pop", 0.0 if c.params.get("lamp") == "twinkle" else 0.35))   # no white pops under twinkle
    bar_s = 60.0 / c.bpm * c.bar_beats
    bar_pop = pop_lvl * c.pulse ** 2 if (c.beat_index % c.bar_beats == 0) else 0.0
    out = {}
    for p in c.props:
        kind = prop_kind(p)
        fr = ANIM[kind](c, p)
        fr = lighten(fr, WARM[None, :] * bar_pop)                          # everyone pops on the downbeat
        if c.unison > 0.5:                                                  # phrase turn: a warm sweep along the row
            sw = gust(c, p, period=bar_s, width_in=45)
            fr = lighten(fr, WARM[None, :] * sw[:, None] * 0.5 * c.unison)
        out[p.id] = np.clip(fr * levels[p.id] * (0.9 + 0.1 * c.intensity), 0, 1)
    return out
