FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# System dependencies for the Python packages used by the backend.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev \
        gcc \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv and resolve the locked dependency set into /app/.venv.
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application code. .dockerignore keeps .venv, secrets, docs and the
# frontend build out of the image.
COPY . .

EXPOSE 5000

CMD ["gunicorn", "--workers", "1", "--bind", "0.0.0.0:5000", "backend.app:app"]
