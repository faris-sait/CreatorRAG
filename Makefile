.PHONY: infra infra-down api worker web test install \
        prod-up prod-down prod-logs prod-ps prod-restart prod-deploy prod-db prod-db-reset

COMPOSE_PROD = docker compose -f docker-compose.prod.yml

# Bring up Redis + Qdrant + Postgres
infra:
	docker compose up -d

infra-down:
	docker compose down

# Backend deps
install:
	cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

# Run the API server
api:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

# Run the ingest worker pool
worker:
	cd backend && . .venv/bin/activate && arq app.pipeline.worker.WorkerSettings

# Run the frontend
web:
	cd frontend && npm run dev

# Backend tests
test:
	cd backend && . .venv/bin/activate && pytest -q

# Inspect the database (no psql needed)
db-show:
	cd backend && . .venv/bin/activate && python -m scripts.show_db

# Open an interactive psql shell inside the postgres container
db:
	docker compose exec postgres psql -U creatorrag -d creatorrag

# Wipe all ingested data (fresh slate for a demo)
db-reset:
	docker compose exec postgres psql -U creatorrag -d creatorrag -c "TRUNCATE pairs, videos CASCADE;"
	@echo "Postgres cleared. Restart the API/worker to recreate the empty Qdrant collection, or run db-show."

# ── Production (droplet) ──────────────────────────────────────────────
# Full containerised stack (DBs + API + worker + Caddy/HTTPS).

# Build + start everything in the background
prod-up:
	$(COMPOSE_PROD) up -d --build

# Stop and remove the stack (volumes are kept)
prod-down:
	$(COMPOSE_PROD) down

# Tail the app + proxy logs
prod-logs:
	$(COMPOSE_PROD) logs -f api worker caddy

# Status of every service
prod-ps:
	$(COMPOSE_PROD) ps

# Restart just the app (e.g. after an env change, no rebuild)
prod-restart:
	$(COMPOSE_PROD) restart api worker

# Pull latest code and roll it out
prod-deploy:
	git pull
	$(COMPOSE_PROD) up -d --build
	$(COMPOSE_PROD) ps

# Interactive psql inside the prod postgres container
prod-db:
	$(COMPOSE_PROD) exec postgres psql -U creatorrag -d creatorrag

# Wipe ingested data on the droplet (fresh demo slate)
prod-db-reset:
	$(COMPOSE_PROD) exec postgres psql -U creatorrag -d creatorrag -c "TRUNCATE pairs, videos CASCADE;"
	@echo "Postgres cleared. Restart api/worker to recreate the empty Qdrant collection."
