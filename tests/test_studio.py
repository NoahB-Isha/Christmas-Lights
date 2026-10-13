"""Studio: project model, effect contract, renderer, palettes, card export."""
import os, sys, json

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lightshow.layout import Layout                                   # noqa: E402
from lightshow.studio.project import Project                          # noqa: E402
from lightshow.studio import palettes as PAL                          # noqa: E402
from lightshow.studio.engine import Renderer, REGISTRY, GroupCtx, Music  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
BENCH = os.path.join(ROOT, "assets", "bench.json")


@pytest.fixture
def layout():
    return Layout.load(BENCH)


@pytest.fixture
def project(layout, tmp_path):
    # no audio: the engine must work in silence (Music defaults)
    return Project.default(str(tmp_path / "p.json"), "assets/bench.json", layout.groups)


def test_registry_has_every_pack():
    kinds = {e.kind for e in REGISTRY.values()}
    assert kinds == {"anim", "trans", "mod"}
    packs = {e.pack for e in REGISTRY.values()}
    assert {"Transitions", "Incandescent", "Lava lamp", "Starfield", "Classic LED", "Modifiers"} <= packs
    assert sum(e.pack == "Incandescent" for e in REGISTRY.values()) >= 5
    for e in REGISTRY.values():
        for s in e.params:
            assert s.kind in ("float", "int", "choice", "bool", "prop")
            if s.kind == "choice":
                assert s.default in s.choices


def test_anim_clips_never_overlap(project):
    t = project.d["tracks"][0]
    a = project.add_clip(t["id"], "anim", "starfield", 0, 20)
    b = project.add_clip(t["id"], "anim", "lavalamp", 5, 10)          # splits a
    anims = sorted((c for c in t["clips"] if c["kind"] == "anim"), key=lambda c: c["t0"])
    spans = [(c["t0"], c["t1"]) for c in anims]
    assert spans == [(0, 5), (5, 10), (10, 20)]
    for x, y in zip(anims, anims[1:]):
        assert x["t1"] <= y["t0"]
    project.add_clip(t["id"], "mod", "mod_twinkle", 0, 20)             # modifiers may overlap
    assert len([c for c in t["clips"] if c["kind"] == "mod"]) == 1


def test_every_effect_renders_varied_frames(project, layout):
    """Every effect on every group: right shapes, finite, in 0..1, and NOT
    uniform (CLAUDE.md rule 3)."""
    anims = [n for n, e in REGISTRY.items() if e.kind == "anim"]
    trans = [n for n, e in REGISTRY.items() if e.kind == "trans"]
    mods = [n for n, e in REGISTRY.items() if e.kind == "mod"]
    for t in project.d["tracks"]:
        for k, name in enumerate(anims):
            project.add_clip(t["id"], "anim", name, k * 10, k * 10 + 10, palette="jewel")
        for k, name in enumerate(trans):
            project.add_clip(t["id"], "trans", name, k * 10 + 9.5, k * 10 + 10.5)
        for name in mods:
            project.add_clip(t["id"], "mod", name, 0, len(anims) * 10 + 10)
    R = Renderer(project, layout, 30.3)
    for k, name in enumerate(anims):
        colours = []
        for t in (k * 10 + 1.0, k * 10 + 3.3, k * 10 + 9.7):
            fr = R.frame(t)
            for pid, v in fr.items():
                assert v.shape == (layout.prop(pid).n, 3)
                assert np.isfinite(v).all() and v.min() >= 0 and v.max() <= 1
            colours.append(np.concatenate(list(fr.values())).round(2))
        # spatially AND temporally varied: several distinct colours, and not the same frame three times
        # a full-white strobe flash is the one uniform frame that is legitimate
        flat = [c for c in colours if len(np.unique(c, axis=0)) == 1 and not np.allclose(c[0], 1.0, atol=0.02)]
        assert not flat, f"uniform frame from {name}"
        assert not (np.allclose(colours[0], colours[1]) and np.allclose(colours[1], colours[2])), f"{name} is static"


