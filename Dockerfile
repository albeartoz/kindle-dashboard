FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN if [ -f uv.lock ]; then uv sync --frozen --no-dev; else uv sync --no-dev; fi

COPY app ./app
COPY config.example.yaml ./config.yaml

EXPOSE 8787

CMD ["uv", "run", "gunicorn", "--bind", "0.0.0.0:8787", "--workers", "1", "--threads", "4", "app.main:app"]

