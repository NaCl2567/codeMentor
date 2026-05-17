#!/usr/bin/env sh
set -eu

PYTHON_BIN="./venv/Scripts/python.exe"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="C:/Users/NaCl/Desktop/codes/helloAgents/agent_py313/python.exe"
fi

. ./backend/.env

echo "[INFO] Using Python: $PYTHON_BIN"
"$PYTHON_BIN" -m uvicorn backend.api_server:app --host 127.0.0.1 --port 8000 --reload

