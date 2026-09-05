# lightshow

Author music-synced LED shows for SD-card pixel controllers.

Replaces a Windows-only vendor tool with something that runs on a Mac,
understands where props physically are, syncs to music, and can be extended
with AI-written effects.

**New here?** Read `CLAUDE.md` — it is the condensed handoff.

## Install

```bash
pip install -r requirements.txt
brew install ffmpeg          # audio decoding
make test                    # 43 tests, ~0.4s
```

The `make` targets set `PYTHONPATH=src`, so no install is needed. If you
prefer `import lightshow` to work from anywhere, also run
`pip install -e ".[dev]"`.

## Try it

```bash
make props                                   # contact sheet of all 15 props
make preview PROP=assets/props/47号.mod
make show   SONG=~/Music/song.mp3            # build the show
make player SONG=~/Music/song.mp3            # audio-synced HTML preview
```

The preview and player are **standalone HTML** — no server, no build step.
The player embeds the rendered frames but loads your own audio locally, and
its offset slider is how you tune sync before committing it to the file.

## What works

- `.rgb` codec that round-trips real controller files **byte-for-byte**
  across 4, 8 and 24 channels
- `.mod` / `.moc` / Colorloong `.xml` all load into one geometry model
- Audio analysis: sections, tempo, meter, beats, onsets, bands, chroma,
  harmonic/percussive separation — numpy + scipy + ffmpeg, no librosa
- Effect registry of pure functions, sized in real inches
- A full 3-minute music-synced show running on real hardware

## Documentation

| Doc | Contents |
|---|---|
| `CLAUDE.md` | handoff: rules, verified facts, unknowns |
| `docs/01-CONTEXT.md` | project, hardware, physical scale |
| `docs/02-FILE-FORMATS.md` | complete verified format reference |
| `docs/03-ARCHITECTURE.md` | design, and what is load-bearing |
| `docs/04-ROADMAP.md` | phases |
| `docs/05-PROMPTS.md` | prompts per phase |
| `docs/06-OPEN-QUESTIONS.md` | what is still unknown |
| `docs/07-MUSIC-MAPPING.md` | how audio becomes light |

## Hardware diagnostics

`tools/fps_test.py`, `tools/chain_map.py`, `tools/bench_effects.py` and
`tools/bus_probe.py` build `.rgb` files for testing on a real controller.

`tools/dmx_listen.py` receives DMX on a USB-RS485 adapter;
`tools/dmx_diff.py` finds which channel carries scene changes. Both have a
`--selftest` / `--demo` mode that runs without hardware.

See `docs/06-OPEN-QUESTIONS.md` for what each one answers.
