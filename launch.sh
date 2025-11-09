#!/bin/bash
# Universal launcher script
# Choose which scan to run

set -e

if [ $# -eq 0 ]; then
    echo "📋 Available Launchers"
    echo "===================="
    echo ""
    echo "Usage: bash launch.sh [OPTION]"
    echo ""
    echo "Options:"
    echo "  fast       - Start FAST file-MD5 scan (recommended first)"
    echo "  audio      - Start AUDIO-MD5 scan (slower, high accuracy)"
    echo "  validate   - Start Batch 3 validation (Repaire_dupes)"
    echo "  status     - Check status of running processes"
    echo "  kill-all   - Kill all running scans"
    echo ""
    exit 0
fi

case "$1" in
    fast)
        bash launch_fast_scan.sh
        ;;
    audio)
        bash launch_audio_scan.sh
        ;;
    validate)
        bash launch_validation_batch3.sh
        ;;
    status)
        echo "🔍 Running Processes Status"
        echo "=========================="
        echo ""
        echo "Fast scan:"
        ps -p $(pgrep -f "find_dupes_fast" || echo "none") 2>/dev/null || echo "  Not running"
        
        echo ""
        echo "Audio scan:"
        ps -p $(pgrep -f "find_exact_dupes" || echo "none") 2>/dev/null || echo "  Not running"
        
        echo ""
        echo "Batch 3 validation:"
        ps -p $(pgrep -f "validate_repair.*Repaire_dupes" || echo "none") 2>/dev/null || echo "  Not running"
        
        echo ""
        echo "📊 Output Files:"
        for f in /tmp/dupes_quarantine_fast.csv /tmp/dupes_quarantine_audio.csv /tmp/validate_Repaire_dupes.csv; do
            if [ -f "$f" ]; then
                lines=$(wc -l < "$f")
                echo "  ✓ $f ($lines lines)"
            fi
        done
        ;;
    kill-all)
        echo "🛑 Stopping all scans..."
        pkill -f "find_dupes_fast" || true
        pkill -f "find_exact_dupes" || true
        pkill -f "validate_repair" || true
        echo "✓ All processes stopped"
        ;;
    *)
        echo "Unknown option: $1"
        echo "Use 'bash launch.sh' for help"
        exit 1
        ;;
esac
