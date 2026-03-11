#!/usr/bin/env bash
# Phase 0: Environment Verification for Gig 2026-03-13
# Run this BEFORE creating profile or running plan mode

set -euo pipefail

echo "====================================="
echo "Phase 0: Environment Verification"
echo "====================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

fail_count=0

# Function to check and report
check_path() {
    local var_name="$1"
    local path="$2"
    
    echo -n "Checking $var_name: $path ... "
    if [ -e "$path" ]; then
        echo -e "${GREEN}OK${NC}"
        ls -lhd "$path"
    else
        echo -e "${RED}FAILED${NC}"
        echo "  ERROR: Path does not exist or is not accessible"
        ((fail_count++))
    fi
    echo ""
}

check_command() {
    local cmd="$1"
    local test_cmd="$2"
    
    echo -n "Checking command: $cmd ... "
    if eval "$test_cmd" &>/dev/null; then
        echo -e "${GREEN}OK${NC}"
        eval "$test_cmd" 2>&1 | head -1
    else
        echo -e "${RED}FAILED${NC}"
        echo "  ERROR: Command not available or errored"
        ((fail_count++))
    fi
    echo ""
}

echo "=== Required Environment Variables ==="
echo ""

if [ -z "${TAGSLUT_DB:-}" ]; then
    echo -e "${RED}ERROR${NC}: TAGSLUT_DB is not set"
    ((fail_count++))
else
    check_path "TAGSLUT_DB" "$TAGSLUT_DB"
fi

if [ -z "${MASTER_LIBRARY:-}" ]; then
    echo -e "${RED}ERROR${NC}: MASTER_LIBRARY is not set"
    ((fail_count++))
else
    check_path "MASTER_LIBRARY" "$MASTER_LIBRARY"
fi

if [ -z "${DJ_LIBRARY:-}" ]; then
    echo -e "${YELLOW}WARNING${NC}: DJ_LIBRARY is not set (may be intentional)"
else
    check_path "DJ_LIBRARY" "$DJ_LIBRARY"
fi

if [ -z "${VOLUME_WORK:-}" ]; then
    echo -e "${RED}ERROR${NC}: VOLUME_WORK is not set"
    ((fail_count++))
else
    check_path "VOLUME_WORK" "$VOLUME_WORK"
    echo "=== Disk Space Check ==="
    df -h "$VOLUME_WORK"
    echo ""
fi

echo "=== CLI Environment ==="
echo ""

check_command "poetry" "poetry --version"
check_command "tagslut CLI" "poetry run tagslut --version"
check_command "pool-wizard help" "poetry run python -m tagslut dj pool-wizard --help"

echo "====================================="
if [ $fail_count -eq 0 ]; then
    echo -e "${GREEN}All checks passed. Environment is ready.${NC}"
    echo "You may proceed to create profile.json and run plan mode."
    exit 0
else
    echo -e "${RED}$fail_count check(s) failed. Fix issues before proceeding.${NC}"
    echo "Do NOT proceed to plan mode with a broken environment."
    exit 1
fi
