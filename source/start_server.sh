#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d ".venv" ]; then
 echo "Creating virtual environment..."
 python3 -m venv .venv
 ./.venv/bin/pip install -r requirements.txt
fi

echo "Starting ReconcileAI on http://localhost:8000..."
./.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
