#!/usr/bin/env sh
set -eu

PYTHON_BIN="/c/Users/NaCl/Desktop/codes/helloAgents/agent_py313/python.exe"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="C:/Users/NaCl/Desktop/codes/helloAgents/agent_py313/python.exe"
fi

echo "[INFO] Using Python: $PYTHON_BIN"
"$PYTHON_BIN" backend/run_cli_session.py "$@"
