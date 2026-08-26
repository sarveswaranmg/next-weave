# Deploying NeuroWeave to Production (Single Server, Docker Compose)

This is the simplest supported production path: one server, Docker Compose, Caddy for automatic
HTTPS, and an optional GitHub Actions workflow for hands-off redeploys on every push to `main`.
For a Kubernetes cluster instead, see `k8s/README.md` - that path exists too, but needs a real
cluster + container registry, which this guide doesn't assume you have.

Files this guide uses:
- `docker-compose.prod.yml` - the production service definitions (Postgres, Redis, API, Celery
  worker/beat, Caddy). Standalone, not merged with the dev `docker-compose.yml`.
- `deploy/Caddyfile` - reverse proxy + automatic TLS config.
- `.env.prod.example` - template for the real secrets file (`.env.prod`), which lives only on the
  server and is gitignored.
- `scripts/deploy.sh` - pulls the target git ref, builds, runs migrations, restarts, health-checks.
- `.github/workflows/deploy.yml` - optional CI/CD trigger that SSHes in and runs `deploy.sh`.

## 1. Provision a server

Any VM works - DigitalOcean, Hetzner, AWS EC2, etc. Minimum: 2 vCPU / 4 GB RAM, Ubuntu 22.04 LTS,
a public IPv4 address. NeuroWeave's own workload is modest at low traffic; scale up if `docker
stats` shows memory pressure once real usage starts.

```bash
ssh root@your-server-ip   # or your provider's default user
adduser deploy && usermod -aG sudo deploy   # don't run everything as root
```

## 2. Point DNS at the server

Create an A record for the domain you'll use (e.g. `neuroweave.yourdomain.com`) pointing at the
server's public IP, before starting Caddy - Caddy's automatic Let's Encrypt provisioning needs
this to already resolve, or the ACME HTTP-01 challenge fails.

## 3. Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $(whoami)
# log out and back in for the group change to take effect
docker compose version   # confirm the Compose plugin is present
```

## 4. Firewall

Only SSH, HTTP, and HTTPS need to be reachable from the internet - Postgres/Redis are not exposed
by `docker-compose.prod.yml` at all (internal Docker network only).

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## 5. Clone the repo and configure secrets

```bash
git clone <this-repo-url> /opt/neuroweave
cd /opt/neuroweave
cp .env.prod.example .env.prod
```

Edit `.env.prod` and fill in:
- `DOMAIN` - the domain you pointed at this server in step 2.
- `POSTGRES_PASSWORD` - generate with `openssl rand -hex 32`.
- `OPENAI_API_KEY` (and `ANTHROPIC_API_KEY` if you use it).
- `CREDENTIAL_ENCRYPTION_KEY` - generate with:
  ```bash
  docker run --rm python:3.11-slim python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- `RUNTIME_API_KEY` - optional. If set, the *first* migration run hashes it into an API key for an
  auto-created tenant, so you have one working key immediately after deploy without a separate
  bootstrap step. Leave blank if you'd rather run `scripts/bootstrap_tenant.py` yourself (step 7).

`.env.prod` is gitignored - it never leaves this server.

## 6. First deploy

```bash
cd /opt/neuroweave
./scripts/deploy.sh main
```

This builds the images, runs `alembic upgrade head` (creating all tables plus, if `RUNTIME_API_KEY`
was set, your first tenant), starts every service, and polls `/runtime/health` until it responds
or 20 attempts (~1 minute) pass. On success it prints `docker compose ps` - confirm `neuroweave-api`,
`neuroweave-celery-worker`, `neuroweave-celery-beat`, `neuroweave-postgres`, `neuroweave-redis`, and
`neuroweave-caddy` are all `Up`.

Caddy needs a few extra seconds on first start to obtain its certificate. Check:

```bash
docker compose -f docker-compose.prod.yml logs caddy --tail=30
curl -I https://$DOMAIN/runtime/health   # replace $DOMAIN or just paste the real domain
```

A `200`/healthy JSON body means you're live.

## 7. Bootstrap a tenant (if you didn't set RUNTIME_API_KEY)

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec neuroweave \
  python scripts/bootstrap_tenant.py --name "My Company" --email me@example.com
```

This prints a `tenant_id` and a plaintext API key - **copy the key now, it is never shown again**
(only its hash is stored). Use it as the `X-API-Key` header on every `/runtime/*` request. Mint
additional keys later (e.g. one per environment/integration) via `POST /runtime/keys` once you
have at least one working key - see the main README's "Multi-Tenancy & Auth" section.