def test_transition_blends_between_animations(project, layout):
    t = project.d["tracks"][0]
    project.add_clip(t["id"], "anim", "led_blocks", 0, 10, palette="classic")
    project.add_clip(t["id"], "anim", "led_rainbow", 10, 20)
    plain = Project(json.loads(json.dumps(project.d)))                # same clips, no transition
    project.add_clip(t["id"], "trans", "wipe", 9, 11)
    R, R0 = Renderer(project, layout, 30.3), Renderer(plain, layout, 30.3)
    for tt in (9.02, 10.98):                                           # ends of the wipe match the plain animations
        a, b = R.frame(tt), R0.frame(tt)
        assert all(np.abs(a[p] - b[p]).max() < 0.35 for p in a)        # (edge glow allowed)
    mid, pl = R.frame(10.0), R0.frame(10.0)
    assert any(not np.allclose(mid[p], pl[p]) for p in mid)            # halfway it is a mix


def test_lamp_model_applied_for_incandescent(project, layout):
    t = project.d["tracks"][0]
    project.add_clip(t["id"], "anim", "inc_build", 0, 60)
    R = Renderer(project, layout, 60)
    # a hard step must be softened by the filament: the first frame after a
    # prop switches on is dimmer than a frame 200 ms later
    fr = [R.frame(k / 60) for k in range(60)]
    lv = np.array([np.mean([v.max() for v in f.values()]) for f in fr])
    assert lv.max() > 0.2 and lv.min() < lv.max() * 0.98      # (level depends on how many bench props light in 1 s)


def test_palettes():
    assert set(PAL.DEFAULTS) == {"classic", "frost", "jewel"}
    for scheme in PAL.SCHEMES:
        p = PAL.Palette(PAL.generate(scheme, 0.3))
        assert p.k >= 2 and p.hex[-1] == "#ffffff"
        assert all(c.max() - c.min() > 0.25 for c in p.chroma)         # saturated
    custom = {"x": {"name": "x", "colors": ["#ff0000", "#00ff00"]}}
    assert PAL.resolve("x", custom).k == 2
    assert PAL.resolve("nope").name == PAL.DEFAULTS["classic"]["name"]


def test_group_ctx_geometry(layout):
    g = GroupCtx("workshop", layout.in_group("workshop"))
    assert g.P == len(layout.in_group("workshop"))
    assert g.D.shape == (g.P, g.P) and np.allclose(np.diag(g.D), 0)
    for p in g.props:
        assert 0 <= g.x01(p).min() and g.x01(p).max() <= 1.0001
    assert list(g.rank) == sorted(g.rank)                              # left -> right


def test_render_cards_identical_frame_counts(project, layout, tmp_path):
    from lightshow.studio.render import render_cards
    from lightshow.formats.rgbfile import Show
    for t in project.d["tracks"]:
        project.add_clip(t["id"], "anim", "led_rainbow", 0, 5)
    project.d["fps"] = 30.3
    man = render_cards(project, layout, str(tmp_path / "cards"), t0=0, t1=2)
    assert man["frames"] == round(2 * 30.3)
    counts = set()
    for cid, c in man["cards"].items():
        sh = Show.load(str(tmp_path / "cards" / c["file"]))
        counts.add(len(sh.frames))
        assert sh.channels == c["channels"]
        f = np.frombuffer(sh.frames[30], np.uint8).reshape(-1, 3)
        assert len(np.unique(f, axis=0)) > 2                            # never uniform
    assert counts == {man["frames"]}


def test_painted_regions_drive_incandescent_colours(project, layout):
    """Santa (61) is painted: at full level every region must show its painted colour."""
    from lightshow import regions as REG
    spec = REG.load("61号.mod")
    assert spec, "61号 must be painted for this test"
    t = project.track_for_group(layout.prop("61").group)
    project.add_clip(t["id"], "anim", "static_picture", 0, 10)
    R = Renderer(project, layout, 60)
    for _ in range(90):                       # let the incandescent/led lamp state settle
        fr = R.frame(_ / 60)
    v = fr["61"]
    for name, r in spec.items():
        want = REG.hex_to_rgb01(r["color"])
        got = v[r["pixels"]]
        assert np.allclose(got, want, atol=0.03), f"region {name}: {got[0]} != {want}"


def test_transition_keeps_both_animations_running(project, layout):
    """During a transition the outgoing animation must keep moving (no frozen last frame)."""
    t = project.d["tracks"][0]
    project.add_clip(t["id"], "anim", "led_rainbow", 0, 10)
    project.add_clip(t["id"], "anim", "lavalamp", 10, 20)
    project.add_clip(t["id"], "trans", "crossfade", 9, 13)         # 3 s past the outgoing clip's end
    R = Renderer(project, layout, 30.3)
    a, b = R.frame(11.0), R.frame(12.0)                            # both inside the window, outgoing "ended" at 10
    pid = next(iter(a))
    # a frozen outgoing frame would make the rainbow component identical; the lava lamp alone moves slowly
    R2 = Renderer(Project(json.loads(json.dumps({**project.d, "tracks": [{**t, "clips": [c for c in t["clips"] if c["effect"] == "lavalamp"]}]}))), layout, 30.3)
    la, lb = R2.frame(11.0), R2.frame(12.0)
    rain_a = a[pid] - la[pid] * 0.5; rain_b = b[pid] - lb[pid] * 0.75
    assert not np.allclose(rain_a, rain_b, atol=0.05)


