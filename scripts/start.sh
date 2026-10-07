#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .tools/plantuml.jar ] || { echo 'Run ./scripts/setup.sh first.'; exit 1; }
[ -d frontend/dist ] || { echo 'Build the frontend first: npm run build --prefix frontend'; exit 1; }
exec .venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port "${PORT:-8018}"
