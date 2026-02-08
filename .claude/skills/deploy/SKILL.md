---
name: deploy
description: Deploy, rebuild, and troubleshoot the gold monitor system. Covers Docker operations, service management, environment setup, and common error fixes.
disable-model-invocation: true
---

# Gold Monitor System — Deployment Guide

All commands assume you are in the `gold-monitor-system/` directory:

```bash
cd gold-monitor-system
```

---

## 1. Full Deployment Steps (Fresh Server)

### Prerequisites

- Docker Engine 20.10+
- Docker Compose v2 (ships with Docker Desktop; on Linux: `docker compose` plugin)
- At least 2 GB RAM, 5 GB disk free
- Ports 3000, 5432, 6379, 8000 available

### Step-by-step

```bash
# 1. Clone the repo
git clone <repo-url> talamala && cd talamala/gold-monitor-system

# 2. Create the environment file from the template
cp .env.example .env

# 3. Edit .env — at minimum, set a real SECRET_KEY and change ADMIN_PASSWORD
#    Set OPENROUTER_API_KEY if you want LLM-generated Persian summaries
nano .env

# 4. Build all images
docker compose build

# 5. Start all services (detached)
docker compose up -d

# 6. Verify everything is healthy
docker compose ps
curl -s http://localhost:8000/api/health | python3 -m json.tool
curl -s http://localhost:3000 -o /dev/null -w "%{http_code}\n"
```

### What happens on first start

1. `db` and `redis` containers start first (health checks gate downstream services)
2. `api` container starts → runs Alembic migrations (`upgrade head`) → seeds the default admin user → snapshots the YAML rules file
3. `worker` container starts → connects to Redis and DB → begins 60-second fetch cycles
4. `web` container starts → serves the Next.js frontend on port 3000 → proxies `/api/*` to `http://api:8000`

---

## 2. Service Architecture

### Container Map

| Service  | Image / Build Context         | Internal Port | Exposed Port | Purpose                                       |
|----------|-------------------------------|---------------|--------------|-----------------------------------------------|
| `db`     | `postgres:16-alpine`          | 5432          | 5432         | PostgreSQL primary data store (7 tables)      |
| `redis`  | `redis:7-alpine`              | 6379          | 6379         | Dedup cache, worker distributed lock          |
| `api`    | `./api/Dockerfile` (Python 3.12-slim) | 8000  | 8000         | FastAPI REST API + Alembic migrations on boot |
| `worker` | Same image as `api`           | —             | —            | Background fetch-match-alert pipeline (60s)   |
| `web`    | `./web/Dockerfile` (Node 22-alpine, multi-stage) | 3000 | 3000 | Next.js 14 frontend with API proxy            |

### Startup Dependency Chain

```
db (healthy) ──┐
               ├──▶ api (healthy) ──▶ web (started)
redis (healthy)┘        │
                        └──▶ worker (started)
```

- `api` and `worker` both wait for `db` and `redis` to be healthy (pg_isready / redis-cli ping)
- `worker` additionally waits for `api` to have started (ensures migrations ran)
- `web` waits for `api` to have started (needs the proxy target)

### Networking

- All services share the `goldmon-net` bridge network
- Services reference each other by container name: `db`, `redis`, `api`
- The Next.js frontend proxies `/api/*` requests to the FastAPI backend via `next.config.js` rewrites using `INTERNAL_API_URL` (default: `http://api:8000`)

### Volumes

| Volume      | Mount Point                      | Purpose                  |
|-------------|----------------------------------|--------------------------|
| `pgdata`    | `/var/lib/postgresql/data`       | Persistent PostgreSQL data |
| `redisdata` | `/data`                          | Persistent Redis RDB/AOF   |

### Dockerfiles Detail

**api/Dockerfile** (Python 3.12-slim, single-stage):
- Installs `build-essential`, `libpq-dev`, `curl` (system deps)
- Copies `api/requirements.txt` → `pip install`
- Copies `api/` source and `gold_monitor_rules_fa.yaml` into `/app/`
- Default CMD: `uvicorn api.main:app --host 0.0.0.0 --port 8000`
- Worker overrides CMD to: `python -m api.worker.main`

**web/Dockerfile** (Node 22-alpine, three-stage):
- **deps**: Installs npm/yarn/pnpm dependencies (uses `npm ci` with `package-lock.json`)
- **builder**: Copies source + `node_modules` → runs `npm run build`
- **runner**: Creates non-root `nextjs` user (uid 1001), copies build artifacts (`.next/`, `public/`, `next.config.js`), runs as `nextjs` user
- CMD: `npm start`

