# Spam Detection API

Run server with

```bash
uv run uvicorn app.main:app --reload
```

---

## Alembic Migrations

```bash
# Setup
uv run alembic init -t async migrations


uv run alembic upgrade head        # apply all pending migrations
uv run alembic upgrade +1          # apply the next one only
uv run alembic downgrade -1        # undo the last one
uv run alembic downgrade base      # undo everything
uv run alembic current             # which revision is the DB at?
uv run alembic history             # list all migrations
uv run alembic heads               # show latest revision(s)
uv run alembic revision -m "msg"   # empty migration for hand-written changes
uv run alembic stamp head          # mark DB as up to date without running anything
```
