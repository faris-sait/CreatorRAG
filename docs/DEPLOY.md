# Deploying CreatoFlow

Backend runs as a containerised stack on a **VPS** (Docker Compose + Caddy for
automatic HTTPS). Frontend runs on **Vercel**. HTTPS on the backend is mandatory
— a Vercel (HTTPS) page cannot call an `http://` origin (mixed-content block), so
we give the box a real cert. The live deployment points the subdomain
**`creatoflow.vaulter.in`** (a GoDaddy-managed A record) at the server's public
IP; any domain you control works the same way.

```
Browser ──HTTPS──▶ Vercel (Next.js)
   │
   └──HTTPS──▶ creatoflow.vaulter.in ─▶ Caddy :443 ─▶ api:8000 ─▶ redis / qdrant / postgres
                                                       worker (arq) ┘
```

Deploy order matters: **DNS must resolve and ports 80/443 must be open before
`compose up`**, or Caddy's Let's Encrypt challenge fails.

---

## 0. Push the code (local machine)

The droplet deploys by cloning this repo, so push first. Suggested commits:

```bash
git add frontend/ docs/architecture.html
git commit -m "feat(web): A-vs-B engagement scoreboard, header/footer links, mobile polish, hide provider source"

git add Caddyfile docker-compose.prod.yml .env.example docs/DEPLOY.md
git commit -m "feat(deploy): config-driven Caddy hostname (SITE_ADDRESS), fix prod healthcheck path, deploy runbook"

git push origin master
```

---

## 1. DNS (subdomain → server IP)

Point a subdomain you control at the server's public IPv4 with a plain **A
record**. The live deployment uses `creatoflow.vaulter.in` on GoDaddy:

1. In your DNS provider (GoDaddy here), open the domain's DNS records.
2. Add an **A** record: host/name `creatoflow`, value = the server's **public
   IPv4**, TTL the default (e.g. 600s). No proxy/CDN in front — Caddy needs to
   answer the Let's Encrypt challenge directly on this IP.
3. Save. A real registrar's nameservers resolve in seconds to a few minutes.

Verify it resolves to the server before going further (from your laptop):

```bash
dig +short creatoflow.vaulter.in    # should print the server's public IP
```

> A managed registrar (GoDaddy/Cloudflare/etc.) is worth it over a free dynamic
> DNS service: this project originally ran on DuckDNS and its authoritative
> nameservers were slow/flaky on a cache-miss (multi-second stalls before the
> app even got the request). Moving to a normal domain dropped resolution to
> ~milliseconds.

---

## 2. Prepare the droplet

SSH in, then:

```bash
# Docker present? (DO marketplace/most devboxes already have it)
docker --version && docker compose version
# If missing:  curl -fsSL https://get.docker.com | sudo sh

# Ports 80 and 443 MUST be free — this is a devbox, so check nothing else holds them:
sudo ss -tlnp | grep -E ':(80|443)\s' || echo "80/443 free ✓"
# If nginx/apache/another Caddy is listening, stop it first (e.g. sudo systemctl stop nginx).

# Firewall: allow SSH *first* so you don't lock yourself out, then web ports.
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status
```

---

## 3. Get the code + configure

```bash
# Fresh droplet: clone it. Already developing on this box? Skip the clone, just cd into the repo.
git clone https://github.com/faris-sait/CreatorRAG.git ~/creatoflow
cd ~/creatoflow
cp .env.example .env.prod
nano .env.prod        # fill in the values below
```

> Prod uses its **own** env file (`.env.prod`) and Compose project name
> (`-p creatoflow`, baked into the `make prod-*` targets), so it never clobbers a
> local dev `.env` or the dev DB containers that may already be running on the
> same machine.

Set these in `.env.prod` (note: **hosts are docker service names, not localhost**):

