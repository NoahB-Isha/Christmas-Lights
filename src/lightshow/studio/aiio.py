"""
aiio.py -- the AI round-trip: export a readable digest of the show (plus the
project.json) for an AI to review, and import an edited project.json back
with validation.

    digest(project, layout, analysis) -> markdown text
    validate(data, layout) -> (clean_project_dict, warnings)
"""

import json, os
from collections import OrderedDict

from .engine import REGISTRY
from . import palettes as PAL
from .project import KINDS


def fmt_t(t):
    t = max(0.0, float(t)); m = int(t // 60); s = t - m * 60
    return f"{m}:{s:05.2f}"


def digest(project, layout, analyses=None, paint=None):
    """Markdown the owner pastes to an AI together with project.json."""
    P = project.d; analyses = analyses or {}; paint = paint or {}
    L = []
    L.append(f"# Lightshow show digest — {P.get('name', 'show')}\n")
    L.append("This is a complete description of a music-synced Christmas light show authored in Lightshow Studio. "
             "The machine-readable source of truth is `project.json` (attached). To change the show, edit `project.json` "
             "and return it: clip times are timeline seconds, `params` use the slider names below (values within the ranges), "
             "`palette` is `classic` / `frost` / `jewel` or a custom id from `palettes`. Anim clips on one track must not overlap; "
             "transitions and modifiers may overlap anything. Keep clip and track ids; new clips need a fresh unique id. "
             "Do not change `audio`, `layout`, `fps` or `cards` unless asked — except the tempo map inside `audio` "
             "(`songs`: split a song and give the new entry its own `bpm`, or add `bpm_end` to make the grid ramp "
             "from `bpm` at `from` to `bpm_end` at `to` for a passage that speeds up or slows down).\n")
    L.append("## Design rules that came from the real props (bench-tested)\n")
    L.append("- Bright saturated LED-Christmas colours, ≤3 per section plus white accent; muted colours look ugly.\n"
             "- Steps and clear events on the beat grid read from a moving car; fast per-beat flicker and volume-following flicker do not.\n"
             "- Props come in and out entirely; one unmistakable look per song; sparkle fields work as intros/ambient.\n"
             "- Incandescent sign programs (walk at half speed, build, alternate) and the drawn painted-region picture were approved.\n"
             "- Avoid total blackouts: props ≥60% bright ≥75% of the time as a soft guideline.\n")
    L.append(f"## Layout — {len(layout.props)} props in {len(layout.groups)} groups (fps {P.get('fps')})\n")
    for gid, g in layout.groups.items():
        ps = sorted(layout.in_group(gid), key=lambda p: p.x)
        L.append(f"### {g.get('label', gid)} (`{gid}`) — {len(ps)} props, {sum(p.n for p in ps):,} px, left→right:")
        for p in ps:
            st = os.path.splitext(p.mod)[0]
            regs = paint.get(st) or {}
            L.append(f"- `{p.id}` {p.label or ''} — {p.n} px, {p.shape()['w']:.0f}×{p.shape()['h']:.0f} in, at x={p.x:.0f} in"
                     + (f", painted regions: {', '.join(regs.keys())}" if regs else ", not painted")
                     + (f", {p.controller}:{p.port}" if p.controller else ""))
        L.append("")
    L.append("## Audio & tempo map\n")
    for a in P.get("audio", []):
        L.append(f"- `{a['id']}` {a['name']} — starts {fmt_t(a['start'])}, {fmt_t(a.get('duration') or 0)} long")
        for sg in a.get("songs") or []:
            L.append(f"  - {fmt_t(a['start'] + sg['from'])}–{fmt_t(a['start'] + sg['to'])} **{sg.get('name', '')}** {sg.get('bpm') or 'detected'}{('→' + str(sg['bpm_end']) + ' (tempo ramps)') if sg.get('bpm') and sg.get('bpm_end') else ''} BPM, {sg.get('beats_per_bar', 4)}/4")
    L.append("\n## Sections (timeline time)\n")
    for s in P.get("sections", []):
        L.append(f"- {fmt_t(s['t0'])}–{fmt_t(s['t1'])} {s.get('label', '')}")
    L.append("\n## Timeline — clips per group\n")
    for tr in P.get("tracks", []):
        g = layout.groups.get(tr["group"], {})
        L.append(f"### {g.get('label', tr['group'])} (track `{tr['id']}`, group `{tr['group']}`)")
        clips = sorted(tr["clips"], key=lambda c: (c["kind"] != "anim", c["kind"] != "trans", c["t0"]))
        if not clips:
            L.append("- (empty)")
        for c in clips:
            fx = REGISTRY.get(c["effect"])
            nondef = {}
            if fx:
                d = fx.defaults()
                nondef = {k: v for k, v in (c.get("params") or {}).items() if k in d and d[k] != v}
            L.append(f"- `{c['id']}` {c['kind']} **{fx.label if fx else c['effect']}** (`{c['effect']}`) {fmt_t(c['t0'])}–{fmt_t(c['t1'])}"
                     f" palette=`{c.get('palette')}`" + (f" params={json.dumps(nondef)}" if nondef else ""))
        L.append("")
    L.append("## Palettes\n")
    for k, v in PAL.DEFAULTS.items():
        L.append(f"- `{k}` {v['name']}: {', '.join(v['colors'])}")
    for k, v in (P.get("palettes") or {}).items():
        L.append(f"- `{k}` {v.get('name')}: {', '.join(v.get('colors', []))}  (custom)")
    L.append("\n## Effect catalogue (what a clip's `effect` may be)\n")
    by_pack = OrderedDict()
    for e in REGISTRY.values():
        by_pack.setdefault(e.pack or e.kind, []).append(e)
    for pack, es in by_pack.items():
        L.append(f"### {pack}")
        for e in es:
            ps = "; ".join(f"`{s.name}` {s.label}: " + (f"one of {s.choices} default {s.default!r}" if s.kind == "choice" else
                            f"on/off default {s.default}" if s.kind == "bool" else
                            "a prop id from the clip's group (\"\" = none)" if s.kind == "prop" else
                            f"{s.lo}–{s.hi} default {s.default}{(' ' + s.unit) if s.unit else ''}")
                           for s in e.params)
            L.append(f"- `{e.name}` ({e.kind}) **{e.label}** — {e.doc}" + (f"\n  - params: {ps}" if ps else ""))
        L.append("")
    return "\n".join(L)


TEMPO_KEYS = ("songs", "bpm", "beat_offset", "beats_per_bar")


def _merge_tempo_maps(cur_audio, new_audio):
    """The import may change the TEMPO MAP of the audio clips (songs, their BPM, an
    accelerando's bpm_end, first beats) but not the clips themselves (file, start, offset,
    duration, transition). -> (merged list, changed) or (None, False) when the clips differ."""
    if not isinstance(new_audio, list) or len(new_audio) != len(cur_audio):
        return None, False
    merged, changed = [], False
    for a, b in zip(cur_audio, new_audio):
        if not isinstance(b, dict):
            return None, False
        strip = lambda d: {k: v for k, v in d.items() if k not in TEMPO_KEYS}
        if json.dumps(strip(a), sort_keys=True) != json.dumps(strip(b), sort_keys=True):
            return None, False
        m = dict(a)
        for k in TEMPO_KEYS:
            if k in b and json.dumps(b.get(k), sort_keys=True) != json.dumps(a.get(k), sort_keys=True):
                m[k] = b[k]; changed = True
        merged.append(m)
    return merged, changed


def validate(data, layout, current=None):
    """Clean an imported project dict. -> (dict, warnings). Never raises on
    content problems: bad clips are dropped with a warning."""
    W = []
    if not isinstance(data, dict):
        raise ValueError("project.json must be a JSON object")
    out = OrderedDict(data)
    cur = current or {}
    for k in ("audio", "layout", "fps", "cards"):
        if k in cur and json.dumps(out.get(k), sort_keys=True) != json.dumps(cur.get(k), sort_keys=True):
            if k == "audio":
                merged, changed = _merge_tempo_maps(cur["audio"], out.get("audio"))
                if merged is not None:
                    out["audio"] = merged
                    if changed:
                        W.append("tempo map (songs / BPM / first beat) updated from the import; the audio clips themselves kept as they are")
                    continue
            W.append(f"`{k}` differs from the current project — kept the current one")
            out[k] = cur[k]
    out.setdefault("palettes", {}); out.setdefault("sections", []); out.setdefault("tracks", [])
    ids = set()
    tracks = []
    for tr in out["tracks"]:
        if tr.get("group") not in layout.groups:
            W.append(f"track {tr.get('id')} refers to unknown group {tr.get('group')!r} — dropped"); continue
        clips = []
        for c in tr.get("clips", []):
            fx = REGISTRY.get(c.get("effect"))
            if c.get("kind") not in KINDS or fx is None or fx.kind != c.get("kind"):
                W.append(f"clip {c.get('id')} ({c.get('kind')} {c.get('effect')!r}) unknown or wrong kind — dropped"); continue
            try:
                t0, t1 = float(c["t0"]), float(c["t1"])
            except Exception:
                W.append(f"clip {c.get('id')} has bad times — dropped"); continue
            if t1 <= t0:
                W.append(f"clip {c.get('id')} ends before it starts — dropped"); continue
            cid = c.get("id") or f"c_{len(ids):06d}"
            while cid in ids:
                cid += "x"
            ids.add(cid)
            d = fx.defaults(); params = {}
            for k, v in (c.get("params") or {}).items():
                if k not in d:
                    W.append(f"clip {cid}: unknown param {k!r} dropped"); continue
                s = next(x for x in fx.params if x.name == k)
                if s.kind == "choice" and v not in s.choices:
                    W.append(f"clip {cid}: {k}={v!r} not one of {s.choices} — default used"); continue
                if s.kind == "prop":
                    v = "" if v is None else str(v)
                    if v and v not in {pl.id for pl in layout.in_group(tr["group"])}:
                        W.append(f"clip {cid}: {k}={v!r} is not a prop of group {tr['group']!r} — cleared"); v = ""
                if s.kind in ("float", "int"):
                    try:
                        v = float(v)
                    except Exception:
                        W.append(f"clip {cid}: {k}={v!r} not a number — default used"); continue
                    if not (s.lo <= v <= s.hi):
                        W.append(f"clip {cid}: {k}={v} clamped to {s.lo}–{s.hi}"); v = min(s.hi, max(s.lo, v))
                    if s.kind == "int":
                        v = int(round(v))
                params[k] = v
            pal = c.get("palette", "classic")
            if not (isinstance(pal, dict) or pal in PAL.DEFAULTS or pal in out["palettes"]):
                W.append(f"clip {cid}: unknown palette {pal!r} — classic used"); pal = "classic"
            clips.append(OrderedDict(id=cid, kind=c["kind"], effect=c["effect"], t0=max(0.0, t0), t1=t1, params=params, palette=pal))
        # anim overlaps: later clip wins (trim earlier)
        anims = sorted([c for c in clips if c["kind"] == "anim"], key=lambda c: c["t0"])
        for a, b in zip(anims[:-1], anims[1:]):
            if a["t1"] > b["t0"]:
                W.append(f"anim clips {a['id']} and {b['id']} overlapped — {a['id']} trimmed"); a["t1"] = b["t0"]
        clips = [c for c in clips if c["t1"] - c["t0"] > 0.05]
        tracks.append(OrderedDict(id=tr.get("id") or f"t_{tr['group']}", group=tr["group"], clips=clips))
    for gid in layout.groups:
        if not any(t["group"] == gid for t in tracks):
            tracks.append(OrderedDict(id=f"t_{gid}", group=gid, clips=[]))
    out["tracks"] = tracks
    secs = []
    for s in out["sections"]:
        try:
            t0, t1 = float(s["t0"]), float(s["t1"])
            if t1 > t0:
                secs.append(OrderedDict(id=s.get("id") or f"s_{len(secs)}", t0=t0, t1=t1, label=str(s.get("label", ""))[:80], audio=s.get("audio")))
        except Exception:
            W.append("a section had bad times — dropped")
    out["sections"] = sorted(secs, key=lambda s: s["t0"])
    for k, v in list(out["palettes"].items()):
        cols = [c for c in (v.get("colors") or []) if isinstance(c, str) and len(c) == 7 and c.startswith("#")]
        if len(cols) < 2:
            W.append(f"palette {k} has fewer than 2 valid colours — dropped"); del out["palettes"][k]
        else:
            out["palettes"][k] = {"name": str(v.get("name", k))[:40], "colors": cols}
    return out, W
