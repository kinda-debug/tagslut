#!/bin/zsh
# Check critical folder status
echo "FOLDER STATUS CHECK"
echo "==================="

if [ -d "/Volumes/COMMUNE/90_REJECTED" ]; then
    SIZE=$(du -sh "/Volumes/COMMUNE/90_REJECTED" 2>/dev/null | awk '{print $1}')
    COUNT=$(find "/Volumes/COMMUNE/90_REJECTED" -type f 2>/dev/null | wc -l)
    echo "✓ Rejected folder STILL EXISTS"
    echo "  Size: $SIZE"
    echo "  Files: $COUNT"
else
    echo "✗ Rejected folder DELETED"
fi

if [ -d "/Volumes/COMMUNE/10_STAGING" ]; then
    echo "✓ Staging folder STILL EXISTS"
else
    echo "✗ Staging folder DELETED"
fi

if [ -d "/Volumes/COMMUNE/20_ACCEPTED" ]; then
    COUNT=$(find "/Volumes/COMMUNE/20_ACCEPTED" -type f 2>/dev/null | wc -l)
    echo "✓ Accepted folder EXISTS with $COUNT files"
else
    echo "✗ Accepted folder MISSING"
fi