def test_effect_previews_render_for_every_effect():
    from lightshow.studio.engine import render_preview
    for name, e in REGISTRY.items():
        g, frames = render_preview(name, seconds=0.5, fps=6)
        assert len(frames) == 3 and all(len(f) == sum(p.n for p in g.props) * 3 for f in frames)


def test_new_packs_present_and_tagged():
    packs = {e.pack for e in REGISTRY.values()}
    assert {"Song themes", "Choreography", "Christmas classics"} <= packs
    assert sum(e.kind == "trans" for e in REGISTRY.values()) >= 10
    assert sum(e.kind == "mod" for e in REGISTRY.values()) >= 8
    # every effect's tags are from the known vocabulary, and the obvious ones are set
    known = {"music", "slow", "regions", "incandescent", "geometry"}
    for e in REGISTRY.values():
        assert set(e.tags) <= known, (e.name, e.tags)
        if e.regions:
            assert "regions" in e.tags
        if e.lamp:
            assert "incandescent" in e.tags
    assert "geometry" in REGISTRY["shockwave"].tags
    assert "music" in REGISTRY["music_eq"].tags


def test_feature_prop_helper(layout):
    from lightshow.studio.engine import GroupCtx, Music
    g = GroupCtx("workshop", layout.in_group("workshop"))
    m = Music(0.0)
    assert g.feature("left end", m) == 0
    assert g.feature("right end", m) == g.P - 1
    assert g.feature("centre", m) == g.P // 2
    assert g.feature("largest", m) == int(np.argmax([p.n for p in g.props]))
    seen = set()
    for bar in range(g.P * 2):
        m.bar_index = bar
        seen.add(g.feature("pass along", m, 1))
    assert seen == set(range(g.P))               # the solo visits every prop
    # a SPECIFIC prop, by id or by label; an id from another group falls back to the centre
    for k, p in enumerate(g.props):
        assert g.feature("specific prop", m, 4, p.id) == k
        assert g.feature("specific prop", m, 4, p.pl.label) == k
    assert g.feature("specific prop", m, 4, "not-a-prop") == g.P // 2
    assert g.feature("specific prop", m, 4, "") == g.P // 2


def test_specific_prop_param_round_trips_through_import(project, layout):
    """The Feature prop clip stores the chosen prop id; the import validator keeps a valid
    id, clears one from another group, and the effect lights the chosen prop brightest."""
    from lightshow.studio.aiio import validate
    gid = layout.groups and list(layout.groups)[0]
    t = project.track_for_group(gid)
    g = GroupCtx(gid, layout.in_group(gid))
    pick = g.props[-1].id
    project.add_clip(t["id"], "anim", "emphasise", 0, 10, params={"feature": "specific prop", "prop": pick, "floor": 0.0, "pulse": False})
    R = Renderer(project, layout, 60)
    for _ in range(30):
        fr = R.frame(_ / 60)
    lv = {pid: float(v.max()) for pid, v in fr.items() if pid in g.ids}
    assert max(lv, key=lv.get) == pick
    assert all(lv[pid] < 0.2 for pid in lv if pid != pick)
    out, warns = validate(json.loads(json.dumps(project.d)), layout, project.d)
    clip = out["tracks"][0]["clips"][0]
    assert clip["params"]["prop"] == pick and not warns
    bad = json.loads(json.dumps(project.d)); bad["tracks"][0]["clips"][0]["params"]["prop"] = "nope"
    out, warns = validate(bad, layout, project.d)
    assert out["tracks"][0]["clips"][0]["params"]["prop"] == "" and any("not a prop" in w for w in warns)


