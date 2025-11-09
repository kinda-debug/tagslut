#!/bin/bash
# Diagnostic script for scan issues

echo "=== Scan Diagnostics ==="
echo "Date: $(date)"
echo ""

echo "1. Check if process is running"
ps aux | grep "find_exact_dupes" | grep -v grep || echo "  No process found"

echo ""
echo "2. Check log file"
if [ -f /tmp/scan_quarantine.log ]; then
    size=$(du -h /tmp/scan_quarantine.log | cut -f1)
    lines=$(wc -l < /tmp/scan_quarantine.log)
    echo "  Log file size: $size"
    echo "  Log lines: $lines"
    echo "  Last 5 lines:"
    tail -5 /tmp/scan_quarantine.log | sed 's/^/    /'
else
    echo "  No log file yet"
fi

echo ""
echo "3. Check CSV output"
if [ -f /tmp/dupes_quarantine.csv ]; then
    size=$(du -h /tmp/dupes_quarantine.csv | cut -f1)
    lines=$(wc -l < /tmp/dupes_quarantine.csv)
    echo "  CSV size: $size"
    echo "  CSV lines: $lines"
else
    echo "  No CSV file yet"
fi

echo ""
echo "4. Check database"
if [ -f ~/.cache/exact_dupes.db ]; then
    size=$(du -h ~/.cache/exact_dupes.db | cut -f1)
    echo "  DB size: $size"
else
    echo "  No database yet"
fi

echo ""
echo "5. Check if FFmpeg is running"
ps aux | grep ffmpeg | grep -v grep || echo "  No ffmpeg process"

echo ""
echo "6. Check for errors in log"
grep -i "error\|timeout\|warn" /tmp/scan_quarantine.log 2>/dev/null | tail -5 || echo "  No errors found"
