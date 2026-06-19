# ── Stage 1: build deps ──────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install dependencies into a separate prefix so the final image is lean
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY due_diligence/ ./due_diligence/
COPY frontend/      ./frontend/

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

# Persist memory JSON outside the container via a volume mount
VOLUME ["/app/data"]

# Tell the app where to write its memory file (overrideable at runtime)
ENV MEMORY_PATH=/app/data/due_diligence_memory.json

EXPOSE 8003

CMD ["uvicorn", "due_diligence.main:app", "--host", "0.0.0.0", "--port", "8003"]
