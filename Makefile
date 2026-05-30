.PHONY: infra infra-down api worker web test install

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
