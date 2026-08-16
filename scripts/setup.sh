#!/usr/bin/env bash
# Install dependencies into a local virtualenv.
#
# Usage: scripts/setup.sh
#
# Uses uv when it is available (uv.lock is checked in), otherwise falls back to
# venv + pip. Interactive Brokers support is optional and not installed here —
# the core, the paper broker, backtests and the API all work without it.

set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if command -v uv >/dev/null 2>&1; then
    echo "==> Installing with uv"
    # --extra dev brings in pytest and ruff, which scripts/run-tests.sh needs.
    uv sync --extra dev
else
    echo "==> Installing with venv + pip"
    "${PYTHON:-python3}" -m venv .venv
    .venv/bin/pip install --quiet --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

echo
echo "Done. Activate with: source .venv/bin/activate"
echo "For live Interactive Brokers trading also run: .venv/bin/pip install ibapi"
