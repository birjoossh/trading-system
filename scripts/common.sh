#!/usr/bin/env bash
# Shared setup for the scripts in this directory. Source it, don't run it.
#
# Everything in this project resolves relative to the repo root: imports use the
# absolute `unified_trading_platform.*` path, and config.yaml is read from the
# working directory. So every script starts from there.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# Prefer the project virtualenv, then $PYTHON, then whatever python3 is on PATH.
if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON="$REPO_ROOT/.venv/bin/python"
else
    PYTHON="${PYTHON:-python3}"
fi
export PYTHON

if ! command -v "$PYTHON" >/dev/null 2>&1 && [ ! -x "$PYTHON" ]; then
    echo "error: python not found (tried '$PYTHON'). Run scripts/setup.sh first." >&2
    exit 1
fi