---

## 3. Rebuild & Update Flow

### Pull changes and rebuild everything

```bash
git pull origin main
docker compose build
docker compose up -d
```

### Rebuild a single service (e.g., after API code change)

```bash
docker compose build api
docker compose up -d api worker
```

Note: `worker` uses the same image as `api`, so rebuilding `api` updates both. You must restart `worker` explicitly.

### Rebuild frontend only

```bash
docker compose build web
docker compose up -d web
```

### Force rebuild without cache

```bash
docker compose build --no-cache api
docker compose build --no-cache web
docker compose up -d
```

### Rolling restart (no rebuild)

```bash
docker compose restart api worker web
```

### Apply database migrations only (without full restart)

Migrations run automatically on API startup. To trigger them manually:

```bash
docker compose exec api alembic -c api/alembic.ini upgrade head
```

### Zero-downtime approach

Docker Compose does not natively support zero-downtime deploys. The closest approach:

```bash
# Rebuild in background
docker compose build api web

# Restart services one at a time
docker compose up -d --no-deps api
docker compose up -d --no-deps worker
docker compose up -d --no-deps web
```

---

## 4. Environment Variables

All defined in `.env` (copied from `.env.example`). Docker Compose reads them automatically.

| Variable              | Required | Description                                                  | Default in .env.example                           |
|-----------------------|----------|--------------------------------------------------------------|---------------------------------------------------|
| `POSTGRES_USER`       | Yes      | PostgreSQL superuser name                                    | `goldmon`                                         |
| `POSTGRES_PASSWORD`   | Yes      | PostgreSQL password                                          | `goldmon_secret`                                  |
| `POSTGRES_DB`         | Yes      | Database name                                                | `goldmonitor`                                     |
| `DATABASE_URL`        | Yes      | Async SQLAlchemy connection string (asyncpg driver)          | `postgresql+asyncpg://goldmon:goldmon_secret@db:5432/goldmonitor` |
| `DATABASE_URL_SYNC`   | Yes      | Sync SQLAlchemy connection string (psycopg2, used by Alembic)| `postgresql://goldmon:goldmon_secret@db:5432/goldmonitor` |
| `REDIS_URL`           | Yes      | Redis connection URL                                         | `redis://redis:6379/0`                            |
| `SECRET_KEY`          | Yes      | JWT signing secret (HS256). **Change for production.**       | `change-me-to-a-random-string`                    |
| `ADMIN_EMAIL`         | Yes      | Default admin email (seeded on first boot)                   | `admin@goldmonitor.ir`                            |
| `ADMIN_PASSWORD`      | Yes      | Default admin password (seeded on first boot). **Change it.**| `admin123`                                        |
| `OPENROUTER_API_KEY`  | No       | OpenRouter API key for LLM Persian summaries. Leave empty to disable. | `sk-or-your-key-here`                   |
| `NEXT_PUBLIC_API_URL` | No       | Client-side API URL (unused in Docker; proxy handles routing)| `http://localhost:8000`                           |
| `INTERNAL_API_URL`    | No       | Server-side API URL for Next.js proxy rewrites               | `http://api:8000` (set in docker-compose.yml)     |

### Important notes on env vars

- `DATABASE_URL` must use `postgresql+asyncpg://` scheme (the API uses async SQLAlchemy)
- `DATABASE_URL_SYNC` must use `postgresql://` scheme (Alembic uses sync connections)
- Both DB URLs must point to the same database with matching credentials
- Hostnames `db` and `redis` refer to the Docker Compose service names on the `goldmon-net` network
- `INTERNAL_API_URL` is set directly in `docker-compose.yml` for the `web` service, not in `.env`

---

## 5. Common Docker Commands

### Build

```bash
# Build all services
docker compose build

# Build specific service
docker compose build api
docker compose build web

# Build without cache
docker compose build --no-cache

# Build with progress output
docker compose build --progress=plain api
```

### Start / Stop

```bash
# Start all services (detached)
docker compose up -d

# Start specific service and its dependencies
docker compose up -d api

# Stop all services (containers remain)
docker compose stop

# Stop and remove containers, networks
docker compose down

# Stop and remove containers, networks, AND volumes (destroys all data)
docker compose down -v
```

### Restart

```bash
# Restart all
docker compose restart

# Restart specific service
docker compose restart api
docker compose restart worker
docker compose restart web
```

### Status

```bash
# Show running containers and health status
docker compose ps

# Show resource usage
docker compose top
docker stats
```

