# Tagslut project Makefile
# Uses Poetry for dependency management.

.PHONY: help install update lock test lint format type-check clean check \
	run intake-help index-help decide-help execute-help verify-help report-help auth-help \
	index-register-dry index-check-dry promote-dry promote audit-layout audit-cli-docs \
	backfill-v3-identities backfill-v3-provenance validate-v3-parity lint-policies test-phase3-exec \
	verify-v3 doctor-v3 report-identity-qa run-move-plan

help: ## Show this help message
	@echo "Tagslut - available targets:"
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
	poetry run flake8 tagslut tools tests scripts

format: ## Format code with black
	poetry run black tagslut tools tests scripts

type-check: ## Run mypy type checking
	poetry run mypy tagslut

clean: ## Clean Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

check: lint type-check test ## Run lint + type-check + tests

# CLI visibility helpers
run: ## Show top-level CLI help
	poetry run python -m tagslut --help

audit-layout: ## Run repository layout/script-surface audit checks
	poetry run python scripts/audit_repo_layout.py

audit-cli-docs: ## Run CLI/docs consistency checks
	poetry run python scripts/check_cli_docs_consistency.py

backfill-v3-identities: ## Backfill v3 asset/identity/link rows (set DB and optional EXECUTE=1)
	@test -n "$$DB" || (echo "Usage: make backfill-v3-identities DB=/path/to/db.sqlite [EXECUTE=1]"; exit 1)
	poetry run python scripts/backfill_v3_identity_links.py --db "$$DB" $(if $(EXECUTE),--execute,)

backfill-v3-provenance: ## Backfill v3 provenance/move rows from logs (set DB, optional LOGS, optional EXECUTE=1)
	@test -n "$$DB" || (echo "Usage: make backfill-v3-provenance DB=/path/to/db.sqlite [LOGS=artifacts] [EXECUTE=1]"; exit 1)
	poetry run python scripts/backfill_v3_provenance_from_logs.py --db "$$DB" $(if $(LOGS),--logs "$(LOGS)",) $(if $(EXECUTE),--execute,)

validate-v3-parity: ## Validate legacy<->v3 dual-write parity (set DB and optional STRICT=1)
	@test -n "$$DB" || (echo "Usage: make validate-v3-parity DB=/path/to/db.sqlite [STRICT=1]"; exit 1)
	poetry run python scripts/validate_v3_dual_write_parity.py --db "$$DB" $(if $(STRICT),--strict,)

verify-v3: ## Verify v2->v3 migration preservation (set V2 and V3; optional STRICT=1)
	@test -n "$$V2" || (echo "Usage: make verify-v3 V2=/path/music_v2.db V3=/path/music_v3.db [STRICT=1]"; exit 1)
	@test -n "$$V3" || (echo "Usage: make verify-v3 V2=/path/music_v2.db V3=/path/music_v3.db [STRICT=1]"; exit 1)
	poetry run python scripts/db/verify_v3_migration.py --v2 "$$V2" --v3 "$$V3" $(if $(STRICT),--strict,)

doctor-v3: ## Run read-only v3 doctor checks (set V3)
	@test -n "$$V3" || (echo "Usage: make doctor-v3 V3=/path/music_v3.db"; exit 1)
	poetry run python scripts/db/doctor_v3.py --v3 "$$V3"

report-identity-qa: ## Generate identity QA summary/CSV for v3 (set V3; optional OUT and LIMIT)
	@test -n "$$V3" || (echo "Usage: make report-identity-qa V3=/path/music_v3.db [OUT=output/identity_qa.csv] [LIMIT=200]"; exit 1)
	poetry run python scripts/db/report_identity_qa_v3.py --db "$$V3" $(if $(OUT),--out "$$OUT",) $(if $(LIMIT),--limit "$(LIMIT)",)

run-move-plan: ## Safely run move-plan cycle (set PLAN and V3; optional STRICT=1 DRY_RUN=1)
	@test -n "$$PLAN" || (echo "Usage: make run-move-plan PLAN=plans/<file>.csv V3=/path/music_v3.db [STRICT=1] [DRY_RUN=1]"; exit 1)
	@test -n "$$V3" || (echo "Usage: make run-move-plan PLAN=plans/<file>.csv V3=/path/music_v3.db [STRICT=1] [DRY_RUN=1]"; exit 1)
	TAGSLUT_DB="$$V3" poetry run python -m tagslut ops run-move-plan "$$PLAN" $(if $(STRICT),--strict,) $(if $(DRY_RUN),--dry-run,)

lint-policies: ## Lint policy profiles in config/policies
	poetry run python scripts/lint_policy_profiles.py

test-phase3-exec: ## Run Phase 3 executor contract tests
	poetry run pytest -q tests/test_exec_engine_phase3.py tests/test_exec_receipts_phase3.py tests/test_move_from_plan_phase3_contract.py tests/test_quarantine_from_plan_phase3_contract.py

intake-help: ## Show intake command help
	poetry run python -m tagslut intake --help

index-help: ## Show index command help
	poetry run python -m tagslut index --help

decide-help: ## Show decide command help
	poetry run python -m tagslut decide --help

execute-help: ## Show execute command help
	poetry run python -m tagslut execute --help

verify-help: ## Show verify command help
	poetry run python -m tagslut verify --help

report-help: ## Show report command help
	poetry run python -m tagslut report --help

auth-help: ## Show auth command help
	poetry run python -m tagslut auth --help

# Safe workflow helpers
index-register-dry: ## Register downloads in dry-run mode (set SRC and SOURCE)
	@test -n "$$SRC" || (echo "Usage: make index-register-dry SRC=/path SOURCE=bpdl"; exit 1)
	@test -n "$$SOURCE" || (echo "Usage: make index-register-dry SRC=/path SOURCE=bpdl"; exit 1)
	poetry run python -m tagslut index register "$$SRC" --source "$$SOURCE"

index-check-dry: ## Pre-check duplicates in dry-run mode (set SRC and optional SOURCE)
	@test -n "$$SRC" || (echo "Usage: make index-check-dry SRC=/path [SOURCE=bpdl]"; exit 1)
	poetry run python -m tagslut index check "$$SRC" $(if $(SOURCE),--source "$(SOURCE)",)

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
