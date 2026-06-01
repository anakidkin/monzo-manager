FROM python:3.14-slim AS builder

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

RUN pip install poetry

COPY pyproject.toml poetry.lock ./

RUN poetry install --no-root

FROM python:3.14-slim AS final

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY src/monzo_manager/ /app/monzo_manager/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn monzo_manager.main:app", "--host", "0.0.0.0", "--port", "8000"]