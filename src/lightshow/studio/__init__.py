"""
lightshow.studio -- the linear timeline editor (HTML front end + Python backend).

    python -m lightshow.studio                 # opens http://127.0.0.1:8765
    python -m lightshow.studio --layout assets/bench.json

Layout of the package
    project.py    project.json model: audio clips, sections, tracks, clips, cards
    palettes.py   default palettes, auto-generation, colour helpers
    audio.py      per-file music analysis cache, beat grids, bar-aware sections
    engine.py     group context, music-at-time, effect registry, compositor
    fx/           the effects: transitions, animations, modifiers
    server.py     FastAPI app: REST for the project/layout/paint, WebSocket preview
    static/       the single-page front end
"""
