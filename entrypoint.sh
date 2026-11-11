#!/bin/sh
set -e

# The app migrates its own database at startup (web/core/metadata/schema.py).
echo "Starting server..."
exec python -m uvicorn web.api:app --host 0.0.0.0 --port 5000
