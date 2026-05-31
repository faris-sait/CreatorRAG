# Deploying CreatorRAG

Backend runs as a containerised stack on a **DigitalOcean droplet** (Docker
Compose + Caddy for automatic HTTPS). Frontend runs on **Vercel**. HTTPS on the
backend is mandatory — a Vercel (HTTPS) page cannot call an `http://` origin
(mixed-content block), so we give the droplet a real cert via a free
**DuckDNS** hostname.

```
Browser ──HTTPS──▶ Vercel (Next.js)
   │
   └──HTTPS──▶ <you>.duckdns.org ─▶ Caddy :443 ─▶ api:8000 ─▶ redis / qdrant / postgres
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

## 1. DuckDNS (free subdomain → droplet IP)

1. Go to <https://www.duckdns.org> and sign in (GitHub/Google/etc).
2. In **"sub domain"** type an available name, e.g. `creatorrag`, click **add domain**.
   Your hostname is now `creatorrag.duckdns.org`.
3. In the **current ip** box for that row, enter your droplet's **public IPv4**
   and click **update ip**. (Find the IP in the DO dashboard.)
4. Copy the **token** shown at the top of the page — keep it private.

Verify it resolves (from your laptop):

```bash
dig +short creatorrag.duckdns.org    # should print the droplet IP
```

> Optional but recommended on the droplet — auto-refresh the IP every 5 min so
> it survives a reboot/IP change:
> ```bash
> mkdir -p ~/duckdns && cat > ~/duckdns/duck.sh <<'EOF'
> echo url="https://www.duckdns.org/update?domains=creatorrag&token=YOUR_TOKEN&ip=" | curl -k -o ~/duckdns/duck.log -K -
> EOF
> chmod +x ~/duckdns/duck.sh
> ( crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1" ) | crontab -
> ```

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

## 3. Clone + configure

```bash
git clone https://github.com/faris-sait/CreatorRAG.git ~/creatorrag
cd ~/creatorrag
cp .env.example .env
nano .env        # fill in the values below
```

Set these in `.env` (note: **hosts are docker service names, not localhost**):

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
SITE_ADDRESS=creatorrag.duckdns.org

# --- CORS: set after the Vercel URL exists (step 6). A placeholder is fine now ---
BACKEND_CORS_ORIGINS=https://creatorrag.vercel.app
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
curl -s https://creatorrag.duckdns.org/api/health | python3 -m json.tool
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
# value: https://creatorrag.duckdns.org   (base URL, NO trailing /api)
```

Then deploy production:

```bash
npx vercel --prod
```

Copy the resulting URL (e.g. `https://creatorrag.vercel.app`).

---

## 7. Wire CORS and finish

Back on the droplet, set the real Vercel URL and restart the app (no rebuild):

```bash
cd ~/creatorrag
nano .env        # BACKEND_CORS_ORIGINS=https://<your-vercel-url>
make prod-restart
```

Open the Vercel URL, paste a YouTube + Instagram Reel pair, and chat. Done.

---

## Redeploying later

```bash
cd ~/creatorrag && make prod-deploy     # git pull + rebuild + restart + ps
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Caddy never gets a cert | DNS not propagated (`dig +short $SITE_ADDRESS`) or ufw didn't open 80/443. Both must be true *before* `compose up`. |
| `api` stuck "starting"/unhealthy | Check `make prod-logs`; usually a bad `DATABASE_URL` (wrong host or mismatched password). |
| Frontend shows CORS / mixed-content errors | `NEXT_PUBLIC_API_URL` must be **https**, and `BACKEND_CORS_ORIGINS` must list the exact Vercel origin; then `make prod-restart`. |
| YouTube ingest fails on the droplet | Datacenter IP blocked — ensure `YOUTUBE_USE_APIFY=true`. |
| Port 80/443 already in use | Another web server on the devbox; stop it (`sudo systemctl stop nginx`) and re-run. |
