# Spam Detection API

A FastAPI service that labels short text messages as spam or ham. The model is a Naive Bayes classifier trained on the UCI SMS Spam Collection. Users sign up, create API keys, and call `/predict` with a key.

- Auth: password login with JWT access tokens and rotating refresh tokens, plus revocable API keys
- Redis caches predictions and counts requests for rate limiting. The API works without it.
- Prometheus metrics and a Grafana dashboard
- A small demo frontend in `frontend/`

## Run it locally

```bash
cp .env.example .env            # then set JWT_SECRET: openssl rand -hex 32
uv sync --group train
uv run python -m ml.train       # trains the model into ml/models (downloads the dataset from Kaggle)
uv run alembic upgrade head     # create the database tables
uv run uvicorn app.main:app --reload
```

Docs are at http://localhost:8000/docs. Redis is optional locally. Without it, predictions are not cached and rate limits are not applied.

## Use the API

```bash
# 1. Create an account and log in
curl -X POST localhost:8000/auth/signup -H 'content-type: application/json' \
  -d '{"username":"alice","password":"password123","confirm_password":"password123"}'
curl -X POST localhost:8000/auth/login -d 'username=alice&password=password123'      # -> access_token, refresh_token

# 2. Create an API key (shown once)
curl -X POST localhost:8000/auth/api-keys -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'content-type: application/json' -d '{"expires_in_days": 90}'

# 3. Classify a message
curl -X POST localhost:8000/predict -H "X-API-Key: $API_KEY" -H 'content-type: application/json' \
  -d '{"text": "WINNER!! Claim your free prize now"}'
# {"label":"spam","spam_probability":0.99,"from_cache":false}
```

Other auth routes: `/auth/refresh` (a refresh token works once), `/auth/logout`, `/auth/logout-all` (ends every session), `/auth/me`, and `GET`/`DELETE /auth/api-keys`.

Usernames use letters, digits, `.`, `_` and `-`, 3 to 20 characters, and are unique ignoring case.

### Limits

Requests over a limit get `429` with a `Retry-After` header. Limits are fixed windows counted in Redis (see `app/core/rate_limit.py`):

| Route | Limit |
| --- | --- |
| `/auth/login` | 10 per minute per IP |
| `/auth/signup` | 5 per hour per IP |
| `/auth/refresh` | 30 per minute per IP |
| `/predict` | 300 per minute per IP, 60 per minute per API key owner |

If Redis is down the limits are skipped.

Behind a reverse proxy every request appears to come from the proxy's address, so the per-IP limits would be shared by all clients. Tell uvicorn which proxy to trust so it reads `X-Forwarded-For`: set `FORWARDED_ALLOW_IPS` to the proxy's address.

## Configuration

Set in `.env` (see `.env.example`) or the environment.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URI` | required | SQLAlchemy async URL, for example `postgresql+psycopg://user:pass@host/db` |
| `JWT_SECRET` | required | At least 32 characters |
| `ACCESS_TOKEN_EXPIRES_MINUTES` | required | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | required | Refresh token lifetime |
| `SPAM_THRESHOLD` | `0.5` | Probability at or above which a message is labelled spam |
| `REDIS_URL` | `redis://localhost:6379/0` | Cache and rate limit counters |
| `ALLOWED_ORIGINS` | two localhost origins | JSON list of browser origins allowed by CORS |
| `METRICS_HOST` / `METRICS_PORT` | `127.0.0.1` / `9100` | Where Prometheus metrics are served |
| `SQL_ECHO` | `false` | Log every SQL statement with parameters. Local debugging only. |
| `GRAFANA_ADMIN_PASSWORD` | required for Docker | Used by docker compose only |

## Docker

```bash
# .env needs GRAFANA_ADMIN_PASSWORD as well
docker compose up --build
```

| Service | URL |
| --- | --- |
| API | http://localhost:8000 |
| Frontend | http://localhost:8080 |
| Prometheus | http://localhost:9090 (localhost only) |
| Grafana | http://localhost:3000 (localhost only) |

For a step-by-step Render Free deployment, see [DEPLOY.md](DEPLOY.md).

The image build trains the model, so it needs internet access to download the dataset and fails if the F1 quality gate fails. A `migrate` service applies database migrations once before the API starts.

Metrics are served on port 9100 inside the compose network and are not published. They are not available on the API port.

## The model

`ml/train.py` trains a bag-of-words `BernoulliNB` and refuses to save a model with a test F1 below 0.90. The dataset is pinned to a version, and `ml/models/metadata.json` records the scores. On the held-out set: F1 0.949, precision 0.984, recall 0.916. It misses spam more often than it blocks real messages. Change `SPAM_THRESHOLD` to trade one for the other.

Limits to know about:

- It was trained on about 5,000 English SMS messages. Other languages, long emails and newer spam styles will do worse.
- `spam_probability` from Naive Bayes is not well calibrated. Treat it as a score, not a percentage.
- The response has no overall model score. The test-set F1 is not a confidence for one message. It is exported as the `spam_model_f1` metric.

`ml/notebooks/01_experiments.ipynb` holds the hyperparameter search. It shares its data and split with `train.py`. Run it with `uv sync --group train --group notebook`.

## Database migrations

```bash
uv run alembic upgrade head        # apply all pending migrations
uv run alembic downgrade -1        # undo the last one
uv run alembic current             # which revision is the database at?
uv run alembic revision --autogenerate -m "msg"   # new migration from model changes
```

The username migration fails if two existing users differ only by case. Rename one and run it again.

## Develop

```bash
uv sync --group train
uv run pytest tests             # uses a small fake model, no trained files needed
uv run ruff check .
```

Tests that check the real model are skipped until `ml/models` exists. CI trains it and runs them.
