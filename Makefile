# Tagslut project Makefile
# Uses Poetry for dependency management.

.PHONY: help install update lock test lint format type-check clean check \
	run intake-help index-help decide-help execute-help verify-help report-help auth-help \
	index-register-dry index-check-dry promote-dry promote audit-layout audit-cli-docs \
	backfill-v3-identities backfill-v3-provenance validate-v3-parity lint-policies test-phase3-exec \
	verify-v3 doctor-v3 report-identity-qa plan-merge-beatport-dupes merge-beatport-dupes \
	plan-preferred-asset compute-preferred-asset plan-identity-status compute-identity-status \
	archive-orphans check-promote-invariant run-move-plan check-hardcoded-paths dj-candidates \
	dj-profile-get dj-profile-set dj-export-ready dj-ready dj-export-plan dj-export-run dj-pool-plan dj-pool-run

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

plan-merge-beatport-dupes: ## Plan duplicate beatport identity merges (set V3; optional OUT and LIMIT)
	@test -n "$$V3" || (echo "Usage: make plan-merge-beatport-dupes V3=/path/music_v3.db [OUT=output/merge_plan_beatport_v3.csv] [LIMIT=200]"; exit 1)
	poetry run python scripts/db/merge_identities_by_beatport_v3.py --db "$$V3" $(if $(OUT),--out "$$OUT",) $(if $(LIMIT),--limit "$(LIMIT)",)

merge-beatport-dupes: ## Plan/execute beatport duplicate merges (set V3; EXECUTE=1 required to write)
	@test -n "$$V3" || (echo "Usage: make merge-beatport-dupes V3=/path/music_v3.db [OUT=output/merge_plan_beatport_v3.csv] [LIMIT=200] [EXECUTE=1]"; exit 1)
	poetry run python scripts/db/merge_identities_by_beatport_v3.py --db "$$V3" $(if $(OUT),--out "$$OUT",) $(if $(LIMIT),--limit "$(LIMIT)",) $(if $(EXECUTE),--execute,)

plan-preferred-asset: ## Plan preferred-asset selection (set V3; optional OUT and LIMIT)
	@test -n "$$V3" || (echo "Usage: make plan-preferred-asset V3=/path/music_v3.db [OUT=output/preferred_asset_plan.csv] [LIMIT=200]"; exit 1)
	poetry run python scripts/db/compute_preferred_asset_v3.py --db "$$V3" $(if $(OUT),--out "$$OUT",) $(if $(LIMIT),--limit "$(LIMIT)",)

compute-preferred-asset: ## Plan/execute preferred-asset selection (set V3; EXECUTE=1 to write; optional VERSION)
	@test -n "$$V3" || (echo "Usage: make compute-preferred-asset V3=/path/music_v3.db [OUT=output/preferred_asset_plan.csv] [LIMIT=200] [VERSION=1] [EXECUTE=1]"; exit 1)
	poetry run python scripts/db/compute_preferred_asset_v3.py --db "$$V3" $(if $(OUT),--out "$$OUT",) $(if $(LIMIT),--limit "$(LIMIT)",) --version "$(if $(VERSION),$(VERSION),1)" $(if $(EXECUTE),--execute,)

plan-identity-status: ## Plan identity lifecycle status recompute (set V3; optional OUT and LIMIT)
	@test -n "$$V3" || (echo "Usage: make plan-identity-status V3=/path/music_v3.db [OUT=output/identity_status_plan.csv] [LIMIT=200]"; exit 1)
	poetry run python scripts/db/compute_identity_status_v3.py --db "$$V3" $(if $(OUT),--out "$$OUT",) $(if $(LIMIT),--limit "$(LIMIT)",)

compute-identity-status: ## Plan/execute identity lifecycle status recompute (set V3; EXECUTE=1 to write; optional VERSION)
	@test -n "$$V3" || (echo "Usage: make compute-identity-status V3=/path/music_v3.db [OUT=output/identity_status_plan.csv] [LIMIT=200] [VERSION=1] [EXECUTE=1]"; exit 1)
	poetry run python scripts/db/compute_identity_status_v3.py --db "$$V3" $(if $(OUT),--out "$$OUT",) $(if $(LIMIT),--limit "$(LIMIT)",) --version "$(if $(VERSION),$(VERSION),1)" $(if $(EXECUTE),--execute,)

