#!/usr/bin/env bash
# Run the lint and test suite, the same two checks CI runs.
#
# Usage: scripts/run-tests.sh [pytest args...]
#   scripts/run-tests.sh                                  # everything
#   scripts/run-tests.sh -k backtest                      # matching tests only
#   scripts/run-tests.sh unified_trading_platform/tests/test_pricing_accuracy.py

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

if command -v ruff >/dev/null 2>&1; then
    echo "==> ruff"
    ruff check .
else
    echo "==> ruff not installed, skipping lint"
fi

echo "==> pytest"
exec "$PYTHON" -m pytest "${@:-unified_trading_platform/tests/}"
