# Works without installing: PYTHONPATH points at src/.
# `pip install -e .` also works and additionally enables
# `python -m lightshow.preview ...` from anywhere.
PY := PYTHONPATH=src python3

.PHONY: test props show player fps chain preview twoprop showcase clean editor cards markers layout

test:            ## run the test suite
	$(PY) -m pytest tests/ -q

props:           ## contact sheet of every prop in assets/props
	$(PY) tools/plot_props.py

show:            ## build the music show (SONG=path/to.mp3)
	$(PY) tools/build_show.py out $(SONG)

player:          ## audio-synced HTML preview (SONG=path/to.mp3)
	$(PY) tools/make_player.py out/player.html out/Show47Music.rgb $(SONG)

fps:             ## build the frame-rate measurement file
	$(PY) tools/fps_test.py out

chain:           ## build the chain-addressing diagnostic
	$(PY) tools/chain_map.py out

showcase:        ## build the 5-minute technique showcase and its viewer
	$(PY) tools/showcase.py out
	SHOW_MODULE=showcase $(PY) tools/make_viewer.py out/showcase.html out/Showcase.rgb

twoprop:         ## build the two-prop show and its HTML viewer
	$(PY) tools/two_prop_show.py out
	$(PY) tools/make_viewer.py out/two_props.html out/TwoProps.rgb

preview:         ## HTML geometry viewer (PROP=assets/props/47号.mod)
	$(PY) -m lightshow.preview $(PROP) out/preview.html

layout:          ## print the layout summary and checks
	$(PY) -m lightshow.layout assets/layout.json

editor:          ## standalone yard layout editor -> out/layout_editor.html
	$(PY) tools/make_layout_editor.py

cards:           ## one .rgb per controller from layout.json (SECONDS=30)
	$(PY) tools/build_cards.py --seconds $(or $(SECONDS),30)

markers:         ## music marker tool -> out/markers.html (SONG=assets/audio/show16.mp3)
	$(PY) tools/make_marker_tool.py $(or $(SONG),assets/audio/show16.mp3)

songs:           ## per-song tempo/beat analysis from markers.json -> out/songs.json
	$(PY) tools/song_report.py

draft:           ## first show.yaml from markers + songs.json (refuses to overwrite)
	$(PY) tools/draft_show.py

cue:             ## bench cue track: music L + start beep R -> out/cue_show.wav
	python3 tools/make_cue_track.py $(or $(SONG),assets/audio/show16.mp3) out/cue_show.wav $(ARGS)

cuetest:         ## audio-box characterisation track: beep every 10 s, no music
	python3 tools/make_cue_track.py --test --every 10 --seconds 180 out/cue_test.wav

bench:           ## bench editor + 30 s ident cards for the 2-controller test bench
	$(PY) tools/make_layout_editor.py assets/bench.json out/bench_editor.html
	$(PY) tools/build_cards.py --layout assets/bench.json --out out/bench_cards --seconds $(or $(SECONDS),30)

clean:
	rm -rf out/* .pytest_cache __pycache__ src/lightshow/__pycache__
