# syntax=docker/dockerfile:1
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    CASES_DB=/data/cases.db

WORKDIR /app

# deps first so a source edit doesn't reinstall them (the project itself declares no
# build-system, so `uv sync` only ever installs dependencies)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# seed only on an empty volume; a restart must not touch an existing DB
RUN printf '%s\n' \
    '#!/bin/sh' \
    'set -e' \
    'if [ ! -f "$CASES_DB" ]; then' \
    '  mkdir -p "$(dirname "$CASES_DB")"' \
    '  python -m scripts.seed' \
    'fi' \
    'exec "$@"' > /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
