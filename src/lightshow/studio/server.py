"""
server.py -- the Studio backend. FastAPI + uvicorn, one process, one project.

    python -m lightshow.studio [--layout assets/layout.json] [--project assets/studio/project.json] [--port 8765]

REST
    GET  /api/state                     everything the UI needs to boot
    PUT  /api/project                   save the whole project (the UI is authoritative while editing)
    PUT  /api/layout                    save the whole layout (groups, props, controllers)
    POST /api/layout/auto_assign        {group?, keep?} -> pack props onto controllers
    GET  /api/paint/{stem}  PUT ...     paint regions for one prop
    GET  /api/audio/{id}/analysis       beats, waveform, proposed sections (query: bpm, beat_offset, bpb)
    GET  /api/audio/{id}/file           the audio itself for the <audio> element
    POST /api/audio/import              {path} add a file already on disk
    POST /api/audio/upload              multipart upload into assets/audio/
    GET  /api/palettes/generate         ?scheme=&hue=
    POST /api/render                    render the timeline to cards (out/studio/cards/<ctrl>/Sc-01-01.rgb)
WS
    /ws/preview   client: {"t": seconds, "groups": [ids] | null, "seek": bool}
                  server: float64 t + uint8 RGB for every prop in /api/state.order
"""

import argparse, asyncio, json, os, shutil, struct, threading, time, webbrowser

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..layout import Layout, shapes_json, PROPS_DIR
from .. import regions as REG
from .project import Project
from .engine import Renderer, registry_json
from . import palettes as PAL
from .audio import Track, ROOT

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")

FPS_HELP = {
    "60": "60 fps -- the controller's native rate when it is started from its own buttons or a DMX scene-select "
          "(measured on the bench). Smoothest motion, files twice as large, 65,535-frame cap = 18:12 of show.",
    "30.3": "30.3 fps -- what the GC-102C audio box pins the controller to when IT starts the show (measured "
            "30.30 fps from 4K video). Use this whenever the audio box is the trigger, or the show runs at half speed. "
            "Half the file size; 65,535 frames = 36 min.",
}


