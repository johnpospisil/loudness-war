# Is the Loudness War Over? — pipeline. Each target is idempotent.
.DEFAULT_GOAL := help
PY := uv run python

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n",$$1,$$2}'

setup: ## Create venv and install deps
	uv sync --all-extras

test: ## Run tests
	uv run pytest -q

lint: ## Ruff lint + format check
	uv run ruff check src tests && uv run ruff format --check src tests

theme: ## Render theme preview figure
	$(PY) -m lw.viz.theme

ingest-ab-sample: ## (P05) Parse the local 100k sample dump -> data/interim/ab_lowlevel/sample.parquet
	$(PY) -m lw.build.parse_lowlevel --sample

ingest-ab: ## (P05/P06) Stream-parse all 30 low-level parts from HTTP (~21 h; resumable per part)
	caffeinate -i $(PY) -m lw.build.parse_lowlevel --parts 0-29 --jobs 2

fetch-mb: ## (P02) Stream the MusicBrainz full export; keep 35 tables in data/raw/musicbrainz/
	$(PY) -m lw.ingest.musicbrainz_dump

MUSIC_ROOTS ?= --root "$(HOME)/Music/iTunes/iTunes Media/Music" --root "$(HOME)/Music/Music"

calibrate: ## (P03) R128 conformance, synthetic + own-library measurements, proxy fit, figures
	$(PY) -m lw.measure.pyloudnorm_check conformance
	$(PY) -m lw.measure.pyloudnorm_check synthetic --jobs 5
	caffeinate -i $(PY) -m lw.measure.pyloudnorm_check library $(MUSIC_ROOTS) --n 1200 --jobs 3
	$(PY) -m lw.measure.calibrate
	$(PY) -m lw.viz.p03

ingest-mb: ## (P07) MusicBrainz tables -> Parquet
	@echo "TODO P07"

build: ## (P08-P10) Release match, dedupe, genres -> data/processed/tracks.parquet
	@echo "TODO P08-P10"

models: ## (P12-P17) Fit models and write figures
	@echo "TODO P12-P17"

report: ## (P21) Render Quarto article
	@echo "TODO P21"

all: ingest-ab ingest-mb build models report ## Full rebuild

.PHONY: help setup test lint theme calibrate ingest-ab-sample ingest-ab fetch-mb ingest-mb build models report all
