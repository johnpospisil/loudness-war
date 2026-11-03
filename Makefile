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

ingest-ab: ## (P05/P06) Stream-parse AcousticBrainz low-level dumps -> Parquet
	@echo "TODO P05/P06"

ingest-mb: ## (P07) MusicBrainz JSON dumps -> Parquet
	@echo "TODO P07"

build: ## (P08-P10) Release match, dedupe, genres -> data/processed/tracks.parquet
	@echo "TODO P08-P10"

models: ## (P12-P17) Fit models and write figures
	@echo "TODO P12-P17"

report: ## (P21) Render Quarto article
	@echo "TODO P21"

all: ingest-ab ingest-mb build models report ## Full rebuild

.PHONY: help setup test lint theme ingest-ab ingest-mb build models report all
