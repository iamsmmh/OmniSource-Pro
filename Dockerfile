# OmniSource Dockerfile
# Multi-stage build for production and development

# ============================================
# Stage 1: Base image with Python and system dependencies
# ============================================
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create and set working directory
WORKDIR /app

# ============================================
# Stage 2: Build stage for dependencies
# ============================================
FROM base as builder

# Install build dependencies
RUN apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --user -r requirements.txt

# ============================================
# Stage 3: Runtime image
# ============================================
FROM base as runtime

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Set environment variables
ENV APP_ENV=production \
    LOG_LEVEL=INFO \
    DATABASE_URL=postgresql+asyncpg://user:password@postgres:5432/omnisource \
    REDIS_URL=redis://redis:6379/0 \
    MEILISEARCH_URL=http://meilisearch:7700 \
    CELERY_BROKER_URL=redis://redis:6379/1 \
    CELERY_RESULT_BACKEND=redis://redis:6379/2

# Create data directory
RUN mkdir -p /app/data/feeds && chown -R www-data:www-data /app/data

# Expose ports
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health/live', timeout=5).raise_for_status()" || exit 1

# Run as non-root user
USER www-data:www-data

# Default command
CMD ["python", "-m", "uvicorn", "omnisource.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ============================================
# Development image
# ============================================
FROM base as development

# Install development dependencies
RUN apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy all requirements
COPY requirements.txt .
COPY pyproject.toml .

# Install all dependencies including dev
RUN pip install --user -e .[dev]

# Copy application code
COPY . .

# Set environment variables
ENV APP_ENV=development \
    LOG_LEVEL=DEBUG \
    DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/omnisource \
    REDIS_URL=redis://localhost:6379/0 \
    MEILISEARCH_URL=http://localhost:7700

# Expose ports
EXPOSE 8000

# Default command for development
CMD ["python", "-m", "uvicorn", "omnisource.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
