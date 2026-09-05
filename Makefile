.PHONY: test props show player fps chain clean

test:            ## run the test suite
	python -m pytest tests/ -q

props:           ## contact sheet of every prop in assets/props
	python tools/plot_props.py

show:            ## build the music show (SONG=path/to.mp3)
	python tools/build_show.py out $(SONG)

player:          ## audio-synced HTML preview (SONG=path/to.mp3)
	python tools/make_player.py out/player.html out/Show47Music.rgb $(SONG)

fps:             ## build the frame-rate measurement file
	python tools/fps_test.py out

chain:           ## build the chain-addressing diagnostic
	python tools/chain_map.py out

clean:
	rm -rf out/* .pytest_cache __pycache__ src/lightshow/__pycache__
