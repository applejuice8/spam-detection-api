# Backend image: FastAPI app served by uvicorn
FROM python:3.13-slim

# uv resolves and installs the exact versions in uv.lock
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first, so this layer is reused until pyproject.toml or uv.lock change.
# --no-dev skips pytest, and the train group (pandas) is not needed at runtime.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

# App code, migrations, and the trained model that app/ml_model.py loads from ml/models
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY ml/models ./ml/models

# Run as a non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# Apply database migrations, then start the server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
