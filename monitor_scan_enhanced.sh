#!/bin/bash
# Enhanced progress monitor with better statistics

echo "🎵 Quarantine Audio Deduplication Scan"
echo "======================================"
echo ""

while true; do
    if [ ! -f /tmp/scan_quarantine.log ]; then
        echo "Waiting for scan to start..."
        sleep 2
        continue
    fi
    
    # Get statistics
    total_lines=$(wc -l < /tmp/scan_quarantine.log 2>/dev/null || echo 0)
    current_file=$(grep "^\[" /tmp/scan_quarantine.log 2>/dev/null | tail -1 | grep -oE "\[[0-9]+/[0-9]+\]" || echo "")
    
    # Extract numbers from progress
    if [[ $current_file =~ \[([0-9]+)/([0-9]+)\] ]]; then
        current="${BASH_REMATCH[1]}"
        total="${BASH_REMATCH[2]}"
        percent=$((current * 100 / total))
        remaining=$((total - current))
        
        clear
        echo "🎵 Quarantine Audio Deduplication Scan"
        echo "======================================"
        echo ""
        echo "Status: RUNNING (process is actively hashing files)"
        echo ""
        echo "Progress: $current / $total files hashed ($percent%)"
        echo ""
        
        # Simple progress bar
        bar_width=50
        filled=$((current * bar_width / total))
        empty=$((bar_width - filled))
        bar=$(printf "█%.0s" $(seq 1 $filled))$(printf "░%.0s" $(seq 1 $empty))
        echo "[$bar]"
        echo ""
        
        echo "Files remaining: $remaining"
        echo ""
        
        # Show current file
        current_filename=$(grep "^\[" /tmp/scan_quarantine.log 2>/dev/null | tail -1)
        echo "Current: ${current_filename#*] }"
        echo ""
        
        echo "--- Latest Activity (last 10 lines) ---"
        tail -10 /tmp/scan_quarantine.log | sed 's/^/  /'
    else
        echo "Initializing scan..."
        tail -5 /tmp/scan_quarantine.log | sed 's/^/  /'
    fi
    
    echo ""
    echo "Database: ~/.cache/exact_dupes.db"
    echo "Log: /tmp/scan_quarantine.log"
    echo "CSV output: /tmp/dupes_quarantine.csv"
    echo ""
    echo "Press Ctrl+C to exit monitor (scan continues in background)"
    
    sleep 3
done
