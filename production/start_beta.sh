#!/bin/sh
set -eu
cd /app/production
python -m alembic upgrade head
cd /app
exec uvicorn production.server.app:app --host 0.0.0.0 --port 8000