archive-orphans: ## Archive eligible orphan identities (set V3 and EXECUTE=1; optional THRESHOLD_DAYS/VERSION)
	@test -n "$$V3" || (echo "Usage: make archive-orphans V3=/path/music_v3.db EXECUTE=1 [THRESHOLD_DAYS=90] [VERSION=1] [ARCHIVE_NO_TIMESTAMP_OK=1]"; exit 1)
	@test "$$EXECUTE" = "1" || (echo "Refusing archive-orphans without EXECUTE=1"; exit 1)
	poetry run python scripts/db/compute_identity_status_v3.py --db "$$V3" --execute --archive-orphans --archive-orphans-threshold-days "$(if $(THRESHOLD_DAYS),$(THRESHOLD_DAYS),90)" --version "$(if $(VERSION),$(VERSION),1)" $(if $(OUT),--out "$$OUT",) $(if $(LIMIT),--limit "$(LIMIT)",) $(if $(ARCHIVE_NO_TIMESTAMP_OK),--archive-orphans-no-timestamp-ok,)

check-promote-invariant: ## Check post-promote preferred-asset invariant (set V3 and ROOT; optional MINUTES/LIMIT/STRICT)
	@test -n "$$V3" || (echo "Usage: make check-promote-invariant V3=/path/music_v3.db ROOT=/promoted/root [MINUTES=240] [LIMIT=200] [STRICT=1]"; exit 1)
	@test -n "$$ROOT" || (echo "Usage: make check-promote-invariant V3=/path/music_v3.db ROOT=/promoted/root [MINUTES=240] [LIMIT=200] [STRICT=1]"; exit 1)
	poetry run python scripts/db/check_promotion_preferred_invariant_v3.py --db "$$V3" --root "$$ROOT" --minutes "$(if $(MINUTES),$(MINUTES),240)" --limit "$(if $(LIMIT),$(LIMIT),200)" $(if $(filter 0,$(STRICT)),--no-strict,--strict)

check-hardcoded-paths: ## Fail if tracked files contain hardcoded machine path patterns
	./scripts/check_hardcoded_paths.sh

dj-candidates: ## Export DJ candidate CSV from v3 (set V3 and OUT; optional LIMIT/MIN_BPM/MAX_BPM/MIN_DUR/MAX_DUR)
	@test -n "$$V3" || (echo "Usage: make dj-candidates V3=/path/music_v3.db OUT=output/dj_candidates.csv [LIMIT=200] [MIN_BPM=] [MAX_BPM=] [MIN_DUR=] [MAX_DUR=] [INCLUDE_ORPHANS=0] [REQUIRE_PREFERRED=1] [STRICT=1]"; exit 1)
	@test -n "$$OUT" || (echo "Usage: make dj-candidates V3=/path/music_v3.db OUT=output/dj_candidates.csv [LIMIT=200] [MIN_BPM=] [MAX_BPM=] [MIN_DUR=] [MAX_DUR=] [INCLUDE_ORPHANS=0] [REQUIRE_PREFERRED=1] [STRICT=1]"; exit 1)
	poetry run python scripts/dj/export_candidates_v3.py --db "$$V3" --out "$$OUT" \
		$(if $(LIMIT),--limit "$(LIMIT)",) \
		$(if $(MIN_BPM),--min-bpm "$(MIN_BPM)",) \
		$(if $(MAX_BPM),--max-bpm "$(MAX_BPM)",) \
		$(if $(MIN_DUR),--min-duration "$(MIN_DUR)",) \
		$(if $(MAX_DUR),--max-duration "$(MAX_DUR)",) \
		$(if $(filter 1,$(INCLUDE_ORPHANS)),--include-orphans,) \
		$(if $(filter 0,$(REQUIRE_PREFERRED)),--no-require-preferred,) \
		$(if $(filter 0,$(STRICT)),--no-strict,)

dj-profile-get: ## Get DJ profile for one identity (set V3 and ID)
	@test -n "$$V3" || (echo "Usage: make dj-profile-get V3=/path/music_v3.db ID=123"; exit 1)
	@test -n "$$ID" || (echo "Usage: make dj-profile-get V3=/path/music_v3.db ID=123"; exit 1)
	poetry run python scripts/dj/profile_v3.py get --db "$$V3" --identity "$$ID"

