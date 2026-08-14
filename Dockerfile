FROM python:3.13-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy files needed by pip/hatchling BEFORE installing
# (pyproject.toml declares readme = "README.md" so both must be present)
COPY pyproject.toml ./
COPY README.md ./

# Install Python package
RUN pip install -e .

# Copy application code
COPY src/ src/
COPY configs/ configs/
COPY schemas/ schemas/
COPY scripts/ scripts/
COPY migrations/ migrations/
COPY alembic.ini ./

# Non-root user for security
RUN useradd --create-home --shell /bin/bash worker && \
    chown -R worker:worker /app
USER worker

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default: run the full pipeline with auto-export
CMD ["python", "-m", "provenmesh.main", "run", \
     "--crawl-workers", "3", \
     "--extract-workers", "2", \
     "--resolve-workers", "2", \
     "--auto-export", \
     "--export-interval", "20"]
