VENV   ?= .venv
PYTHON := $(VENV)/bin/python
EPISODE ?= examples/episode-001.json
OUT     ?= out/episode-001
TTS_PROVIDER ?= espeak
PROFILE ?= preview

.PHONY: install test test-e2e validate narrate scenes scenes-full render qa demo demo-full clean

install:  ## editable install of robotics101 (+ pytest) into the existing .venv
	uv pip install --python $(PYTHON) -e ".[dev]"

test:  ## unit + integration tests (~25 s; real Manim/Blender/ffmpeg smoke renders auto-skip if missing)
	$(PYTHON) -m pytest

test-e2e:  ## also run the full sample-episode render test (~100 s on 8 CPUs)
	ROBOTICS101_E2E=1 $(PYTHON) -m pytest tests/test_render_e2e.py

validate:
	$(VENV)/bin/robotics101 validate $(EPISODE)

narrate:  ## per-scene TTS (espeak|fixture) -> $(OUT)/audio/*.wav, timing.json, captions.srt
	$(VENV)/bin/robotics101 narrate $(EPISODE) --out $(OUT) --provider $(TTS_PROVIDER)

scenes:  ## Manim 2D + Blender 3D scenes -> $(OUT)/scenes/<sceneId>.mp4 (preview 854x480@30; uses $(OUT)/timing.json if present)
	$(VENV)/bin/robotics101 render-scenes $(EPISODE) --out $(OUT) --profile $(PROFILE)

scenes-full:  ## same at 1920x1080@30
	$(MAKE) scenes PROFILE=full

render:  ## validate -> narrate -> render-scenes -> compose -> manifest -> QA into $(OUT)
	$(VENV)/bin/robotics101 render $(EPISODE) --out $(OUT) --profile $(PROFILE) --tts $(TTS_PROVIDER)

qa:  ## re-run QA on an existing bundle (rewrites qa_report.*, re-seals manifest.json)
	$(VENV)/bin/robotics101 qa $(OUT)

demo:  ## full pipeline, preview 854x480 (~1.5-2 min on 8 CPUs) -> $(OUT)/final.mp4 + captions, QA, manifest
	$(MAKE) render PROFILE=preview

demo-full:  ## full pipeline at 1920x1080@30 (~8-10 min on 8 CPUs; Blender scene dominates)
	$(MAKE) render PROFILE=full

clean:
	rm -rf out .pytest_cache build dist src/*.egg-info
