#!/bin/zsh
# Check critical folder status
echo "FOLDER STATUS CHECK"
echo "==================="

if [ -d "/Volumes/dotad/Garbage" ]; then
    SIZE=$(du -sh "/Volumes/dotad/Garbage" 2>/dev/null | awk '{print $1}')
    COUNT=$(find "/Volumes/dotad/Garbage" -type f 2>/dev/null | wc -l)
    echo "✓ Garbage folder STILL EXISTS"
    echo "  Size: $SIZE"
    echo "  Files: $COUNT"
else
    echo "✗ Garbage folder DELETED"
fi

if [ -d "/Volumes/dotad/Quarantine" ]; then
    echo "✓ Quarantine folder STILL EXISTS"
else
    echo "✗ Quarantine folder DELETED"
fi

if [ -d "/Volumes/dotad/NEW_LIBRARY" ]; then
    COUNT=$(find "/Volumes/dotad/NEW_LIBRARY" -type f 2>/dev/null | wc -l)
    echo "✓ NEW_LIBRARY folder EXISTS with $COUNT files"
else
    echo "✗ NEW_LIBRARY folder MISSING"
fi
