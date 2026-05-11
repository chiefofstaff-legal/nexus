#!/usr/bin/env bash
PID_FILE="$(cd "$(dirname "$0")" && pwd)/.demo-pids"
if [[ -f "$PID_FILE" ]]; then
  while IFS= read -r pid; do
    kill "$pid" 2>/dev/null && echo "Stopped PID $pid" || true
  done < "$PID_FILE"
  rm -f "$PID_FILE"
  echo "Demo stopped."
else
  echo "No demo PIDs found. Checking ports..."
  lsof -i :3847 -i :8100 2>/dev/null | grep LISTEN || echo "No processes on demo ports."
fi