### Execute commands inside containers

```bash
# Open a shell in the API container
docker compose exec api bash

# Open a Python REPL in the API container
docker compose exec api python

# Connect to PostgreSQL directly
docker compose exec db psql -U goldmon -d goldmonitor

# Connect to Redis CLI
docker compose exec redis redis-cli

# Run the seed script
docker compose exec api python -m api.seed

# Run tests inside the container
docker compose exec api python -m pytest api/tests/ -v

# Run Alembic migrations manually
docker compose exec api alembic -c api/alembic.ini upgrade head

# Check Alembic migration history
docker compose exec api alembic -c api/alembic.ini history
```

### Cleanup

```bash
# Remove stopped containers
docker compose rm -f

# Remove unused images for this project
docker compose down --rmi local

# Remove ALL unused Docker resources (global)
docker system prune -f

# Remove unused volumes (caution: destroys data)
docker volume prune -f

# Remove specific project volumes
docker volume rm gold-monitor-system_pgdata
docker volume rm gold-monitor-system_redisdata

# Remove dangling/build-cache layers
docker builder prune -f
```

---

## 6. Troubleshooting Guide

### Docker build cache corruption

**Symptoms**: Build fails with cryptic layer errors, stale dependencies, or missing files.

**Fix**:
```bash
# Clear build cache and rebuild
docker builder prune -f
docker compose build --no-cache
docker compose up -d
```

### Container restart loops

**Symptoms**: `docker compose ps` shows a service as `restarting` with an incrementing restart count.

**Diagnose**:
```bash
docker compose logs --tail=50 <service-name>
```

**Common causes and fixes**:

- **api restarting**: Usually a database connection failure. Check that `db` is healthy:
  ```bash
  docker compose ps db
  docker compose exec db pg_isready -U goldmon -d goldmonitor
  ```
  If db is not ready yet, api will retry (restart policy: `unless-stopped`). Wait for db health check to pass.

- **worker restarting**: The worker depends on `api` being started. If api is in a restart loop, fix api first. Also check Redis:
  ```bash
  docker compose exec redis redis-cli ping
  ```

- **web restarting**: Typically a build error. Check if `.next/` was generated properly:
  ```bash
  docker compose logs --tail=100 web
  ```
  Rebuild: `docker compose build --no-cache web && docker compose up -d web`

### Port conflicts

**Symptoms**: `Bind for 0.0.0.0:XXXX failed: port is already allocated`

**Fix**: Find what's using the port and stop it:
```bash
# Check what's on port 3000/5432/6379/8000
lsof -i :3000
lsof -i :5432
lsof -i :6379
lsof -i :8000

# Or use ss
ss -tlnp | grep -E '3000|5432|6379|8000'

# Kill the process, then restart
docker compose up -d
```

Alternatively, remap ports in `docker-compose.yml`:
```yaml
ports:
  - "3001:3000"   # Map host port 3001 to container port 3000
```

### Database connection failures

**Symptoms**: API logs show `connection refused` or `could not connect to server` for PostgreSQL.

**Check order**:
```bash
# 1. Is the db container running and healthy?
docker compose ps db

# 2. Can you connect manually?
docker compose exec db psql -U goldmon -d goldmonitor -c "SELECT 1"

# 3. Check DATABASE_URL matches the db credentials
docker compose exec api env | grep DATABASE_URL

# 4. Are credentials consistent between POSTGRES_USER/POSTGRES_PASSWORD and DATABASE_URL?
# Both must use the same username, password, and database name
```

**Common fix**: Credentials mismatch between `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` and `DATABASE_URL`/`DATABASE_URL_SYNC`. All must use the same values. After fixing `.env`:
```bash
docker compose down -v   # Reset the DB volume (credentials are baked in on first init)
docker compose up -d
```

**Important**: PostgreSQL only applies `POSTGRES_USER`/`POSTGRES_PASSWORD` on first initialization. If you change credentials after the volume was created, you must delete the volume (`docker compose down -v`) or manually alter the role inside the database.

### Redis connection failures

**Symptoms**: Worker logs show Redis connection errors; health check shows `"redis": false`.

```bash
# Check Redis is running
docker compose ps redis

# Test connectivity from api container
docker compose exec api python -c "import redis; r = redis.from_url('redis://redis:6379/0'); print(r.ping())"

# Restart Redis
docker compose restart redis
```

### Memory / disk issues

**Symptoms**: Containers killed by OOM, builds fail with no space.

