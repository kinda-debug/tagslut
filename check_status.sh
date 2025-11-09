#!/bin/bash
# Status checker that writes to file (works around terminal issues)

{
    echo "=== Scan Status Check ==="
    echo "Time: $(date)"
    echo ""
    
    echo "--- Running Processes ---"
    pgrep -af "find_dupes" 2>/dev/null || echo "No find_dupes process"
    pgrep -af "validate_repair" 2>/dev/null || echo "No validate_repair process"
    
    echo ""
    echo "--- Log Files ---"
    for log in /tmp/scan*.log /tmp/validate*.log; do
        if [ -f "$log" ]; then
            echo "$log:"
            echo "  Size: $(du -h "$log" | cut -f1)"
            echo "  Lines: $(wc -l < "$log")"
            echo "  Last entry:"
            tail -1 "$log" | sed 's/^/    /'
        fi
    done
    
    echo ""
    echo "--- CSV Results ---"
    for csv in /tmp/dupes*.csv /tmp/validate*.csv; do
        if [ -f "$csv" ]; then
            echo "$csv:"
            echo "  Lines: $(wc -l < "$csv")"
            head -2 "$csv" | tail -1 | sed 's/^/    /'
        fi
    done
    
} > /tmp/status_report.txt 2>&1

cat /tmp/status_report.txt