def seed_from_show_yaml(project, clip):
    """First run: take the per-song boundaries + reference tempos from
    assets/show/show.yaml and the listening notes from assets/show/markers.json
    so the medley arrives with its songs and labelled sections in place."""
    import re
    try:
        import yaml
        spec = yaml.safe_load(open(os.path.join(ROOT, "assets", "show", "show.yaml"), encoding="utf-8"))
    except Exception:
        return
    if os.path.basename(spec.get("audio", "")) != os.path.basename(clip["file"]):
        return
    from ..show import parse_t
    songs = []
    for s in spec.get("songs", []):
        m = re.match(r"\s*([\d.]+)", str(s.get("tempo_hint", "")))
        bpm = float(m.group(1)) if m else None
        pb = int(s.get("pulse_beats", 1)); bb = int(s.get("bar_beats", 4))
        songs.append({"name": s["name"], "from": parse_t(s["from"]), "to": parse_t(s["to"]),
                      "bpm": round(bpm / pb, 2) if bpm else None, "beats_per_bar": max(2, bb // pb), "beat_offset": None})
    clip["songs"] = songs
    mpath = os.path.join(ROOT, "assets", "show", "markers.json")
    if os.path.exists(mpath):
        ms = json.load(open(mpath)).get("markers", [])
        ms = sorted(ms, key=lambda m: m["t"])
        secs = []
        for k, m in enumerate(ms):
            t1 = ms[k + 1]["t"] if k + 1 < len(ms) else clip.get("duration") or spec.get("duration", m["t"] + 10)
            label = (m.get("label") or "").strip()
            if m.get("type") == "song":
                label = "♪ " + (label or "song")
            secs.append({"t0": clip["start"] + m["t"], "t1": clip["start"] + t1, "label": label[:60], "audio": clip["id"]})
        project.set_sections(secs)


class State:
    def __init__(self, layout_path, project_path):
        self.layout_path = layout_path
        self.project_path = project_path
        self.tracks = {}
        self.lock = threading.Lock()
        self.load()

    def load(self):
        self.layout = Layout.load(self.layout_path)
        rel = os.path.relpath(self.layout_path, ROOT)
        if os.path.exists(self.project_path):
            self.project = Project.load(self.project_path)
            self.project.d["layout"] = rel
        else:
            audio = os.path.join(ROOT, "assets", "audio", "show16.mp3")
            self.project = Project.default(self.project_path, rel, self.layout.groups,
                                           "assets/audio/show16.mp3" if os.path.exists(audio) else None)
            if self.project.audio:
                seed_from_show_yaml(self.project, self.project.audio[0])
            self.project.save()
        for gid in self.layout.groups:
            self.project.ensure_track(gid)
        self.rebuild()

    def rebuild(self):
        with self.lock:
            self.renderer = Renderer(self.project, self.layout, self.project.d.get("fps", 30.3), self.tracks)

    def track(self, clip):
        tr = self.tracks.get(clip["file"])
        if tr is None:
            tr = self.tracks[clip["file"]] = Track(clip["file"])
        return tr

    def audio_clip(self, aid):
        for a in self.project.audio:
            if a["id"] == aid:
                return a
        raise HTTPException(404, f"audio clip {aid}")

    def paint_json(self):
        out = {}
        for p in self.layout.props:
            st = REG.stem(p.mod)
            if st not in out:
                out[st] = REG.load(p.mod)
        return out

    def state_json(self):
        L = self.layout
        R = self.renderer
        # world coordinates per prop for the preview, rounded
        world = {}
        for p in L.props:
            W = p.world()
            world[p.id] = {"x": np.round(W[:, 0], 1).tolist(), "y": np.round(W[:, 1], 1).tolist(), "z": np.round(W[:, 2], 1).tolist()}
        return {
            "project": self.project.to_json(),
            "layout": L.to_json(),
            "layout_path": os.path.relpath(self.layout_path, ROOT),
            "shapes": shapes_json(L),
            "paint": self.paint_json(),
            "world": world,
            "order": R.prop_order(),
            "effects": registry_json(),
            "default_palettes": PAL.DEFAULTS,
            "schemes": PAL.SCHEMES,
            "fps_help": FPS_HELP,
            "issues": [{"level": a, "msg": b} for a, b in L.validate()],
            "audio_files": sorted(f for f in os.listdir(os.path.join(ROOT, "assets", "audio"))
                                  if f.lower().endswith((".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"))) if os.path.isdir(os.path.join(ROOT, "assets", "audio")) else [],
        }


def make_app(state: State):
    app = FastAPI(title="Lightshow Studio")

    @app.get("/", response_class=HTMLResponse)
    def index():
        # cache-bust the static files with their newest mtime so a browser never runs an old app.js against a new server
        import re
        v = str(int(max(os.path.getmtime(os.path.join(STATIC, f)) for f in os.listdir(STATIC))))
        html = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
        return re.sub(r'(/static/[\w.-]+\.(?:js|css))', lambda m: f"{m.group(1)}?v={v}", html)

    SITE_DIR = os.path.join(ROOT, "assets", "site")

    @app.get("/api/site")
    def site_images():
        """Backdrop images for the placement grid (assets/site/*.png|jpg)."""
        if not os.path.isdir(SITE_DIR):
            return []
        return sorted(f for f in os.listdir(SITE_DIR) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))

    @app.get("/api/site/{name}")
    def site_image(name: str):
        from fastapi.responses import FileResponse
        path = os.path.join(SITE_DIR, os.path.basename(name))
        if not os.path.isfile(path):
            raise HTTPException(404, "no such site image")
        return FileResponse(path)

    @app.post("/api/site/upload")
    async def site_upload(file: UploadFile = File(...)):
        """Upload a backdrop (PNG/JPG, or a PDF which is rendered to PNG at 150 dpi with pdftoppm if available)."""
        os.makedirs(SITE_DIR, exist_ok=True)
        name = os.path.basename(file.filename or "map.png")
        data = await file.read()
        if name.lower().endswith(".pdf"):
            import subprocess, tempfile
            with tempfile.TemporaryDirectory() as td:
                src = os.path.join(td, "in.pdf"); open(src, "wb").write(data)
                stem = os.path.splitext(name)[0]
                try:
                    subprocess.run(["pdftoppm", "-r", "150", "-png", "-singlefile", src, os.path.join(td, "out")], check=True, capture_output=True)
                except Exception as e:
                    raise HTTPException(400, f"could not render the PDF (needs poppler's pdftoppm: brew install poppler): {e}")
                data = open(os.path.join(td, "out.png"), "rb").read(); name = stem + ".png"
        with open(os.path.join(SITE_DIR, name), "wb") as fh:
            fh.write(data)
        return {"ok": True, "file": name}

    @app.get("/sort", response_class=HTMLResponse)
    def sort_page():
        """Sort props into groups by theme -- drag/drop board, saves via PUT /api/layout."""
        return open(os.path.join(STATIC, "sort.html"), encoding="utf-8").read()

    @app.get("/api/state")
    def get_state():
        return state.state_json()

    # ------------------------------------------------------------ project
    @app.put("/api/project")
    async def put_project(body: dict):
        body["layout"] = state.project.d["layout"]
        state.project = Project(body, state.project_path)
        for gid in state.layout.groups:
            state.project.ensure_track(gid)
        state.project.save()
        state.rebuild()
        return {"ok": True, "duration": state.project.duration()}

    # ------------------------------------------------------------- layout
    @app.put("/api/layout")
    async def put_layout(body: dict):
        from ..layout import Placement
        props = [Placement(**{k: v for k, v in p.items() if k in Placement.FIELDS}) for p in body.get("props", [])]
        L = Layout(body.get("groups", {}), props, body.get("controllers", {}), {"notes": body.get("notes", ""), "map": body.get("map"), "route": body.get("route")})
        L.path = state.layout_path
        L.save()
        state.layout = L
        for gid in L.groups:
            state.project.ensure_track(gid)
        state.project.save()
        state.rebuild()
        return {"ok": True, "issues": [{"level": a, "msg": b} for a, b in L.validate()]}

    class AutoAssign(BaseModel):
        group: str | None = None
        keep: bool = False

    @app.post("/api/layout/auto_assign")
    def auto_assign(body: AutoAssign):
        touched = state.layout.auto_assign(body.group, body.keep)
        state.layout.save()
        state.rebuild()
        return {"ok": True, "touched": touched, "layout": state.layout.to_json(),
                "issues": [{"level": a, "msg": b} for a, b in state.layout.validate()]}

    @app.get("/api/props")
    def all_props():
        """Every .mod in assets/props, for adding props that are not yet in the layout."""
        from ..layout import prop_shape
        out = []
        for f in sorted(os.listdir(PROPS_DIR)):
            if f.endswith(".mod"):
                s = prop_shape(f)
                out.append({"mod": f, "n": s["n"], "w": round(s["w"], 1), "h": round(s["h"], 1), "pitch_in": round(s["pitch_in"], 3),
                            "lx": [round(float(v), 1) for v in s["lx"]], "ly": [round(float(v), 1) for v in s["ly"]]})
        return out

    # -------------------------------------------------------------- paint
    @app.get("/api/paint/{stem}")
    def get_paint(stem: str):
        return REG.load(stem + ".mod")

    @app.put("/api/paint/{stem}")
    async def put_paint(stem: str, body: dict):
        REG.save(stem + ".mod", body.get("regions", {}))
        state.rebuild()                                  # PropGeom caches regions
        return {"ok": True}

    # -------------------------------------------------------------- audio
    @app.get("/api/audio/{aid}/analysis")
    def audio_analysis(aid: str):
        """Beat grid, waveform and proposed sections for one audio clip, using
        the clip's tempo map (songs) as saved in the project."""
        a = state.audio_clip(aid)
        tr = state.track(a)
        if not a.get("duration"):
            a["duration"] = tr.duration
        songs = a.get("songs") or []
        ui = tr.ui_json(songs, a.get("bpm"), a.get("beat_offset"), a.get("beats_per_bar") or 4)
        secs, used = tr.sections_songs(songs if songs else [{"from": 0.0, "to": tr.duration, "bpm": a.get("bpm"),
                                                             "beats_per_bar": a.get("beats_per_bar") or 4, "beat_offset": a.get("beat_offset")}])
        ui["sections"] = [{"t0": round(s0, 3), "t1": round(s1, 3), "kind": k, "song": si} for s0, s1, k, si in secs]
        ui["novelty_sections"] = [{"t0": round(float(r[0]), 3), "t1": round(float(r[1]), 3), "intensity": round(float(r[2]), 2)}
                                  for r in tr.novelty_secs]
        return ui

    @app.get("/api/audio/{aid}/file")
    def audio_file(aid: str):
        a = state.audio_clip(aid)
        path = a["file"] if os.path.isabs(a["file"]) else os.path.join(ROOT, a["file"])
        if not os.path.exists(path):
            raise HTTPException(404, path)
        return FileResponse(path)

    class Import(BaseModel):
        path: str
        name: str | None = None

    @app.post("/api/audio/import")
    def audio_import(body: Import):
        path = body.path
        if not os.path.isabs(path):
            cand = os.path.join(ROOT, "assets", "audio", path)
            path = cand if os.path.exists(cand) else os.path.join(ROOT, path)
        if not os.path.exists(path):
            raise HTTPException(404, path)
        rel = os.path.relpath(path, ROOT) if path.startswith(ROOT) else path
        tr = state.tracks[rel] = Track(rel)
        a = state.project.add_audio(rel, body.name, tr.duration, None)
        state.project.save(); state.rebuild()
        return a

    @app.post("/api/audio/upload")
    async def audio_upload(file: UploadFile = File(...)):
        dest_dir = os.path.join(ROOT, "assets", "audio")
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(file.filename))
        with open(dest, "wb") as fh:
            shutil.copyfileobj(file.file, fh)
        rel = os.path.relpath(dest, ROOT)
        tr = state.tracks[rel] = Track(rel)
        a = state.project.add_audio(rel, file.filename, tr.duration, None)
        state.project.save(); state.rebuild()
        return a

    # ----------------------------------------------------------- palettes
    @app.get("/api/palettes/generate")
    def palette_generate(scheme: str = "triad", hue: float | None = None):
        return PAL.generate(scheme, hue)

    # ------------------------------------------------------------- render
    class RenderReq(BaseModel):
        t0: float = 0.0
        t1: float | None = None
        scene: int = 1
        out: str | None = None

    @app.post("/api/render")
    def render(body: RenderReq):
        from .render import render_cards
        out = body.out or os.path.join(ROOT, "out", "studio", "cards")
        man = render_cards(state.project, state.layout, out, t0=body.t0, t1=body.t1, scene=body.scene)
        return man

    class RenderSongsReq(BaseModel):
        first_scene: int = 1
        out: str | None = None
        warm_s: float = 1.5

    @app.post("/api/render_songs")
    def render_songs_api(body: RenderSongsReq):
        """One scene per song of the tempo map (+ cues.json for the runner)."""
        from .render import render_songs
        out = body.out or os.path.join(ROOT, "out", "studio", "cards")
        return render_songs(state.project, state.layout, out, first_scene=body.first_scene, warm_s=body.warm_s)

    @app.get("/api/render_songs/plan")
    def render_songs_plan(first_scene: int = 1):
        from .render import song_scenes
        fps = float(state.project.d.get("fps", 30.3))
        return [{"scene": first_scene + k, "name": n, "t0": t0, "t1": t1, "frames": int(round((t1 - t0) * fps)), "dmx_value": (first_scene + k - 1) * 4 + 1}
                for k, (n, t0, t1) in enumerate(song_scenes(state.project))]

    # ------------------------------------------------------- fx previews
    @app.get("/api/fx/rig")
    def fx_rig():
        from .engine import preview_rig
        g = preview_rig()
        return {"props": [{"id": p.id, "n": p.n, "x": np.round(p.wx, 1).tolist(), "z": np.round(p.wz, 1).tolist()} for p in g.props]}

    @app.get("/api/fx/preview/{name}")
    def fx_preview(name: str, palette: str = "classic"):
        from .engine import render_preview, REGISTRY
        from fastapi.responses import Response
        if name not in REGISTRY:
            raise HTTPException(404, name)
        with state.lock:
            g, frames = render_preview(name, palette=palette)
        # header: uint32 n_frames, uint32 bytes_per_frame; then the frames back to back
        body = struct.pack("<II", len(frames), len(frames[0])) + b"".join(frames)
        return Response(content=body, media_type="application/octet-stream", headers={"Cache-Control": "max-age=600"})

    # ------------------------------------------------------------- sheets
    @app.get("/api/print/placement.pdf")
    def placement_pdf():
        from .sheets import placement_pdf as make
        path = os.path.join(ROOT, "out", "studio", "placement.pdf")
        try:
            make(state.layout, state.project, path)
        except ImportError:
            raise HTTPException(500, "matplotlib is not installed: pip install matplotlib")
        return FileResponse(path, media_type="application/pdf", filename="placement.pdf")

    # ------------------------------------------------------- AI round-trip
    @app.get("/api/export/digest.md")
    def export_digest():
        from .aiio import digest
        from fastapi.responses import PlainTextResponse
        txt = digest(state.project, state.layout, paint=state.paint_json())
        return PlainTextResponse(txt, headers={"Content-Disposition": 'attachment; filename="show_digest.md"'})

    @app.get("/api/export/project.json")
    def export_project():
        return JSONResponse(state.project.to_json(), headers={"Content-Disposition": 'attachment; filename="project.json"'})

    @app.post("/api/import/project")
    async def import_project(file: UploadFile = File(...)):
        from .aiio import validate
        try:
            data = json.loads((await file.read()).decode("utf-8"))
        except Exception as e:
            raise HTTPException(400, f"not valid JSON: {e}")
        clean, warnings = validate(data, state.layout, state.project.to_json())
        # keep a backup of what was there
        bak = state.project_path + f".bak-{time.strftime('%Y%m%d-%H%M%S')}"
        try:
            shutil.copy(state.project_path, bak)
        except Exception:
            bak = None
        state.project = Project(clean, state.project_path)
        for gid in state.layout.groups:
            state.project.ensure_track(gid)
        state.project.save(); state.rebuild()
        return {"ok": True, "warnings": warnings, "backup": os.path.relpath(bak, ROOT) if bak else None,
                "clips": sum(len(t["clips"]) for t in state.project.d["tracks"])}

    # ------------------------------------------------------------ preview
    @app.websocket("/ws/preview")
    async def ws_preview(ws: WebSocket):
        await ws.accept()
        loop = asyncio.get_event_loop()
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                t = float(msg.get("t", 0.0))
                groups = msg.get("groups") or None
                R = state.renderer

                def work():
                    with state.lock:
                        if msg.get("seek"):
                            R.reset()
                        fr = R.frame(t, groups)
                        return R.pack(fr, gamma=1.0)
                data = await loop.run_in_executor(None, work)
                await ws.send_bytes(struct.pack("<d", t) + data)
        except WebSocketDisconnect:
            pass

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lightshow Studio -- timeline editor")
    ap.add_argument("--layout", default=os.path.join(ROOT, "assets", "layout.json"))
    ap.add_argument("--project", default=None, help="default: assets/studio/<layout stem>.project.json")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    layout = os.path.abspath(a.layout)
    project = a.project or os.path.join(ROOT, "assets", "studio",
                                        os.path.splitext(os.path.basename(layout))[0] + ".project.json")
    state = State(layout, os.path.abspath(project))
    app = make_app(state)
    import uvicorn
    url = f"http://127.0.0.1:{a.port}"
    print(f"Lightshow Studio  {url}   layout={os.path.relpath(layout, ROOT)}  project={os.path.relpath(project, ROOT)}")
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
