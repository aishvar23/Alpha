VENV   ?= .venv
PYTHON := $(VENV)/bin/python
EPISODE ?= examples/episode-001.json

.PHONY: install test validate demo clean

install:  ## editable install of robotics101 (+ pytest) into the existing .venv
	uv pip install --python $(PYTHON) -e ".[dev]"

test:
	$(PYTHON) -m pytest

validate:
	$(VENV)/bin/robotics101 validate $(EPISODE)

demo:
	@echo "make demo arrives in M01.5 (render CLI). Nothing rendered."
	@exit 1

clean:
	rm -rf out .pytest_cache build dist src/*.egg-info
