# AI Finance Controller — reproducible image for the reconciliation UI + batch job.
FROM python:3.12-slim

# System hygiene: no cache, no pyc, unbuffered logs (so JSON log lines stream out).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first so the layer caches across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY . .

# Generate the deterministic dataset at build time so the image is self-contained
# and verify integrity — the build fails if the ground-truth invariants don't hold.
RUN python src/generate_data.py && python src/selftest_data.py

EXPOSE 8501

# Default: the reconciliation UI. Override for the batch job, e.g.
#   docker run --rm <img> python src/pipeline.py --execute --cycle 2026-07-15
CMD ["streamlit", "run", "app.py", \
     "--server.address", "0.0.0.0", "--server.port", "8501", "--server.headless", "true"]
