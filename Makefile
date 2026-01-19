# FLAC Deduplication Project Makefile
# Uses Poetry for dependency management

.PHONY: help install update lock test lint format clean run sync quarantine-inspect quarantine-inventory quarantine-duration type-check check

help: ## Show this help message
	@echo "FLAC Deduplication Project"
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

install: ## Install project dependencies with Poetry
	poetry install

update: ## Update dependencies
	poetry update

lock: ## Update poetry.lock file
	poetry lock

test: ## Run tests
	poetry run pytest

lint: ## Run linting (flake8)
	poetry run flake8 dedupe tools tests

format: ## Format code
	# Suggest using black if installed
	poetry run black dedupe tools tests || echo "Black not found, skipping format"

type-check: ## Run mypy type checking
	poetry run mypy dedupe

clean: ## Clean Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

# CLI Commands
run: ## Show top-level CLI help
	poetry run dedupe --help

sync: ## Run the sync workflow (dry run)
	poetry run dedupe sync --dry-run

quarantine-inspect: ## Run detailed quarantine analysis
	poetry run dedupe quarantine inspect --help

quarantine-inventory: ## Run lightweight quarantine scan
	poetry run dedupe quarantine inventory --help

quarantine-duration: ## Detect quarantine playback length issues
	poetry run dedupe quarantine duration --help

promote-dry: ## Dry-run promote: show what would be copied/moved to canonical layout
	@echo "Dry-run promote from staging to library..."
	poetry run python tools/review/promote_by_tags.py \
		--source-root "$${KEEP_DIR:-/Volumes/COMMUNE/M/_staging}" \
		--dest-root "$${LIBRARY_ROOT:-/Volumes/COMMUNE/M/Library}" \
		--db "$${DB_PATH:-artifacts/dedupe.db}" \
		--mode move \
		--progress-only

promote: ## Execute promote: copy/move files to canonical layout (requires KEEP_DIR, LIBRARY_ROOT, DB_PATH)
	@echo "Executing promote from staging to library..."
	@read -p "This will move files from $${KEEP_DIR:-/Volumes/COMMUNE/M/_staging} to $${LIBRARY_ROOT:-/Volumes/COMMUNE/M/Library}. Continue? [y/N] " confirm && [ "$$confirm" = "y" ]
	poetry run python tools/review/promote_by_tags.py \
		--source-root "$${KEEP_DIR:-/Volumes/COMMUNE/M/_staging}" \
		--dest-root "$${LIBRARY_ROOT:-/Volumes/COMMUNE/M/Library}" \
		--db "$${DB_PATH:-artifacts/dedupe.db}" \
		--mode move \
		--execute \
		--progress-only

check: lint type-check test ## Run all checks (lint, type-check, test)