```bash
# Check disk usage
df -h
docker system df

# Free space: remove unused images, containers, build cache
docker system prune -af
docker volume prune -f
docker builder prune -af

# Check container memory usage
docker stats --no-stream
```

For persistent memory issues, add memory limits in `docker-compose.yml`:
```yaml
services:
  api:
    deploy:
      resources:
        limits:
          memory: 512M
```

### Permission errors

**Symptoms**: `Permission denied` in the web container, or volume mount permission issues.

- The `web` container runs as user `nextjs` (uid 1001). If volume-mounted files are owned by root, the container cannot read them.
- The `api` container runs as root (default). No typical permission issues.
- PostgreSQL data volume is managed by the `postgres` user inside the container.

```bash
# Check file ownership inside a container
docker compose exec web ls -la /app/

# If volume permissions are wrong, recreate
docker compose down -v
docker compose up -d
```

### Alembic migration failures

**Symptoms**: API startup logs show `Alembic migration skipped` with an error.

```bash
# Check migration status
docker compose exec api alembic -c api/alembic.ini current
docker compose exec api alembic -c api/alembic.ini history

# Manually run migrations
docker compose exec api alembic -c api/alembic.ini upgrade head

# If migrations are corrupted, stamp current state and retry
docker compose exec api alembic -c api/alembic.ini stamp head
```

Note: The API has a fallback — if Alembic fails, it calls `Base.metadata.create_all()` to create tables directly from ORM models.

### Next.js API proxy not working

**Symptoms**: Frontend shows errors fetching data; API calls from the browser return 500 or hang.

```bash
# Check that INTERNAL_API_URL is set correctly in the web container
docker compose exec web env | grep INTERNAL_API_URL
# Should be: http://api:8000

# Check that the api container is reachable from web
docker compose exec web wget -qO- http://api:8000/api/health

# Check next.config.js is present in the container
docker compose exec web cat /app/next.config.js
```

### Worker not creating alerts

**Symptoms**: Worker logs show cycles but no alerts appear on the dashboard.

```bash
# Check worker logs for cycle output
docker compose logs --tail=100 worker

# Verify sources exist and are enabled
docker compose exec db psql -U goldmon -d goldmonitor -c "SELECT name, enabled, last_fetched_at, last_error FROM sources"

# Check if rules are loaded
curl -s http://localhost:8000/api/health | python3 -m json.tool
# Look for "rules_loaded" > 0

# Check if raw items are being stored
docker compose exec db psql -U goldmon -d goldmonitor -c "SELECT COUNT(*) FROM raw_items"

# Check if alerts exist
docker compose exec db psql -U goldmon -d goldmonitor -c "SELECT COUNT(*) FROM alerts"
```

---

## 7. Log Checking

### View logs (all services)

```bash
docker compose logs
```

### Follow logs in real-time

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f web
docker compose logs -f db
docker compose logs -f redis
```

### View recent logs (last N lines)

```bash
docker compose logs --tail=100 api
docker compose logs --tail=100 worker
docker compose logs --tail=50 web
docker compose logs --tail=50 db
```

### Filter logs by time

```bash
docker compose logs --since="2024-01-01T00:00:00" api
docker compose logs --since="1h" worker
docker compose logs --since="30m" web
```

### What to look for in each service

**api**:
- `Alembic migrations applied successfully` — migrations ran
- `Default admin user ... seeded` — admin was created
- `Rules snapshot v... persisted` — rules file loaded
- `Startup complete` — API is ready
- HTTP request logs (method, path, status code, duration)

**worker**:
- `Worker ready` — connected to Redis + loaded rules
- `=== Cycle start ===` / `=== Cycle end ===` — fetch cycle boundaries
- `Sources due for fetching: N` — how many sources polled
- `Fetched N items from source X` — per-source fetch results
- `Source X done — fetched=N, new=N, alerts=N` — cycle summary
- `Lock held by another instance` — another worker has the lock (normal in multi-replica)

**web**:
- `ready - started server on 0.0.0.0:3000` — Next.js is serving
- Rewrite/proxy errors if API is unreachable

**db**:
- `database system is ready to accept connections` — PostgreSQL is up
- Connection or authentication errors

**redis**:
- `Ready to accept connections` — Redis is up

---

## 8. Backup & Restore

### PostgreSQL backup

```bash
# Full database dump (SQL format)
docker compose exec db pg_dump -U goldmon goldmonitor > backup_$(date +%Y%m%d_%H%M%S).sql

# Compressed dump (custom format, recommended for large DBs)
docker compose exec db pg_dump -U goldmon -Fc goldmonitor > backup_$(date +%Y%m%d_%H%M%S).dump

