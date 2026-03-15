#!/bin/bash

# Codex Session Automation Script
#
# Automates:
# 1. Pre-session: Load prior recap context
# 2. Mid-session: [Manual] Run Codex task
# 3. Post-session: Capture task output, update recap, auto-commit
#
# Usage:
#   bash codex_session.sh start <task-number>  # Start Task 1.1, etc.
#   bash codex_session.sh end <task-number>    # End task, commit recap
#   bash codex_session.sh recap                # Show current recap
#   bash codex_session.sh prompt <task>        # Generate prompt to paste

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Paths
REPO_ROOT="/Users/georgeskhawam/Projects/tagslut"
RECAP_FILE="$REPO_ROOT/.codex/CODEX_SESSION_RECAP.md"
PROMPTS_FILE="$REPO_ROOT/.codex/CODEX_PROMPTS.md"

# ============================================================================
# FUNCTIONS
# ============================================================================

show_recap() {
    if [[ ! -f "$RECAP_FILE" ]]; then
        echo -e "${RED}Recap file not found: $RECAP_FILE${NC}"
        return 1
    fi
    cat "$RECAP_FILE"
}

generate_prompt() {
    local task=$1
    
    if [[ -z "$task" ]]; then
        echo -e "${RED}Error: Task number required (e.g., 1.1)${NC}"
        return 1
    fi
    
    # Extract prompt from CODEX_PROMPTS.md
    # Assumes prompts are labeled "## PROMPT N:" or similar
    
    if [[ ! -f "$PROMPTS_FILE" ]]; then
        echo -e "${RED}Prompts file not found: $PROMPTS_FILE${NC}"
        return 1
    fi
    
    echo ""
    echo -e "${YELLOW}Generated prompt for Task $task:${NC}"
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo ""
    echo "@AGENT.md @.codex/CODEX_SESSION_RECAP.md"
    echo ""
    echo "Task: $task"
    echo ""
    echo "From prior session recap:"
    echo "[Paste relevant prior session context here]"
    echo ""
    echo "Evidence files:"
    find "$REPO_ROOT/docs/audit" -type f -name "*.md" -mtime -7 2>/dev/null | sed 's|^|  @|' || true
    echo ""
    echo "Ready to proceed. Show me:"
    echo "1. [Task-specific requirements from CODEX_PROMPTS.md]"
    echo "2. Any blocking constraints"
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
}

start_session() {
    local task=$1
    
    if [[ -z "$task" ]]; then
        echo -e "${RED}Error: Task number required (e.g., 1.1)${NC}"
        return 1
    fi
    
    echo -e "${BLUE}Starting Codex session for Task $task${NC}"
    echo ""
    
    # Show recap
    echo -e "${YELLOW}Prior session recap:${NC}"
    echo ""
    show_recap
    echo ""
    
    # Generate prompt to paste
    echo -e "${YELLOW}Prompt to paste into Codex:${NC}"
    echo ""
    generate_prompt "$task"
    echo ""
    
    # Create session file
    SESSION_FILE="$REPO_ROOT/.codex/.session_${task}_$(date +%s).log"
    cat > "$SESSION_FILE" << EOF
Session Started: $(date)
Task: $task
Repo: $REPO_ROOT

Copy and paste this prompt into Codex:

@AGENT.md @.codex/CODEX_SESSION_RECAP.md @docs/audit/TOOLS_GET_DJ_RUNTIME_TRACE_2026-03-15.md

Task $task — Continuing from recap above.

Ready for guidance.

---
EOF
    
    echo -e "${GREEN}✓ Session file: $SESSION_FILE${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "1. Open Codex in VS Code (Cmd+Shift+C)"
    echo "2. Copy prompt above and paste into chat"
    echo "3. Let Codex work"
    echo "4. Run: bash codex_session.sh end $task <output-file>"
}

end_session() {
    local task=$1
    local output_file=$2
    
    if [[ -z "$task" ]]; then
        echo -e "${RED}Error: Task number required${NC}"
        return 1
    fi
    
    if [[ -z "$output_file" ]]; then
        echo -e "${YELLOW}No output file specified. Skipping file capture.${NC}"
    elif [[ ! -f "$output_file" ]]; then
        echo -e "${RED}Output file not found: $output_file${NC}"
        return 1
    fi
    
    echo -e "${BLUE}Ending Codex session for Task $task${NC}"
    echo ""
    
    # Determine task name and status from prompts
    local task_name=""
    local task_status="✅ Completed"
    
    case "$task" in
        0.1) task_name="Verify CHANGELOG Claims" ;;
        0.2) task_name="Audit CLI Help Text" ;;
        0.3) task_name="Trace DJ Execution Paths" ;;
        1.1) task_name="Write P0 Contract Tests" ;;
        1.2) task_name="Write P1 E2E Tests" ;;
        1.3) task_name="Normalize Docs Around Single Contract" ;;
        1.4) task_name="Update CLI Help & Error Messages" ;;
        2.1) task_name="Deprecate or Rewire tools/get --dj" ;;
        2.2) task_name="Enforce Import Layering" ;;
        2.3) task_name="Harden Invariants via Tests" ;;
        2.4) task_name="Schema Migration Safeguards" ;;
        *) task_name="Unknown Task" ;;
    esac
    
    # Update recap
    echo -e "${YELLOW}Updating recap file...${NC}"
    
    cat >> "$RECAP_FILE" << EOF

