# Works without installing: PYTHONPATH points at src/.
# `pip install -e .` also works and additionally enables
# `python -m lightshow.preview ...` from anywhere.
PY := PYTHONPATH=src python3

.PHONY: test props show player fps chain preview twoprop clean

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

twoprop:         ## build the two-prop show and its HTML viewer
	$(PY) tools/two_prop_show.py out
	$(PY) tools/make_viewer.py out/two_props.html out/TwoProps.rgb

preview:         ## HTML geometry viewer (PROP=assets/props/47号.mod)
	$(PY) -m lightshow.preview $(PROP) out/preview.html

clean:
	rm -rf out/* .pytest_cache __pycache__ src/lightshow/__pycache__
