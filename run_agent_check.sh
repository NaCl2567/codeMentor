#!/usr/bin/env sh
set -eu

# Default Python path for the specified environment.
PYTHON_DEFAULT="/c/Users/NaCl/Desktop/codes/helloAgents/agent_py313/python.exe"

# Fallback for environments where /c/... is not mounted (e.g. WSL path mapping not present).
PYTHON_FALLBACK="C:/Users/NaCl/Desktop/codes/helloAgents/agent_py313/python.exe"

if [ -x "$PYTHON_DEFAULT" ]; then
  PYTHON_BIN="$PYTHON_DEFAULT"
elif [ -x "$PYTHON_FALLBACK" ]; then
  PYTHON_BIN="$PYTHON_FALLBACK"
else
  echo "[ERROR] Python not found in agent_py313 environment."
  echo "Tried:"
  echo "  $PYTHON_DEFAULT"
  echo "  $PYTHON_FALLBACK"
  exit 1
fi

echo "[INFO] Using Python: $PYTHON_BIN"

# Offline smoke check
"$PYTHON_BIN" backend/run_agent_check.py

# Live check (uncomment if you want to test real API call)
# "$PYTHON_BIN" backend/run_agent_check.py --live