dj-profile-set: ## Set DJ profile fields for one identity (set V3 and ID; optional RATING/ENERGY/ROLE/TAG/NOTES/LAST_PLAYED_AT)
	@test -n "$$V3" || (echo "Usage: make dj-profile-set V3=/path/music_v3.db ID=123 [RATING=] [ENERGY=] [ROLE=] [TAG=] [NOTES=] [LAST_PLAYED_AT=]"; exit 1)
	@test -n "$$ID" || (echo "Usage: make dj-profile-set V3=/path/music_v3.db ID=123 [RATING=] [ENERGY=] [ROLE=] [TAG=] [NOTES=] [LAST_PLAYED_AT=]"; exit 1)
	poetry run python scripts/dj/profile_v3.py set --db "$$V3" --identity "$$ID" \
		$(if $(RATING),--rating "$(RATING)",) \
		$(if $(ENERGY),--energy "$(ENERGY)",) \
		$(if $(ROLE),--set-role "$(ROLE)",) \
		$(if $(ADD_TAG),--add-tag "$(ADD_TAG)",) \
		$(if $(REMOVE_TAG),--remove-tag "$(REMOVE_TAG)",) \
		$(if $(TAG),--add-tag "$(TAG)",) \
		$(if $(NOTES),--notes "$(NOTES)",) \
		$(if $(LAST_PLAYED_AT),--last-played-at "$(LAST_PLAYED_AT)",)

dj-export-ready: ## Export DJ-ready list with profile fields (set V3 and OUT; optional MIN_RATING/ROLE/MIN_ENERGY/ONLY_PROFILED=1)
	@test -n "$$V3" || (echo "Usage: make dj-export-ready V3=/path/music_v3.db OUT=output/dj_ready.csv [MIN_RATING=] [ROLE=] [MIN_ENERGY=] [ONLY_PROFILED=0]"; exit 1)
	@test -n "$$OUT" || (echo "Usage: make dj-export-ready V3=/path/music_v3.db OUT=output/dj_ready.csv [MIN_RATING=] [ROLE=] [MIN_ENERGY=] [ONLY_PROFILED=0]"; exit 1)
	poetry run python scripts/dj/export_ready_v3.py --db "$$V3" --out "$$OUT" \
		$(if $(MIN_RATING),--min-rating "$(MIN_RATING)",) \
		$(if $(ROLE),--set-role "$(ROLE)",) \
		$(if $(MIN_ENERGY),--min-energy "$(MIN_ENERGY)",) \
		$(if $(LIMIT),--limit "$(LIMIT)",) \
		$(if $(filter 1,$(ONLY_PROFILED)),--only-profiled,)

dj-ready: ## Alias of dj-export-ready
	@$(MAKE) dj-export-ready V3="$$V3" OUT="$$OUT" MIN_RATING="$$MIN_RATING" MIN_ENERGY="$$MIN_ENERGY" ROLE="$$ROLE" ONLY_PROFILED="$$ONLY_PROFILED" LIMIT="$$LIMIT"

dj-export-plan: ## Plan DJ export build (set V3 and OUTDIR; optional MANIFEST/MIN_RATING/ROLE/MIN_ENERGY/LIMIT)
	@test -n "$$V3" || (echo "Usage: make dj-export-plan V3=/path/music_v3.db OUTDIR=/tmp/dj_export [MANIFEST=...] [MIN_RATING=] [ROLE=] [MIN_ENERGY=] [LIMIT=]"; exit 1)
	@test -n "$$OUTDIR" || (echo "Usage: make dj-export-plan V3=/path/music_v3.db OUTDIR=/tmp/dj_export [MANIFEST=...] [MIN_RATING=] [ROLE=] [MIN_ENERGY=] [LIMIT=]"; exit 1)
	poetry run python scripts/dj/build_export_v3.py --db "$$V3" --out-dir "$$OUTDIR" \
		$(if $(MANIFEST),--manifest "$$MANIFEST",) \
		$(if $(MIN_RATING),--min-rating "$(MIN_RATING)",) \
		$(if $(ROLE),--set-role "$(ROLE)",) \
		$(if $(MIN_ENERGY),--min-energy "$(MIN_ENERGY)",) \
		$(if $(LIMIT),--limit "$(LIMIT)",)

