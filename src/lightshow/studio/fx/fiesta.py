"""fiesta.py -- the Fiesta pack, written for "Feliz Navidad" (José Feliciano) but general.

Every piece is a lyric or an instrument of that track made visible on the props:

    Guitar strum          the props are the six strings; each stroke sweeps the pick across them and they ring
    Fiesta banners        papel picado -- strings of lace-cut pennants that step colours on the beat and flutter
    Nochebuena bloom      the poinsettia, Mexico's Christmas flower: red bracts open over green leaves, gold centre
    From the bottom       a beating heart rises "from the bottom" of every prop, fills it, and bursts into glow
    Confetti              "próspero año y felicidad": a piñata-burst of tumbling paper squares in the palette colours

All sizes in inches, times in seconds, bursts anchored to the clip's own clock (t = 0 at
the clip start) so a burst lands where the editor put the clip, not on a hidden grid.
"""

import math
import numpy as np

from ..engine import effect, Slider, choice, toggle
from ...effects import lighten
from .util import noise, fbm, smoothstep, rng, glints, gradient

PACK = "Fiesta"
WHITE = np.ones(3)


# ------------------------------------------------------------------ guitar strum
@effect("strum", "anim", "Guitar strum", pack=PACK, tags=["music"], params=[
    choice("pattern", "Strum pattern", "down / up", ["down only", "down / up", "rumba (d d-u u-d-u)"]),
    Slider("sweep_s", "Pick sweep across the row (s)", 0.12, 0.03, 0.4, 0.01, unit="s"),
    Slider("ring_s", "Ring (decay, s)", 0.9, 0.2, 3.0, 0.05, unit="s"),
    Slider("floor", "String idle level", 0.3, 0.0, 0.7, 0.05),
    choice("chord", "Chord colour changes", "every bar", ["every bar", "every 2 beats", "every 2 bars", "per string"]),
    Slider("harmonic", "Vibration pattern", 2, 1, 4, 1, kind="int"),
    Slider("vib_hz", "Vibration rate (Hz)", 3.0, 1.0, 8.0, 0.5),
], doc="The props are guitar strings. On every beat the pick sweeps left-to-right across the row (a downstroke) and each prop lights white-hot as it is struck, then rings in the chord colour: a standing wave of bright and dim bands wobbles along the prop and dies away. Upstrokes on the off-beat go right-to-left, softer. The chord colour changes per bar from the palette.")
def strum(g, m, t, p, pal, st):
    bl = m.beat_len; since = m.beat_phase * bl
    sweep = p["sweep_s"]; ring = p["ring_s"]
    # strokes of this beat: (time offset within the beat, direction +1 L->R / -1, strength)
    pat = p["pattern"]
    if pat == "down only":
        strokes = [(0.0, 1, 1.0)]
    elif pat == "down / up":
        strokes = [(0.0, 1, 1.0), (0.5, -1, 0.55)]
    else:   # rumba: beat 1 down, beat 2 down-up, beat 3 up-down-up (4/4 flamenco-ish pattern over 2 beats)
        k = m.beat_index % 2
        strokes = [(0.0, 1, 1.0), (0.5, -1, 0.5)] if k == 0 else [(0.0, -1, 0.6), (0.33, 1, 0.9), (0.66, -1, 0.5)]
    out = {}
    for pr in g.props:
        r = g.rank[pr.idx] if g.P > 1 else 0.5
        # most recent stroke that has reached this string (this beat or the previous one)
        best_age, best_w = None, 0.0
        for back in (0, 1):
            for off, d, w in strokes:
                pos = r if d > 0 else 1 - r
                age = since + back * bl - (off * bl + pos * sweep)
                if age >= 0 and (best_age is None or age < best_age):
                    best_age, best_w = age, w
        if best_age is None:
            best_age, best_w = ring * 3, 0.3
        env = best_w * math.exp(-best_age / ring)
        # chord colour
        ch = p["chord"]
        if ch == "per string":
            col = pal.color(pr.idx)
        elif ch == "every 2 beats":
            col = pal.color(m.beat_index // 2)
        elif ch == "every 2 bars":
            col = pal.color(m.bar_index // 2)
        else:
            col = pal.color(m.bar_index)
        # standing wave along the string: bright antinodes, dim nodes, wobbling at vib_hz and settling as it rings
        k = int(p["harmonic"])
        wave = np.sin(math.pi * k * pr.y01) * math.cos(2 * math.pi * p["vib_hz"] * best_age)
        bright = p["floor"] + (1 - p["floor"]) * env * (0.55 + 0.45 * wave)
        fr = col[None, :] * np.clip(bright, 0, 1)[:, None]
        # the pluck: a white flash at the moment the pick crosses, strongest at the pick's height (lower third)
        flash = max(0.0, 1 - best_age / 0.09) * best_w
        if flash > 0:
            fr = lighten(fr, WHITE[None, :] * (flash * np.exp(-((pr.y01 - 0.35) / 0.25) ** 2))[:, None])
        out[pr.id] = np.clip(fr, 0, 1)
    return out


# ------------------------------------------------------------------ papel picado
@effect("papel_picado", "anim", "Fiesta banners", pack=PACK, params=[
    Slider("flag_in", "Flag width (in)", 7.0, 3.0, 20.0, 0.5, unit="in"),
    Slider("row_in", "Row spacing (in)", 12.0, 6.0, 40.0, 1.0, unit="in"),
    Slider("sag", "String sag", 0.5, 0.0, 1.0, 0.05),
    Slider("lace", "Lace cut-outs", 0.5, 0.0, 1.0, 0.05),
    choice("step", "Colours step", "every beat", ["every beat", "every 2 beats", "every bar", "never"]),
    Slider("flutter", "Flutter", 0.6, 0.0, 1.5, 0.05),
    choice("shape", "Flag shape", "rectangle", ["rectangle", "pennant", "scallop"]),
    toggle("string", "Show the string", True),
], doc="Papel picado: strings of paper-cut pennants hung in rows across every prop, each flag a different palette colour, the colours stepping one flag along on the beat so the whole party marches. Lace holes twinkle dark in the paper, the rows sag like real string, and a breeze ripples the flags.")
def papel_picado(g, m, t, p, pal, st):
    # which beat-step we are on
    s = p["step"]
    step = 0 if s == "never" else (m.beat_index if s == "every beat" else (m.beat_index // 2 if s == "every 2 beats" else m.bar_index))
    fw, rh = p["flag_in"], p["row_in"]
    out = {}
    for pr in g.props:
        # rows hang from the top of the prop; string sags between hooks at the prop edges
        hook = pr.h - 1.0
        row = np.floor((hook - pr.ly) / rh)                                  # 0 = top row
        rowtop = hook - row * rh
        sag = p["sag"] * 0.12 * pr.w * np.sin(np.pi * np.clip((pr.lx / max(1e-3, pr.w) + 0.5), 0, 1))
        y_in_row = rowtop - sag - pr.ly                                     # 0 at the string, grows downward
        flag_h = rh * 0.74
        # flag columns along the string, offset by half a flag on odd rows
        col_i = np.floor((pr.lx + pr.w / 2) / fw + 0.5 * (row % 2))
        xin = (pr.lx + pr.w / 2) / fw + 0.5 * (row % 2) - col_i             # 0..1 across the flag
        # flag mask by shape
        if p["shape"] == "pennant":
            bottom = flag_h * (1 - 0.9 * np.abs(xin - 0.5) * 2)
        elif p["shape"] == "scallop":
            bottom = flag_h * (0.8 + 0.2 * np.abs(np.sin(xin * np.pi * 3)))
        else:
            bottom = np.full(pr.n, flag_h)
        inflag = (y_in_row > 0.4) & (y_in_row < bottom) & (np.abs(xin - 0.5) < 0.46) & (row >= 0)
        # colour per flag, stepping along on the beat; neighbouring rows offset so the diagonal reads
        idx = (col_i + row * 2 - step).astype(int)
        rgb = pal.pick(idx)
        # breeze: a travelling wave of light across the paper (flags catching the light as they lift)
        fl = 0.72 + 0.28 * np.sin(2 * np.pi * (pr.lx / 30.0) - t * 2.2 * (1 + 0.5 * p["flutter"]) + row * 1.1)
        fl = 1 - p["flutter"] * 0.6 * (1 - fl)
        # lace: holes punched through the paper, a few per flag, scrolling very slowly like pattern repeats
        holes = fbm(pr.lx / 2.2 + col_i * 3.1, pr.ly / 2.2, 0.0, 7, octaves=2)
        lace = 1 - p["lace"] * smoothstep(0.62, 0.72, holes)
        fr = rgb * (inflag * fl * lace)[:, None]
        if p["string"]:
            on_string = np.exp(-(y_in_row / 0.9) ** 2) * (row >= 0)
            fr = lighten(fr, WHITE[None, :] * (0.55 * on_string)[:, None])
        # gaps between flags are never black-black: a faint warm night glow
        fr = lighten(fr, np.array([0.06, 0.03, 0.0])[None, :] * np.ones((pr.n, 1)))
        out[pr.id] = np.clip(fr, 0, 1)
    return out


# ------------------------------------------------------------------ poinsettia
@effect("poinsettia", "anim", "Nochebuena bloom", pack=PACK, tags=["slow"], params=[
    Slider("bars", "Bars per bloom", 2, 1, 16, 1, kind="int"),
    Slider("petals", "Bracts", 6, 4, 9, 1, kind="int"),
    Slider("size", "Flower size (share of prop)", 0.95, 0.4, 1.3, 0.05),
    Slider("leaves", "Green leaves behind", 0.7, 0.0, 1.0, 0.05),
    Slider("centre", "Gold centre", 0.8, 0.0, 1.0, 0.05),
    Slider("spin", "Slow turn (deg/s)", 4.0, 0.0, 30.0, 1.0),
    choice("colours", "Colours", "red / green / gold", ["red / green / gold", "palette"]),
    toggle("music", "Centre twinkles with the beat", True),
], doc="The flor de Nochebuena -- the poinsettia, Mexico's Christmas flower. On each cycle pointed red bracts unfold outward from the centre of every prop over a ring of darker green leaves, with a cluster of gold seed-lights twinkling in the middle; the flower turns very slowly and the bracts pulse brighter on the beat. The radial props (snowflakes) make perfect flowers.")
def poinsettia(g, m, t, p, pal, st):
    if p["colours"] == "palette":
        red, green, gold = pal.color(0), pal.color(1), pal.color(2)
    else:
        red, green, gold = np.array([1.0, 0.05, 0.05]), np.array([0.05, 0.55, 0.12]), np.array([1.0, 0.75, 0.1])
    k = int(p["petals"])
    cyc = max(1, int(p["bars"]))
    u = ((m.bar_index % cyc) + m.bar_phase) / cyc                           # 0..1 through the bloom cycle
    grow = smoothstep(0.0, 0.55, u) * (1 - smoothstep(0.86, 1.0, u))       # bracts open over the first half, hold, close again at the end
    rot = math.radians(p["spin"]) * t
    beat = 0.85 + 0.15 * m.beat_env
    out = {}
    for pr in g.props:
        R = pr.r.max() * p["size"]
        a = pr.ang - rot
        # leaves: k petals rotated half a step, larger and darker; bracts: pointed petals in front
        leaf_R = R * (0.45 + 0.55 * np.clip(np.cos(k * (a + math.pi / k)), 0, 1) ** 0.7) * (0.55 + 0.45 * grow)
        brac_R = R * 0.8 * (0.3 + 0.7 * np.clip(np.cos(k * a), 0, 1) ** 0.55) * grow
        leaf = smoothstep(leaf_R + pr.pitch, leaf_R - pr.pitch, pr.r) * p["leaves"]
        brac = smoothstep(brac_R + pr.pitch, brac_R - pr.pitch, pr.r)
        # veins: a bright midrib down each bract, shading darker toward the edges
        vein = np.exp(-((np.abs(((a * k / (2 * math.pi)) % 1.0) - 0.0) * 2) ** 2) * 60) * 0.35
        shade = 0.7 + 0.3 * (1 - pr.r / max(1e-3, R)) + vein
        fr = green[None, :] * (leaf * (0.75 + 0.25 * (1 - pr.r / max(1e-3, R))))[:, None]
        fr = np.where((brac > 0.02)[:, None], red[None, :] * np.clip(brac * (shade + 0.25) * beat, 0, 1)[:, None], fr)
        fr = lighten(fr, red[None, :] * (brac * 0.6)[:, None])
        # gold centre: a cluster of seed lights, each on its own glint clock
        cr = R * 0.17 * (0.6 + 0.4 * grow)
        core = smoothstep(cr + pr.pitch, cr * 0.4, pr.r) * p["centre"]
        tw = glints(pr, t, rate=0.8 if not p["music"] else 0.5 + 1.5 * m.beat_env, seed=3, sharp=9.0)
        fr = lighten(fr, gold[None, :] * (core * (0.55 + 0.45 * tw))[:, None])
        fr = lighten(fr, WHITE[None, :] * (core * tw * 0.5)[:, None])
        # a hint of the night around the flower so the prop never reads as "off"
        fr = lighten(fr, green[None, :] * 0.14)
        out[pr.id] = np.clip(fr, 0, 1)
    return out


# ------------------------------------------------------------------ corazón
def _heart(x, y):
    """Implicit heart: <= 0 inside, for x in -1.3..1.3, y in -1.2..1.3 (point at the bottom)."""
    return (x * x + y * y - 1) ** 3 - x * x * y ** 3


@effect("corazon", "anim", "From the bottom of my heart", pack=PACK, tags=["music"], params=[
    Slider("bars", "Bars per cycle", 4, 1, 16, 1, kind="int"),
    Slider("rise", "Share of cycle rising", 0.6, 0.2, 0.9, 0.05),
    Slider("size", "Heart size (share of prop)", 0.8, 0.3, 1.2, 0.05),
    Slider("pulse", "Heartbeat pulse", 0.12, 0.0, 0.3, 0.01),
    Slider("burst", "Burst at the end", 1.0, 0.0, 1.0, 0.05),
    Slider("glow", "Warm glow behind", 0.25, 0.0, 0.5, 0.02),
    choice("colours", "Heart colours", "red / pink", ["red / pink", "palette"]),
    toggle("anchor", "Cycle starts at the clip start", True),
], doc="'From the bottom of my heart': a small heart appears at the very bottom of every prop and rises, growing, to fill it, beating lub-dub on the beat; when it reaches the top of its cycle it bursts into a warm glow that washes out through the whole prop, then the next heart starts again at the bottom. Cycle length in bars; anchored to the clip start so the burst lands on the lyric where you put it.")
def corazon(g, m, t, p, pal, st):
    if p["colours"] == "palette":
        red, pink = pal.color(0), pal.color(1)
    else:
        red, pink = np.array([1.0, 0.0, 0.08]), np.array([1.0, 0.25, 0.55])
    cyc = max(1, int(p["bars"]))
    period = cyc * m.beat_len * m.beats_per_bar
    if p["anchor"]:
        u = (t % period) / period
    else:
        u = ((m.bar_index % cyc) + m.bar_phase) / cyc
    rise = p["rise"]
    up = smoothstep(0.0, rise, u)                                            # 0 at the bottom .. 1 centred
    # heartbeat: lub on the beat, dub a third of a beat later
    ph = m.beat_phase
    lub = math.exp(-ph * 9); dub = math.exp(-max(0.0, ph - 0.3) * 9) * 0.6 * (ph > 0.3)
    beat = 1 + p["pulse"] * (lub + dub)
    # the burst: from the end of the rise, a ring runs out and the heart dissolves into glow
    bu = smoothstep(rise, min(1.0, rise + 0.25), u)
    out = {}
    for pr in g.props:
        size = p["size"] * min(pr.w * 0.42, pr.h * 0.3) * (0.35 + 0.65 * up) * beat
        cy = pr.h * (0.12 + 0.38 * up)                                       # centre: bottom edge .. middle
        x = pr.lx / max(1e-3, size); y = (pr.ly - cy) / max(1e-3, size)
        f = _heart(x, y)
        inside = smoothstep(0.08, -0.08, f)
        edge = np.exp(-(f / 0.12) ** 2)                                      # the outline, brightest
        # shaded fill: pink highlight up-left, red body
        hi = np.exp(-((x + 0.45) ** 2 + (y - 0.45) ** 2) / 0.25)
        fill = red[None, :] * (inside * (0.75 + 0.25 * (1 - np.abs(x) * 0.5)))[:, None]
        fill = lighten(fill, pink[None, :] * (inside * hi * 0.9)[:, None])
        fill = lighten(fill, WHITE[None, :] * (edge * 0.5)[:, None])
        fill = fill * (1 - bu) * smoothstep(0.0, 0.05, u)                    # fades in at the bottom, lets go in the burst
        # glow behind, warm and rising with the heart; the burst washes the whole prop
        gl = p["glow"] * (0.5 + 0.5 * np.exp(-((pr.ly - cy) / (pr.h * 0.5)) ** 2))
        ring_r = bu * max(pr.w, pr.h) * 0.9
        ring = np.exp(-((np.hypot(pr.lx, pr.ly - cy) - ring_r) / (6.0 + 4 * bu)) ** 2) * p["burst"] * (bu > 0) * (1 - bu * 0.6)
        wash = p["burst"] * smoothstep(0.0, 0.5, bu) * (1 - smoothstep(0.88, 1.0, u)) * 0.6        # holds until the next heart starts
        fr = lighten(fill, pink[None, :] * (gl + wash)[:, None])
        fr = lighten(fr, WHITE[None, :] * (ring * 0.9)[:, None])
        fr = lighten(fr, red[None, :] * (ring * 0.7)[:, None])
        # a few warm sparkles drifting up through the glow, so the dark parts still live
        sp = glints(pr, t, rate=0.35, seed=11, sharp=16.0) * (0.12 + 0.25 * bu)
        fr = lighten(fr, pink[None, :] * sp[:, None])
        out[pr.id] = np.clip(fr, 0, 1)
    return out


# ------------------------------------------------------------------ confetti
@effect("confetti", "anim", "Confetti", pack=PACK, params=[
    Slider("density", "Pieces (per 10 ft)", 90, 10, 300, 5, kind="int"),
    Slider("size_in", "Piece size (in)", 3.5, 1.0, 8.0, 0.25, unit="in"),
    Slider("speed", "Fall speed (in/s)", 22.0, 5.0, 80.0, 1.0, unit="in/s"),
    Slider("tumble", "Tumble", 1.0, 0.0, 2.0, 0.1),
    Slider("drift", "Sideways drift", 0.8, 0.0, 2.0, 0.1),
    choice("burst", "Piñata burst", "once, at the start", ["none", "once, at the start", "every N bars"]),
    Slider("every_bars", "N bars", 2, 1, 16, 1, kind="int"),
    Slider("burst_s", "Burst length (s)", 1.6, 0.4, 5.0, 0.1, unit="s"),
    Slider("rain", "Steady rain after the burst", 0.6, 0.0, 1.0, 0.05),
    Slider("floor", "Glow floor", 0.18, 0.0, 0.4, 0.02),
], doc="A piñata breaks: a flash at the top of every prop and a dense shower of paper squares in all the palette colours tumbles down -- each piece flips as it falls, so it flashes bright edge-on and dark face-on -- then settles into a lighter steady rain. 'Próspero año y felicidad.' Bursts are anchored to the clip start (or every N bars of clip time).")
def confetti(g, m, t, p, pal, st):
    period = max(0.1, int(p["every_bars"]) * m.beat_len * m.beats_per_bar)
    if p["burst"] == "none":
        since = 1e9
    elif p["burst"] == "once, at the start":
        since = t
    else:
        since = t % period
    bs = p["burst_s"]
    burst = smoothstep(bs, 0.0, since)                                     # 1 at the bang, 0 after burst_s
    out = {}
    for pr in g.props:
        r = rng(pr.idx * 13 + 5)
        n = max(4, int(p["density"] * max(pr.w, 24) / 120))
        x0 = -pr.w / 2 + r.random(n) * pr.w; y0 = r.random(n); sp = 0.7 + 0.6 * r.random(n)
        spin = (0.8 + 1.4 * r.random(n)) * p["tumble"]; ph = r.random(n) * 6.283; ci = r.integers(0, 1 << 20, n)
        span = pr.h + 2 * p["size_in"]
        # steady rain pieces loop forever; burst pieces all start at the top at the bang and fall together
        fall = t * p["speed"] * sp
        y_rain = pr.h + p["size_in"] - ((y0 * span + fall) % span)
        # the burst is three times as dense as the rain: every piece plus two extra sets, all released at the top at once
        xb = np.concatenate([x0, -pr.w / 2 + r.random(2 * n) * pr.w]); spb = np.concatenate([sp, 0.7 + 0.6 * r.random(2 * n)])
        y0b = np.concatenate([y0, r.random(2 * n)]); phb = np.concatenate([ph, r.random(2 * n) * 6.283]); cib = np.concatenate([ci, r.integers(0, 1 << 20, 2 * n)])
        spinb = np.concatenate([spin, (0.8 + 1.4 * r.random(2 * n)) * p["tumble"]])
        y_burst = pr.h + p["size_in"] - since * p["speed"] * spb * (1.0 + 0.8 * y0b)
        x_burst = xb + p["drift"] * (4.0 * np.sin(t * 1.1 * spb + phb) + 1.5 * np.sin(t * 2.9 * spb + phb * 2))
        flip_b = 0.35 + 0.65 * np.abs(np.cos(t * spinb * 2.5 + phb)) ** 0.6 if p["tumble"] > 0 else np.ones(3 * n)
        cols_b = pal.pick(cib)
        x = x0 + p["drift"] * (4.0 * np.sin(t * 1.1 * sp + ph) + 1.5 * np.sin(t * 2.9 * sp + ph * 2))
        flip = 0.35 + 0.65 * np.abs(np.cos(t * spin * 2.5 + ph)) ** 0.6 if p["tumble"] > 0 else np.ones(n)
        cols = pal.pick(ci)
        rad = p["size_in"] / 2
        fr = np.zeros((pr.n, 3))
        for xs, ys, fl, cl, w in ((x, y_rain, flip, cols, p["rain"] * (1 - 0.5 * burst)),
                                  (x_burst, y_burst, flip_b, cols_b, 1.0 if since < bs * 2.5 + pr.h / max(1.0, p["speed"] * 0.7) else 0.0)):
            if w <= 0:
                continue
            sel = (ys > -rad) & (ys < pr.h + rad)
            if not sel.any():
                continue
            d2 = (pr.lx[:, None] - xs[sel][None, :]) ** 2 + (pr.ly[:, None] - ys[sel][None, :]) ** 2
            v = np.exp(-d2 / rad ** 2) * (fl[sel] * w)[None, :]
            k = np.argmax(v, axis=1)
            vv = v[np.arange(pr.n), k]
            fr = lighten(fr, cl[sel][k] * vv[:, None])
        # the bang: a white flash at the top that drops through the prop in the first moments
        if since < bs:
            front = pr.h * (1 - since / bs * 1.3)
            flash = np.exp(-((pr.ly - front) / 5.0) ** 2) * (1 - since / bs) + 0.5 * (1 - since / (bs * 0.35)) * (pr.ly > pr.h * 0.7) * (since < bs * 0.35)
            fr = lighten(fr, WHITE[None, :] * np.clip(flash, 0, 1)[:, None])
        # floor: a dim party-colour wash so the prop never goes black between pieces
        fr = lighten(fr, gradient(pal, (pr.y01 * 0.5 + t * 0.03) % 1.0) * p["floor"])
        out[pr.id] = np.clip(fr, 0, 1)
    return out
