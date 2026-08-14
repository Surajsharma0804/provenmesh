FROM python:3.13-slim AS base

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

# Install Python dependencies first (better Docker layer caching)
COPY pyproject.toml ./
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
     "--crawl-workers", "2", \
     "--extract-workers", "1", \
     "--resolve-workers", "1", \
     "--auto-export", \
     "--export-interval", "20"]


# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies for Playwright and lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install -e . && \
    playwright install chromium && \
    playwright install-deps chromium

# Copy application code
COPY src/ src/
COPY configs/ configs/
COPY schemas/ schemas/
COPY migrations/ migrations/
COPY alembic.ini ./

# Non-root user for security
RUN useradd --create-home --shell /bin/bash worker
USER worker

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

ENTRYPOINT ["python", "-m"]
