#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting server..."
exec python -m uvicorn web.api:app --host 0.0.0.0 --port 5000

