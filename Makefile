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
poetry run flake8 src scripts tests

format: ## Format code with Black
poetry run black src scripts tests

type-check: ## Run mypy type checking
poetry run mypy src

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

check: lint type-check test ## Run all checks (lint, type-check, test)
