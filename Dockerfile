# ═══════════════════════════════════════
# The Lore Weaver's Cauldron — Docker
# ═══════════════════════════════════════
FROM python:3.11-slim

WORKDIR /app

# System deps (PyMuPDF behöver libmupdf)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# App code
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY state-schema.json /app/state-schema.json

# Data directory (kampanjer + användare persistas via volym)
RUN mkdir -p /app/backend/data/campaigns

WORKDIR /app/backend

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8090/api/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
