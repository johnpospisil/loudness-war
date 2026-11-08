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

ingest-ab-hl: ## (P06) Stream-parse all 30 high-level parts (genre/mood classifiers; ~32 GB)
	caffeinate -i $(PY) -m lw.build.parse_highlevel --parts 0-29 --jobs 2

ingest-ab-tags: ## (P09) Re-stream the 30 low-level parts for gain/provenance tags only (~21 h; resumable)
	caffeinate -i $(PY) -m lw.build.parse_gaintags --parts 0-29 --jobs 2

ab-report: ## (P06) Ingest report: rows, failures, null rates, figures
	$(PY) -m lw.viz.p06

fetch-mb: ## (P02) Stream the MusicBrainz full export; keep 35 tables in data/raw/musicbrainz/
	$(PY) -m lw.ingest.musicbrainz_dump

MUSIC_ROOTS ?= --root "$(HOME)/Music/iTunes/iTunes Media/Music" --root "$(HOME)/Music/Music"

calibrate: ## (P03) R128 conformance, synthetic + own-library measurements, proxy fit, figures
	$(PY) -m lw.measure.pyloudnorm_check conformance
	$(PY) -m lw.measure.pyloudnorm_check synthetic --jobs 5
	caffeinate -i $(PY) -m lw.measure.pyloudnorm_check library $(MUSIC_ROOTS) --n 1200 --jobs 3
	$(PY) -m lw.measure.calibrate
	$(PY) -m lw.viz.p03

timeline: ## (P04) Normalisation timeline figure from data/reference/normalisation_timeline.csv
	$(PY) -m lw.viz.p04

ingest-mb: ## (P07) MusicBrainz tables -> data/interim/mb/*.parquet (~1 min)
	$(PY) -m lw.build.mb_tables

match: ## (P08) Match AB submissions to MB releases, reissue flags -> data/interim/ab_matched.parquet
	$(PY) -m lw.build.release_match
	$(PY) -m lw.viz.p08

dedupe: ## (P09) Exclusions + median per (recording, release) -> data/processed/tracks.parquet
	$(PY) -m lw.build.dedupe
	$(PY) -m lw.viz.p09

genres: ## (P10) Genre per unit (adds columns to tracks.parquet; rerun after dedupe) + MB mix
	$(PY) -m lw.build.genres
	$(PY) -m lw.viz.p10

eda: ## (P11) Profile + album spot-check -> data/processed/p11_*.{json,csv}, figures
	$(PY) -m lw.eda
	$(PY) -m lw.viz.p11

build: match dedupe genres ## (P08-P10) Release match, dedupe, genres -> data/processed/tracks.parquet

models: ## (P12-P17) Fit models and write figures
	$(PY) -m lw.models.yearly
	$(PY) -m lw.viz.p12
	$(PY) -m lw.models.its
	$(PY) -m lw.viz.p13
	$(PY) -m lw.models.quantile_trends
	$(PY) -m lw.viz.p14
	$(PY) -m lw.models.genre_hier
	$(PY) -m lw.viz.p15
	$(PY) -m lw.models.remaster_pairs
	$(PY) -m lw.viz.p16

report: ## (P21) Render Quarto article
	@echo "TODO P21"

all: ingest-ab ingest-mb build models report ## Full rebuild

.PHONY: match dedupe genres eda ingest-ab-tags help setup test lint theme calibrate timeline ingest-ab-hl ab-report ingest-ab-sample ingest-ab fetch-mb ingest-mb build models report all