# Dump specific tables
docker compose exec db pg_dump -U goldmon -t alerts goldmonitor > alerts_backup.sql
docker compose exec db pg_dump -U goldmon -t sources goldmonitor > sources_backup.sql
```

### PostgreSQL restore

```bash
# Restore from SQL dump
docker compose exec -T db psql -U goldmon goldmonitor < backup_20240101_120000.sql

# Restore from custom format dump
docker compose exec -T db pg_restore -U goldmon -d goldmonitor --clean backup_20240101_120000.dump
```

### Redis backup

Redis uses RDB snapshots persisted to the `redisdata` volume.

```bash
# Trigger a manual save
docker compose exec redis redis-cli BGSAVE

# Copy the dump file out of the container
docker compose cp redis:/data/dump.rdb ./redis_backup_$(date +%Y%m%d).rdb

# Restore: copy dump.rdb back and restart Redis
docker compose cp ./redis_backup.rdb redis:/data/dump.rdb
docker compose restart redis
```

### Volume-level backup

```bash
# Backup the PostgreSQL data volume
docker run --rm -v gold-monitor-system_pgdata:/data -v $(pwd):/backup alpine \
  tar czf /backup/pgdata_backup.tar.gz -C /data .

# Restore
docker run --rm -v gold-monitor-system_pgdata:/data -v $(pwd):/backup alpine \
  sh -c "cd /data && tar xzf /backup/pgdata_backup.tar.gz"
```

### Full system backup (database + rules)

```bash
# Backup database + rules file together
mkdir -p backups/$(date +%Y%m%d)
docker compose exec db pg_dump -U goldmon -Fc goldmonitor > backups/$(date +%Y%m%d)/database.dump
cp gold_monitor_rules_fa.yaml backups/$(date +%Y%m%d)/rules.yaml
cp .env backups/$(date +%Y%m%d)/env.backup
```

---

## 9. Health Checks

### Built-in Docker health checks

The `docker-compose.yml` defines health checks for `db`, `redis`, and `api`:

| Service | Health check command                                              | Interval | Timeout | Retries | Start period |
|---------|-------------------------------------------------------------------|----------|---------|---------|--------------|
| `db`    | `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}`               | 5s       | 5s      | 10      | —            |
| `redis` | `redis-cli ping`                                                  | 5s       | 5s      | 10      | —            |
| `api`   | `python -c "import httpx; httpx.get('http://localhost:8000/api/health')"` | 10s | 10s     | 5       | 15s          |

```bash
# View health status of all containers
docker compose ps
# Look for "(healthy)" in the STATUS column
```

### Application-level health endpoint

```bash
# Full health check (DB + Redis + rules + last worker run)
curl -s http://localhost:8000/api/health | python3 -m json.tool
```

Expected healthy response:
```json
{
    "status": "ok",
    "db": true,
    "redis": true,
    "last_worker_run": "2024-01-01T12:00:00+00:00",
    "rules_loaded": 32
}
```

Degraded response (e.g., Redis down):
```json
{
    "status": "degraded",
    "db": true,
    "redis": false,
    "last_worker_run": "2024-01-01T12:00:00+00:00",
    "rules_loaded": 32
}
```

### Manual verification checklist

```bash
# 1. All containers running
docker compose ps

# 2. API responds
curl -s http://localhost:8000/api/health

# 3. Frontend loads
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
# Should return 200

# 4. API proxy works through frontend
curl -s http://localhost:3000/api/health | python3 -m json.tool

# 5. Database is accessible
docker compose exec db psql -U goldmon -d goldmonitor -c "SELECT COUNT(*) FROM sources"

# 6. Redis is responsive
docker compose exec redis redis-cli ping
# Should return PONG

# 7. Worker has run at least one cycle (check fetch_logs)
docker compose exec db psql -U goldmon -d goldmonitor -c "SELECT COUNT(*) FROM fetch_logs"

# 8. Admin login works
curl -s -X POST http://localhost:8000/api/admin/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@goldmonitor.ir","password":"admin123"}'
# Should return a JSON object with "access_token"

# 9. Swagger API docs accessible
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs
# Should return 200
```

### Monitoring the worker cycle

```bash
# Watch worker cycles in real-time
docker compose logs -f worker | grep -E "Cycle|Sources due|done"

# Check last successful fetch per source
docker compose exec db psql -U goldmon -d goldmonitor -c \
  "SELECT name, last_fetched_at, last_success_at, last_error FROM sources ORDER BY name"
```
