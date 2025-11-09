#!/bin/bash
# Live progress viewer for the scan

echo "📊 Quarantine Scan Live Progress Monitor"
echo "========================================="
echo ""
echo "Watching: /tmp/scan_quarantine.log"
echo "CSV output: /tmp/dupes_quarantine.csv"
echo ""
echo "Press Ctrl+C to stop monitoring (scan continues in background)"
echo ""

# Show last 30 lines continuously
last_count=0

while true; do
    clear
    echo "📊 Quarantine Scan Live Progress Monitor"
    echo "========================================="
    echo "Updated: $(date '+%H:%M:%S')"
    echo ""
    
    if [ -f /tmp/scan_quarantine.log ]; then
        count=$(wc -l < /tmp/scan_quarantine.log)
        echo "Log lines: $count (was $last_count)"
        last_count=$count
        
        # Extract progress line if available
        current=$(grep "^\[" /tmp/scan_quarantine.log | tail -1)
        echo "Current: $current"
        
        echo ""
        echo "--- Last 25 log entries ---"
        tail -25 /tmp/scan_quarantine.log
    else
        echo "Waiting for log file..."
    fi
    
    echo ""
    echo "Press Ctrl+C to stop monitoring"
    sleep 3
done
