#!/usr/bin/env bash
# Check whether the API gateway is up.
#
# Usage: scripts/check-api.sh [BASE_URL]
#   scripts/check-api.sh                       # http://127.0.0.1:8000
#   scripts/check-api.sh http://host:9000
#
# Exits non-zero if the gateway does not answer, so it works in a wait loop.

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"

if curl --silent --fail --max-time 5 "$BASE_URL/health/ready" >/dev/null; then
    echo "API is up at $BASE_URL (docs: $BASE_URL/docs)"
else
    echo "API is not responding at $BASE_URL" >&2
    exit 1
fi