This is the manual, admin-run path for tenants you create yourself. If you want other people to
sign up for their own tenant without you running anything, see **Letting others self-serve
sign up** below instead.

### Letting others self-serve sign up

`https://$DOMAIN/signup` is a public web page (no API key needed) where anyone can create their
own tenant: they submit an email, click the verification link they're sent, and land on a page
showing their API key once. Each self-serve tenant is capped at
`FREE_TIER_MONTHLY_CHAT_LIMIT` (default 200) `/runtime/chat` calls per calendar month - there's
no billing integration yet, so this is a hard ceiling, not a paid plan. To actually use this in
production you need real SMTP credentials set in `.env.prod` (`SMTP_HOST`/`SMTP_PORT`/
`SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_FROM_EMAIL`) - without them, verification links are only
logged inside the container, which real signups can't see. `SIGNUP_MAX_PER_IP_PER_DAY` (default
5) rate-limits repeat signups from one address; this only works correctly because
`docker-compose.prod.yml`'s uvicorn command runs with `--proxy-headers`, trusting Caddy's
`X-Forwarded-For` for the real caller IP.

## 8. Verify end-to-end

```bash
curl -X POST https://$DOMAIN/runtime/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: nw_live_..." \
  -d '{"user_id": "00000000-0000-0000-0000-000000000001", "message": "hello", "provider": "echo"}'
```

Expect a `200` with an echoed response. Swap `provider` to `"openai"` once you're ready to use a
real model.

## 9. Automate future deploys (optional)

To have every push to `main` deploy automatically (only after CI passes - see
`.github/workflows/deploy.yml`):

1. Generate a dedicated SSH keypair for CI (don't reuse your personal key):
   ```bash
   ssh-keygen -t ed25519 -f deploy_key -N ""
   ```
2. On the server, add the **public** key to the deploy user's `~/.ssh/authorized_keys`.
3. In the GitHub repo settings, add these Actions secrets:
   - `DEPLOY_HOST` - the server's IP or hostname.
   - `DEPLOY_USER` - the SSH user (e.g. `deploy`).
   - `DEPLOY_SSH_KEY` - the **private** key contents (`deploy_key`, not `deploy_key.pub`).
   - `DEPLOY_REPO_DIR` - the path on the server, e.g. `/opt/neuroweave`.
4. Push to `main`. The `CI` workflow runs first; `Deploy` runs automatically once it succeeds, and
   just SSHes in and runs the same `scripts/deploy.sh` you ran manually in step 6 - no secrets are
   ever transmitted through CI, since `.env.prod` already lives on the server.

You can also trigger a deploy manually from the Actions tab (`workflow_dispatch`) to redeploy a
specific ref without waiting for a new push.

## Day-2 operations

**Logs:**
```bash
docker compose -f docker-compose.prod.yml logs -f neuroweave          # API
docker compose -f docker-compose.prod.yml logs -f celery-worker       # background tasks
docker compose -f docker-compose.prod.yml logs -f celery-beat         # scheduler
```

**Restart a single service** (e.g. after an env var change):
```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d neuroweave
```

**Database backups** (run on a cron; adjust retention to your needs):
```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U neuroweave neuroweave | gzip > backup-$(date +%F).sql.gz
```

**Rolling back a bad deploy:**
```bash
git log --oneline -5   # find the previous good SHA
./scripts/deploy.sh <previous-sha>
```
This re-runs migrations against the previous code. If the deploy you're rolling back *added* a new
migration, rolling the code back does **not** automatically reverse the schema change - check
`migrations/versions/` for what the new revision did before deciding whether a schema rollback
(`alembic downgrade`) is also needed and safe (it usually isn't once real data exists - prefer
forward-fixing over downgrading a live database).

**Certificate renewal:** automatic - Caddy renews Let's Encrypt certs on its own well before
expiry. Nothing to schedule.

**Scaling:** this compose file runs exactly one of each service. If you need more API throughput,
add `deploy: replicas: N` under `neuroweave` (Compose, not Swarm, so this only works with `docker
compose up --scale neuroweave=N` today) - or move to the Kubernetes path (`k8s/README.md`), which
already has HPAs wired up for this. Never scale `celery-beat` beyond 1 replica (see the comment in
`docker-compose.prod.yml` - a second scheduler double-fires every scheduled task).
