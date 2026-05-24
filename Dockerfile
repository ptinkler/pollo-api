# ── Stage 1: Build the Vue frontend ──────────────────────────────────
FROM node:24-alpine AS frontend-builder

WORKDIR /build
COPY web/frontend/package.json web/frontend/package-lock.json* ./
RUN npm install
COPY web/frontend/ ./
RUN npm run build

# ── Stage 2: Python API runtime ─────────────────────────────────────
FROM python:3.13-slim

# System deps for opencv (cv2)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY img2vid/ ./img2vid/
COPY web/api.py web/auth.py ./web/
COPY alembic/ ./alembic/
COPY alembic.ini entrypoint.sh ./

# Copy built frontend into web/static (where vite outputs it)
COPY --from=frontend-builder /static ./web/static/


# Data directory (db + assets + cache) will be mounted as a volume
ENV POLLO_DATA_DIR=/data

RUN groupadd -r pollo && useradd -r -g pollo pollo && \
    chmod +x entrypoint.sh && \
    chown -R pollo:pollo /app
USER pollo

EXPOSE 5000

ENTRYPOINT ["/app/entrypoint.sh"]
