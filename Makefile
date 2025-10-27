# FLAC Deduplication Project Makefile
# Uses Poetry for dependency management

.PHONY: help install update lock test lint format clean run scan repair dedupe workflow status

help: ## Show this help message
	@echo "FLAC Deduplication Project"
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

install: ## Install project dependencies with Poetry
	poetry install

update: ## Update dependencies
	poetry update

lock: ## Update poetry.lock file
	poetry lock

test: ## Run tests
	poetry run pytest

lint: ## Run linting (flake8)
	poetry run flake8 *.py

format: ## Format code with Black
	poetry run black *.py

type-check: ## Run mypy type checking
	poetry run mypy *.py

clean: ## Clean Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

# CLI Commands
run: ## Run the main CLI
	poetry run dedupe --help

scan: ## Run scan command
	poetry run dedupe scan --verbose

repair: ## Run repair command
	poetry run dedupe repair

dedupe: ## Run deduplication (dry run)
	poetry run dedupe dedupe

dedupe-commit: ## Run deduplication (actually move files)
	poetry run dedupe dedupe --commit

workflow: ## Run complete workflow
	poetry run dedupe workflow

status: ## Show current status
	poetry run dedupe status

# Development
shell: ## Start Poetry shell
	poetry shell

check: lint type-check test ## Run all checks (lint, type-check, test)

# ScaReD Commands (short aliases)
sc: ## Scan with ScaReD
	./scrd sc --verbose

r: ## Repair with ScaReD
	./scrd r

dd: ## Dedupe with ScaReD
	./scrd d

wf: ## Workflow with ScaReD
	./scrd wf

st: ## Status with ScaReD
	./scrd st

cl: ## Clean with ScaReD
	./scrd cl