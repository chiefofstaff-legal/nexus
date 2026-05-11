#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$PROJECT_DIR/frontend"
BACKEND_DIR="$PROJECT_DIR/backend"

DEMO_PORT=3847
BACKEND_PORT=8100
PID_FILE="$PROJECT_DIR/.demo-pids"

GREEN='\033[0;32m'
ORANGE='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[NEXUS]${NC} $1"; }
warn() { echo -e "${ORANGE}[NEXUS]${NC} $1"; }
err()  { echo -e "${RED}[NEXUS]${NC} $1" >&2; }

cleanup() {
  log "Shutting down demo..."
  if [[ -f "$PID_FILE" ]]; then
    while IFS= read -r pid; do
      kill "$pid" 2>/dev/null || true
    done < "$PID_FILE"
    rm -f "$PID_FILE"
  fi
  log "Demo stopped."
}

trap cleanup EXIT INT TERM

# --- Pre-flight ---

if lsof -i ":$DEMO_PORT" -t &>/dev/null; then
  warn "Port $DEMO_PORT in use — stopping existing process..."
  lsof -i ":$DEMO_PORT" -t | xargs kill 2>/dev/null || true
  sleep 2
fi

if [[ ! -f "$FRONTEND_DIR/.env.local" ]]; then
  err "Missing $FRONTEND_DIR/.env.local"
  exit 1
fi

# --- Backend ---

if ! lsof -i ":$BACKEND_PORT" -t &>/dev/null; then
  log "Starting FastAPI backend on port $BACKEND_PORT..."
  cd "$BACKEND_DIR"
  source venv/bin/activate 2>/dev/null || true
  # Demo-safe defaults:
  #   Vision OCR -> Claude Haiku Vision only (2.8 s/page, no memory pressure).
  #   Qwen2.5-VL 7B is the on-prem path but concurrent load with any other
  #   warm Ollama model blows 16 GB unified memory on the demo laptop (H4
  #   finding, Gen 499 W4 sprint). Operators with a dedicated box can
  #   export NEXUS_VISION_OCR_ENABLED=true before invoking start-demo.sh.
  : "${NEXUS_VISION_OCR_ENABLED:=false}"
  export NEXUS_VISION_OCR_ENABLED
  uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" &
  echo $! >> "$PID_FILE"
  cd "$PROJECT_DIR"

  for i in $(seq 1 10); do
    if curl -sf "http://localhost:$BACKEND_PORT/health" >/dev/null 2>&1; then
      log "Backend ready."
      break
    fi
    sleep 1
  done
else
  log "Backend already running on port $BACKEND_PORT."
fi

# --- Frontend ---

log "Building Next.js frontend..."
cd "$FRONTEND_DIR"
npm run build 2>&1 | tail -5

log "Starting Next.js on port $DEMO_PORT..."
npx next start --port "$DEMO_PORT" &
echo $! >> "$PID_FILE"
cd "$PROJECT_DIR"

for i in $(seq 1 15); do
  if curl -sf "http://localhost:$DEMO_PORT/login" >/dev/null 2>&1; then
    log "Frontend ready."
    break
  fi
  sleep 1
done

# --- Prevent sleep ---
caffeinate -dims &
echo $! >> "$PID_FILE"

echo ""
log "============================================"
log "  NEXUS demo live at https://try.grip-web.com"
log "  Backend:  http://localhost:$BACKEND_PORT"
log "  Frontend: http://localhost:$DEMO_PORT"
log "  Press Ctrl+C to stop"
log "============================================"
echo ""

wait
