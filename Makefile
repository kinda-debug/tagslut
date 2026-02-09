# Dedupe project Makefile
# Uses Poetry for dependency management.

.PHONY: help install update lock test lint format type-check clean check \
	run mgmt-help metadata-help recovery-help \
	mgmt-register-dry mgmt-check-dry promote-dry promote audit-layout

help: ## Show this help message
	@echo "Dedupe - available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-22s %s\n", $$1, $$2}'

install: ## Install project dependencies with Poetry
	poetry install

update: ## Update dependencies
	poetry update

lock: ## Refresh poetry.lock
	poetry lock

test: ## Run tests
	poetry run pytest

lint: ## Run linting (flake8)
	poetry run flake8 dedupe tools tests scripts

format: ## Format code with black
	poetry run black dedupe tools tests scripts

type-check: ## Run mypy type checking
	poetry run mypy dedupe

clean: ## Clean Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

check: lint type-check test ## Run lint + type-check + tests

# CLI visibility helpers
run: ## Show top-level CLI help
	poetry run dedupe --help

audit-layout: ## Run repository layout/script-surface audit checks
	poetry run python scripts/audit_repo_layout.py

mgmt-help: ## Show management mode command help
	poetry run dedupe mgmt --help

metadata-help: ## Show metadata command help
	poetry run dedupe metadata --help

recovery-help: ## Show recovery command help (currently stub)
	poetry run dedupe recovery --help

# Safe workflow helpers
mgmt-register-dry: ## Register downloads in dry-run mode (set SRC and SOURCE)
	@test -n "$$SRC" || (echo "Usage: make mgmt-register-dry SRC=/path SOURCE=bpdl"; exit 1)
	@test -n "$$SOURCE" || (echo "Usage: make mgmt-register-dry SRC=/path SOURCE=bpdl"; exit 1)
	poetry run dedupe mgmt register "$$SRC" --source "$$SOURCE"

mgmt-check-dry: ## Pre-check duplicates in dry-run mode (set SRC and optional SOURCE)
	@test -n "$$SRC" || (echo "Usage: make mgmt-check-dry SRC=/path [SOURCE=bpdl]"; exit 1)
	poetry run dedupe mgmt check "$$SRC" $(if $(SOURCE),--source "$(SOURCE)",)

promote-dry: ## Dry-run promote using active script (set KEEP_DIR LIBRARY_ROOT DB_PATH)
	@test -n "$$KEEP_DIR" || (echo "Usage: make promote-dry KEEP_DIR=/staging LIBRARY_ROOT=/library DB_PATH=/path/db.sqlite"; exit 1)
	@test -n "$$LIBRARY_ROOT" || (echo "Usage: make promote-dry KEEP_DIR=/staging LIBRARY_ROOT=/library DB_PATH=/path/db.sqlite"; exit 1)
	@test -n "$$DB_PATH" || (echo "Usage: make promote-dry KEEP_DIR=/staging LIBRARY_ROOT=/library DB_PATH=/path/db.sqlite"; exit 1)
	poetry run python tools/review/promote_by_tags.py \
		--source-root "$$KEEP_DIR" \
		--dest-root "$$LIBRARY_ROOT" \
		--db "$$DB_PATH" \
		--mode move \
		--progress-only

promote: ## Execute promote using active script (set KEEP_DIR LIBRARY_ROOT DB_PATH)
	@test -n "$$KEEP_DIR" || (echo "Usage: make promote KEEP_DIR=/staging LIBRARY_ROOT=/library DB_PATH=/path/db.sqlite"; exit 1)
	@test -n "$$LIBRARY_ROOT" || (echo "Usage: make promote KEEP_DIR=/staging LIBRARY_ROOT=/library DB_PATH=/path/db.sqlite"; exit 1)
	@test -n "$$DB_PATH" || (echo "Usage: make promote KEEP_DIR=/staging LIBRARY_ROOT=/library DB_PATH=/path/db.sqlite"; exit 1)
	@read -p "This will move files from $$KEEP_DIR to $$LIBRARY_ROOT. Continue? [y/N] " confirm && [ "$$confirm" = "y" ]
	poetry run python tools/review/promote_by_tags.py \
		--source-root "$$KEEP_DIR" \
		--dest-root "$$LIBRARY_ROOT" \
		--db "$$DB_PATH" \
		--mode move \
		--execute \
		--progress-only
