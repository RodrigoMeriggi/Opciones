#!/usr/bin/env bash
# Arranque local paper: API + frontend
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -e ".[dev]"
fi

pkill -f "uvicorn opciones.api.app" 2>/dev/null || true
pkill -f "next dev --hostname 127.0.0.1" 2>/dev/null || true
sleep 1

.venv/bin/uvicorn opciones.api.app:app --host 127.0.0.1 --port 8000 --reload &
API_PID=$!

cd frontend
npm run dev &
UI_PID=$!

echo "API  http://127.0.0.1:8000/docs  (pid $API_PID)"
echo "UI   http://127.0.0.1:3000/login (pid $UI_PID)"
echo "Login: admin / admin-change-me"
wait
