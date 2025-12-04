#!/usr/bin/env bash
set -euo pipefail
while true; do
  echo "Test script running: $(date)" >> test_nohup.log
  sleep 5
done