def test_round4_effects_present():
    for name in ("bokeh", "kaleidoscope", "fairy_lights", "garland", "toy_train", "mod_snowcap", "melt"):
        assert name in REGISTRY, name
    assert REGISTRY["ornaments"].label == "Tree & ornaments"
    # the tree is many greens, never one: a frame of the plain tree has plenty of distinct colours
    from lightshow.studio.engine import preview_rig, Music
    g = preview_rig()
    from lightshow.studio import palettes as PAL
    fx = REGISTRY["ornaments"]
    p = fx.defaults(); p.update({"density": 0, "fairy": 0.0, "garland": False, "star": False})
    fr = fx.fn(g, Music(1.0), 1.0, p, PAL.resolve("classic"), {})
    for pr in g.props:
        v = fr[pr.id]
        assert len(np.unique(v.round(2), axis=0)) > 20 and v[:, 1].max() > 2.5 * v[:, 1].min()
        assert (v[:, 1] > v[:, 0]).all() and (v[:, 1] > v[:, 2]).all()      # every bulb is some green


def test_tempo_ramp_beats_accelerate():
    """A song entry with bpm_end makes the beat grid ramp linearly (accelerando), and the
    Music the renderer hands effects reports the instantaneous tempo."""
    from lightshow.studio.audio import ramp_beats
    b = ramp_beats(10.0, 30.0, 110.0, 164.0, 10.0)
    ioi = np.diff(b)
    assert b[0] == 10.0 and b[-1] < 30.0
    assert (np.diff(ioi) < 0).all()                                   # every beat shorter than the last
    assert abs(60 / ioi[0] - 110) < 3 and abs(60 / ioi[-1] - 164) < 4
    # a flat ramp is the plain grid
    f = ramp_beats(0.0, 10.0, 120.0, 120.0, 0.0)
    assert np.allclose(np.diff(f), 0.5)


def test_fiesta_pack_present():
    for name in ("strum", "papel_picado", "poinsettia", "corazon", "confetti"):
        assert name in REGISTRY and REGISTRY[name].pack == "Fiesta", name
    assert REGISTRY["corazon"].label == "From the bottom of my heart"


def test_seamless_loop_join(project, layout, tmp_path):
    """loop_s crossfades the tail into a pre-roll of the start: the last frame is as close to
    the first as any two neighbouring frames, not a cut."""
    from lightshow.studio.render import render_cards
    from lightshow.formats.rgbfile import Show
    t = project.d["tracks"][0]
    project.add_clip(t["id"], "anim", "led_gradient_flow", 0, 12)
    man = render_cards(project, layout, str(tmp_path), t1=12.0, scene=3, loop_s=2.0)
    sh = Show.load(str(tmp_path / list(man["cards"].values())[0]["file"]))
    f = lambda i: np.frombuffer(sh.frames[i], np.uint8).astype(float)
    n = len(sh.frames)
    join = np.abs(f(n - 1) - f(0)).mean(); step = np.abs(f(n // 2) - f(n // 2 + 1)).mean()
    assert join < 4 * step + 1.0, (join, step)


def test_render_one_scene_per_song(project, layout, tmp_path):
    """The show cut at song boundaries: consecutive scene numbers, frame counts that add up to the
    whole, identical frame counts across cards within a scene, and a cues.json for the runner."""
    from lightshow.studio.render import render_songs, song_scenes
    from lightshow.formats.rgbfile import Show
    t = project.d["tracks"][0]
    project.add_clip(t["id"], "anim", "led_gradient_flow", 0, 30)
    project.d["audio"] = [{"id": "a_test", "file": "missing.mp3", "name": "x", "start": 0, "offset": 0, "duration": 30,
                           "songs": [{"name": "one", "from": 0, "to": 12.5, "bpm": 120, "beats_per_bar": 4},
                                     {"name": "two", "from": 12.5, "to": 30, "bpm": 100, "beats_per_bar": 4}]}]
    assert [s[0] for s in song_scenes(project)] == ["one", "two"]
    cues = render_songs(project, layout, str(tmp_path), first_scene=3, warm_s=0.5)
    assert [c["scene"] for c in cues["scenes"]] == [3, 4] and [c["dmx_value"] for c in cues["scenes"]] == [9, 13]
    total = 0
    for c in cues["scenes"]:
        counts = {cid: len(Show.load(str(tmp_path / f)).frames) for cid, f in c["cards"].items()}
        assert len(set(counts.values())) == 1 and list(counts.values())[0] == c["frames"]
        total += c["frames"]
    assert abs(total - round(project.duration() * float(project.d["fps"]))) <= 1   # last scene runs to the timeline end
    assert (tmp_path / "cues.json").exists()
