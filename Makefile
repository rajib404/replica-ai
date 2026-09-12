.PHONY: dev build db-migrate db-seed docker-up docker-down lint type-check install clean

# ─── Development ──────────────────────────────────────────

dev: ## Start all services in dev mode
	@echo "Starting infrastructure..."
	docker compose up -d
	@echo "Waiting for services to be healthy..."
	@sleep 3
	@echo "Starting apps..."
	npx turbo dev

build: ## Build all packages and apps
	npx turbo build

install: ## Install all dependencies
	npm install
	# apps/api pins Python 3.11: pydub (voice chat) depends on the stdlib
	# `audioop` module, which Python 3.13 removed outright.
	cd apps/api && python3.11 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
	cd apps/ai && python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"

# ─── Database ─────────────────────────────────────────────

db-migrate: ## Run Prisma migrations
	cd packages/db && npx prisma migrate dev

db-seed: ## Seed the database
	cd packages/db && npx tsx prisma/seed.ts

db-generate: ## Generate Prisma client
	cd packages/db && npx prisma generate

db-studio: ## Open Prisma Studio
	cd packages/db && npx prisma studio

# ─── Docker ───────────────────────────────────────────────

docker-up: ## Start Docker services (PostgreSQL, Redis, Qdrant, Ollama)
	docker compose up -d

docker-down: ## Stop Docker services
	docker compose down

docker-clean: ## Stop Docker services and remove volumes
	docker compose down -v

# ─── Quality ──────────────────────────────────────────────

lint: ## Run linters across all packages
	npx turbo lint
	cd apps/api && ruff check .
	cd apps/ai && ruff check .

type-check: ## Run type checking across all packages
	npx turbo type-check
	cd apps/api && mypy app
	cd apps/ai && mypy app

format: ## Format all code
	npx prettier --write "**/*.{ts,tsx,js,jsx,json,md}"
	cd apps/api && ruff format .
	cd apps/ai && ruff format .

# ─── Utilities ────────────────────────────────────────────

clean: ## Clean build artifacts
	rm -rf node_modules/.cache
	npx turbo clean

env: ## Copy .env.example to .env
	cp -n .env.example .env || true
	cp -n apps/web/.env.example apps/web/.env.local || true
	cp -n apps/api/.env.example apps/api/.env || true
	cp -n apps/ai/.env.example apps/ai/.env || true

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