```ini
# --- secrets (your own keys) ---
GOOGLE_API_KEY=...          # one or more; GOOGLE_API_KEY_2/_3 for rotation
GROQ_API_KEY=...            # Whisper transcription
APIFY_TOKEN=...             # Instagram + YouTube scraping
YOUTUBE_API_KEY=            # optional

# --- models (defaults are correct) ---
LLM_MODEL=gemini-2.5-flash-lite
EMBED_MODEL=models/gemini-embedding-001
EMBED_DIM=768
WHISPER_MODEL=whisper-large-v3-turbo

# --- ingest behaviour ---
USE_FIXTURES=false
YOUTUBE_USE_APIFY=true       # IMPORTANT on a droplet: datacenter IPs get
                             # YouTube-blocked, so route YouTube through Apify.

# --- infra: use the docker SERVICE NAMES here ---
POSTGRES_PASSWORD=<choose-a-strong-password>
DATABASE_URL=postgresql://creatorrag:<same-strong-password>@postgres:5432/creatorrag
REDIS_URL=redis://redis:6379/0
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=video_chunks

# --- public hostname for Caddy's cert ---
SITE_ADDRESS=creatoflow.vaulter.in

# --- CORS: set after the Vercel URL exists (step 6). A placeholder is fine now ---
BACKEND_CORS_ORIGINS=https://creatoflow.vercel.app
```

> `POSTGRES_PASSWORD` and the password inside `DATABASE_URL` **must match** —
> the first initialises the DB, the second is how the app connects.

---

## 4. Bring the stack up

Make sure `dig +short $SITE_ADDRESS` already returns this droplet's IP, then:

```bash
make prod-up          # = docker compose -f docker-compose.prod.yml up -d --build
make prod-logs        # watch caddy obtain the Let's Encrypt cert (Ctrl-C to stop tailing)
make prod-ps          # all services should be "running"/"healthy"
```

Caddy logs a line like `certificate obtained successfully` within ~30s once DNS
+ ports are correct.

---

## 5. Verify the backend

```bash
curl -s https://creatoflow.vaulter.in/api/health | python3 -m json.tool
```

Expect `"status": "ok"` with `postgres: ok` and a `qdrant_chunks` count. A valid
HTTPS cert (no `-k` needed) means Caddy succeeded.

---

## 6. Deploy the frontend (Vercel)

From your laptop in `frontend/` (or via the Vercel dashboard → Import Git repo,
**Root Directory = `frontend`**):

```bash
cd frontend
npx vercel            # link/create the project (first run)
```

Set the production env var (dashboard → Settings → Environment Variables, or CLI):

```bash
npx vercel env add NEXT_PUBLIC_API_URL production
# value: https://creatoflow.vaulter.in   (base URL, NO trailing /api)
```

Then deploy production:

```bash
npx vercel --prod
```

Copy the resulting URL (e.g. `https://creatoflow.vercel.app`).

---

## 7. Wire CORS and finish

Back on the droplet, set the real Vercel URL and restart the app (no rebuild):

```bash
cd ~/creatoflow
nano .env.prod        # BACKEND_CORS_ORIGINS=https://<your-vercel-url>
make prod-restart
```

Open the Vercel URL, paste a YouTube + Instagram Reel pair, and chat. Done.

---

## Redeploying later

```bash
cd ~/creatoflow && make prod-deploy     # git pull + rebuild + restart + ps
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Caddy never gets a cert | DNS not propagated (`dig +short $SITE_ADDRESS`) or ufw didn't open 80/443. Both must be true *before* `compose up`. |
| `api` stuck "starting"/unhealthy | Check `make prod-logs`; usually a bad `DATABASE_URL` (wrong host or mismatched password). |
| Frontend shows CORS / mixed-content errors | `NEXT_PUBLIC_API_URL` must be **https**, and `BACKEND_CORS_ORIGINS` must list the exact Vercel origin; then `make prod-restart`. |
| YouTube ingest fails on the droplet | Datacenter IP blocked — ensure `YOUTUBE_USE_APIFY=true`. |
| Port 80/443 already in use | Another web server on the devbox; stop it (`sudo systemctl stop nginx`) and re-run. |
