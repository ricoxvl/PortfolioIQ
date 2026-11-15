#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
if command -v npm >/dev/null 2>&1; then
  (cd web && npm install --no-audit --no-fund && npm run build) || echo 'React install/build unavailable, using bundled fallback.'
fi
echo 'Open http://127.0.0.1:8000'
python -m uvicorn server.app:app --host 127.0.0.1 --port 8000