### Session — Task $task ($task_name)
- Date: $(date +%Y-%m-%d\ %H:%M:%S)
- Task: $task — $task_name
- Status: $task_status
EOF
    
    if [[ -n "$output_file" && -f "$output_file" ]]; then
        local file_size=$(wc -c < "$output_file" 2>/dev/null || echo "0")
        echo "- Output: $output_file ($file_size bytes)" >> "$RECAP_FILE"
    fi
    
    cat >> "$RECAP_FILE" << EOF
- Evidence: [Review logs/diffs below]

EOF
    
    echo -e "${GREEN}✓ Recap updated${NC}"
    echo ""
    
    # Show git status
    echo -e "${YELLOW}Git status:${NC}"
    cd "$REPO_ROOT"
    git status --short
    echo ""
    
    # Prompt for auto-commit
    echo -e "${YELLOW}Auto-commit changes? (y/n)${NC}"
    read -r response
    
    if [[ "$response" == "y" || "$response" == "Y" ]]; then
        # Generate commit message
        local commit_msg="docs(codex): task $task — $task_name"
        
        echo -e "${BLUE}Committing with message: $commit_msg${NC}"
        
        git add .codex/CODEX_SESSION_RECAP.md
        
        if [[ -n "$output_file" && -f "$output_file" ]]; then
            git add "$output_file"
        fi
        
        git commit -m "$commit_msg" || echo -e "${YELLOW}Commit skipped (no changes staged)${NC}"
        
        echo -e "${GREEN}✓ Committed${NC}"
    else
        echo -e "${YELLOW}Skipped auto-commit. Commit manually when ready.${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}Session $task complete${NC}"
}

list_tasks() {
    echo -e "${BLUE}Available Tasks (Phase 0 & 1):${NC}"
    echo ""
    echo "Phase 0 (Verification):"
    echo "  0.1  Verify CHANGELOG Claims"
    echo "  0.2  Audit CLI Help Text"
    echo "  0.3  Trace DJ Execution Paths"
    echo ""
    echo "Phase 1 (Closure):"
    echo "  1.1  Write P0 Contract Tests"
    echo "  1.2  Write P1 E2E Tests"
    echo "  1.3  Normalize Docs Around Single Contract"
    echo "  1.4  Update CLI Help & Error Messages"
    echo ""
    echo "Phase 2 (Enforcement):"
    echo "  2.1  Deprecate or Rewire tools/get --dj"
    echo "  2.2  Enforce Import Layering"
    echo "  2.3  Harden Invariants via Tests"
    echo "  2.4  Schema Migration Safeguards"
    echo ""
}

show_help() {
    cat << EOF
${GREEN}Codex Session Automation${NC}

${BLUE}Usage:${NC}
  bash codex_session.sh <command> [options]

${BLUE}Commands:${NC}

  start <task>        Start Codex session for task (e.g., 1.1)
                      - Shows recap
                      - Generates prompt to paste into Codex
                      - Creates session log file

  end <task>          End Codex session and update recap
  <output-file>       - Updates CODEX_SESSION_RECAP.md
                      - Stages files for commit
                      - Prompts for auto-commit

  recap               Show current session recap

  prompt <task>       Generate prompt for task to paste into Codex
                      - No session file created
                      - Useful for re-running same task

  list                List available tasks

  help                Show this help message

${BLUE}Examples:${NC}

  # Start Task 1.1 (P0 tests)
  bash codex_session.sh start 1.1

  # Codex runs... let it work ...

  # End task, update recap, commit
  bash codex_session.sh end 1.1 tests/exec/test_precheck_dj_contract.py

  # Show current progress
  bash codex_session.sh recap

  # Generate prompt for Task 2.1 (without starting session)
  bash codex_session.sh prompt 2.1

${BLUE}Workflow:${NC}

  1. bash codex_session.sh start 1.1
  2. Open Codex, copy prompt, let it work
  3. bash codex_session.sh end 1.1 <output-file>
  4. Review changes, confirm commit
  5. bash codex_session.sh start 1.2 (next task)

EOF
}

# ============================================================================
# MAIN
# ============================================================================

if [[ ! -d "$REPO_ROOT" ]]; then
    echo -e "${RED}Error: Repo root not found: $REPO_ROOT${NC}"
    exit 1
fi

cd "$REPO_ROOT"

case "$1" in
    start)
        start_session "$2"
        ;;
    end)
        end_session "$2" "$3"
        ;;
    recap)
        show_recap
        ;;
    prompt)
        generate_prompt "$2"
        ;;
    list)
        list_tasks
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac
