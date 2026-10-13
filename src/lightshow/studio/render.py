"""
render.py -- the timeline -> one .rgb per controller.

    render_cards(project, layout, out_dir, t0=0, t1=None, scene=1)

Frame f is rendered at T = t0 + f / fps with the project's fps (60 or 30.3),
so a 30.3 card plays in real time under the audio box. Every controller gets
the identical frame count; empty ports are 32-px stubs (layout.controller_rigs).
Filenames Sc-<scene>-01.rgb as confirmed on the GC-6004.
"""

import hashlib, json, os, time
from collections import OrderedDict

import numpy as np

from ..formats.rgbfile import Show
from ..effects import to_bytes
from .engine import Renderer


def render_cards(project, layout, out_dir, t0=0.0, t1=None, scene=1, progress=None, loop_s=0.0, warm_s=0.0, manifest="manifest.json"):
    """loop_s > 0 makes the card a seamless loop: the last loop_s seconds crossfade into the
    first loop_s seconds, so an ambient scene left on repeat never shows its join."""
    fps = float(project.d.get("fps", 30.3))
    R = Renderer(project, layout, fps)
    t1 = project.duration() if t1 is None else t1
    n = int(round((t1 - t0) * fps))
    if n > 65535:
        raise ValueError(f"{n} frames exceeds the 65,535-frame cap; shorten the timeline or use 30.3 fps")
    rigs = layout.controller_rigs()
    shows = {cid: Show(rig.channels()) for cid, rig in rigs.items()}
    offs = {cid: np.cumsum([0] + rig.channels()) * 3 for cid, rig in rigs.items()}
    t_start = time.time()

    def pack(fr, cid):
        rig = rigs[cid]; buf = np.zeros(shows[cid].frame_size, np.uint8)
        for k, pr in enumerate(rig.ports):
            if pr.placement is None:
                continue
            b = to_bytes(fr[pr.placement.id]).reshape(-1)
            buf[offs[cid][k]:offs[cid][k] + len(b)] = b
        return buf

    k = int(round(loop_s * fps))
    pre = {cid: [] for cid in rigs}
    if 0 < k < n // 2:
        # seamless loop: render a PRE-ROLL first -- the frames the timeline would show just before
        # t0 (every clip pulled loop_s earlier, local time running negative up to 0) -- then hand its
        # lamp and effect state to the main renderer so frame 0 continues from it, and finally
        # crossfade the tail into the pre-roll so frame n-1 flows straight into frame 0.
        import copy
        from .project import Project
        pre_p = Project(copy.deepcopy(project.d))
        for tr in pre_p.d["tracks"]:
            for c in tr["clips"]:
                c["t0"] -= loop_s; c["_local_shift"] = loop_s
        R2 = Renderer(pre_p, layout, fps, tracks_cache=R._tracks)
        for i in range(k):
            fr = R2.frame(t0 - (k - i) / fps)
            for cid in rigs:
                pre[cid].append(pack(fr, cid))
        R.lamps, R.state = R2.lamps, R2.state
    if warm_s > 0 and not (0 < k < n // 2):
        # a scene cut out of the middle of the show: run the timeline up to t0 first so lamp and
        # effect state (filament warmth, random seeds, envelopes) are what they would be mid-show
        for j in range(int(round(warm_s * fps)), 0, -1):
            R.frame(t0 - j / fps)
    for f in range(n):
        fr = R.frame(t0 + f / fps)
        for cid in rigs:
            shows[cid].frames.append(pack(fr, cid).tobytes())
        if progress and f % 300 == 0:
            progress(f, n)
    if 0 < k < n // 2:
        for cid, sh in shows.items():
            for i in range(k):
                w = (i + 1) / (k + 1)
                tail = np.frombuffer(sh.frames[n - k + i], np.uint8).astype(np.float32)
                sh.frames[n - k + i] = np.clip(tail * (1 - w) + pre[cid][i].astype(np.float32) * w, 0, 255).astype(np.uint8).tobytes()
    os.makedirs(out_dir, exist_ok=True)
    fname = f"Sc-{scene:02d}-01.rgb"
    man = OrderedDict(fps=fps, frames=n, seconds=round(n / fps, 2), scene=scene, loop_s=loop_s,
                      rendered=time.strftime("%Y-%m-%d %H:%M"), render_s=round(time.time() - t_start, 1), cards=OrderedDict())
    for cid, sh in shows.items():
        d = os.path.join(out_dir, cid); os.makedirs(d, exist_ok=True)
        path = os.path.join(d, fname); sh.save(path)
        with open(path, "rb") as fh:
            data = fh.read()
        rig = rigs[cid]
        man["cards"][cid] = {"file": f"{cid}/{fname}", "bytes": len(data), "md5": hashlib.md5(data).hexdigest(),
                             "channels": rig.channels(),
                             "ports": [pr.placement.id if pr.placement else None for pr in rig.ports],
                             "sd_label": project.card(cid).get("sd_label", cid)}
        project.card(cid)["written"] = man["rendered"]
    man["t0"], man["t1"] = round(t0, 3), round(t0 + n / fps, 3)
    json.dump(man, open(os.path.join(out_dir, manifest), "w"), indent=1)
    project.save()
    return man


def song_scenes(project):
    """The show cut at the tempo map's song boundaries -> [(name, t0, t1)] in timeline seconds.
    Falls back to one scene for the whole timeline when there is no tempo map."""
    import re
    base = lambda n: re.split(r"\s+[—–-]\s+|\s*\(", n or "", 1)[0].strip().lower()
    out = []
    for a in project.audio:
        start = float(a.get("start") or 0.0); off = float(a.get("offset") or 0.0)
        for sg in a.get("songs") or []:
            t0 = start - off + float(sg["from"]); t1 = start - off + float(sg["to"])
            if t1 - t0 <= 0.5:
                continue
            name = sg.get("name") or f"song {len(out) + 1}"
            # a tempo-map entry that only exists for a tempo change ("God Rest Ye — accelerando") stays in its
            # song's scene: merge when the names share their base, or when the entry says cut: false
            cut = sg.get("cut")
            same = out and (base(name) and (base(out[-1][0]).startswith(base(name)) or base(name).startswith(base(out[-1][0]))))
            if out and (cut is False or (cut is None and same)):
                out[-1] = (out[-1][0], out[-1][1], t1)
            else:
                out.append((name, t0, t1))
    if not out:
        out.append((project.d.get("name", "show"), 0.0, project.duration()))
    # the first scene starts with the timeline and the last runs to its end, so nothing is left out
    out[0] = (out[0][0], min(0.0, out[0][1]), out[0][2])
    out[-1] = (out[-1][0], out[-1][1], max(out[-1][2], project.duration()))
    return out


def render_songs(project, layout, out_dir, first_scene=1, warm_s=1.5, progress=None):
    """One scene per song: Sc-<first>, Sc-<first+1>, ... each rendered from that song's start so a DMX
    scene-select at the boundary restarts every controller from frame 0 together (free re-sync),
    and no single file is longer than a song. Writes cues.json for the show runner."""
    scenes = song_scenes(project)
    fps = float(project.d.get("fps", 30.3))
    cues = OrderedDict(fps=fps, first_scene=first_scene, rendered=time.strftime("%Y-%m-%d %H:%M"), scenes=[])
    for k, (name, t0, t1) in enumerate(scenes):
        sc = first_scene + k
        if progress:
            progress(k, len(scenes), name)
        man = render_cards(project, layout, out_dir, t0=t0, t1=t1, scene=sc, loop_s=0.0, warm_s=warm_s,
                           manifest=f"manifest-Sc-{sc:02d}.json")
        cues["scenes"].append(OrderedDict(scene=sc, name=name, t0=round(t0, 3), t1=round(t1, 3), frames=man["frames"],
                                          dmx_value=(sc - 1) * 4 + 1,
                                          cards={cid: c["file"] for cid, c in man["cards"].items()},
                                          bytes={cid: c["bytes"] for cid, c in man["cards"].items()}))
    json.dump(cues, open(os.path.join(out_dir, "cues.json"), "w"), indent=1)
    return cues
