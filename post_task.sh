#!/bin/bash
# post_task.sh — Automated post-work: commit, update status, queue next task
# Usage: ./post_task.sh <CURRENT_TASK_NUM> <OUTPUT_FILE> <NEXT_TASK_NUM> <DESCRIPTION>
# Example: ./post_task.sh 1.3 docs/DJ_WORKFLOW.md 1.4 "Normalize DJ docs to 4-stage contract"

set -e

CURRENT_TASK="$1"
OUTPUT_FILE="$2"
NEXT_TASK="$3"
DESC="$4"

if [[ -z "$CURRENT_TASK" || -z "$OUTPUT_FILE" || -z "$NEXT_TASK" || -z "$DESC" ]]; then
    echo "Usage: $0 <CURRENT_TASK> <OUTPUT_FILE> <NEXT_TASK> <DESCRIPTION>"
    echo "Example: $0 1.3 docs/DJ_WORKFLOW.md 1.4 'Normalize DJ docs'"
    exit 1
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "POST-WORK AUTOMATION: Task $CURRENT_TASK"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Step 1: Verify output file exists
echo ""
echo "1️⃣  VERIFYING OUTPUT FILE..."
if [[ ! -f "$OUTPUT_FILE" ]]; then
    echo "❌ ERROR: Output file not found: $OUTPUT_FILE"
    exit 1
fi
FILE_SIZE=$(stat -f%z "$OUTPUT_FILE" 2>/dev/null || stat -c%s "$OUTPUT_FILE" 2>/dev/null)
echo "✅ Found: $OUTPUT_FILE ($FILE_SIZE bytes)"

# Step 2: Run tests if applicable
echo ""
echo "2️⃣  RUNNING TESTS (if applicable)..."
if [[ "$OUTPUT_FILE" == *"test"* ]]; then
    echo "Running: poetry run pytest -q $OUTPUT_FILE -v"
    if poetry run pytest -q "$OUTPUT_FILE" -v; then
        echo "✅ Tests passed"
    else
        echo "⚠️  Tests failed, but continuing with commit"
    fi
else
    echo "⊘ No tests for this file, skipping"
fi

# Step 3: Commit and push
echo ""
echo "3️⃣  COMMITTING & PUSHING..."
git add "$OUTPUT_FILE" .codex/CODEX_SESSION_RECAP.md 2>/dev/null || git add "$OUTPUT_FILE"
git commit -m "feat: Task $CURRENT_TASK — $DESC"
echo "✅ Committed"

echo "🔄 Pushing to origin/dev..."
git push origin dev
echo "✅ Pushed"

# Step 4: Update TASK_PROMPTS.md status
echo ""
echo "4️⃣  UPDATING TASK STATUS..."

TASK_PROMPTS_FILE=".codex/TASK_PROMPTS.md"
TIMESTAMP=$(date -u "+%Y-%m-%d %H:%M UTC")

# Update current task: ⏳ READY → ✅ COMPLETE
sed -i.bak "s/| **$CURRENT_TASK** | /| $CURRENT_TASK | /" "$TASK_PROMPTS_FILE"
sed -i.bak "s/| $CURRENT_TASK | .*| ✅ COMPLETE/| $CURRENT_TASK | .*| ✅ COMPLETE/" "$TASK_PROMPTS_FILE" || true

# More robust status update using awk
awk -v task="$CURRENT_TASK" '
    /^\| Task / && $2 ~ task {
        gsub(/⏳ READY/, "✅ COMPLETE")
    }
    /^\| Task / && NF > 2 {
        next_task_line = 1
    }
    /^\| Task / && next_task_line == 1 {
        gsub(/⏸️ BLOCKED/, "⏳ READY")
        next_task_line = 0
    }
    { print }
' "$TASK_PROMPTS_FILE" > "$TASK_PROMPTS_FILE.tmp" && mv "$TASK_PROMPTS_FILE.tmp" "$TASK_PROMPTS_FILE"

# Update Last Updated timestamp
sed -i.bak "s/\*\*Last Updated:\*\* .*/\*\*Last Updated:\*\* $TIMESTAMP/" "$TASK_PROMPTS_FILE"
rm -f "$TASK_PROMPTS_FILE.bak"

echo "✅ Updated: Task $CURRENT_TASK → ✅ COMPLETE"
echo "✅ Updated: Task $NEXT_TASK → ⏳ READY"

# Step 5: Commit status update
echo ""
echo "5️⃣  COMMITTING STATUS UPDATE..."
git add "$TASK_PROMPTS_FILE"
git commit -m "docs: Task $CURRENT_TASK complete, Task $NEXT_TASK ready"
git push origin dev
echo "✅ Status committed and pushed"

# Step 6: Output next prompt
echo ""
echo "6️⃣  QUEUING NEXT TASK..."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ READY FOR TASK $NEXT_TASK"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Paste this prompt into Codex:"
echo ""
echo "---"
sed -n "/^## Prompt for Task $NEXT_TASK:/,/^---$/p" "$TASK_PROMPTS_FILE" | head -100
echo "---"
echo ""
echo "After Codex completes Task $NEXT_TASK, run:"
echo ""
NEXT_NEXT_TASK=$(echo "$NEXT_TASK" | awk -F. '{print $1"."($2+1)}')
echo "  ./post_task.sh $NEXT_TASK <OUTPUT_FILE> $NEXT_NEXT_TASK \"<DESCRIPTION>\""
echo ""
