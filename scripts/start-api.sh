#!/usr/bin/env bash
# Start the FastAPI gateway.
#
# Usage: scripts/start-api.sh [--host HOST] [--port PORT] [--reload]
#
# Defaults to 0.0.0.0:8000. Docs are served at /docs once it is up.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

exec "$PYTHON" unified_trading_platform/examples/run_api.py "$@"