dj-export-run: ## Execute DJ export build (set V3 OUTDIR EXECUTE=1; optional OVERWRITE/FORMAT/LAYOUT/MANIFEST/MIN_RATING/ROLE/MIN_ENERGY/LIMIT)
	@test -n "$$V3" || (echo "Usage: make dj-export-run V3=/path/music_v3.db OUTDIR=/tmp/dj_export EXECUTE=1 [OVERWRITE=if_same_hash] [FORMAT=copy]"; exit 1)
	@test -n "$$OUTDIR" || (echo "Usage: make dj-export-run V3=/path/music_v3.db OUTDIR=/tmp/dj_export EXECUTE=1 [OVERWRITE=if_same_hash] [FORMAT=copy]"; exit 1)
	@test "$$EXECUTE" = "1" || (echo "Refusing dj-export-run without EXECUTE=1"; exit 1)
	poetry run python scripts/dj/build_export_v3.py --db "$$V3" --out-dir "$$OUTDIR" --execute \
		--overwrite "$(if $(OVERWRITE),$(OVERWRITE),if_same_hash)" \
		--format "$(if $(FORMAT),$(FORMAT),copy)" \
		--layout "$(if $(LAYOUT),$(LAYOUT),by_role)" \
		$(if $(MANIFEST),--manifest "$$MANIFEST",) \
		$(if $(MIN_RATING),--min-rating "$(MIN_RATING)",) \
		$(if $(ROLE),--set-role "$(ROLE)",) \
		$(if $(MIN_ENERGY),--min-energy "$(MIN_ENERGY)",) \
		$(if $(LIMIT),--limit "$(LIMIT)",)

dj-pool-plan: ## Plan DJ pool export build (set V3 and OUTDIR; optional MANIFEST/RECEIPTS/MIN_RATING/MIN_ENERGY/ROLE/ONLY_PROFILED/LIMIT)
	@test -n "$$V3" || (echo "Usage: make dj-pool-plan V3=/path/music_v3.db OUTDIR=/tmp/dj_pool [MANIFEST=...] [RECEIPTS=...]"; exit 1)
	@test -n "$$OUTDIR" || (echo "Usage: make dj-pool-plan V3=/path/music_v3.db OUTDIR=/tmp/dj_pool [MANIFEST=...] [RECEIPTS=...]"; exit 1)
	poetry run python scripts/dj/build_pool_v3.py --db "$$V3" --out-dir "$$OUTDIR" \
		$(if $(MANIFEST),--manifest "$$MANIFEST",) \
		$(if $(RECEIPTS),--receipts "$$RECEIPTS",) \
		$(if $(MIN_RATING),--min-rating "$(MIN_RATING)",) \
		$(if $(MIN_ENERGY),--min-energy "$(MIN_ENERGY)",) \
		$(if $(ROLE),--set-role "$(ROLE)",) \
		$(if $(filter 1,$(ONLY_PROFILED)),--only-profiled,) \
		$(if $(LIMIT),--limit "$(LIMIT)",)

dj-pool-run: ## Execute DJ pool export build (set V3 OUTDIR EXECUTE=1; optional OVERWRITE/FORMAT/LAYOUT/MANIFEST/RECEIPTS/MIN_RATING/ROLE/MIN_ENERGY/LIMIT)
	@test -n "$$V3" || (echo "Usage: make dj-pool-run V3=/path/music_v3.db OUTDIR=/tmp/dj_pool EXECUTE=1"; exit 1)
	@test -n "$$OUTDIR" || (echo "Usage: make dj-pool-run V3=/path/music_v3.db OUTDIR=/tmp/dj_pool EXECUTE=1"; exit 1)
	@test "$$EXECUTE" = "1" || (echo "Refusing dj-pool-run without EXECUTE=1"; exit 1)
	poetry run python scripts/dj/build_pool_v3.py --db "$$V3" --out-dir "$$OUTDIR" --execute \
		--overwrite "$(if $(OVERWRITE),$(OVERWRITE),if_same_hash)" \
		--format "$(if $(FORMAT),$(FORMAT),copy)" \
		--layout "$(if $(LAYOUT),$(LAYOUT),by_role)" \
		$(if $(MANIFEST),--manifest "$$MANIFEST",) \
		$(if $(RECEIPTS),--receipts "$$RECEIPTS",) \
		$(if $(MIN_RATING),--min-rating "$(MIN_RATING)",) \
		$(if $(ROLE),--set-role "$(ROLE)",) \
		$(if $(MIN_ENERGY),--min-energy "$(MIN_ENERGY)",) \
		$(if $(filter 1,$(ONLY_PROFILED)),--only-profiled,) \
		$(if $(LIMIT),--limit "$(LIMIT)",)

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
