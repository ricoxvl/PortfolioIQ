#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/backend"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
. .venv/bin/activate
python -m pip install -r requirements.txt
echo "Open http://127.0.0.1:8000 in a browser. Press Ctrl+C to stop."
python -m uvicorn main:app --reload
