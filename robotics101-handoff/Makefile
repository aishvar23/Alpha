VENV   ?= .venv
PYTHON := $(VENV)/bin/python
EPISODE ?= examples/episode-001.json
OUT     ?= out/episode-001
TTS_PROVIDER ?= espeak
PROFILE ?= preview

.PHONY: install test validate narrate scenes scenes-full demo clean

install:  ## editable install of robotics101 (+ pytest) into the existing .venv
	uv pip install --python $(PYTHON) -e ".[dev]"

test:
	$(PYTHON) -m pytest

validate:
	$(VENV)/bin/robotics101 validate $(EPISODE)

narrate:  ## per-scene TTS (espeak|fixture) -> $(OUT)/audio/*.wav, timing.json, captions.srt
	$(VENV)/bin/robotics101 narrate $(EPISODE) --out $(OUT) --provider $(TTS_PROVIDER)

scenes:  ## Manim 2D + Blender 3D scenes -> $(OUT)/scenes/<sceneId>.mp4 (preview 854x480@30; uses $(OUT)/timing.json if present)
	$(VENV)/bin/robotics101 render-scenes $(EPISODE) --out $(OUT) --profile $(PROFILE)

scenes-full:  ## same at 1920x1080@30
	$(MAKE) scenes PROFILE=full

demo:
	@echo "make demo arrives in M01.5 (render CLI). Nothing rendered."
	@exit 1

clean:
	rm -rf out .pytest_cache build dist src/*.egg-info
