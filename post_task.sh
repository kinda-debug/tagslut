#!/bin/bash
# post_task.sh — Fully automated post-work (after you manually commit+push)
# Usage: ./post_task.sh <CURRENT_TASK_NUM> <NEXT_TASK_NUM>
# Example: ./post_task.sh 1.3 1.4

set -e

CURRENT_TASK="$1"
NEXT_TASK="$2"

if [[ -z "$CURRENT_TASK" || -z "$NEXT_TASK" ]]; then
    echo "Usage: $0 <CURRENT_TASK> <NEXT_TASK>"
    echo "Example: $0 1.3 1.4"
    echo ""
    echo "This script runs AFTER you manually:"
    echo "  1. Complete the task in Codex"
    echo "  2. Commit: git add <files> && git commit -m '...'"
    echo "  3. Push: git push origin dev"
    echo ""
    exit 1
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "AUTO-ADVANCE: Task $CURRENT_TASK → Task $NEXT_TASK"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Step 1: Update TASK_PROMPTS.md status
echo ""
echo "1️⃣  UPDATING TASK STATUS..."

TASK_PROMPTS_FILE=".codex/TASK_PROMPTS.md"

# Use Python for safe, reliable status updates
python3 << PYTHON_EOF
import re
from datetime import datetime

task_num = "$CURRENT_TASK"
next_task_num = "$NEXT_TASK"
file_path = "$TASK_PROMPTS_FILE"

with open(file_path, 'r') as f:
    content = f.read()

# Update current task: ⏳ READY → ✅ COMPLETE
pattern = r'(\| ' + re.escape(task_num) + r' \|[^|]+\| )⏳ READY'
content = re.sub(pattern, r'\1✅ COMPLETE', content)

# Update next task: ⏸️ BLOCKED → ⏳ READY
pattern = r'(\| ' + re.escape(next_task_num) + r' \|[^|]+\| )⏸️ BLOCKED'
content = re.sub(pattern, r'\1⏳ READY', content)

# Update Last Updated timestamp
content = re.sub(r'\*\*Last Updated:\*\* .*', f'**Last Updated:** {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}', content)

with open(file_path, 'w') as f:
    f.write(content)

print(f"✅ Updated: Task {task_num} → ✅ COMPLETE")
print(f"✅ Updated: Task {next_task_num} → ⏳ READY")
PYTHON_EOF

# Step 2: Commit and push status update
echo ""
echo "2️⃣  COMMITTING STATUS UPDATE..."
git add "$TASK_PROMPTS_FILE"
git commit -m "docs: Task $CURRENT_TASK complete, Task $NEXT_TASK ready"
git push origin dev
echo "✅ Committed and pushed"

# Step 3: Output next prompt
echo ""
echo "3️⃣  GENERATING NEXT PROMPT..."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ TASK $NEXT_TASK — READY TO GO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 PROMPT:"
echo ""
sed -n "/^## Prompt for Task $NEXT_TASK:/,/^---$/p" "$TASK_PROMPTS_FILE" | sed '1d;$d'
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✅ Copy the prompt above into Codex"
echo ""
echo "When Task $NEXT_TASK is complete, commit and run:"
NEXT_NEXT_TASK=$(echo "$NEXT_TASK" | awk -F. '{print $1"."($2+1)}')
echo "  ./post_task.sh $NEXT_TASK $NEXT_NEXT_TASK"
echo ""
