#!/usr/bin/env bash
# Run from anywhere. Creates ~/Desktop/tagslut_context_bundle/
set -euo pipefail

REPO=/Users/georgeskhawam/Projects/tagslut
BUNDLE=~/Desktop/tagslut_context_bundle
ZIP_OUT=/Users/georgeskhawam/Library/CloudStorage/Dropbox/tagslut_context_bundle.zip

mkdir -p "$BUNDLE"

copy() {
  local src="$1"
  if [[ -f "$src" ]]; then
    cp "$src" "$BUNDLE/$(basename "$src")"
    echo "  ✓ $(basename "$src")"
  else
    echo "  ✗ MISSING: $src"
  fi
}

echo "=== Agent instructions ==="
copy "$REPO/AGENT.md"
copy "$REPO/CLAUDE.md"

echo "=== Project directives ==="
copy "$REPO/docs/PROJECT_DIRECTIVES.md"

echo "=== Core docs ==="
copy "$REPO/docs/ROADMAP.md"
copy "$REPO/docs/CORE_MODEL.md"
copy "$REPO/docs/DB_V3_SCHEMA.md"
copy "$REPO/docs/ARCHITECTURE.md"
copy "$REPO/docs/PHASE1_STATUS.md"
copy "$REPO/docs/PROGRESS_REPORT.md"
copy "$REPO/docs/INGESTION_PROVENANCE.md"
copy "$REPO/docs/DJ_WORKFLOW.md"
copy "$REPO/docs/OPERATIONS.md"
copy "$REPO/docs/WORKFLOWS.md"

echo "=== Agent prompts ==="
copy "$REPO/.github/prompts/resume-refresh-fix.prompt.md"
copy "$REPO/.github/prompts/repo-cleanup.prompt.md"
copy "$REPO/.github/prompts/dj-pipeline-hardening.prompt.md"
copy "$REPO/.github/prompts/dj-workflow-audit.prompt.md"
copy "$REPO/.github/prompts/open-streams-post-0010.prompt.md"
copy "$REPO/.github/copilot-instructions.md"

echo "=== Project config ==="
copy "$REPO/pyproject.toml"
copy "$REPO/CHANGELOG.md"

echo "=== Storage / schema layer ==="
copy "$REPO/tagslut/storage/v3/schema.py"
copy "$REPO/tagslut/storage/v3/identity_service.py"
copy "$REPO/tagslut/storage/v3/identity_status.py"
copy "$REPO/tagslut/storage/v3/db.py"
copy "$REPO/tagslut/storage/v3/migration_runner.py"
copy "$REPO/tagslut/storage/v3/migrations/0010_track_identity_provider_uniqueness.py"
copy "$REPO/tagslut/storage/v3/migrations/0011_track_identity_provider_uniqueness_hardening.py"

echo "=== Exec / intake layer ==="
copy "$REPO/tagslut/exec/intake_orchestrator.py"
copy "$REPO/tagslut/exec/get_intake_console.py"
copy "$REPO/tagslut/exec/intake_pretty_summary.py"
copy "$REPO/tagslut/exec/mp3_build.py"
copy "$REPO/tagslut/exec/precheck_inventory_dj.py"
copy "$REPO/tagslut/exec/canonical_writeback.py"

echo "=== Pipeline scripts ==="
copy "$REPO/tools/get-intake"
copy "$REPO/tools/get"

echo "=== DJ layer ==="
copy "$REPO/tagslut/exec/dj_pool_wizard.py"
copy "$REPO/tagslut/exec/dj_manifest_receipts.py"
copy "$REPO/scripts/dj/build_pool_v3.py"

echo "=== Tests ==="
copy "$REPO/tests/conftest.py"
for f in "$REPO/tests/exec/"*.py; do
  [[ -f "$f" ]] && copy "$f"
done

echo ""
echo "Bundle: $BUNDLE"
echo "Files:  $(ls "$BUNDLE" | wc -l | tr -d ' ')"
echo "Size:   $(du -sh "$BUNDLE" | cut -f1)"
echo ""
rm -f "$ZIP_OUT"
cd "$(dirname "$BUNDLE")"
zip -r "$ZIP_OUT" "$(basename "$BUNDLE")"
echo "Zip:    $ZIP_OUT ($(du -sh "$ZIP_OUT" | cut -f1))"
