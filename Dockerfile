FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends fonts-dejavu-core; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN if [ -f uv.lock ]; then uv sync --frozen --no-dev; else uv sync --no-dev; fi

COPY app ./app
COPY config.example.yaml ./config.yaml

EXPOSE 8787

CMD ["uv", "run", "gunicorn", "--bind", "0.0.0.0:8787", "--workers", "1", "--threads", "4", "app.main:app"]
