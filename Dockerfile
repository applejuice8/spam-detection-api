# Backend image: FastAPI app served by uvicorn.
# Two stages: the first trains the model, the second is the runtime image and only receives the trained files.

# ---- Stage 1: train the model ----
FROM python:3.13-slim AS model

# uv resolves and installs the exact versions in uv.lock
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Runtime dependencies plus the train group (pandas, kagglehub). Cached until pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --group train --no-install-project

# Downloads the pinned dataset from Kaggle (public, no credentials) and fails the build if the F1 quality gate fails.
# This layer is reused until ml/train.py changes.
COPY ml/__init__.py ml/train.py ./ml/
RUN python -m ml.train


# ---- Stage 2: runtime ----
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first, so this layer is reused until pyproject.toml or uv.lock change.
# --no-dev leaves out pytest and ruff, and the train group (pandas) is not needed at runtime.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

# App code, migrations, and the trained model that app/ml_model.py loads from ml/models
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY --from=model /app/ml/models ./ml/models

# Run as a non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# Migrations are not run here: with several containers they would race. Docker Compose runs them once
# in the "migrate" service (alembic upgrade head) before the API starts.
# Exec form, so uvicorn is PID 1 and receives SIGTERM for a graceful shutdown.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
