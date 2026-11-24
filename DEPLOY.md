# Deploy on Render Free

This guide deploys the API as a Render Free Web Service and the demo page as a separate Render Static Site. PostgreSQL is hosted on Neon Free because Render's free PostgreSQL expires after 30 days. Redis is optional; Upstash Free is included here for caching and rate limits.

Free plan limits change. The limits below were checked on 2026-11-24 against the providers' documentation. Render Free web services use 512 MB RAM and 0.1 CPU, sleep after 15 minutes without traffic, and can take about a minute to wake. Render Static Sites are free. Render Free PostgreSQL expires after 30 days, so don't use it for the app's persistent data. See [Render's Free plan](https://render.com/docs/free) and [compute plans](https://render.com/docs/compute-plans).

## 1. Create the database

1. Create a project on [Neon](https://neon.com/).
2. Copy its PostgreSQL connection string. Neon Free currently includes 100 compute hours and 1 GB of database storage per project; its compute scales to zero after five idle minutes. See [Neon's plan limits](https://neon.com/docs/introduction/plans).
3. The app uses SQLAlchemy's psycopg driver. Set `DATABASE_URI` to the connection string with the scheme `postgresql+psycopg://`. Keep any query parameters such as `sslmode=require`.

## 2. Create Redis (optional)

If you want prediction caching and rate limits, create a database on [Upstash Redis](https://upstash.com/). Copy the TLS connection URL (`rediss://...`) for `REDIS_URL`. Upstash Free currently includes 250 MB of data, 500,000 commands, and 10 GB of monthly bandwidth. See [Upstash Redis pricing](https://upstash.com/pricing/redis).

The API still works without Redis. If you omit it, caching is unavailable and rate limits are skipped when Redis is down.

## 3. Apply the database migrations

Run the migrations from your local checkout before using the API. In the project root, use the Neon URL for this one command:

```bash
DATABASE_URI='postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require' uv run alembic upgrade head
```

The command reads the other required settings (`JWT_SECRET`, `ACCESS_TOKEN_EXPIRES_MINUTES`, and `REFRESH_TOKEN_EXPIRE_DAYS`) from your local `.env`. Make sure those are set. Use your real Neon values in place of the example URL, and don't commit `.env`.

## 4. Deploy the frontend as a Static Site

Create a Render Static Site from this repository and the branch you plan to deploy (usually `main` after merging):

1. Set **Root Directory** to `frontend`.
2. Leave **Build Command** blank.
3. Set **Publish Directory** to `.`.
4. Deploy, then copy the site's HTTPS origin, such as `https://spam-demo.onrender.com`.

The frontend is plain HTML, CSS, and JavaScript. It doesn't need the frontend Dockerfile or a build step. See [Render's Static Site setup](https://render.com/docs/static-sites).

## 5. Deploy the API as a Web Service

Create a separate Render Web Service from the same repository and branch:

1. Choose **Docker** as the runtime and **Free** as the instance type.
2. Leave **Root Directory** blank so the build context is the repository root. Use `Dockerfile` as the Dockerfile path.
3. Set the service's HTTP port to `8000` by adding `PORT=8000` to its environment. This matches the port hard-coded in the Dockerfile's Uvicorn command. Set the health check path to `/health`.
4. Add the environment variables below in Render. Replace the example frontend origin with the URL from step 4.

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URI` | Neon URL using `postgresql+psycopg://...` |
   | `JWT_SECRET` | Generate with `openssl rand -hex 32` |
   | `ACCESS_TOKEN_EXPIRES_MINUTES` | `30` |
   | `REFRESH_TOKEN_EXPIRE_DAYS` | `14` |
   | `ALLOWED_ORIGINS` | JSON array, e.g. `["https://spam-demo.onrender.com"]` |
   | `REDIS_URL` | Upstash TLS URL beginning with `rediss://` (optional) |
   | `SPAM_THRESHOLD` | `0.5` (optional) |
   | `SQL_ECHO` | `false` (optional) |

   `METRICS_HOST` and `METRICS_PORT` can stay at their defaults. Metrics use a separate port and are not exposed as part of this deployment. `GRAFANA_ADMIN_PASSWORD` is only needed for the full Docker Compose setup.

5. Deploy the service. The Docker image trains the model during its build and downloads the pinned public dataset from Kaggle. The first build may take several minutes. Render Free's 512 MB runtime memory and 0.1 CPU are limited; if the image build or app is killed for resource use, this configuration may not fit the Free plan without reducing the build/runtime requirements.
6. Copy the API's HTTPS URL, such as `https://spam-api.onrender.com`.

Render recommends that web services bind to the `PORT` environment variable on `0.0.0.0`. This app's current Docker command uses port `8000`, so keep the Render port at `8000` unless you change the Docker command too. See [Render's port binding documentation](https://render.com/docs/web-services#port-binding).

## 6. Connect and check the services

1. Open the Static Site URL.
2. Enter the API URL from step 5 in the page's **API URL** field. The field defaults to `127.0.0.1` for local development.
3. Confirm the health message changes to `Connected (status: ok)`.
4. Sign up, log in, create an API key, and try a prediction.

If the browser reports a CORS error, check that `ALLOWED_ORIGINS` is a JSON array containing the Static Site's exact HTTPS origin, with no path or trailing slash. Save the API environment change and redeploy.

## What to expect on Free

- Render Free Web Services sleep after 15 minutes idle and take about a minute to wake. Static Sites stay available.
- Render provides 750 Free instance hours per workspace per month. A spun-down service does not consume instance hours.
- The API container's local filesystem is temporary. This project stores account data in Neon and does not need local persistent files at runtime.
- Prometheus and Grafana are not deployed in this two-service setup. The API's `/metrics` listener is on a separate internal port.
- Free tiers have resource and usage limits and may restart or suspend services. Recheck provider limits when deploying.
